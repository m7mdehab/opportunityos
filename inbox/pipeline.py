"""Operational Pipeline Event Store and Deterministic State Synchronizer."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
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
            if current_stage == OpportunityStage.DISCOVERED:
                return OpportunityStage.APPLIED
            return current_stage

        if category in (SignalCategory.REJECTION, SignalCategory.PROPOSAL_REJECTION):
            # If currently interviewing or holding an offer, record rejection for that branch
            return OpportunityStage.REJECTED

        return current_stage

    @classmethod
    def replay_events(
        cls,
        opportunity_id: str,
        track: Track,
        events: Sequence[PipelineEvent],
    ) -> DerivedOpportunityState:
        """Deterministically derive opportunity state from sorted event log."""
        sorted_events = sorted(events, key=lambda e: (e.occurred_at, e.recorded_at))
        stage = OpportunityStage.APPLIED
        latest_event_id = ""
        last_cat = SignalCategory.APPLICATION_CONFIRMATION
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
    """Append-only immutable event store with deterministic state replay."""

    def __init__(self) -> None:
        self._events: list[PipelineEvent] = []
        self._seen_signal_opp_pairs: set[tuple[str, str]] = set()

    def record_signal_event(
        self,
        signal: InboundSignal,
        correlation: CorrelationEvidence,
        track: Track,
    ) -> PipelineEvent | None:
        """Record an event if correlation is authoritative and event is not duplicated."""
        if not correlation.is_authoritative or not correlation.opportunity_id:
            return None

        pair = (signal.signal_id, correlation.opportunity_id)
        if pair in self._seen_signal_opp_pairs:
            return None
        self._seen_signal_opp_pairs.add(pair)

        current_state = self.get_opportunity_state(correlation.opportunity_id, track)
        prev_stage = current_state.current_stage if current_state else OpportunityStage.APPLIED
        next_stage = PipelineStateSynchronizer.determine_next_stage(prev_stage, signal.category)

        event = PipelineEvent(
            event_id=f"ev-pipe-{uuid.uuid4().hex[:12]}", opportunity_id=correlation.opportunity_id,
            signal_id=signal.signal_id, previous_stage=prev_stage, new_stage=next_stage,
            track=track, trigger_category=signal.category,
            message_content_hash=signal.message_content_hash, occurred_at=signal.detected_at,
            recorded_at=datetime.now(timezone.utc).isoformat(), notes=signal.summary,
        )
        self._events.append(event)
        return event

    def get_events_for_opportunity(self, opportunity_id: str) -> tuple[PipelineEvent, ...]:
        return tuple([e for e in self._events if e.opportunity_id == opportunity_id])

    def get_opportunity_state(self, opportunity_id: str, track: Track = Track.EMPLOYMENT) -> DerivedOpportunityState:
        evs = self.get_events_for_opportunity(opportunity_id)
        return PipelineStateSynchronizer.replay_events(opportunity_id, track, evs)

    def all_events(self) -> tuple[PipelineEvent, ...]:
        return tuple(self._events)
