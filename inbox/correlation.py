"""Deterministic Opportunity and Outbound Action Correlation Engine."""
from __future__ import annotations

import re
from typing import Sequence
from opportunity.models import Opportunity
from outbound.models import OutboundActionRecord
from .models import (
    CorrelationEvidence,
    CorrelationStatus,
    InboundMessageEvidence,
    InboundSignal,
)


class OpportunityCorrelationEngine:
    """Correlates inbound signals to opportunities with zero tolerance for false correlation."""

    def __init__(
        self,
        opportunities: Sequence[Opportunity] = (),
        outbound_records: Sequence[OutboundActionRecord] = (),
        thread_to_action_map: dict[str, str] | None = None,
    ) -> None:
        self.opportunities = list(opportunities)
        self.outbound_records = list(outbound_records)
        self._action_by_opp_id = {r.opportunity_id: r for r in self.outbound_records}
        self._thread_to_action = dict(thread_to_action_map or {})

    def correlate(self, signal: InboundSignal, evidence: InboundMessageEvidence) -> CorrelationEvidence:
        """Correlate signal using strict deterministic hierarchy. Returns UNLINKED on any ambiguity."""
        # 1. Explicit Reference / Receipt ID Match
        if signal.extracted_references:
            matched_records: list[OutboundActionRecord] = []
            for ref in signal.extracted_references:
                for rec in self.outbound_records:
                    if rec.external_reference_id and rec.external_reference_id.lower() == ref.lower():
                        if rec not in matched_records:
                            matched_records.append(rec)
                    if rec.confirmation_evidence and rec.confirmation_evidence.receipt_reference and rec.confirmation_evidence.receipt_reference.lower() == ref.lower():
                        if rec not in matched_records:
                            matched_records.append(rec)

            if len(matched_records) == 1:
                rec = matched_records[0]
                return CorrelationEvidence(
                    signal_id=signal.signal_id, opportunity_id=rec.opportunity_id,
                    outbound_action_id=rec.action_id, status=CorrelationStatus.EXACT_REFERENCE_MATCH,
                    matching_criteria=(f"reference:{signal.extracted_references[0]}",),
                    confidence=1.0, is_authoritative=True,
                    reason=f"Matched exact external reference ID '{signal.extracted_references[0]}'",
                )
            elif len(matched_records) > 1:
                # Multiple matching records in quoted thread -> strictly fail toward review
                return CorrelationEvidence(
                    signal_id=signal.signal_id, opportunity_id=None, outbound_action_id=None,
                    status=CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE,
                    matching_criteria=tuple([f"action_id:{r.action_id}" for r in matched_records]),
                    confidence=0.0, is_authoritative=False,
                    reason=f"Ambiguous: {len(matched_records)} distinct outbound actions matched references in message/quoted text",
                )

            # Check opportunity source_id
            matched_by_src_id = [opp for opp in self.opportunities if opp.source_id and opp.source_id.lower() in [r.lower() for r in signal.extracted_references]]
            if len(matched_by_src_id) == 1:
                opp = matched_by_src_id[0]
                act = self._action_by_opp_id.get(opp.id)
                return CorrelationEvidence(
                    signal_id=signal.signal_id, opportunity_id=opp.id,
                    outbound_action_id=act.action_id if act else None,
                    status=CorrelationStatus.SOURCE_ID_MATCH, matching_criteria=(f"source_id:{opp.source_id}",),
                    confidence=0.98, is_authoritative=True, reason=f"Matched exact source opportunity ID '{opp.source_id}'",
                )
            elif len(matched_by_src_id) > 1:
                return CorrelationEvidence(
                    signal_id=signal.signal_id, opportunity_id=None, outbound_action_id=None,
                    status=CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE, matching_criteria=tuple([f"opp_id:{o.id}" for o in matched_by_src_id]),
                    confidence=0.0, is_authoritative=False,
                    reason=f"Ambiguous match: {len(matched_by_src_id)} opportunities match references",
                )

        # 2. Persisted Provider Thread ID Match
        if evidence.thread_id and evidence.thread_id in self._thread_to_action:
            action_id = self._thread_to_action[evidence.thread_id]
            rec = next((r for r in self.outbound_records if r.action_id == action_id), None)
            if rec:
                return CorrelationEvidence(
                    signal_id=signal.signal_id, opportunity_id=rec.opportunity_id,
                    outbound_action_id=rec.action_id, status=CorrelationStatus.THREAD_LINKED,
                    matching_criteria=(f"persisted_thread_id:{evidence.thread_id}",), confidence=0.98, is_authoritative=True,
                    reason=f"Matched established provider thread ID '{evidence.thread_id}'",
                )

        # 3. Strong Multi-Field Deterministic Match (Org + Exact Role Title)
        norm_subj = evidence.subject.lower()
        matched_opps: list[Opportunity] = []

        for opp in self.opportunities:
            org_match = opp.organization and (opp.organization.lower() in norm_subj or opp.organization.lower() in evidence.body_text[:500].lower())
            title_tokens = [t.lower() for t in re.split(r"[\s\-_/,]+", opp.title) if len(t) > 3]
            title_match = opp.title.lower() in norm_subj or (title_tokens and all(tok in norm_subj for tok in title_tokens))
            if org_match and title_match:
                matched_opps.append(opp)

        if len(matched_opps) == 1:
            opp = matched_opps[0]
            act = self._action_by_opp_id.get(opp.id)
            return CorrelationEvidence(
                signal_id=signal.signal_id, opportunity_id=opp.id,
                outbound_action_id=act.action_id if act else None,
                status=CorrelationStatus.STRONG_MULTI_FIELD_MATCH,
                matching_criteria=(f"organization:{opp.organization}", f"title:{opp.title}"),
                confidence=0.92, is_authoritative=True,
                reason=f"Unique deterministic match on org '{opp.organization}' and title '{opp.title}'",
            )
        elif len(matched_opps) > 1:
            return CorrelationEvidence(
                signal_id=signal.signal_id, opportunity_id=None, outbound_action_id=None,
                status=CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE,
                matching_criteria=tuple([f"opp_id:{o.id}" for o in matched_opps]),
                confidence=0.0, is_authoritative=False,
                reason=f"Ambiguous: {len(matched_opps)} distinct opportunities match organization and role tokens",
            )

        # 4. Unlinked / Review Required
        return CorrelationEvidence(
            signal_id=signal.signal_id, opportunity_id=None, outbound_action_id=None,
            status=CorrelationStatus.UNLINKED, matching_criteria=(), confidence=0.0, is_authoritative=False,
            reason="No deterministic reference or unique multi-field match found",
        )
