import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from storage.models import (
    OpportunityRecord,
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
)


# BRIEF-FR-006 C2: `search_tsv` document definition, shared verbatim between
# the per-row population below (`_refresh_search_tsv`, called at the end of
# every `save_opportunity`) and the idempotent batch backfill
# (`backfill_search_tsv`). Both are the *same* UPDATE body -- one scoped to a
# single `id`, the other to every row (or every row still missing a value) --
# so a row written by either path can never end up indexed against a
# different document shape than a row written by the other. Source columns:
# title, organization ("employer"), description, and location (no single
# "location" column exists on `opportunities` -- `location_country`,
# `location_city`, `location_region` are concatenated instead). `requirements`
# is included via a correlated subquery over `field_provenances` for any row
# where `field_name = 'requirements'` -- no current adapter populates that
# field (BRIEF-FR-006 C2 assumption, named in the work order return), so this
# is presently a no-op, but a row written by a future adapter that does
# populate it becomes searchable on it with no further change here.
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
        o.description,
        o.location_country,
        o.location_city,
        o.location_region,
        (
            SELECT string_agg(fp.normalized_value, ' ')
            FROM field_provenances fp
            WHERE fp.opportunity_id = o.id AND fp.field_name = 'requirements'
        )
    )
)
"""


def _is_postgres(session: Session) -> bool:
    bind = session.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def backfill_search_tsv(session: Session, *, only_missing: bool = True) -> int:
    """Idempotent batch (re)population of `search_tsv` for existing rows.

    A no-op (returns 0) against a non-PostgreSQL bind (e.g. SQLite in
    matching-suite tests that build `Base.metadata` directly): `search_tsv`
    is a plain TEXT column there with no `to_tsvector` function to call --
    see the column comment in `storage/models.py`.

    `only_missing=True` (the default) only (re)writes rows where
    `search_tsv IS NULL`, which is both the common backfill case (rows
    written before this column existed) and safely re-runnable: running it
    twice in a row touches zero rows the second time. Pass
    `only_missing=False` to force a full reindex of every row (e.g. after
    changing the document definition above).
    """
    if not _is_postgres(session):
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
        return
    session.execute(text(_SEARCH_TSV_UPDATE_SQL + " WHERE o.id = :id"), {"id": opportunity_id})
    session.commit()


class StorageRepository:
    """Production Repository interface for OpportunityOS PostgreSQL relational persistence."""

    def __init__(self, session: Session):
        self.session = session

    # Opportunity Operations
    def save_opportunity(self, opp_data: Dict[str, Any], provenances: List[Dict[str, Any]]) -> OpportunityRecord:
        record = OpportunityRecord(
            id=opp_data["id"],
            track=opp_data["track"],
            title=opp_data["title"],
            organization=opp_data["organization"],
            description=opp_data["description"],
            source_id=opp_data["source_id"],
            source_url=opp_data["source_url"],
            content_hash=opp_data["content_hash"],
            country=opp_data.get("country"),
            region=opp_data.get("region"),
            geographic_scope=opp_data.get("geographic_scope"),
            posted_date=opp_data.get("posted_date"),
            deadline=opp_data.get("deadline"),
            is_stale=opp_data.get("is_stale", False),
            raw_payload_json=opp_data.get("raw_payload_json"),
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
        )
        for prov in provenances:
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
        self.session.commit()

        # BRIEF-FR-006 C2: keep search_tsv current for every write path that
        # goes through this method -- see `_refresh_search_tsv` for why this
        # is application-side rather than a trigger/generated column.
        _refresh_search_tsv(self.session, opp_data["id"])

        return record

    def get_opportunity(self, opportunity_id: str) -> Optional[OpportunityRecord]:
        return self.session.query(OpportunityRecord).filter_by(id=opportunity_id).first()

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
