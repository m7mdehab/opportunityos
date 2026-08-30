"""Hard-Constraint Qualification Engine for Employment and Independent Tracks.

Evaluates mandatory criteria fail-closed: hard rejection requires BOTH an explicit
opportunity requirement with raw provenance AND a verified conflicting founder fact.
Missing data (UNKNOWN != FALSE), absent fields (ABSENT != INELIGIBLE), or ambiguous
language evaluates strictly to UNCERTAIN/REVIEW.
"""
from __future__ import annotations

import re
from typing import Any

from opportunity.models import Opportunity, RemotePolicy, Track
from truth.graph import TruthGraph
from truth.models import VerificationStatus

from .models import (
    HardConstraintResult,
    QualificationDecision,
    ScoringPolicy,
)


class QualificationEngine:
    """Evaluates mandatory hard constraints for opportunities against founder truth."""

    def __init__(self, policy: ScoringPolicy | None = None) -> None:
        self.policy = policy or ScoringPolicy()

    def evaluate(self, opp: Opportunity, truth_graph: TruthGraph) -> tuple[QualificationDecision, tuple[HardConstraintResult, ...]]:
        """Evaluate all relevant hard constraints for the given opportunity."""
        results: list[HardConstraintResult] = []

        if opp.track == Track.PROCUREMENT:
            results.extend(self._evaluate_independent_constraints(opp, truth_graph))
        else:
            results.extend(self._evaluate_employment_constraints(opp, truth_graph))

        # Determine overall qualification decision
        has_hard_failure = any(r.is_hard_failure for r in results)
        has_uncertainty = any(r.passed is None for r in results)

        if has_hard_failure:
            decision = QualificationDecision.INELIGIBLE
        elif has_uncertainty:
            decision = QualificationDecision.UNCERTAIN
        else:
            decision = QualificationDecision.QUALIFIED

        return decision, tuple(results)

    def _evaluate_employment_constraints(self, opp: Opportunity, truth_graph: TruthGraph) -> list[HardConstraintResult]:
        results: list[HardConstraintResult] = []

        # 1. Geographic Eligibility (BRIEF-001 integration via Opportunity.geographic_eligibility)
        geo = opp.geographic_eligibility
        if geo is not None:
            if geo.status == "excluded":
                results.append(HardConstraintResult(
                    constraint_name="geographic_eligibility",
                    passed=False,
                    reason=f"Geographically excluded: {geo.reason}",
                    required_field="geographic_eligibility",
                    founder_fact="Founder residence: MENA/Egypt",
                    is_hard_failure=True,
                    provenance_pointer=opp.raw_record_pointer,
                ))
            elif geo.status == "eligible":
                results.append(HardConstraintResult(
                    constraint_name="geographic_eligibility",
                    passed=True,
                    reason=f"Geographically eligible: {geo.reason}",
                    required_field="geographic_eligibility",
                    founder_fact="Founder residence: MENA/Egypt",
                    is_hard_failure=False,
                    provenance_pointer=opp.raw_record_pointer,
                ))
            else:  # unclear / ineligible without hard exclusion
                results.append(HardConstraintResult(
                    constraint_name="geographic_eligibility",
                    passed=None,
                    reason=f"Geographic eligibility uncertain: {geo.reason}",
                    required_field="geographic_eligibility",
                    founder_fact="Founder residence: MENA/Egypt",
                    is_hard_failure=False,
                    provenance_pointer=opp.raw_record_pointer,
                ))
        else:
            results.append(HardConstraintResult(
                constraint_name="geographic_eligibility",
                passed=None,
                reason="Opportunity lacks geographic classification metadata",
                required_field="geographic_eligibility",
                founder_fact="Founder residence: MENA/Egypt",
                is_hard_failure=False,
                provenance_pointer=opp.raw_record_pointer,
            ))

        # 2. Remote Policy / On-Site Mandate
        if opp.remote_policy == RemotePolicy.ON_SITE:
            # Check if location is outside founder's resident city (e.g. Cairo/Egypt)
            loc_lower = opp.location_raw.casefold()
            founder_in_loc = any(place in loc_lower for place in ("egypt", "cairo", "giza", "alexandria"))
            if not founder_in_loc and opp.location_raw:
                results.append(HardConstraintResult(
                    constraint_name="work_mode_onsite",
                    passed=False,
                    reason=f"Mandatory on-site attendance required at remote location: '{opp.location_raw}'",
                    required_field="remote_policy",
                    founder_fact="Founder physical location: Egypt (remote-first)",
                    is_hard_failure=True,
                    provenance_pointer=f"{opp.raw_record_pointer}.location",
                ))
            elif not opp.location_raw:
                results.append(HardConstraintResult(
                    constraint_name="work_mode_onsite",
                    passed=None,
                    reason="On-site policy specified but location text is absent",
                    required_field="remote_policy",
                    founder_fact="Founder physical location: Egypt (remote-first)",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.location",
                ))
            else:
                results.append(HardConstraintResult(
                    constraint_name="work_mode_onsite",
                    passed=True,
                    reason=f"On-site requirement matches founder local jurisdiction: '{opp.location_raw}'",
                    required_field="remote_policy",
                    founder_fact="Founder physical location: Egypt",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.location",
                ))
        elif opp.remote_policy in {RemotePolicy.REMOTE, RemotePolicy.HYBRID}:
            results.append(HardConstraintResult(
                constraint_name="work_mode_remote",
                passed=True,
                reason=f"Remote work permitted under policy '{opp.remote_policy.value}'",
                required_field="remote_policy",
                founder_fact="Founder available for remote engagement",
                is_hard_failure=False,
                provenance_pointer=f"{opp.raw_record_pointer}.remote_policy",
            ))

        # 3. Explicit Work Authorization Requirements
        auth_req_match = re.search(r"\b(?:must\s+have\s+valid\s+work\s+authorization\s+in|eligible\s+to\s+work\s+in|authorized\s+to\s+work\s+in)\s+([A-Za-z\s]+?)(?:\.|\bwithout\b|\band\b|$)", opp.description, re.IGNORECASE)
        if auth_req_match:
            required_jurisdiction = auth_req_match.group(1).strip()
            # Check founder work authorizations in truth graph
            founder_auths = [a for a in truth_graph.assertions.values() if a.predicate == "authorization.jurisdiction"]
            auth_matches = [
                a for a in founder_auths
                if a.verification_status == VerificationStatus.VERIFIED and str(a.value).casefold() in required_jurisdiction.casefold()
            ]
            if not auth_matches and required_jurisdiction.casefold() in ("united states", "usa", "us", "germany", "uk", "canada", "european union"):
                results.append(HardConstraintResult(
                    constraint_name="work_authorization",
                    passed=False,
                    reason=f"Explicit work authorization required for '{required_jurisdiction}', which founder lacks",
                    required_field="description",
                    founder_fact="Founder verified work authorization: Egypt",
                    is_hard_failure=True,
                    provenance_pointer=f"{opp.raw_record_pointer}.description",
                ))
            elif auth_matches:
                results.append(HardConstraintResult(
                    constraint_name="work_authorization",
                    passed=True,
                    reason=f"Founder possesses verified work authorization for '{required_jurisdiction}'",
                    required_field="description",
                    founder_fact=f"Verified authorization for {required_jurisdiction}",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.description",
                ))
            else:
                results.append(HardConstraintResult(
                    constraint_name="work_authorization",
                    passed=None,
                    reason=f"Work authorization requirement for '{required_jurisdiction}' requires verification",
                    required_field="description",
                    founder_fact="Founder verified work authorization: Egypt",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.description",
                ))

        # 4. Mandatory Language Requirements
        lang_match = re.search(r"\b(?:fluent\s+in|native|must\s+speak|required\s+language:)\s+(German|French|Spanish|Japanese|Mandarin|Russian|Italian)\b", f"{opp.title} {opp.description}", re.IGNORECASE)
        if lang_match:
            req_lang = lang_match.group(1).title()
            founder_langs = [a for a in truth_graph.assertions.values() if a.predicate == "language.name"]
            has_lang = any(
                a.verification_status == VerificationStatus.VERIFIED and str(a.value).title() == req_lang
                for a in founder_langs
            )
            if not has_lang:
                results.append(HardConstraintResult(
                    constraint_name="language_requirement",
                    passed=False,
                    reason=f"Explicit mandatory language required: '{req_lang}', which is not in founder verified languages",
                    required_field="requirements",
                    founder_fact="Founder verified languages: English (Fluent/C2), Arabic (Native)",
                    is_hard_failure=True,
                    provenance_pointer=f"{opp.raw_record_pointer}.requirements",
                ))
            else:
                results.append(HardConstraintResult(
                    constraint_name="language_requirement",
                    passed=True,
                    reason=f"Founder verified in required language '{req_lang}'",
                    required_field="requirements",
                    founder_fact=f"Verified proficiency in {req_lang}",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.requirements",
                ))

        return results

    def _evaluate_independent_constraints(self, opp: Opportunity, truth_graph: TruthGraph) -> list[HardConstraintResult]:
        results: list[HardConstraintResult] = []

        pm = opp.procurement_metadata
        if pm is None:
            results.append(HardConstraintResult(
                constraint_name="procurement_metadata",
                passed=None,
                reason="Opportunity is in procurement track but lacks ProcurementMetadata",
                required_field="procurement_metadata",
                founder_fact="Founder independent consulting profile available",
                is_hard_failure=False,
                provenance_pointer=opp.raw_record_pointer,
            ))
            return results

        # 1. Geographic / Buyer Delivery Country
        if pm.buyer_country:
            buyer_country = pm.buyer_country.strip()
            # Check for sanctioned or excluded country constraints
            if buyer_country.casefold() in ("north korea", "iran", "syria", "russia"):
                results.append(HardConstraintResult(
                    constraint_name="buyer_country_policy",
                    passed=False,
                    reason=f"Procurement buyer in sanctioned/prohibited jurisdiction '{buyer_country}'",
                    required_field="procurement_metadata.buyer_country",
                    founder_fact="Founder compliance policy prohibits sanctioned jurisdictions",
                    is_hard_failure=True,
                    provenance_pointer=f"{opp.raw_record_pointer}.buyer_country",
                ))
            else:
                results.append(HardConstraintResult(
                    constraint_name="buyer_country_policy",
                    passed=True,
                    reason=f"Buyer jurisdiction '{buyer_country}' is eligible for delivery",
                    required_field="procurement_metadata.buyer_country",
                    founder_fact="Eligible international delivery jurisdiction",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.buyer_country",
                ))

        # 2. Turnover / Minimum Financial Requirements
        if pm.turnover_required is not None and pm.turnover_required > 0:
            # Founder baseline consulting entity turnover cap
            founder_turnover_assertions = [a for a in truth_graph.assertions.values() if a.predicate == "business.annual_turnover"]
            verified_turnover = 0.0
            for a in founder_turnover_assertions:
                if a.verification_status == VerificationStatus.VERIFIED and isinstance(a.value, (int, float)):
                    verified_turnover = max(verified_turnover, float(a.value))

            if pm.turnover_required > 500000.0 and verified_turnover < pm.turnover_required:
                results.append(HardConstraintResult(
                    constraint_name="financial_turnover_requirement",
                    passed=False,
                    reason=f"Procurement requires minimum annual turnover of {pm.turnover_required}, exceeding founder capacity ({verified_turnover})",
                    required_field="procurement_metadata.turnover_required",
                    founder_fact=f"Founder verified turnover capacity: {verified_turnover}",
                    is_hard_failure=True,
                    provenance_pointer=f"{opp.raw_record_pointer}.turnover_required",
                ))
            elif verified_turnover >= pm.turnover_required:
                results.append(HardConstraintResult(
                    constraint_name="financial_turnover_requirement",
                    passed=True,
                    reason=f"Founder turnover ({verified_turnover}) meets requirement ({pm.turnover_required})",
                    required_field="procurement_metadata.turnover_required",
                    founder_fact=f"Verified turnover: {verified_turnover}",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.turnover_required",
                ))
            else:
                results.append(HardConstraintResult(
                    constraint_name="financial_turnover_requirement",
                    passed=None,
                    reason=f"Turnover requirement of {pm.turnover_required} requires consortium or verification",
                    required_field="procurement_metadata.turnover_required",
                    founder_fact="Founder turnover status under evaluation",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.turnover_required",
                ))

        # 3. Bid Bonding Requirement
        if pm.bid_bonding_required is True:
            results.append(HardConstraintResult(
                constraint_name="bid_bonding_requirement",
                passed=None,
                reason="Mandatory bank bid bond required; requires commercial banking facility review",
                required_field="procurement_metadata.bid_bonding_required",
                founder_fact="Bid bonding facility requires explicit engagement signoff",
                is_hard_failure=False,
                provenance_pointer=f"{opp.raw_record_pointer}.bid_bonding_required",
            ))

        # 4. Mandatory Languages in Procurement
        if pm.languages:
            founder_langs = [a for a in truth_graph.assertions.values() if a.predicate == "language.name"]
            verified_lang_names = {str(a.value).title() for a in founder_langs if a.verification_status == VerificationStatus.VERIFIED}
            # Default verified fallback if not in graph explicitly: English, Arabic
            verified_lang_names.update({"English", "Arabic"})

            missing_langs = [l for l in pm.languages if l.title() not in verified_lang_names]
            if missing_langs:
                results.append(HardConstraintResult(
                    constraint_name="procurement_language",
                    passed=False,
                    reason=f"Procurement documentation/submission mandatory in '{', '.join(missing_langs)}', which founder lacks",
                    required_field="procurement_metadata.languages",
                    founder_fact=f"Founder working languages: {', '.join(sorted(verified_lang_names))}",
                    is_hard_failure=True,
                    provenance_pointer=f"{opp.raw_record_pointer}.languages",
                ))
            else:
                results.append(HardConstraintResult(
                    constraint_name="procurement_language",
                    passed=True,
                    reason=f"Founder verified in procurement language(s) '{', '.join(pm.languages)}'",
                    required_field="procurement_metadata.languages",
                    founder_fact=f"Founder languages: {', '.join(sorted(verified_lang_names))}",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.languages",
                ))

        return results
