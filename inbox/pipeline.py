"""Operational Pipeline Event Store and Deterministic State Synchronizer with Durable SQLite Backing."""
from __future__ import annotations

import hashlib
from typing import Sequence
from matching.models import Track
from .models import (
    CorrelationEvidence,
    CorrelationStatus,
    DerivedOpportunityState,
    InboundSignal,
    OpportunityStage,
    PipelineEvent,
    SignalCategory,
)
from .persistence import DurableInboxStore


class PipelineStateSynchronizer:
    """Synchronizes pipeline events into current derived opportunity states deterministically."""

    @classmethod
    def determine_next_stage(
        cls,
        current_stage: OpportunityStage,
        category: SignalCategory,
    ) -> OpportunityStage:
        """Determine transition logic supporting legitimate non-monotonic process updates."""
        if category in (SignalCategory.OFFER, SignalCategory.AWARD_OR_WIN):
            return OpportunityStage.OFFER_RECEIVED if category == SignalCategory.OFFER else OpportunityStage.AWARDED

        if category in (SignalCategory.INTERVIEW_REQUEST, SignalCategory.DISCOVERY_CALL_OR_MEETING_REQUEST, SignalCategory.SHORTLIST_OR_INVITATION):
            return OpportunityStage.INTERVIEWING

        if category in (SignalCategory.ASSESSMENT, SignalCategory.CLARIFICATION_REQUEST):
            return OpportunityStage.ASSESSMENT_SCHEDULED

        if category in (SignalCategory.RECRUITER_OUTREACH, SignalCategory.CLIENT_OR_BUYER_RESPONSE, SignalCategory.INFORMATION_REQUEST):
            return OpportunityStage.IN_REVIEW

        if category in (SignalCategory.APPLICATION_CONFIRMATION, SignalCategory.PROPOSAL_CONFIRMATION):
            if current_stage in (OpportunityStage.DISCOVERED, OpportunityStage.NO_EVENTS):
                return OpportunityStage.APPLIED
            return current_stage

        if category in (SignalCategory.REJECTION, SignalCategory.PROPOSAL_REJECTION):
            return OpportunityStage.REJECTED

        return current_stage

    @classmethod
    def replay_events(
        cls,
        opportunity_id: str,
        track: Track,
        events: Sequence[PipelineEvent],
        initial_stage: OpportunityStage = OpportunityStage.NO_EVENTS,
    ) -> DerivedOpportunityState:
        """Deterministically derive opportunity state from sorted event log using source timestamps."""
        if not events:
            return DerivedOpportunityState(
                opportunity_id=opportunity_id, track=track, current_stage=initial_stage,
                latest_event_id="", last_signal_category=None, last_signal_at="",
                active_action_required=False, action_deadline=None, action_summary="",
                event_history_count=0,
            )

        sorted_events = sorted(events, key=lambda e: (e.occurred_at, e.recorded_at, e.event_id))
        stage = initial_stage if initial_stage != OpportunityStage.NO_EVENTS else OpportunityStage.APPLIED
        latest_event_id = ""
        last_cat = None
        last_at = ""
        action_req = False
        deadline_str = None
        action_sum = ""

        for ev in sorted_events:
            stage = ev.new_stage
            latest_event_id = ev.event_id
            last_cat = ev.trigger_category
            last_at = ev.occurred_at
            if ev.trigger_category in (
                SignalCategory.INTERVIEW_REQUEST, SignalCategory.OFFER, SignalCategory.ASSESSMENT,
                SignalCategory.CLARIFICATION_REQUEST, SignalCategory.DISCOVERY_CALL_OR_MEETING_REQUEST,
                SignalCategory.RECRUITER_OUTREACH, SignalCategory.PROCUREMENT_AMENDMENT,
            ):
                action_req = True
                action_sum = f"Action required: {ev.trigger_category.value}"
            elif ev.trigger_category in (SignalCategory.REJECTION, SignalCategory.PROPOSAL_REJECTION):
                action_req = False

        return DerivedOpportunityState(
            opportunity_id=opportunity_id, track=track, current_stage=stage,
            latest_event_id=latest_event_id, last_signal_category=last_cat, last_signal_at=last_at,
            active_action_required=action_req, action_deadline=deadline_str, action_summary=action_sum,
            event_history_count=len(sorted_events),
        )


class PipelineEventStore:
    """Append-only immutable event store with SQLite backing and deterministic replay."""

    def __init__(self, store: DurableInboxStore | None = None) -> None:
        self.store = store or DurableInboxStore(":memory:")

    @classmethod
    def compute_event_id(cls, signal_id: str, opportunity_id: str) -> str:
        payload = f"{signal_id}:{opportunity_id}".encode("utf-8")
        return f"ev-pipe-{hashlib.sha256(payload).hexdigest()[:16]}"

    def record_signal_event(
        self,
        signal: InboundSignal,
        correlation: CorrelationEvidence,
        track: Track,
    ) -> PipelineEvent | None:
        """Record an event if correlation is authoritative and event is not duplicated."""
        if not correlation.is_authoritative or not correlation.opportunity_id:
            return None

        event_id = self.compute_event_id(signal.signal_id, correlation.opportunity_id)
        current_state = self.get_opportunity_state(correlation.opportunity_id, track)
        prev_stage = current_state.current_stage if current_state and current_state.current_stage != OpportunityStage.NO_EVENTS else OpportunityStage.APPLIED
        next_stage = PipelineStateSynchronizer.determine_next_stage(prev_stage, signal.category)

        event = PipelineEvent(
            event_id=event_id, opportunity_id=correlation.opportunity_id,
            signal_id=signal.signal_id, previous_stage=prev_stage, new_stage=next_stage,
            track=track, trigger_category=signal.category,
            message_content_hash=signal.message_content_hash, occurred_at=signal.detected_at,
            recorded_at=signal.detected_at, notes=signal.summary,
        )
        inserted = self.store.store_pipeline_event(event)
        return event if inserted else None

    def get_events_for_opportunity(self, opportunity_id: str) -> tuple[PipelineEvent, ...]:
        return self.store.get_events_for_opportunity(opportunity_id)

    def get_opportunity_state(self, opportunity_id: str, track: Track = Track.EMPLOYMENT) -> DerivedOpportunityState:
        evs = self.get_events_for_opportunity(opportunity_id)
        return PipelineStateSynchronizer.replay_events(opportunity_id, track, evs)

    def all_events(self) -> tuple[PipelineEvent, ...]:
        return self.store.get_all_pipeline_events()
