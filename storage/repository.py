import hashlib
import json
import zlib
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, text, union
from sqlalchemy.orm import Session
from storage.models import (
    OpportunityRecord,
    OpportunityColdArchiveRecord,
    OpportunityArchiveOrphanRecord,
    FieldProvenanceRecord,
    OutboundActionRecordModel,
    IdempotencyReservationRecord,
    InboundEvidenceRecord,
    PipelineEventRecord,
    NotificationRecord,
    InboxCheckpointRecord,
    ReconciliationRecordModel,
    WorkerJobRecord,
    FounderFeedbackRecord,
    FounderFacetRecord,
    FounderSavedViewRecord,
    OpportunityFamilyRecord,
    FounderActivityEventRecord,
    FounderOpportunityViewRecord,
    FounderTriageStateRecord,
    MatchEvaluationRecord,
    FounderCVSelectionRecord,
)
from storage.cold_storage import (
    delete as delete_cold_object,
    get as get_cold_object,
    pack as pack_cold_object,
    put as put_cold_object,
    unpack as unpack_cold_object,
)


# Storage V2: `search_tsv` is one compact searchable representation, shared verbatim between
# the per-row population below (`_refresh_search_tsv`, called at the end of
# every `save_opportunity`) and the idempotent batch backfill
# (`backfill_search_tsv`). Both are the *same* UPDATE body -- one scoped to a
# single `id`, the other to every row (or every row still missing a value) --
# so a row written by either path can never end up indexed against a
# different document shape than a row written by the other. Full descriptions
# and provenance stay in the private cold archive; hot search is limited to
# title, organization, normalized location, track and title-family keywords.
# `concat_ws`/`string_agg` both silently skip NULL inputs, so a row missing
# any of these fields still gets a valid (possibly shorter) document rather
# than a NULL search_tsv.
_SEARCH_TSV_UPDATE_SQL = """
UPDATE opportunities o
SET search_tsv = to_tsvector(
    'english',
    concat_ws(
        ' ',
        o.title,
        o.organization,
        o.location_country,
        o.location_city,
        o.location_region,
        o.track,
        o.title_family,
        o.family_key
    )
)
"""


logger = logging.getLogger(__name__)


def _is_postgres(session: Session) -> bool:
    bind = session.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def backfill_search_tsv(session: Session, *, only_missing: bool = True) -> int:
    """Idempotent batch (re)population of `search_tsv` for existing rows.

    A no-op (returns 0) against a non-PostgreSQL bind (e.g. SQLite in
    matching-suite tests that build `Base.metadata` directly): `search_tsv`
    is a plain TEXT column there with no `to_tsvector` function to call --
    see the column comment in `storage/models.py`. This is a deliberate
    fail-*open* skip (council review #3, finding 9) -- it does not violate
    the FR-002 fail-closed invariant, because `storage/engine.py` still
    refuses SQLite outright without the explicit test opt-in, and this
    function running against a SQLite session only ever happens inside that
    already-opted-in test path. It is logged at WARNING rather than raised
    so a genuinely misconfigured production bind is not silently invisible.

    `only_missing=True` (the default) only (re)writes rows where
    `search_tsv IS NULL`, which is both the common backfill case (rows
    written before this column existed) and safely re-runnable: running it
    twice in a row touches zero rows the second time. Pass
    `only_missing=False` to force a full reindex of every row (e.g. after
    changing the document definition above).
    """
    if not _is_postgres(session):
        logger.warning(
            "backfill_search_tsv: skipped -- non-PostgreSQL bind (%s); "
            "search_tsv was not (re)populated for any row",
            getattr(session.get_bind(), "dialect", None) and session.get_bind().dialect.name,
        )
        return 0
    sql = _SEARCH_TSV_UPDATE_SQL
    if only_missing:
        sql += " WHERE o.search_tsv IS NULL"
    result = session.execute(text(sql))
    session.commit()
    return result.rowcount or 0


