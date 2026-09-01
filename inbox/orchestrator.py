"""Production Operational Loop with Durable Checkpointing and Crash-Safe Message Processing."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Sequence, Union
from matching.models import Track
from opportunity.models import Opportunity
from outbound.models import ActionStatus, OutboundActionRecord
from .analytics import DualTrackAnalyticsEngine
from .classifier import ResponseClassifier
from .correlation import OpportunityCorrelationEngine
from .ingestion import InboundIngestionService
from .learning import SafeLearningEngine
from .models import (
    DerivedOpportunityState,
    FounderNotificationRecord,
    InboundMessageEvidence,
    InboundSignal,
    PipelineEvent,
    SignalCategory,
)
from .notifications import NotificationEngine
from .persistence import DurableInboxStore
from .postgres_persistence import PostgresInboxStore
from .pipeline import PipelineEventStore


@dataclass(frozen=True, slots=True)
class InboundProcessingCycleResult:
    """Summary result of an operational processing cycle."""
    messages_ingested: int
    signals_detected: int
    events_recorded: int
    notifications_emitted: int
    reconciliations_created: int
    cursor_checkpoint: str


class ProductionOperationalOrchestrator:
    """Coordinates polling, classification, correlation, pipeline update, notifications, and analytics."""

    def __init__(
        self,
        ingestion_service: InboundIngestionService,
        opportunities: Sequence[Opportunity] = (),
        outbound_records: Sequence[OutboundActionRecord] = (),
        workspace: str = "default",
        candidate_id: str = "founder",
        store: Union[DurableInboxStore, PostgresInboxStore] | None = None,
        thread_to_action_map: dict[str, str] | None = None,
    ) -> None:
        if store is not None:
            self.store = store
        elif hasattr(ingestion_service, "store") and ingestion_service.store is not None:
            self.store = ingestion_service.store
        else:
            self.store = PostgresInboxStore()

        self.ingestion_service = ingestion_service
        self.opportunities = list(opportunities)
        self.outbound_records = list(outbound_records)
        self.classifier = ResponseClassifier()
        self.correlation_engine = OpportunityCorrelationEngine(self.opportunities, self.outbound_records, thread_to_action_map=thread_to_action_map)
        self.pipeline_store = PipelineEventStore(store=self.store)
        self.notification_engine = NotificationEngine(workspace=workspace, candidate_id=candidate_id, store=self.store)
        self.checkpoint_key = f"cursor:{workspace}:{candidate_id}"

    def get_checkpoint_cursor(self) -> str:
        cur = self.store.get_checkpoint(self.checkpoint_key)
        return cur if cur is not None else "0"

    def run_cycle(
        self,
        limit: int = 50,
        hook_after_message: Callable[[int, InboundMessageEvidence], None] | None = None,
    ) -> InboundProcessingCycleResult:
        """Run a single polling and processing cycle with exact-once message completion."""
        current_cursor = self.get_checkpoint_cursor()
        new_msgs, next_cursor = self.ingestion_service.poll_new_messages(current_cursor=current_cursor, limit=limit)

        signals_count = 0
        events_count = 0
        notifs_count = 0
        reconciliations_count = 0

        for idx, msg in enumerate(new_msgs, start=1):
            sig = self.classifier.classify(msg)
            signals_count += 1

            corr = self.correlation_engine.correlate(sig, msg)
            if corr.is_authoritative and corr.opportunity_id:
                act = next((r for r in self.outbound_records if r.opportunity_id == corr.opportunity_id), None)
                if act and act.action_status == ActionStatus.UNKNOWN_OUTCOME and sig.category in (SignalCategory.APPLICATION_CONFIRMATION, SignalCategory.PROPOSAL_CONFIRMATION):
                    recon_id = f"recon-{hashlib.sha256(f'{act.action_id}:{sig.signal_id}'.encode('utf-8')).hexdigest()[:16]}"
                    self.store.record_reconciliation(
                        reconciliation_id=recon_id, outbound_action_id=act.action_id,
                        opportunity_id=corr.opportunity_id, signal_id=sig.signal_id,
                        inbound_content_hash=msg.message_content_hash,
                        reason="Inbound confirmation received for action in UNKNOWN_OUTCOME state; founder reconciliation required",
                        created_at=sig.detected_at,
                    )
                    reconciliations_count += 1

                ev = self.pipeline_store.record_signal_event(sig, corr, sig.track)
                if ev:
                    events_count += 1

            notif = self.notification_engine.process_signal(sig, corr)
            if notif:
                notifs_count += 1

            # Mark this specific message as PROCESSED in durable store
            self.store.mark_evidence_processed(msg.message_content_hash, datetime.now(timezone.utc).isoformat())

            # Optional injection hook for crash simulation
            if hook_after_message is not None:
                hook_after_message(idx, msg)

        # Durably commit cursor only when all messages in the batch are processed
        self.store.save_checkpoint(self.checkpoint_key, next_cursor, datetime.now(timezone.utc).isoformat())

        return InboundProcessingCycleResult(
            messages_ingested=len(new_msgs), signals_detected=signals_count,
            events_recorded=events_count, notifications_emitted=notifs_count,
            reconciliations_created=reconciliations_count,
            cursor_checkpoint=next_cursor,
        )

    def get_opportunity_state(self, opportunity_id: str, track: Track = Track.EMPLOYMENT) -> DerivedOpportunityState:
        return self.pipeline_store.get_opportunity_state(opportunity_id, track)

    def get_active_notifications(self) -> tuple[FounderNotificationRecord, ...]:
        return self.notification_engine.get_active_notifications()

    def get_analytics(self) -> dict:
        return DualTrackAnalyticsEngine.compute_multi_dimensional_metrics(self.outbound_records, self.pipeline_store.all_events())
