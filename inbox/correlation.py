"""Deterministic Opportunity Correlation Engine with Strict Exact Authority and Hardened Multi-Candidate Protection."""
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
    """Correlates an InboundSignal with a known Opportunity and OutboundActionRecord using strict normalized exact matching."""

    def __init__(
        self,
        opportunities: Sequence[Opportunity] = (),
        outbound_records: Sequence[OutboundActionRecord] = (),
        thread_to_action_map: dict[str, str] | None = None,
    ) -> None:
        self.opportunities = list(opportunities)
        self.outbound_records = list(outbound_records)
        self._thread_to_action = thread_to_action_map or {}
        self._action_by_opp_id: dict[str, OutboundActionRecord] = {
            r.opportunity_id: r for r in self.outbound_records if r.opportunity_id
        }
        self._opp_by_id: dict[str, Opportunity] = {o.id: o for o in self.opportunities}

    @classmethod
    def _normalize_ref(cls, ref: str) -> str:
        """Normalize reference string by stripping whitespace and common casing."""
        return ref.strip().upper()

    def correlate(self, signal: InboundSignal, evidence: InboundMessageEvidence) -> CorrelationEvidence:
        """Deterministically correlate inbound signal against opportunities with zero false merges and strict exact reference matching."""
        # 1. Multiple extracted references in message/history fail closed
        if len(signal.extracted_references) > 1:
            norm_refs = {self._normalize_ref(r) for r in signal.extracted_references}
            matched_by_ref = [
                r for r in self.outbound_records
                if (r.external_reference_id and self._normalize_ref(r.external_reference_id) in norm_refs)
                or (r.action_id and self._normalize_ref(r.action_id) in norm_refs)
                or (r.confirmation_evidence and r.confirmation_evidence.receipt_reference and self._normalize_ref(r.confirmation_evidence.receipt_reference) in norm_refs)
                or (r.confirmation_evidence and r.confirmation_evidence.application_id and self._normalize_ref(r.confirmation_evidence.application_id) in norm_refs)
            ]
            if len(matched_by_ref) > 1:
                return CorrelationEvidence(
                    signal_id=signal.signal_id, opportunity_id=None, outbound_action_id=None,
                    status=CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE,
                    matching_criteria=tuple([f"ref:{r.external_reference_id or r.action_id}" for r in matched_by_ref]),
                    confidence=0.0, is_authoritative=False,
                    reason=f"Ambiguous: multiple distinct outbound actions ({len(matched_by_ref)}) matched references in message history",
                )

        # Single explicit reference match (Strict Normalized Exact Match Only)
        if len(signal.extracted_references) == 1:
            ref_raw = signal.extracted_references[0]
            ref_norm = self._normalize_ref(ref_raw)

            # Match OutboundActionRecord (external_reference_id, action_id, or confirmation_evidence.receipt_reference / application_id)
            matched_records = [
                r for r in self.outbound_records
                if (r.external_reference_id and self._normalize_ref(r.external_reference_id) == ref_norm)
                or (r.action_id and self._normalize_ref(r.action_id) == ref_norm)
                or (r.confirmation_evidence and r.confirmation_evidence.receipt_reference and self._normalize_ref(r.confirmation_evidence.receipt_reference) == ref_norm)
                or (r.confirmation_evidence and r.confirmation_evidence.application_id and self._normalize_ref(r.confirmation_evidence.application_id) == ref_norm)
            ]
            if len(matched_records) == 1:
                rec = matched_records[0]
                return CorrelationEvidence(
                    signal_id=signal.signal_id, opportunity_id=rec.opportunity_id,
                    outbound_action_id=rec.action_id, status=CorrelationStatus.EXACT_REFERENCE_MATCH,
                    matching_criteria=(f"exact_reference:{ref_raw}",), confidence=1.0, is_authoritative=True,
                    reason=f"Matched exact normalized reference ID '{ref_raw}'",
                )
            elif len(matched_records) > 1:
                return CorrelationEvidence(
                    signal_id=signal.signal_id, opportunity_id=None, outbound_action_id=None,
                    status=CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE,
                    matching_criteria=tuple([f"action_id:{r.action_id}" for r in matched_records]),
                    confidence=0.0, is_authoritative=False,
                    reason=f"Ambiguous reference match: {len(matched_records)} actions share reference",
                )

            # Match against Opportunity.source_id (Strict Normalized Exact Match Only)
            matched_by_src_id = [
                o for o in self.opportunities
                if o.source_id and self._normalize_ref(o.source_id) == ref_norm
            ]
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

        # 3. Strong Multi-Field Deterministic Match (Org + Title) OR Title-only collision detection
        norm_subj = evidence.subject.lower()
        full_text = f"{norm_subj} {evidence.body_text[:500].lower()}"
        matched_opps: list[Opportunity] = []
        title_only_matched: list[Opportunity] = []

        for opp in self.opportunities:
            org_match = opp.organization and (opp.organization.lower() in norm_subj or opp.organization.lower() in evidence.body_text[:500].lower())
            title_tokens = [t.lower() for t in re.split(r"[\s\-_/,]+", opp.title) if len(t) > 3]
            title_match = opp.title.lower() in full_text or (title_tokens and all(tok in full_text for tok in title_tokens))
            if org_match and title_match:
                matched_opps.append(opp)
            elif title_match:
                title_only_matched.append(opp)

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
        elif len(title_only_matched) > 1:
            return CorrelationEvidence(
                signal_id=signal.signal_id, opportunity_id=None, outbound_action_id=None,
                status=CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE,
                matching_criteria=tuple([f"opp_id:{o.id}" for o in title_only_matched]),
                confidence=0.0, is_authoritative=False,
                reason=f"Ambiguous: {len(title_only_matched)} distinct opportunities share identical/near-identical title without explicit org/reference",
            )

        # 4. Unlinked / Review Required
        return CorrelationEvidence(
            signal_id=signal.signal_id, opportunity_id=None, outbound_action_id=None,
            status=CorrelationStatus.UNLINKED, matching_criteria=(), confidence=0.0, is_authoritative=False,
            reason="No deterministic reference or unique multi-field match found",
        )
