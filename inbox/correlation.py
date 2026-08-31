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
    ) -> None:
        self.opportunities = list(opportunities)
        self.outbound_records = list(outbound_records)
        self._action_by_opp_id = {r.opportunity_id: r for r in self.outbound_records}

    def correlate(self, signal: InboundSignal, evidence: InboundMessageEvidence) -> CorrelationEvidence:
        """Correlate signal using strict deterministic hierarchy. Returns UNLINKED on any ambiguity."""
        full_text = f"{evidence.subject} {evidence.body_text} {' '.join(signal.extracted_references)}"
        
        # 1. Explicit Reference / Receipt ID Match
        if signal.extracted_references:
            for ref in signal.extracted_references:
                # Check outbound action external reference or action_id
                for rec in self.outbound_records:
                    if rec.external_reference_id and rec.external_reference_id.lower() == ref.lower():
                        return CorrelationEvidence(
                            signal_id=signal.signal_id, opportunity_id=rec.opportunity_id,
                            outbound_action_id=rec.action_id, status=CorrelationStatus.EXACT_REFERENCE_MATCH,
                            matching_criteria=(f"external_reference_id:{ref}",), confidence=1.0, is_authoritative=True,
                            reason=f"Matched exact external reference ID '{ref}'",
                        )
                    if rec.confirmation_evidence and rec.confirmation_evidence.receipt_reference and rec.confirmation_evidence.receipt_reference.lower() == ref.lower():
                        return CorrelationEvidence(
                            signal_id=signal.signal_id, opportunity_id=rec.opportunity_id,
                            outbound_action_id=rec.action_id, status=CorrelationStatus.EXACT_REFERENCE_MATCH,
                            matching_criteria=(f"receipt_reference:{ref}",), confidence=1.0, is_authoritative=True,
                            reason=f"Matched exact confirmation receipt '{ref}'",
                        )
                # Check opportunity source_id
                matched_by_src_id = [opp for opp in self.opportunities if opp.source_id and opp.source_id.lower() == ref.lower()]
                if len(matched_by_src_id) == 1:
                    opp = matched_by_src_id[0]
                    act = self._action_by_opp_id.get(opp.id)
                    return CorrelationEvidence(
                        signal_id=signal.signal_id, opportunity_id=opp.id,
                        outbound_action_id=act.action_id if act else None,
                        status=CorrelationStatus.SOURCE_ID_MATCH, matching_criteria=(f"source_id:{ref}",),
                        confidence=0.98, is_authoritative=True, reason=f"Matched exact source opportunity ID '{ref}'",
                    )
                elif len(matched_by_src_id) > 1:
                    return CorrelationEvidence(
                        signal_id=signal.signal_id, opportunity_id=None, outbound_action_id=None,
                        status=CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE, matching_criteria=(f"source_id:{ref}",),
                        confidence=0.0, is_authoritative=False,
                        reason=f"Ambiguous match: {len(matched_by_src_id)} opportunities share source_id '{ref}'",
                    )

        # 2. Exact Thread ID Match
        if evidence.thread_id:
            matched_by_thread = [
                rec for rec in self.outbound_records
                if rec.external_reference_id and rec.external_reference_id == evidence.thread_id
            ]
            if len(matched_by_thread) == 1:
                rec = matched_by_thread[0]
                return CorrelationEvidence(
                    signal_id=signal.signal_id, opportunity_id=rec.opportunity_id,
                    outbound_action_id=rec.action_id, status=CorrelationStatus.THREAD_LINKED,
                    matching_criteria=(f"thread_id:{evidence.thread_id}",), confidence=0.98, is_authoritative=True,
                    reason=f"Matched known thread ID '{evidence.thread_id}'",
                )

        # 3. Strong Multi-Field Deterministic Match (Org + Exact Role Title)
        norm_subj = evidence.subject.lower()
        matched_opps: list[Opportunity] = []

        for opp in self.opportunities:
            org_match = opp.organization and (opp.organization.lower() in norm_subj or opp.organization.lower() in evidence.body_text[:500].lower())
            # Require exact role title or strong title tokens
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
            # Multiple concurrent applications at the same company with similar titles -> STRICT AMBIGUITY BLOCK
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
