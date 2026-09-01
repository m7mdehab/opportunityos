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