def _refresh_search_tsv(session: Session, opportunity_id: str) -> None:
    """Populate/refresh `search_tsv` for exactly one row, right after it
    (and its `field_provenances` children) have been committed. Called from
    `StorageRepository.save_opportunity` on every insert and every update --
    application-side, not a trigger or a generated column, because
    migration `0004_founder_control` (frozen for this work order) already
    added `search_tsv` as a plain nullable `TSVECTOR` column rather than a
    `GENERATED ALWAYS AS (...) STORED` column, and adding a database trigger
    outside of a migration would not be reproducible across environments.
    Application-side population at this single call site is also where
    every current write path already funnels through: `save_opportunity` is
    the only method that writes an `OpportunityRecord`, so a row written by
    any path (initial ingestion, re-ingestion/update) ends up indexed here;
    the batch path above (`backfill_search_tsv`) exists only to catch rows
    written before this code existed.
    """
    if not _is_postgres(session):
        logger.warning(
            "_refresh_search_tsv: skipped for opportunity %s -- "
            "non-PostgreSQL bind (%s); search_tsv was not refreshed",
            opportunity_id,
            getattr(session.get_bind(), "dialect", None) and session.get_bind().dialect.name,
        )
        return
    session.execute(text(_SEARCH_TSV_UPDATE_SQL + " WHERE o.id = :id"), {"id": opportunity_id})
    session.commit()


