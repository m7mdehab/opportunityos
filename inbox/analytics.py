"""Dual-Track Outcome Analytics with Uncertainty-Aware Small-Denominator Reporting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from matching.models import Track
from opportunity.models import Opportunity
from .models import OpportunityStage, PipelineEvent, SignalCategory


@dataclass(frozen=True, slots=True)
class ConversionMetric:
    """Conversion metric retaining visible sample size and missing-data flags."""
    dimension: str
    dimension_value: str
    total_applications: int
    confirmations_count: int
    interviews_count: int
    offers_count: int
    rejections_count: int
    interview_rate: float | None
    offer_rate: float | None
    is_sample_sufficient: bool  # False if total_applications < 5
    notes: str = ""


class DualTrackAnalyticsEngine:
    """Calculates outcome and conversion metrics without inventing zeroes for missing data."""

    @classmethod
    def compute_source_metrics(
        cls,
        opportunities: Sequence[Opportunity],
        events: Sequence[PipelineEvent],
    ) -> dict[str, ConversionMetric]:
        """Aggregate conversion performance by opportunity source."""
        opp_by_id = {o.id: o for o in opportunities}
        events_by_opp: dict[str, list[PipelineEvent]] = {}
        for ev in events:
            events_by_opp.setdefault(ev.opportunity_id, []).append(ev)

        source_opps: dict[str, list[Opportunity]] = {}
        for opp in opportunities:
            source_opps.setdefault(opp.source, []).append(opp)

        results: dict[str, ConversionMetric] = {}
        for source, opp_list in source_opps.items():
            total = len(opp_list)
            conf_count = 0
            interview_count = 0
            offer_count = 0
            rejection_count = 0

            for o in opp_list:
                evs = events_by_opp.get(o.id, [])
                has_conf = any(e.trigger_category in (SignalCategory.APPLICATION_CONFIRMATION, SignalCategory.PROPOSAL_CONFIRMATION) for e in evs)
                has_interview = any(e.trigger_category in (SignalCategory.INTERVIEW_REQUEST, SignalCategory.DISCOVERY_CALL_OR_MEETING_REQUEST, SignalCategory.SHORTLIST_OR_INVITATION) for e in evs)
                has_offer = any(e.trigger_category in (SignalCategory.OFFER, SignalCategory.AWARD_OR_WIN) for e in evs)
                has_rejection = any(e.trigger_category in (SignalCategory.REJECTION, SignalCategory.PROPOSAL_REJECTION) for e in evs)

                if has_conf: conf_count += 1
                if has_interview: interview_count += 1
                if has_offer: offer_count += 1
                if has_rejection: rejection_count += 1

            interview_rate = (interview_count / total) if total > 0 else None
            offer_rate = (offer_count / total) if total > 0 else None
            sufficient = total >= 5

            results[source] = ConversionMetric(
                dimension="source", dimension_value=source, total_applications=total,
                confirmations_count=conf_count, interviews_count=interview_count,
                offers_count=offer_count, rejections_count=rejection_count,
                interview_rate=interview_rate, offer_rate=offer_rate,
                is_sample_sufficient=sufficient,
                notes="Caution: small sample size (< 5)" if not sufficient else "",
            )
        return results
