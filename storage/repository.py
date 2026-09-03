import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
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
    FounderFacetRecord,
    FounderSavedViewRecord,
)


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
