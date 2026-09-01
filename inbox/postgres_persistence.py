import json
from datetime import datetime, timezone
from typing import Any, Optional, Sequence, List
from sqlalchemy.orm import Session
from storage.engine import get_engine, get_session_factory, get_production_db_url
from storage.models import (
    InboundEvidenceRecord,
    PipelineEventRecord,
    NotificationRecord,
    InboxCheckpointRecord,
    ReconciliationRecordModel,
)
from matching.models import Track
from inbox.models import (
    DerivedOpportunityState,
    ExtractedDeadline,
    FounderNotificationRecord,
    InboundMessageEvidence,
    InboundSignal,
    OpportunityStage,
    PipelineEvent,
    SignalCategory,
    SignalPriority,
)


class PostgresInboxStore:
    """Thread-safe and process-durable PostgreSQL/Relational persistence store for inbox with 100% frozen interface parity."""

    def __init__(self, db_url: Optional[str] = None, session: Optional[Session] = None):
        self._external_session = session
        if self._external_session is None:
            self.db_url = db_url or get_production_db_url()
            self.engine = get_engine(self.db_url)
            self.session_factory = get_session_factory(self.engine)
        else:
            self.db_url = db_url
            self.engine = None
            self.session_factory = None

    def _get_session(self) -> Session:
        if self._external_session is not None:
            return self._external_session
        return self.session_factory()

    def store_evidence(self, msg: InboundMessageEvidence, status: str = "FETCHED") -> bool:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            existing = session.query(InboundEvidenceRecord).filter_by(message_content_hash=msg.message_content_hash).first()
            if existing:
                return False
            rec_at = datetime.fromisoformat(msg.received_at) if msg.received_at else datetime.now(timezone.utc)
            rec = InboundEvidenceRecord(
                message_content_hash=msg.message_content_hash,
                provider=msg.provider,
                provider_message_id=msg.provider_message_id,
                thread_id=msg.thread_id,
                sender_email=msg.sender_email,
                sender_name=msg.sender_name,
                recipient_email=msg.recipient_email,
                subject=msg.subject,
                snippet=msg.snippet,
                body_text=msg.body_text,
                body_html=msg.body_html,
                received_at=rec_at,
                headers_json=json.dumps(msg.headers),
                attachment_names_json=json.dumps(msg.attachment_names),
                processing_status=status,
                processed_at=None,
            )
            session.add(rec)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            if owns_session:
                session.close()

    def mark_evidence_processed(self, content_hash: str, processed_at: Optional[str] = None) -> None:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            rec = session.query(InboundEvidenceRecord).filter_by(message_content_hash=content_hash).first()
            if rec:
                rec.processing_status = "PROCESSED"
                rec.processed_at = datetime.fromisoformat(processed_at) if processed_at else datetime.now(timezone.utc)
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if owns_session:
                session.close()

    def is_evidence_processed(self, content_hash: str) -> bool:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            rec = session.query(InboundEvidenceRecord).filter_by(message_content_hash=content_hash).first()
            return rec is not None and rec.processing_status == "PROCESSED"
        finally:
            if owns_session:
                session.close()

    def get_evidence(self, content_hash: str) -> Optional[InboundMessageEvidence]:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            rec = session.query(InboundEvidenceRecord).filter_by(message_content_hash=content_hash).first()
            if not rec:
                return None
            return self._row_to_evidence(rec)
        finally:
            if owns_session:
                session.close()

    def get_all_evidence(self) -> tuple[InboundMessageEvidence, ...]:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            records = session.query(InboundEvidenceRecord).order_by(InboundEvidenceRecord.received_at.asc()).all()
            return tuple(self._row_to_evidence(r) for r in records)
        finally:
            if owns_session:
                session.close()

    def store_pipeline_event(self, event: PipelineEvent) -> bool:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            occ_at = datetime.fromisoformat(event.occurred_at) if event.occurred_at else datetime.now(timezone.utc)
            rec_at = datetime.fromisoformat(event.recorded_at) if event.recorded_at else datetime.now(timezone.utc)
            rec = PipelineEventRecord(
                event_id=event.event_id,
                opportunity_id=event.opportunity_id,
                signal_id=event.signal_id,
                previous_stage=event.previous_stage.value,
                new_stage=event.new_stage.value,
                track=event.track.value,
                trigger_category=event.trigger_category.value,
                message_content_hash=event.message_content_hash,
                occurred_at=occ_at,
                recorded_at=rec_at,
                actor=event.actor,
                notes=event.notes,
            )
            session.add(rec)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            if owns_session:
                session.close()

    def store_event(self, event: PipelineEvent) -> bool:
        return self.store_pipeline_event(event)

    def get_events_for_opportunity(self, opportunity_id: str) -> tuple[PipelineEvent, ...]:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            records = (
                session.query(PipelineEventRecord)
                .filter_by(opportunity_id=opportunity_id)
                .order_by(PipelineEventRecord.occurred_at.asc(), PipelineEventRecord.recorded_at.asc(), PipelineEventRecord.event_id.asc())
                .all()
            )
            return tuple(self._row_to_event(r) for r in records)
        finally:
            if owns_session:
                session.close()

    def get_all_pipeline_events(self) -> tuple[PipelineEvent, ...]:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            records = (
                session.query(PipelineEventRecord)
                .order_by(PipelineEventRecord.occurred_at.asc(), PipelineEventRecord.recorded_at.asc(), PipelineEventRecord.event_id.asc())
                .all()
            )
            return tuple(self._row_to_event(r) for r in records)
        finally:
            if owns_session:
                session.close()

    def store_notification(self, notif: FounderNotificationRecord) -> bool:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            c_at = datetime.fromisoformat(notif.created_at) if notif.created_at else datetime.now(timezone.utc)
            rec = NotificationRecord(
                notification_key=notif.notification_key,
                notification_id=notif.notification_id,
                opportunity_id=notif.opportunity_id,
                signal_id=notif.signal_id,
                priority=notif.priority.value,
                category=notif.category.value,
                title=notif.title,
                message=notif.message,
                action_required=notif.action_required,
                deadline=notif.deadline,
                created_at=c_at,
                acknowledged=notif.acknowledged,
                acknowledged_at=None,
            )
            session.add(rec)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            if owns_session:
                session.close()

    def get_pending_notifications(self) -> tuple[FounderNotificationRecord, ...]:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            records = (
                session.query(NotificationRecord)
                .filter_by(acknowledged=False)
                .order_by(NotificationRecord.created_at.asc(), NotificationRecord.notification_id.asc())
                .all()
            )
            return tuple(self._row_to_notification(r) for r in records)
        finally:
            if owns_session:
                session.close()

    def get_all_notifications(self) -> tuple[FounderNotificationRecord, ...]:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            records = (
                session.query(NotificationRecord)
                .order_by(NotificationRecord.created_at.asc(), NotificationRecord.notification_id.asc())
                .all()
            )
            return tuple(self._row_to_notification(r) for r in records)
        finally:
            if owns_session:
                session.close()

    def acknowledge_notification(self, notification_key: str, acknowledged_at: str | None = None) -> bool:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            rec = session.query(NotificationRecord).filter_by(notification_key=notification_key).first()
            if rec:
                rec.acknowledged = True
                rec.acknowledged_at = datetime.fromisoformat(acknowledged_at) if acknowledged_at else datetime.now(timezone.utc)
                session.commit()
                return True
            return False
        except Exception:
            session.rollback()
            return False
        finally:
            if owns_session:
                session.close()

    def save_checkpoint(self, checkpoint_key: str, cursor_value: str, updated_at: str | None = None) -> None:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            now = datetime.fromisoformat(updated_at) if updated_at else datetime.now(timezone.utc)
            rec = session.query(InboxCheckpointRecord).filter_by(checkpoint_key=checkpoint_key).first()
            if rec:
                rec.cursor_value = cursor_value
                rec.updated_at = now
            else:
                rec = InboxCheckpointRecord(checkpoint_key=checkpoint_key, cursor_value=cursor_value, updated_at=now)
                session.add(rec)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if owns_session:
                session.close()

    def get_checkpoint(self, checkpoint_key: str) -> Optional[str]:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            rec = session.query(InboxCheckpointRecord).filter_by(checkpoint_key=checkpoint_key).first()
            return rec.cursor_value if rec else None
        finally:
            if owns_session:
                session.close()

    def record_reconciliation(
        self,
        reconciliation_id: str,
        outbound_action_id: str,
        opportunity_id: str,
        signal_id: str,
        inbound_content_hash: str,
        reason: str,
        created_at: str | None = None,
    ) -> bool:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            c_at = datetime.fromisoformat(created_at) if created_at else datetime.now(timezone.utc)
            rec = ReconciliationRecordModel(
                reconciliation_id=reconciliation_id,
                outbound_action_id=outbound_action_id,
                opportunity_id=opportunity_id,
                signal_id=signal_id,
                inbound_content_hash=inbound_content_hash,
                reason=reason,
                created_at=c_at,
                resolved=False,
                resolved_at=None,
            )
            session.add(rec)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            if owns_session:
                session.close()

    def store_reconciliation(self, rec_id: str, outbound_action_id: str, opportunity_id: str, signal_id: str, inbound_content_hash: str, reason: str) -> bool:
        return self.record_reconciliation(rec_id, outbound_action_id, opportunity_id, signal_id, inbound_content_hash, reason)

    def get_unresolved_reconciliations(self) -> tuple[dict[str, Any], ...]:
        session = self._get_session()
        owns_session = self._external_session is None
        try:
            records = session.query(ReconciliationRecordModel).filter_by(resolved=False).all()
            res = []
            for r in records:
                res.append({
                    "reconciliation_id": r.reconciliation_id,
                    "outbound_action_id": r.outbound_action_id,
                    "opportunity_id": r.opportunity_id,
                    "signal_id": r.signal_id,
                    "inbound_content_hash": r.inbound_content_hash,
                    "reason": r.reason,
                    "created_at": r.created_at.isoformat() if r.created_at else "2026-08-30T00:00:00Z",
                    "resolved": 1 if r.resolved else 0,
                    "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
                })
            return tuple(res)
        finally:
            if owns_session:
                session.close()

    def _row_to_evidence(self, r: InboundEvidenceRecord) -> InboundMessageEvidence:
        headers_raw = json.loads(r.headers_json) if r.headers_json else []
        headers_tuple = tuple(tuple(item) for item in headers_raw)
        attachments_raw = json.loads(r.attachment_names_json) if r.attachment_names_json else []
        return InboundMessageEvidence(
            message_content_hash=r.message_content_hash,
            provider=r.provider,
            provider_message_id=r.provider_message_id,
            thread_id=r.thread_id,
            sender_email=r.sender_email,
            sender_name=r.sender_name,
            recipient_email=r.recipient_email,
            subject=r.subject,
            snippet=r.snippet,
            body_text=r.body_text,
            body_html=r.body_html,
            received_at=r.received_at.isoformat() if r.received_at else "2026-08-30T00:00:00Z",
            headers=headers_tuple,
            attachment_names=tuple(attachments_raw),
        )

    def _row_to_event(self, r: PipelineEventRecord) -> PipelineEvent:
        return PipelineEvent(
            event_id=r.event_id,
            opportunity_id=r.opportunity_id,
            signal_id=r.signal_id,
            previous_stage=OpportunityStage(r.previous_stage),
            new_stage=OpportunityStage(r.new_stage),
            track=Track(r.track),
            trigger_category=SignalCategory(r.trigger_category),
            message_content_hash=r.message_content_hash,
            occurred_at=r.occurred_at.isoformat() if r.occurred_at else "2026-08-30T00:00:00Z",
            recorded_at=r.recorded_at.isoformat() if r.recorded_at else "2026-08-30T00:00:00Z",
            actor=r.actor,
            notes=r.notes,
        )

    def _row_to_notification(self, r: NotificationRecord) -> FounderNotificationRecord:
        return FounderNotificationRecord(
            notification_key=r.notification_key,
            notification_id=r.notification_id,
            opportunity_id=r.opportunity_id,
            signal_id=r.signal_id,
            priority=SignalPriority(r.priority),
            category=SignalCategory(r.category),
            title=r.title,
            message=r.message,
            action_required=r.action_required,
            deadline=r.deadline,
            created_at=r.created_at.isoformat() if r.created_at else "2026-08-30T00:00:00Z",
            acknowledged=r.acknowledged,
            acknowledged_at=r.acknowledged_at.isoformat() if r.acknowledged_at else None,
        )
