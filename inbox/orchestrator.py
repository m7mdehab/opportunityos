"""Production Operational Loop with Checkpoint and Replay Safety."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from matching.models import Track
from opportunity.models import Opportunity
from outbound.models import OutboundActionRecord
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
)
from .notifications import NotificationEngine
from .pipeline import PipelineEventStore


@dataclass(frozen=True, slots=True)
class InboundProcessingCycleResult:
    """Summary result of an operational processing cycle."""
    messages_ingested: int
    signals_detected: int
    events_recorded: int
    notifications_emitted: int
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
    ) -> None:
        self.ingestion_service = ingestion_service
        self.opportunities = list(opportunities)
        self.outbound_records = list(outbound_records)
        self.classifier = ResponseClassifier()
        self.correlation_engine = OpportunityCorrelationEngine(self.opportunities, self.outbound_records)
        self.pipeline_store = PipelineEventStore()
        self.notification_engine = NotificationEngine(workspace=workspace, candidate_id=candidate_id)
        self.checkpoint_cursor = "0"

    def run_cycle(self, limit: int = 50) -> InboundProcessingCycleResult:
        """Run a single polling and processing cycle."""
        new_msgs, next_cursor = self.ingestion_service.poll_new_messages(current_cursor=self.checkpoint_cursor, limit=limit)
        self.checkpoint_cursor = next_cursor

        signals_count = 0
        events_count = 0
        notifs_count = 0

        for msg in new_msgs:
            sig = self.classifier.classify(msg)
            signals_count += 1

            corr = self.correlation_engine.correlate(sig, msg)
            if corr.is_authoritative and corr.opportunity_id:
                ev = self.pipeline_store.record_signal_event(sig, corr, sig.track)
                if ev:
                    events_count += 1

            notif = self.notification_engine.process_signal(sig, corr)
            if notif:
                notifs_count += 1

        return InboundProcessingCycleResult(
            messages_ingested=len(new_msgs), signals_detected=signals_count,
            events_recorded=events_count, notifications_emitted=notifs_count,
            cursor_checkpoint=self.checkpoint_cursor,
        )

    def get_opportunity_state(self, opportunity_id: str, track: Track = Track.EMPLOYMENT) -> DerivedOpportunityState:
        return self.pipeline_store.get_opportunity_state(opportunity_id, track)

    def get_active_notifications(self) -> tuple[FounderNotificationRecord, ...]:
        return self.notification_engine.get_active_notifications()

    def get_analytics(self) -> dict:
        return DualTrackAnalyticsEngine.compute_source_metrics(self.opportunities, self.pipeline_store.all_events())
