"""Dual-Track Outcome Analytics with Multi-Dimensional Coverage and Real Application Denominators."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from matching.models import Track
from opportunity.models import Opportunity
from outbound.models import ActionStatus, OutboundActionRecord
from .models import OpportunityStage, PipelineEvent, SignalCategory


@dataclass(frozen=True, slots=True)
class ConversionMetric:
    """Conversion metric retaining visible sample size, application denominator, and missing-data flags."""
    dimension: str
    dimension_value: str
    total_submissions: int
    confirmations_count: int
    interviews_count: int
    offers_count: int
    rejections_count: int
    pending_count: int
    interview_rate: float | None
    offer_rate: float | None
    is_sample_sufficient: bool  # False if total_submissions < 5
    notes: str = ""


class DualTrackAnalyticsEngine:
    """Calculates outcome and conversion metrics across multiple dimensions where denominator is real submissions."""

    SUPPORTED_DIMENSIONS = (
        "source",
        "track",
        "role_family",
        "score_band",
        "adapter_version",
        "compensation_band",
        "qualified_conversation",
    )

    QUALIFYING_CONVERSATION_CATEGORIES = (
        SignalCategory.INTERVIEW_REQUEST,
        SignalCategory.RECRUITER_OUTREACH,
        SignalCategory.DISCOVERY_CALL_OR_MEETING_REQUEST,
        SignalCategory.SHORTLIST_OR_INVITATION,
        SignalCategory.CLIENT_OR_BUYER_RESPONSE,
        SignalCategory.CLARIFICATION_REQUEST,
    )

    @classmethod
    def _extract_dimension_value(
        cls,
        record: OutboundActionRecord,
        events: Sequence[PipelineEvent],
        dimension: str,
    ) -> str:
        if dimension == "source":
            return record.source or "UNAVAILABLE"
        elif dimension == "track":
            return record.track.value if record.track else "UNAVAILABLE"
        elif dimension == "adapter_version":
            return record.adapter_version or "UNAVAILABLE"
        elif dimension == "score_band":
            if record.match_score_snapshot is None:
                return "UNAVAILABLE"
            score = record.match_score_snapshot
            if score >= 0.8:
                return "high (>=0.80)"
            elif score >= 0.5:
                return "medium (0.50-0.79)"
            else:
                return "low (<0.50)"
        elif dimension == "qualified_conversation":
            opp_events = [e for e in events if e.opportunity_id == record.opportunity_id]
            if not opp_events:
                return "pending_outcome"
            has_qual_conv = any(e.trigger_category in cls.QUALIFYING_CONVERSATION_CATEGORIES for e in opp_events)
            return "qualified_conversation_achieved" if has_qual_conv else "no_qualified_conversation"
        else:
            # Dimension genuinely not present in outbound record evidence
            return "UNAVAILABLE"

    @classmethod
    def compute_dimension_metrics(
        cls,
        outbound_records: Sequence[OutboundActionRecord],
        events: Sequence[PipelineEvent],
        dimension: str = "source",
    ) -> dict[str, ConversionMetric]:
        """Aggregate conversion performance by a specific dimension."""
        submitted_actions = [
            r for r in outbound_records
            if r.action_status in (ActionStatus.CONFIRMED, ActionStatus.SUBMITTED, ActionStatus.UNKNOWN_OUTCOME)
        ]
        events_by_opp: dict[str, list[PipelineEvent]] = {}
        for ev in events:
            events_by_opp.setdefault(ev.opportunity_id, []).append(ev)

        actions_by_dim: dict[str, list[OutboundActionRecord]] = {}
        for r in submitted_actions:
            dim_val = cls._extract_dimension_value(r, events_by_opp.get(r.opportunity_id, ()), dimension)
            actions_by_dim.setdefault(dim_val, []).append(r)

        results: dict[str, ConversionMetric] = {}
        for dim_val, act_list in actions_by_dim.items():
            total = len(act_list)
            conf_count = 0
            interview_count = 0
            offer_count = 0
            rejection_count = 0
            pending_count = 0

            for act in act_list:
                evs = events_by_opp.get(act.opportunity_id, [])
                has_conf = any(e.trigger_category in (SignalCategory.APPLICATION_CONFIRMATION, SignalCategory.PROPOSAL_CONFIRMATION) for e in evs)
                has_interview = any(e.trigger_category in (SignalCategory.INTERVIEW_REQUEST, SignalCategory.DISCOVERY_CALL_OR_MEETING_REQUEST, SignalCategory.SHORTLIST_OR_INVITATION) for e in evs)
                has_offer = any(e.trigger_category in (SignalCategory.OFFER, SignalCategory.AWARD_OR_WIN) for e in evs)
                has_rejection = any(e.trigger_category in (SignalCategory.REJECTION, SignalCategory.PROPOSAL_REJECTION) for e in evs)

                if has_conf: conf_count += 1
                if has_interview: interview_count += 1
                if has_offer: offer_count += 1
                if has_rejection: rejection_count += 1
                if not has_interview and not has_offer and not has_rejection:
                    pending_count += 1

            interview_rate = (interview_count / total) if total > 0 else None
            offer_rate = (offer_count / total) if total > 0 else None
            sufficient = total >= 5

            results[dim_val] = ConversionMetric(
                dimension=dimension, dimension_value=dim_val, total_submissions=total,
                confirmations_count=conf_count, interviews_count=interview_count,
                offers_count=offer_count, rejections_count=rejection_count,
                pending_count=pending_count,
                interview_rate=interview_rate, offer_rate=offer_rate,
                is_sample_sufficient=sufficient,
                notes="Caution: small sample size (< 5)" if not sufficient else "",
            )
        return results

    @classmethod
    def compute_source_metrics(
        cls,
        outbound_records: Sequence[OutboundActionRecord],
        events: Sequence[PipelineEvent],
    ) -> dict[str, ConversionMetric]:
        return cls.compute_dimension_metrics(outbound_records, events, dimension="source")

    @classmethod
    def compute_multi_dimensional_metrics(
        cls,
        outbound_records: Sequence[OutboundActionRecord],
        events: Sequence[PipelineEvent],
    ) -> dict[str, dict[str, ConversionMetric]]:
        """Compute metrics across all supported dimensions."""
        return {
            dim: cls.compute_dimension_metrics(outbound_records, events, dimension=dim)
            for dim in cls.SUPPORTED_DIMENSIONS
        }