class StorageRepository:
    """Production Repository interface for OpportunityOS PostgreSQL relational persistence."""

    def __init__(self, session: Session, *, cold_storage_client=None):
        self.session = session
        self.cold_storage_client = cold_storage_client

    def prepare_cold_archive(
        self,
        opp_data: Dict[str, Any],
        provenances: List[Dict[str, Any]],
        *,
        normalized_opportunity=None,
    ) -> Dict[str, Any]:
        """Upload a lossless compressed source version before opening a write transaction."""
        raw_source = opp_data.get("raw_source_record_json")
        if not raw_source:
            raise ValueError("cold-tier source record is missing; refusing lossy archive")
        archived_fields = {
            key: value
            for key, value in opp_data.items()
            if key not in {"lifecycle_tier", "cold_archive"}
        }
        payload = {
            "schema_version": 2,
            "opportunity_id": opp_data["id"],
            "source_id": opp_data["source_id"],
            "content_hash": opp_data["content_hash"],
            "source_url": opp_data["source_url"],
            "original_source_payload": raw_source,
            "canonical_description": opp_data.get("description") or "",
            "provenance": list(provenances),
            "opportunity": archived_fields,
            "normalized_opportunity": (
                asdict(normalized_opportunity)
                if normalized_opportunity is not None and is_dataclass(normalized_opportunity)
                else None
            ),
        }
        compressed, digest, original_size = pack_cold_object(payload)
        object_key, digest, compressed_size = put_cold_object(
            compressed,
            opp_data["content_hash"],
            opportunity_id=opp_data["id"],
            client=self.cold_storage_client,
        )
        return {
            "storage_backend": "supabase_storage",
            "object_key": object_key,
            "payload_sha256": digest,
            "compressed_size_bytes": compressed_size,
            "original_size_bytes": original_size,
            "archive_version": "v2",
            "archived_at": datetime.now(timezone.utc),
        }

    def _queue_archive_orphan(self, archive: OpportunityColdArchiveRecord | None) -> None:
        if archive is None or archive.storage_backend != "supabase_storage" or not archive.object_key:
            return
        self.queue_archive_orphan({
            "object_key": archive.object_key,
            "payload_sha256": archive.payload_sha256,
            "compressed_size_bytes": archive.compressed_size_bytes or 0,
        })

    def queue_archive_orphan(self, archive_metadata: Dict[str, Any]) -> None:
        object_key = archive_metadata.get("object_key")
        if not object_key:
            return
        existing = self.session.get(OpportunityArchiveOrphanRecord, object_key)
        if existing is None:
            self.session.add(
                OpportunityArchiveOrphanRecord(
                    object_key=object_key,
                    payload_sha256=archive_metadata.get("payload_sha256") or "",
                    compressed_size_bytes=archive_metadata.get("compressed_size_bytes") or 0,
                    created_at=datetime.now(timezone.utc),
                )
            )

    def cleanup_archive_orphans(self, *, limit: int = 20) -> int:
        """Retry bounded stale-object deletes; failed deletes remain observable/retryable."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = (
            self.session.query(OpportunityArchiveOrphanRecord)
            .order_by(OpportunityArchiveOrphanRecord.created_at.asc())
            .limit(limit)
            .all()
        )
        removed = 0
        for orphan in rows:
            referenced = (
                self.session.query(OpportunityColdArchiveRecord.opportunity_id)
                .filter_by(object_key=orphan.object_key)
                .first()
            )
            if referenced:
                self.session.delete(orphan)
                self.session.commit()
                continue
            try:
                delete_cold_object(orphan.object_key, client=self.cold_storage_client)
            except Exception as exc:
                self.session.rollback()
                logger.warning("cold_archive_orphan_delete_failed", extra={"object_key": orphan.object_key, "reason": type(exc).__name__})
                continue
            self.session.delete(orphan)
            self.session.commit()
            removed += 1
        return removed

    def is_founder_protected(self, opportunity_id: str) -> bool:
        """Return true for any persisted Founder, application, or outbound history."""
        return bool(self.get_founder_protected_ids([opportunity_id]))

    def get_founder_protected_ids(self, opportunity_ids: List[str], *, chunk_size: int = 500) -> set[str]:
        """Find protected IDs with narrow UNION queries instead of loading opportunity bodies."""
        protected: set[str] = set()
        models = (
            FounderFeedbackRecord,
            FounderTriageStateRecord,
            FounderOpportunityViewRecord,
            FounderActivityEventRecord,
            OutboundActionRecordModel,
            IdempotencyReservationRecord,
            PipelineEventRecord,
            ReconciliationRecordModel,
            NotificationRecord,
            FounderCVSelectionRecord,
        )
        ids = list(dict.fromkeys(opportunity_ids))
        for start in range(0, len(ids), chunk_size):
            chunk = ids[start:start + chunk_size]
            if not chunk:
                continue
            statements = [
                select(model.opportunity_id).where(model.opportunity_id.in_(chunk))
                for model in models
            ]
            protected.update(row[0] for row in self.session.execute(union(*statements)).all())
        return protected

    # Opportunity Operations
    def save_opportunity(self, opp_data: Dict[str, Any], provenances: List[Dict[str, Any]]) -> OpportunityRecord:
        tier = opp_data.get("lifecycle_tier", "hot")
        if tier not in {"hot", "cold", "protected"}:
            raise ValueError(f"invalid lifecycle tier: {tier}")
        archive_metadata = opp_data.get("cold_archive")
        if tier == "cold" and (
            not archive_metadata
            or archive_metadata.get("storage_backend") != "supabase_storage"
            or not archive_metadata.get("object_key")
            or not archive_metadata.get("payload_sha256")
        ):
            raise ValueError("cold opportunity must have a verified private archive pointer")
        previous_archive = self.session.get(OpportunityColdArchiveRecord, opp_data["id"])
        if previous_archive is not None and (
            tier != "cold" or previous_archive.object_key != archive_metadata.get("object_key")
        ):
            self._queue_archive_orphan(previous_archive)
        record = OpportunityRecord(
            id=opp_data["id"],
            track=opp_data["track"],
            title=opp_data["title"],
            organization=opp_data["organization"],
            description=None if tier == "cold" else opp_data["description"],
            source_id=opp_data["source_id"],
            source_url=opp_data["source_url"],
            content_hash=opp_data["content_hash"],
            country=opp_data.get("country"),
            region=opp_data.get("region"),
            geographic_scope=opp_data.get("geographic_scope"),
            posted_date=opp_data.get("posted_date"),
            deadline=opp_data.get("deadline"),
            is_stale=opp_data.get("is_stale", False),
            reverified_at=opp_data.get("reverified_at"),
            raw_payload_json=None if tier == "cold" else opp_data.get("raw_payload_json"),
            work_mode=opp_data.get("work_mode", "unspecified"),
            work_mode_source=opp_data.get("work_mode_source"),
            location_country=opp_data.get("location_country"),
            location_city=opp_data.get("location_city"),
            location_region=opp_data.get("location_region"),
            remote_scope=opp_data.get("remote_scope", "unspecified"),
            remote_scope_regions=opp_data.get("remote_scope_regions"),
            employment_type=opp_data.get("employment_type", "unspecified"),
            seniority_level=opp_data.get("seniority_level", "unspecified"),
            compensation_min=opp_data.get("compensation_min"),
            compensation_max=opp_data.get("compensation_max"),
            compensation_currency=opp_data.get("compensation_currency"),
            compensation_period=opp_data.get("compensation_period"),
            title_family=opp_data.get("title_family"),
            title_level=opp_data.get("title_level"),
            family_key=opp_data.get("family_key"),
            search_tsv=opp_data.get("search_tsv"),
            lifecycle_tier=tier,
            archive_object_key=archive_metadata.get("object_key") if tier == "cold" else None,
            archive_sha256=archive_metadata.get("payload_sha256") if tier == "cold" else None,
            archive_state="verified" if tier == "cold" else None,
        )
        for prov in (() if tier == "cold" else provenances):
            prov_rec = FieldProvenanceRecord(
                field_name=prov["field_name"],
                raw_value=prov.get("raw_value"),
                normalized_value=prov.get("normalized_value"),
                derivation_type=prov["derivation_type"],
                raw_pointer=prov.get("raw_pointer"),
                record_checksum=prov["record_checksum"],
                rule_id=prov.get("rule_id"),
            )
            record.provenances.append(prov_rec)

        # Delete any provenance rows already stored for this opportunity
        # before merging in the fresh set built above. `Session.merge()`
        # cannot match the incoming `FieldProvenanceRecord` children to
        # already-persisted rows -- they carry no natural key of their own
        # until they are inserted, only a DB-assigned autoincrement `id` that
        # a freshly-built child never has -- so left to itself it would
        # insert every incoming child as new *before* the unit of work gets
        # around to orphaning the old ones, which now that
        # (opportunity_id, field_name, record_checksum) is a real unique
        # constraint (see migration 0003_provenance_identity) raises
        # IntegrityError instead of upserting. Running this DELETE first, as
        # its own statement in the same transaction, guarantees the old rows
        # are gone before the merge below ever emits its INSERTs, so a
        # re-persist (identical or changed content, same opportunity id) is
        # genuinely idempotent: the row count for this opportunity ends up
        # exactly matching `provenances` again, with no exception raised.
        self.session.query(FieldProvenanceRecord).filter_by(
            opportunity_id=opp_data["id"]
        ).delete(synchronize_session=False)

        self.session.merge(record)
        if tier == "cold":
            archive = OpportunityColdArchiveRecord(
                opportunity_id=opp_data["id"],
                content_hash=opp_data["content_hash"],
                payload_zlib=None,
                storage_backend="supabase_storage",
                object_key=archive_metadata["object_key"],
                compressed_size_bytes=archive_metadata["compressed_size_bytes"],
                payload_sha256=archive_metadata["payload_sha256"],
                original_size_bytes=archive_metadata["original_size_bytes"],
                archive_version=archive_metadata["archive_version"],
                archived_at=archive_metadata["archived_at"],
            )
            self.session.merge(archive)
        elif previous_archive is not None:
            self.session.delete(previous_archive)
        self.session.commit()

        # BRIEF-FR-006 C2: keep search_tsv current for every write path that
        # goes through this method -- see `_refresh_search_tsv` for why this
        # is application-side rather than a trigger/generated column.
        _refresh_search_tsv(self.session, opp_data["id"])

        # The only read model is published after a current-pack evaluation.
        self.cleanup_archive_orphans()
        return record

    def hydrate_cold_opportunity(self, opportunity_id: str) -> OpportunityRecord:
        """Reject legacy persistent rehydration; callers must reconstruct in memory."""
        raise RuntimeError(
            "persistent cold rehydration is prohibited; use load_cold_opportunity_payload and rebuild in memory"
        )

    def load_cold_opportunity_payload(
        self, opportunity_id: str, *, record: Optional[OpportunityRecord] = None
    ) -> Dict[str, Any]:
        """Return verified archived source truth without changing hot state.

        Matching must be able to score a cold row without expanding its
        ``[archived]`` marker back into ``opportunities``.  This method is the
        non-mutating counterpart to legacy hydration: it verifies
        bytes, identity and the current content hash, then returns the
        decompressed payload in memory.  Callers must not persist its fields.
        """
        record = record or self.get_opportunity(opportunity_id)
        if record is None:
            raise ValueError(f"opportunity not found: {opportunity_id}")
        row = self.session.execute(
            text(
                "SELECT content_hash, payload_zlib, payload_sha256, storage_backend, object_key, compressed_size_bytes "
                "FROM opportunity_cold_archive WHERE opportunity_id = :id"
            ),
            {"id": opportunity_id},
        ).mappings().first()
        if row is None:
            raise RuntimeError("cold archive missing for archived opportunity")
        if row["content_hash"] != record.content_hash:
            raise RuntimeError("cold archive content hash is stale")
        if row["storage_backend"] == "supabase_storage":
            if not row["object_key"]:
                raise RuntimeError("cold archive object metadata is missing")
            compressed = get_cold_object(
                row["object_key"], row["payload_sha256"], client=self.cold_storage_client
            )
            if row["compressed_size_bytes"] is not None and len(compressed) != row["compressed_size_bytes"]:
                raise RuntimeError("cold archive compressed size verification failed")
        else:
            if row["payload_zlib"] is None:
                raise RuntimeError("cold archive payload is unavailable")
            compressed = bytes(row["payload_zlib"])
            if hashlib.sha256(compressed).hexdigest() != row["payload_sha256"]:
                raise RuntimeError("cold archive checksum verification failed")
        return unpack_cold_object(
            compressed,
            row["payload_sha256"],
            opportunity_id=opportunity_id,
            content_hash=record.content_hash,
        )

    def get_opportunity(self, opportunity_id: str) -> Optional[OpportunityRecord]:
        return self.session.query(OpportunityRecord).filter_by(id=opportunity_id).first()

    def get_opportunity_identity_state(self, opportunity_ids: List[str], *, chunk_size: int = 500) -> Dict[str, str]:
        """Return only persisted identity/content-hash state for a bounded id set.

        Ingestion uses this deliberately narrow projection to classify a batch
        without loading descriptions, payloads, or ORM relationships.  Chunking
        keeps PostgreSQL bind counts bounded for large source feeds.
        """
        result: Dict[str, str] = {}
        ids = list(dict.fromkeys(opportunity_ids))
        for start in range(0, len(ids), chunk_size):
            rows = (
                self.session.query(OpportunityRecord.id, OpportunityRecord.content_hash)
                .filter(OpportunityRecord.id.in_(ids[start:start + chunk_size]))
                .all()
            )
            result.update({row[0]: row[1] for row in rows})
        return result

    def lock_opportunity_identity(self, opportunity_id: str) -> None:
        """Serialize one identity's write decision through its commit boundary.

        ``save_opportunity`` commits internally, so a source-wide transaction
        advisory lock cannot span that method.  This lock is intentionally
        acquired immediately before a fresh read and write for one candidate;
        the repository commit releases it at exactly the boundary it protects.
        """
        if _is_postgres(self.session):
            self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:opportunity_id)::bigint)"),
                {"opportunity_id": opportunity_id},
            )

    def get_evaluation_projection_ids(
        self, opportunity_ids: List[str], truth_pack_hash: str, *, chunk_size: int = 500
    ) -> tuple[set[str], set[str]]:
        """Bulk-read current-pack evaluation/projection identities only."""
        from storage.models import MatchEvaluationRecord
        from storage.feed_projection import FeedProjectionRecord

        evaluated: set[str] = set()
        projected: set[str] = set()
        ids = list(dict.fromkeys(opportunity_ids))
        for start in range(0, len(ids), chunk_size):
            chunk = ids[start:start + chunk_size]
            evaluated.update(
                row[0]
                for row in self.session.query(MatchEvaluationRecord.opportunity_id)
                .filter(
                    MatchEvaluationRecord.opportunity_id.in_(chunk),
                    MatchEvaluationRecord.truth_pack_hash == truth_pack_hash,
                )
                .all()
            )
            projected.update(
                row[0]
                for row in self.session.query(FeedProjectionRecord.opportunity_id)
                .filter(
                    FeedProjectionRecord.opportunity_id.in_(chunk),
                    FeedProjectionRecord.truth_pack_hash == truth_pack_hash,
                )
                .all()
            )
        return evaluated, projected

    # Founder Feedback Operations with Deduplication & ID alignment
    def record_feedback(
        self,
        opp_id: str,
        label: str,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
        feedback_id: Optional[str] = None,
    ) -> FounderFeedbackRecord:
        norm_notes = (notes or "").strip()
        norm_reason = (reason or "").strip()
        dedup_payload = f"{opp_id}:{label}:{norm_reason}:{norm_notes}".encode("utf-8")
        dedup_hash = hashlib.sha256(dedup_payload).hexdigest()

        # Check for existing identical feedback replay
        existing = self.session.query(FounderFeedbackRecord).filter_by(dedup_hash=dedup_hash).first()
        if existing:
            return existing

        now = datetime.now(timezone.utc)
        rec_id = feedback_id or f"fb-{hashlib.sha256(f'{dedup_hash}:{now.isoformat()}'.encode()).hexdigest()[:12]}"
        
        record = FounderFeedbackRecord(
            id=rec_id,
            opportunity_id=opp_id,
            feedback_label=label,
            structured_reason=reason,
            notes=notes,
            dedup_hash=dedup_hash,
            created_at=now,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def list_feedback_for_opportunity(self, opp_id: str) -> List[FounderFeedbackRecord]:
        return self.session.query(FounderFeedbackRecord).filter_by(opportunity_id=opp_id).all()

    # C1 (BRIEF-FR-006) -- Facet Operations
    # `api/routes_api.py` queries `founder_facets`/`founder_saved_views`
    # directly (matching every other route in that module's own convention
    # for `founder_filter_settings`); these thin wrappers exist so
    # `storage/test_postgres_integration.py` can exercise persistence and
    # round-tripping without going through the HTTP layer at all.
    def get_facet(self, facet_id: str) -> Optional[FounderFacetRecord]:
        return self.session.query(FounderFacetRecord).filter_by(facet_id=facet_id).first()

    def list_facets(self) -> List[FounderFacetRecord]:
        return self.session.query(FounderFacetRecord).all()

    def upsert_facet(self, facet_id: str, mode: str, values_json: Optional[str], updated_at: datetime) -> FounderFacetRecord:
        row = self.get_facet(facet_id)
        if row is None:
            row = FounderFacetRecord(facet_id=facet_id, mode=mode, values_json=values_json, updated_at=updated_at)
            self.session.add(row)
        else:
            row.mode = mode
            row.values_json = values_json
            row.updated_at = updated_at
        self.session.commit()
        return row

    # C1 (BRIEF-FR-006) -- Saved View Operations
    def list_saved_views(self) -> List[FounderSavedViewRecord]:
        return self.session.query(FounderSavedViewRecord).order_by(FounderSavedViewRecord.name.asc()).all()

    def get_saved_view(self, view_id: str) -> Optional[FounderSavedViewRecord]:
        return self.session.query(FounderSavedViewRecord).filter_by(id=view_id).first()

    def get_default_saved_view(self) -> Optional[FounderSavedViewRecord]:
        return self.session.query(FounderSavedViewRecord).filter_by(is_default=True).first()

    def delete_saved_view(self, view_id: str) -> bool:
        row = self.get_saved_view(view_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True
    # Opportunity Family Operations (A2 clustering, BRIEF-FR-006)
    def upsert_family(
        self,
        *,
        family_key: str,
        employer: str,
        normalized_title: str,
        member_count: int,
        best_member_id: str,
    ) -> OpportunityFamilyRecord:
        """Insert or update one ``opportunity_families`` row from a freshly
        computed :class:`opportunity.clustering.Family`.

        ``split_out`` (the reversible "show separately" toggle) is
        deliberately preserved across an upsert rather than reset to its
        column default: re-running clustering after new postings arrive for
        an existing family must not silently undo a founder's earlier
        "show separately" choice for that family.
        """
        existing = (
            self.session.query(OpportunityFamilyRecord)
            .filter_by(family_key=family_key)
            .first()
        )
        now = datetime.now(timezone.utc)
        if existing is None:
            record = OpportunityFamilyRecord(
                family_key=family_key,
                employer=employer,
                normalized_title=normalized_title,
                member_count=member_count,
                best_member_id=best_member_id,
                split_out=False,
                updated_at=now,
            )
            self.session.add(record)
        else:
            existing.employer = employer
            existing.normalized_title = normalized_title
            existing.member_count = member_count
            existing.best_member_id = best_member_id
            existing.updated_at = now
            record = existing
        self.session.commit()
        return record

    def get_family(self, family_key: str) -> Optional[OpportunityFamilyRecord]:
        return (
            self.session.query(OpportunityFamilyRecord)
            .filter_by(family_key=family_key)
            .first()
        )

    def list_families(self) -> List[OpportunityFamilyRecord]:
        return (
            self.session.query(OpportunityFamilyRecord)
            .order_by(OpportunityFamilyRecord.family_key.asc())
            .all()
        )

    def set_family_split_out(
        self, family_key: str, split_out: bool
    ) -> Optional[OpportunityFamilyRecord]:
        """Reversible per-family "show separately" toggle, persisted.

        Setting ``split_out=True`` makes the family's members appear as
        individual cards; setting it back to ``False`` re-collapses them.
        Returns ``None`` (no write) if the family row does not exist yet --
        a family must be upserted (from a clustering run) before its
        ``split_out`` flag can be toggled.
        """
        record = self.get_family(family_key)
        if record is None:
            return None
        record.split_out = split_out
        record.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        return record
