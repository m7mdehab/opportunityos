from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from storage.models import (
    OpportunityRecord,
    FieldProvenanceRecord,
    OutboundActionRecord,
    IdempotencyReservationRecord,
    InboundEvidenceRecord,
    PipelineEventRecord,
    NotificationRecord,
    WorkerJobRecord,
    FounderFeedbackRecord,
)

class StorageRepository:
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

    # Outbound / Idempotency Operations
    def reserve_idempotency(self, idempotency_key: str, action_id: str, opportunity_id: str) -> bool:
        existing = self.session.query(IdempotencyReservationRecord).filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return False
        reservation = IdempotencyReservationRecord(
            idempotency_key=idempotency_key,
            action_id=action_id,
            opportunity_id=opportunity_id,
            status="RESERVED",
        )
        self.session.add(reservation)
        self.session.commit()
        return True

    def save_outbound_action(self, action_data: Dict[str, Any]) -> OutboundActionRecord:
        record = OutboundActionRecord(
            id=action_data["id"],
            opportunity_id=action_data["opportunity_id"],
            execution_mode=action_data["execution_mode"],
            action_status=action_data["action_status"],
            idempotency_key=action_data["idempotency_key"],
            prepared_manifest_hash=action_data.get("prepared_manifest_hash"),
            receipt_reference=action_data.get("receipt_reference"),
            confirmation_text=action_data.get("confirmation_text"),
            receipt_checksum=action_data.get("receipt_checksum"),
            error_message=action_data.get("error_message"),
        )
        self.session.merge(record)
        self.session.commit()
        return record

    # Inbound / Pipeline Operations
    def save_inbound_evidence(self, evidence_data: Dict[str, Any]) -> InboundEvidenceRecord:
        record = InboundEvidenceRecord(
            id=evidence_data["id"],
            message_id=evidence_data["message_id"],
            source_provider=evidence_data["source_provider"],
            sender=evidence_data["sender"],
            subject=evidence_data["subject"],
            body_hash=evidence_data["body_hash"],
            received_at=evidence_data["received_at"],
            processing_status=evidence_data.get("processing_status", "FETCHED"),
            processed_at=evidence_data.get("processed_at"),
            raw_headers_json=evidence_data.get("raw_headers_json"),
        )
        self.session.merge(record)
        self.session.commit()
        return record

    def save_pipeline_event(self, event_data: Dict[str, Any]) -> PipelineEventRecord:
        record = PipelineEventRecord(
            id=event_data["id"],
            opportunity_id=event_data["opportunity_id"],
            signal_id=event_data["signal_id"],
            signal_category=event_data["signal_category"],
            source_timestamp=event_data["source_timestamp"],
            confidence=event_data["confidence"],
            provenance_hash=event_data["provenance_hash"],
            event_metadata_json=event_data.get("event_metadata_json"),
        )
        self.session.merge(record)
        self.session.commit()
        return record

    def save_notification(self, notif_data: Dict[str, Any]) -> NotificationRecord:
        record = NotificationRecord(
            id=notif_data["id"],
            notification_key=notif_data["notification_key"],
            opportunity_id=notif_data["opportunity_id"],
            priority=notif_data["priority"],
            headline=notif_data["headline"],
            body=notif_data["body"],
            action_required=notif_data.get("action_required", False),
            deadline=notif_data.get("deadline"),
        )
        self.session.merge(record)
        self.session.commit()
        return record

    # Founder Feedback Operations
    def record_feedback(self, opp_id: str, label: str, reason: Optional[str] = None, notes: Optional[str] = None) -> FounderFeedbackRecord:
        import hashlib
        rec_id = hashlib.sha256(f"{opp_id}:{label}:{datetime.now(timezone.utc).isoformat()}".encode("utf-8")).hexdigest()[:16]
        record = FounderFeedbackRecord(
            id=rec_id,
            opportunity_id=opp_id,
            feedback_label=label,
            structured_reason=reason,
            notes=notes,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def list_feedback_for_opportunity(self, opp_id: str) -> List[FounderFeedbackRecord]:
        return self.session.query(FounderFeedbackRecord).filter_by(opportunity_id=opp_id).all()
