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
from truth.models import Modality, Polarity, VerificationStatus

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
                    founder_fact=f"Policy exclusion: {geo.reason}",
                    is_hard_failure=True,
                    provenance_pointer=opp.raw_record_pointer,
                ))
            elif geo.status == "eligible":
                results.append(HardConstraintResult(
                    constraint_name="geographic_eligibility",
                    passed=True,
                    reason=f"Geographically eligible: {geo.reason}",
                    required_field="geographic_eligibility",
                    founder_fact=f"Eligible status: {geo.reason}",
                    is_hard_failure=False,
                    provenance_pointer=opp.raw_record_pointer,
                ))
            else:  # unclear / ineligible without hard exclusion
                results.append(HardConstraintResult(
                    constraint_name="geographic_eligibility",
                    passed=None,
                    reason=f"Geographic eligibility uncertain: {geo.reason}",
                    required_field="geographic_eligibility",
                    founder_fact="Geographic eligibility requires applicant confirmation",
                    is_hard_failure=False,
                    provenance_pointer=opp.raw_record_pointer,
                ))
        else:
            results.append(HardConstraintResult(
                constraint_name="geographic_eligibility",
                passed=None,
                reason="Opportunity lacks geographic classification metadata",
                required_field="geographic_eligibility",
                founder_fact="Geographic metadata unasserted",
                is_hard_failure=False,
                provenance_pointer=opp.raw_record_pointer,
            ))

        # 2. Remote Policy / On-Site Mandate
        if opp.remote_policy == RemotePolicy.ON_SITE:
            founder_locs = [
                str(a.value).casefold()
                for a in truth_graph.assertions.values()
                if a.predicate in ("residence.country", "residence.city", "location.city", "location.country", "residence.jurisdiction")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            if not founder_locs:
                results.append(HardConstraintResult(
                    constraint_name="work_mode_onsite",
                    passed=None,
                    reason=f"Mandatory on-site attendance required at '{opp.location_raw or 'unspecified location'}'; founder physical location not asserted in truth graph",
                    required_field="remote_policy",
                    founder_fact="Founder physical location unasserted in truth graph",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.location",
                ))
            elif not opp.location_raw:
                results.append(HardConstraintResult(
                    constraint_name="work_mode_onsite",
                    passed=None,
                    reason="On-site policy specified but location text is absent",
                    required_field="remote_policy",
                    founder_fact=f"Founder verified location: {', '.join(founder_locs)}",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.location",
                ))
            else:
                loc_lower = opp.location_raw.casefold()
                founder_in_loc = any(fl in loc_lower or loc_lower in fl for fl in founder_locs)
                if founder_in_loc:
                    results.append(HardConstraintResult(
                        constraint_name="work_mode_onsite",
                        passed=True,
                        reason=f"On-site requirement matches founder verified location: '{opp.location_raw}'",
                        required_field="remote_policy",
                        founder_fact=f"Founder verified location: {', '.join(founder_locs)}",
                        is_hard_failure=False,
                        provenance_pointer=f"{opp.raw_record_pointer}.location",
                    ))
                else:
                    results.append(HardConstraintResult(
                        constraint_name="work_mode_onsite",
                        passed=False,
                        reason=f"Mandatory on-site attendance required at '{opp.location_raw}', conflicting with verified founder location",
                        required_field="remote_policy",
                        founder_fact=f"Founder verified location: {', '.join(founder_locs)}",
                        is_hard_failure=True,
                        provenance_pointer=f"{opp.raw_record_pointer}.location",
                    ))
        elif opp.remote_policy in {RemotePolicy.REMOTE, RemotePolicy.HYBRID}:
            results.append(HardConstraintResult(
                constraint_name="work_mode_remote",
                passed=True,
                reason=f"Remote work permitted under policy '{opp.remote_policy.value}'",
                required_field="remote_policy",
                founder_fact="Opportunity permits remote/hybrid engagement",
                is_hard_failure=False,
                provenance_pointer=f"{opp.raw_record_pointer}.remote_policy",
            ))

        # 3. Explicit Work Authorization Requirements
        auth_req_match = re.search(
            r"\b(?:must\s+have\s+valid\s+work\s+authorization\s+in|eligible\s+to\s+work\s+in|authorized\s+to\s+work\s+in)\s+([A-Za-z\s]+?)(?:\.|\bwithout\b|\band\b|$)",
            opp.description,
            re.IGNORECASE,
        )
        if auth_req_match:
            required_jurisdiction = auth_req_match.group(1).strip()
            founder_auths = [
                a for a in truth_graph.assertions.values()
                if a.predicate in ("authorization.jurisdiction", "work_authorization")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            auth_matches = [
                a for a in founder_auths
                if (str(a.value).casefold() in required_jurisdiction.casefold() or required_jurisdiction.casefold() in str(a.value).casefold())
                and a.polarity != Polarity.NEGATIVE and str(a.value).casefold() != "none"
            ]
            auth_negations = [
                a for a in founder_auths
                if (str(a.value).casefold() in required_jurisdiction.casefold() or required_jurisdiction.casefold() in str(a.value).casefold())
                and (a.polarity == Polarity.NEGATIVE or str(a.value).casefold() in ("none", "ineligible", "unauthorized"))
            ]
            if auth_matches and not auth_negations:
                results.append(HardConstraintResult(
                    constraint_name="work_authorization",
                    passed=True,
                    reason=f"Founder possesses verified work authorization for '{required_jurisdiction}'",
                    required_field="description",
                    founder_fact=f"Verified authorization for {required_jurisdiction}",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.description",
                ))
            elif auth_negations:
                results.append(HardConstraintResult(
                    constraint_name="work_authorization",
                    passed=False,
                    reason=f"Explicit work authorization required for '{required_jurisdiction}', which founder verified negative status for",
                    required_field="description",
                    founder_fact=f"Verified lack of work authorization for {required_jurisdiction}",
                    is_hard_failure=True,
                    provenance_pointer=f"{opp.raw_record_pointer}.description",
                ))
            else:
                results.append(HardConstraintResult(
                    constraint_name="work_authorization",
                    passed=None,
                    reason=f"Work authorization required for '{required_jurisdiction}'; founder authorization status for '{required_jurisdiction}' unasserted in truth graph",
                    required_field="description",
                    founder_fact="Founder work authorization unasserted in truth graph",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.description",
                ))

        # 4. Mandatory Language Requirements
        lang_match = re.search(
            r"\b(?:fluent\s+in|native|must\s+speak|required\s+language:)\s+(German|French|Spanish|Japanese|Mandarin|Russian|Italian)\b",
            f"{opp.title} {opp.description}",
            re.IGNORECASE,
        )
        if lang_match:
            req_lang = lang_match.group(1).title()
            founder_langs = [
                a for a in truth_graph.assertions.values()
                if a.predicate in ("language.name", "language.proficiency")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            matching_langs = [
                a for a in founder_langs
                if str(a.value).title() == req_lang
                and a.polarity != Polarity.NEGATIVE
                and str(a.value).casefold() != "none"
            ]
            negated_langs = [
                a for a in founder_langs
                if (str(a.value).title() == req_lang and a.polarity == Polarity.NEGATIVE)
                or str(a.value).casefold() in (f"no {req_lang.casefold()}", f"not proficient in {req_lang.casefold()}")
            ]
            if matching_langs:
                results.append(HardConstraintResult(
                    constraint_name="language_requirement",
                    passed=True,
                    reason=f"Founder verified in required language '{req_lang}'",
                    required_field="requirements",
                    founder_fact=f"Verified proficiency in {req_lang}",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.requirements",
                ))
            elif negated_langs:
                results.append(HardConstraintResult(
                    constraint_name="language_requirement",
                    passed=False,
                    reason=f"Mandatory language required: '{req_lang}', which founder explicitly lacks under verified truth graph",
                    required_field="requirements",
                    founder_fact=f"Verified lack of proficiency in {req_lang}",
                    is_hard_failure=True,
                    provenance_pointer=f"{opp.raw_record_pointer}.requirements",
                ))
            else:
                results.append(HardConstraintResult(
                    constraint_name="language_requirement",
                    passed=None,
                    reason=f"Mandatory language required: '{req_lang}'; founder proficiency unasserted in truth graph",
                    required_field="requirements",
                    founder_fact=f"Language proficiency for '{req_lang}' unasserted in truth graph",
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
                founder_fact="Procurement metadata unasserted",
                is_hard_failure=False,
                provenance_pointer=opp.raw_record_pointer,
            ))
            return results

        # 1. Geographic / Buyer Delivery Country
        if pm.buyer_country:
            buyer_country = pm.buyer_country.strip()
            prohibited = getattr(self.policy, "prohibited_jurisdictions", ())
            approved = getattr(self.policy, "approved_delivery_jurisdictions", ())
            if prohibited and any(p.casefold() in buyer_country.casefold() for p in prohibited):
                results.append(HardConstraintResult(
                    constraint_name="buyer_country_policy",
                    passed=False,
                    reason=f"Procurement buyer in prohibited jurisdiction '{buyer_country}' under founder policy",
                    required_field="procurement_metadata.buyer_country",
                    founder_fact=f"Policy prohibited jurisdictions: {', '.join(prohibited)}",
                    is_hard_failure=True,
                    provenance_pointer=f"{opp.raw_record_pointer}.buyer_country",
                ))
            elif approved and any(a.casefold() in buyer_country.casefold() for a in approved):
                results.append(HardConstraintResult(
                    constraint_name="buyer_country_policy",
                    passed=True,
                    reason=f"Buyer jurisdiction '{buyer_country}' is in approved delivery list",
                    required_field="procurement_metadata.buyer_country",
                    founder_fact=f"Approved delivery jurisdiction: {buyer_country}",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.buyer_country",
                ))
            else:
                results.append(HardConstraintResult(
                    constraint_name="buyer_country_policy",
                    passed=None,
                    reason=f"Procurement buyer in jurisdiction '{buyer_country}'; delivery compliance requires review",
                    required_field="procurement_metadata.buyer_country",
                    founder_fact="Buyer jurisdiction compliance unconfirmed",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.buyer_country",
                ))

        # 2. Turnover / Minimum Financial Requirements
        if pm.turnover_required is not None and pm.turnover_required > 0:
            founder_turnover_assertions = [
                a for a in truth_graph.assertions.values()
                if a.predicate in ("business.annual_turnover", "capacity.annual_turnover")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            if not founder_turnover_assertions:
                results.append(HardConstraintResult(
                    constraint_name="financial_turnover_requirement",
                    passed=None,
                    reason=f"Procurement requires minimum annual turnover of {pm.turnover_required}; founder annual turnover unasserted in truth graph",
                    required_field="procurement_metadata.turnover_required",
                    founder_fact="Founder annual turnover unasserted in truth graph",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.turnover_required",
                ))
            else:
                verified_turnover = max(
                    (float(a.value) for a in founder_turnover_assertions if isinstance(a.value, (int, float))),
                    default=0.0,
                )
                if verified_turnover >= pm.turnover_required:
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
                        passed=False,
                        reason=f"Procurement requires minimum annual turnover of {pm.turnover_required}, exceeding founder verified capacity ({verified_turnover})",
                        required_field="procurement_metadata.turnover_required",
                        founder_fact=f"Founder verified turnover capacity: {verified_turnover}",
                        is_hard_failure=True,
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
            founder_langs = [
                a for a in truth_graph.assertions.values()
                if a.predicate in ("language.name", "language.proficiency")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            verified_lang_names = {
                str(a.value).title()
                for a in founder_langs
                if a.polarity != Polarity.NEGATIVE and str(a.value).casefold() != "none"
            }
            if not verified_lang_names:
                results.append(HardConstraintResult(
                    constraint_name="procurement_language",
                    passed=None,
                    reason=f"Procurement documentation requires language(s) '{', '.join(pm.languages)}'; founder languages unasserted in truth graph",
                    required_field="procurement_metadata.languages",
                    founder_fact="Founder languages unasserted in truth graph",
                    is_hard_failure=False,
                    provenance_pointer=f"{opp.raw_record_pointer}.languages",
                ))
            else:
                missing_langs = [l for l in pm.languages if l.title() not in verified_lang_names]
                if missing_langs:
                    results.append(HardConstraintResult(
                        constraint_name="procurement_language",
                        passed=None,
                        reason=f"Procurement documentation requires language(s) '{', '.join(missing_langs)}'; founder proficiency unasserted in truth graph",
                        required_field="procurement_metadata.languages",
                        founder_fact=f"Founder verified languages: {', '.join(sorted(verified_lang_names))}",
                        is_hard_failure=False,
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
