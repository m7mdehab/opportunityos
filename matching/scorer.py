"""Explainable Dual-Track Matching & Ranking Scorer for OpportunityOS.

Implements multidimensional scoring separated into explicit dimensions for employment
versus independent consulting tracks. Emits comprehensive MatchEvaluation objects with
score breakdowns, supporting strengths, gaps, unknowns, and explicit links to TruthGraph
assertions without keyword dominance or false certainty.
"""
from __future__ import annotations

import math
from typing import Any

from opportunity.models import Opportunity, SeniorityLevel, Track
from truth.graph import TruthGraph
from truth.models import VerificationStatus

from .models import (
    HardConstraintResult,
    MatchDimensionScore,
    MatchEvaluation,
    QualificationDecision,
    ScoringPolicy,
)
from .qualification import QualificationEngine


class OpportunityScorer:
    """Evaluates multidimensional fit and ranking for opportunities against founder truth."""

    def __init__(
        self,
        policy: ScoringPolicy | None = None,
        qualification_engine: QualificationEngine | None = None,
    ) -> None:
        self.policy = policy or ScoringPolicy()
        self.qual_engine = qualification_engine or QualificationEngine(policy=self.policy)

    def evaluate(self, opp: Opportunity, truth_graph: TruthGraph, evaluated_at: str = "2026-08-30") -> MatchEvaluation:
        """Run complete qualification and explainable multidimensional scoring."""
        qual_decision, hard_results = self.qual_engine.evaluate(opp, truth_graph)

        if opp.track == Track.PROCUREMENT:
            dim_scores, uncertainty = self._score_independent(opp, truth_graph)
        else:
            dim_scores, uncertainty = self._score_employment(opp, truth_graph)

        # Calculate weighted overall score
        total_weighted = sum(ds.weighted_score for ds in dim_scores)
        overall_score = max(0.0, min(100.0, (total_weighted - (uncertainty * self.policy.uncertainty_penalty_weight)) * 100.0))

        # If hard failure occurred and auto-rejection is enabled, cap score
        if qual_decision == QualificationDecision.INELIGIBLE:
            if self.policy.auto_rejection_enabled:
                overall_score = 0.0
            else:
                overall_score = min(overall_score, 40.0)

        # Aggregate strengths, gaps, unknowns
        strengths: list[str] = []
        gaps: list[str] = []
        unknowns: list[str] = []
        for ds in dim_scores:
            strengths.extend(ds.strengths)
            gaps.extend(ds.gaps)
            unknowns.extend(ds.unknowns)

        breakdown = tuple((ds.dimension_name, round(ds.weighted_score * 100.0, 2)) for ds in dim_scores)

        # Construct explainability summary
        explanation_parts = [
            f"Qualification: {qual_decision.value.upper()}.",
            f"Overall Fit Score: {round(overall_score, 1)}/100.",
            f"Strengths: {len(strengths)} identified.",
            f"Gaps: {len(gaps)} identified.",
            f"Unknowns: {len(unknowns)} identified.",
        ]
        if hard_results:
            failed_hard = [hr for hr in hard_results if hr.passed is False]
            if failed_hard:
                explanation_parts.append(f"Hard constraints failed: {', '.join(hr.constraint_name for hr in failed_hard)}.")

        return MatchEvaluation(
            opportunity_id=opp.id,
            track=opp.track,
            qualification_decision=qual_decision,
            overall_fit_score=round(overall_score, 2),
            hard_constraints=hard_results,
            dimension_scores=tuple(dim_scores),
            strengths=tuple(strengths),
            gaps=tuple(gaps),
            unknowns=tuple(unknowns),
            uncertainty_penalty=round(uncertainty, 3),
            explanation=" ".join(explanation_parts),
            policy_version=self.policy.version,
            evaluated_at=evaluated_at,
            score_breakdown=breakdown,
        )

    def _score_employment(self, opp: Opportunity, truth_graph: TruthGraph) -> tuple[list[MatchDimensionScore], float]:
        scores: list[MatchDimensionScore] = []
        uncertainty_acc = 0.0
        weights = self.policy.employment_weights

        # 1. Core Skill Fit
        founder_skills = {
            str(a.value).casefold(): a
            for a in truth_graph.assertions.values()
            if a.predicate == "skill.name" and a.verification_status == VerificationStatus.VERIFIED
        }
        opp_skills = [s.casefold() for s in opp.skills]
        if not founder_skills:
            if opp_skills:
                skill_ratio = 0.0
                skill_strengths = ()
                skill_gaps = tuple(f"Unverified skill requirement: {s.title()}" for s in opp_skills)
                skill_unknowns = ("Founder truth graph contains 0 verified skills",)
                skill_ev_refs = ()
                uncertainty_acc += 0.4
            else:
                skill_ratio = 0.5
                skill_strengths = ()
                skill_gaps = ()
                skill_unknowns = ("No explicit skills in opportunity or founder truth graph",)
                skill_ev_refs = ()
                uncertainty_acc += 0.3
        else:
            if opp_skills:
                matched_skills = [s for s in opp_skills if s in founder_skills]
                missing_skills = [s for s in opp_skills if s not in founder_skills]
                skill_ratio = len(matched_skills) / len(opp_skills)
                skill_strengths = tuple(f"Verified core skill: {s.title()}" for s in matched_skills)
                skill_gaps = tuple(f"Unverified skill requirement: {s.title()}" for s in missing_skills)
                skill_unknowns = ()
                skill_ev_refs = tuple(founder_skills[s].id for s in matched_skills)
            else:
                skill_ratio = 0.5  # Neutral when skills unstated in job payload
                skill_strengths = ()
                skill_gaps = ()
                skill_unknowns = ("Opportunity payload lacks explicit skills list",)
                skill_ev_refs = ()
                uncertainty_acc += 0.2

        w_skill = weights.get("skills", 0.35)
        scores.append(MatchDimensionScore(
            dimension_name="core_skills",
            raw_score=skill_ratio,
            weight=w_skill,
            weighted_score=skill_ratio * w_skill,
            explanation=f"Matched {len(skill_strengths)}/{len(opp_skills)} required skills." if opp_skills else "No explicit skills specified in posting.",
            strengths=skill_strengths,
            gaps=skill_gaps,
            unknowns=skill_unknowns,
            evidence_refs=skill_ev_refs,
            opportunity_field_refs=("skills",) if opp_skills else (),
        ))

        # 2. Experience & Seniority Fit
        emp_title_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == "employment.title" and a.verification_status == VerificationStatus.VERIFIED
        ]
        opp_level = opp.seniority
        if not emp_title_assertions:
            seniority_score = 0.5
            seniority_strengths = ()
            seniority_gaps = ()
            seniority_unknowns = ("No verified employment history in founder truth graph",)
            seniority_ev_refs = ()
            uncertainty_acc += 0.3
        else:
            is_senior = any(
                any(k in str(a.value).casefold() for k in ("senior", "sr", "lead", "principal", "staff", "architect", "chief", "director", "head"))
                for a in emp_title_assertions
            )
            if is_senior:
                if opp_level in {SeniorityLevel.SENIOR, SeniorityLevel.LEAD, SeniorityLevel.PRINCIPAL, SeniorityLevel.EXECUTIVE}:
                    seniority_score = 1.0
                    seniority_strengths = (f"Seniority alignment: {opp_level.value.title()} matches verified founder experience",)
                    seniority_gaps = ()
                    seniority_unknowns = ()
                elif opp_level == SeniorityLevel.MID:
                    seniority_score = 0.8
                    seniority_strengths = ("Experienced background covers mid-level scope",)
                    seniority_gaps = ()
                    seniority_unknowns = ()
                elif opp_level == SeniorityLevel.ENTRY:
                    seniority_score = 0.4
                    seniority_strengths = ()
                    seniority_gaps = ("Role is entry level; founder has senior experience",)
                    seniority_unknowns = ()
                else:
                    seniority_score = 0.7
                    seniority_strengths = ()
                    seniority_gaps = ()
                    seniority_unknowns = ("Opportunity seniority unspecified",)
                    uncertainty_acc += 0.1
            else:
                if opp_level == SeniorityLevel.ENTRY:
                    seniority_score = 0.9
                    seniority_strengths = ("Entry level alignment",)
                    seniority_gaps = ()
                    seniority_unknowns = ()
                elif opp_level == SeniorityLevel.MID:
                    seniority_score = 0.8
                    seniority_strengths = ("Mid level alignment",)
                    seniority_gaps = ()
                    seniority_unknowns = ()
                else:
                    seniority_score = 0.5
                    seniority_strengths = ()
                    seniority_gaps = (f"Role requires {opp_level.value.title()}; founder verified title is mid/entry",)
                    seniority_unknowns = ()
            seniority_ev_refs = tuple(a.id for a in emp_title_assertions)

        w_exp = weights.get("experience", 0.20)
        scores.append(MatchDimensionScore(
            dimension_name="seniority_and_experience",
            raw_score=seniority_score,
            weight=w_exp,
            weighted_score=seniority_score * w_exp,
            explanation=f"Seniority requirement evaluated as {opp_level.value.title()}.",
            strengths=seniority_strengths,
            gaps=seniority_gaps,
            unknowns=seniority_unknowns,
            evidence_refs=seniority_ev_refs,
            opportunity_field_refs=("seniority", "title"),
        ))

        # 3. Responsibility & Scope Fit
        founder_resp_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate in ("responsibility.item", "employment.role_description", "service.name", "experience.summary", "achievement.description")
            and a.verification_status == VerificationStatus.VERIFIED
        ]
        if not founder_resp_assertions:
            resp_score = 0.5
            resp_strengths = ()
            resp_gaps = ()
            resp_unknowns = ("No verified responsibility/experience records in founder truth graph",)
            resp_ev_refs = ()
            uncertainty_acc += 0.25
        else:
            opp_resps = list(opp.responsibilities)
            if not opp_resps and opp.description:
                opp_resps = [opp.description]
            matched_resps = [
                a for a in founder_resp_assertions
                if any(str(a.value).casefold() in r.casefold() or any(w in r.casefold() for w in str(a.value).casefold().split() if len(w) > 4) for r in opp_resps)
            ]
            if matched_resps:
                resp_score = min(1.0, 0.5 + (len(matched_resps) * 0.15))
                resp_strengths = tuple(f"Verified experience alignment: {str(a.value)[:60]}" for a in matched_resps[:3])
                resp_gaps = ()
                resp_unknowns = ()
                resp_ev_refs = tuple(a.id for a in matched_resps)
            else:
                resp_score = 0.5
                resp_strengths = ()
                resp_gaps = ()
                resp_unknowns = ("No specific keyword overlap with founder experience assertions",)
                resp_ev_refs = ()
                uncertainty_acc += 0.1

        w_resp = weights.get("responsibilities", 0.15)
        scores.append(MatchDimensionScore(
            dimension_name="responsibility_scope",
            raw_score=resp_score,
            weight=w_resp,
            weighted_score=resp_score * w_resp,
            explanation=f"Evaluated responsibility alignment against {len(founder_resp_assertions)} verified experience assertion(s).",
            strengths=resp_strengths,
            gaps=resp_gaps,
            unknowns=resp_unknowns,
            evidence_refs=resp_ev_refs,
            opportunity_field_refs=("responsibilities", "description"),
        ))

        # 4. Domain / Industry Fit
        founder_domain_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate in ("skill.name", "service.name", "employment.title", "achievement.description")
            and a.verification_status == VerificationStatus.VERIFIED
        ]
        if not founder_domain_assertions:
            domain_score = 0.5
            domain_strengths = ()
            domain_unknowns = ("No verified domain records in founder truth graph",)
            domain_ev_refs = ()
            uncertainty_acc += 0.2
        else:
            desc_lower = f"{opp.title} {opp.description}".casefold()
            matched_domain_assertions = [
                a for a in founder_domain_assertions
                if len(str(a.value).strip()) > 3 and str(a.value).casefold() in desc_lower
            ]
            if matched_domain_assertions:
                domain_score = min(1.0, 0.4 + (len(matched_domain_assertions) * 0.15))
                domain_strengths = tuple(f"Domain match on verified asset: {str(a.value)}" for a in matched_domain_assertions[:3])
                domain_unknowns = ()
                domain_ev_refs = tuple(a.id for a in matched_domain_assertions)
            else:
                domain_score = 0.4
                domain_strengths = ()
                domain_unknowns = ("Limited direct domain term overlap with founder truth graph",)
                domain_ev_refs = ()
                uncertainty_acc += 0.1

        w_dom = weights.get("domain", 0.10)
        scores.append(MatchDimensionScore(
            dimension_name="domain_fit",
            raw_score=domain_score,
            weight=w_dom,
            weighted_score=domain_score * w_dom,
            explanation=f"Domain overlap verified against {len(founder_domain_assertions)} founder truth assertions.",
            strengths=domain_strengths,
            gaps=(),
            unknowns=domain_unknowns,
            evidence_refs=domain_ev_refs,
            opportunity_field_refs=("description", "title"),
        ))

        # 5. Geography & Remote Policy Fit
        geo_status = opp.geographic_eligibility.status if opp.geographic_eligibility else "unclear"
        founder_res_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate in ("residence.country", "authorization.jurisdiction")
            and a.verification_status == VerificationStatus.VERIFIED
        ]
        if geo_status == "eligible" and founder_res_assertions:
            geo_score = 1.0
            geo_strengths = (f"Verified geographic eligibility for {str(founder_res_assertions[0].value)}",)
            geo_gaps = ()
            geo_unknowns = ()
            geo_refs = (founder_res_assertions[0].id,)
        elif geo_status == "eligible":
            geo_score = 0.8
            geo_strengths = ()
            geo_gaps = ()
            geo_unknowns = ("Founder jurisdiction unasserted in truth graph",)
            geo_refs = ()
            uncertainty_acc += 0.1
        elif geo_status == "excluded":
            geo_score = 0.0
            geo_strengths = ()
            geo_gaps = ("Geographically excluded for applicant jurisdiction",)
            geo_unknowns = ()
            geo_refs = ()
        else:
            geo_score = 0.5
            geo_strengths = ()
            geo_gaps = ()
            geo_unknowns = ("Geographic eligibility requires applicant confirmation",)
            geo_refs = ()
            uncertainty_acc += 0.2

        w_geo = weights.get("geography", 0.10)
        scores.append(MatchDimensionScore(
            dimension_name="geography_and_remote",
            raw_score=geo_score,
            weight=w_geo,
            weighted_score=geo_score * w_geo,
            explanation=f"Geographic eligibility status: {geo_status.upper()}.",
            strengths=geo_strengths,
            gaps=geo_gaps,
            unknowns=geo_unknowns,
            evidence_refs=geo_refs,
            opportunity_field_refs=("geographic_eligibility", "location_raw"),
        ))

        # 6. Compensation Fit
        comp = opp.compensation
        min_target = getattr(self.policy, "min_target_compensation", None)
        if min_target is None:
            comp_score = 0.5
            comp_strengths = ()
            comp_gaps = ()
            comp_unknowns = ("Founder target compensation unconfigured; market viability not evaluated",)
            uncertainty_acc += 0.1
        else:
            if comp is not None and comp.min_amount is not None:
                max_amt = comp.max_amount if comp.max_amount is not None else comp.min_amount
                if max_amt >= min_target:
                    comp_score = 0.90
                    comp_strengths = (f"Opportunity compensation ({comp.min_amount}-{comp.max_amount} {comp.currency or ''}) meets target ({min_target})",)
                    comp_gaps = ()
                    comp_unknowns = ()
                else:
                    comp_score = 0.30
                    comp_strengths = ()
                    comp_gaps = (f"Opportunity compensation ({max_amt}) below founder target ({min_target})",)
                    comp_unknowns = ()
            else:
                comp_score = 0.50
                comp_strengths = ()
                comp_gaps = ()
                comp_unknowns = ("Compensation unstated in opportunity posting",)
                uncertainty_acc += 0.1

        w_comp = weights.get("compensation", 0.05)
        scores.append(MatchDimensionScore(
            dimension_name="compensation_fit",
            raw_score=comp_score,
            weight=w_comp,
            weighted_score=comp_score * w_comp,
            explanation="Compensation evaluated against founder target policy." if min_target else "Compensation unconfigured on founder side.",
            strengths=comp_strengths,
            gaps=comp_gaps,
            unknowns=comp_unknowns,
            evidence_refs=(),
            opportunity_field_refs=("compensation",),
        ))

        # 7. Career Trajectory
        target_role_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate in ("career.target_role", "preference.track", "career.goal")
            and a.verification_status == VerificationStatus.VERIFIED
        ]
        if not target_role_assertions:
            traj_score = 0.50
            traj_strengths = ()
            traj_gaps = ()
            traj_unknowns = ("Founder career trajectory preferences unstated in truth graph",)
            traj_ev_refs = ()
            uncertainty_acc += 0.1
        else:
            matched_traj = [a for a in target_role_assertions if str(a.value).casefold() in opp.title.casefold()]
            if matched_traj:
                traj_score = 0.95
                traj_strengths = (f"Opportunity title matches target role: {str(matched_traj[0].value)}",)
                traj_gaps = ()
                traj_unknowns = ()
                traj_ev_refs = tuple(a.id for a in matched_traj)
            else:
                traj_score = 0.60
                traj_strengths = ()
                traj_gaps = ()
                traj_unknowns = ("Role does not explicitly match target preference",)
                traj_ev_refs = tuple(a.id for a in target_role_assertions)

        w_traj = weights.get("trajectory", 0.05)
        scores.append(MatchDimensionScore(
            dimension_name="career_trajectory",
            raw_score=traj_score,
            weight=w_traj,
            weighted_score=traj_score * w_traj,
            explanation="Career trajectory evaluated against verified preferences." if target_role_assertions else "Career preferences unstated.",
            strengths=traj_strengths,
            gaps=traj_gaps,
            unknowns=traj_unknowns,
            evidence_refs=traj_ev_refs,
            opportunity_field_refs=("title",),
        ))

        return scores, uncertainty_acc

    def _score_independent(self, opp: Opportunity, truth_graph: TruthGraph) -> tuple[list[MatchDimensionScore], float]:
        scores: list[MatchDimensionScore] = []
        uncertainty_acc = 0.0
        weights = self.policy.independent_weights
        pm = opp.procurement_metadata

        # 1. Services & Capability Fit
        founder_services = {
            str(a.value).casefold(): a
            for a in truth_graph.assertions.values()
            if a.predicate == "service.name" and a.verification_status == VerificationStatus.VERIFIED
        }
        if not founder_services:
            srv_score = 0.0
            srv_strengths = ()
            srv_gaps = ("No verified consulting service offerings in truth graph",)
            srv_unknowns = ("Founder service offerings unasserted",)
            srv_refs = ()
            uncertainty_acc += 0.4
        else:
            title_lower = f"{opp.title} {opp.description}".casefold()
            matched_services = [s for s in founder_services if s in title_lower]
            if matched_services:
                srv_score = 0.95
                srv_strengths = tuple(f"Direct verified capability match: {s.title()}" for s in matched_services)
                srv_gaps = ()
                srv_unknowns = ()
                srv_refs = tuple(founder_services[s].id for s in matched_services)
            else:
                srv_score = 0.30
                srv_strengths = ()
                srv_gaps = ("No direct match between RFP terms and verified service offerings",)
                srv_unknowns = ()
                srv_refs = ()
                uncertainty_acc += 0.15

        w_srv = weights.get("services", 0.35)
        scores.append(MatchDimensionScore(
            dimension_name="service_capabilities",
            raw_score=srv_score,
            weight=w_srv,
            weighted_score=srv_score * w_srv,
            explanation=f"Consulting scope evaluated against {len(founder_services)} verified service offering(s).",
            strengths=srv_strengths,
            gaps=srv_gaps,
            unknowns=srv_unknowns,
            evidence_refs=srv_refs,
            opportunity_field_refs=("title", "description", "procurement_metadata"),
        ))

        # 2. Scope & Requirement Complexity
        founder_caps = [
            a for a in truth_graph.assertions.values()
            if a.predicate in ("service.name", "business.capacity", "capacity.annual_turnover")
            and a.verification_status == VerificationStatus.VERIFIED
        ]
        if not founder_caps:
            scope_score = 0.50
            scope_strengths = ()
            scope_gaps = ()
            scope_unknowns = ("Founder consulting delivery capacity unasserted in truth graph",)
            scope_refs = ()
            uncertainty_acc += 0.30
        else:
            scope_score = 0.85
            scope_strengths = ("Terms of reference within single-practitioner / boutique consulting delivery capacity",)
            scope_gaps = ()
            scope_unknowns = ()
            scope_refs = tuple(a.id for a in founder_caps)

        w_scope = weights.get("scope", 0.20)
        scores.append(MatchDimensionScore(
            dimension_name="scope_complexity",
            raw_score=scope_score,
            weight=w_scope,
            weighted_score=scope_score * w_scope,
            explanation="RFP terms of reference evaluated against founder delivery capacity.",
            strengths=scope_strengths,
            gaps=scope_gaps,
            unknowns=scope_unknowns,
            evidence_refs=scope_refs,
            opportunity_field_refs=("description",),
        ))

        # 3. Portfolio & Case Study Evidence Sufficiency
        portfolio_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == "portfolio.item" and a.verification_status == VerificationStatus.VERIFIED
        ]
        if not portfolio_assertions:
            port_score = 0.0
            port_strengths = ()
            port_gaps = ("No verified portfolio/case studies in truth graph",)
            port_unknowns = ()
            port_refs = ()
            uncertainty_acc += 0.30
        else:
            port_score = 0.90
            port_strengths = (f"Verified portfolio and client case studies available in truth graph ({len(portfolio_assertions)} items)",)
            port_gaps = ()
            port_unknowns = ()
            port_refs = tuple(a.id for a in portfolio_assertions)

        w_port = weights.get("portfolio", 0.20)
        scores.append(MatchDimensionScore(
            dimension_name="portfolio_evidence",
            raw_score=port_score,
            weight=w_port,
            weighted_score=port_score * w_port,
            explanation="Verified case studies and client delivery records available for tender response." if portfolio_assertions else "No verified case studies.",
            strengths=port_strengths,
            gaps=port_gaps,
            unknowns=port_unknowns,
            evidence_refs=port_refs,
            opportunity_field_refs=(),
        ))

        # 4. Budget & Financial Fit
        w_bud = weights.get("budget", 0.10)
        if opp.compensation and opp.compensation.min_amount:
            bud_score = 0.80
            bud_strengths = (f"Procurement budget structured: {opp.compensation.min_amount}-{opp.compensation.max_amount or ''} {opp.compensation.currency or ''}",)
            bud_unknowns = ()
        else:
            bud_score = 0.50
            bud_strengths = ()
            bud_unknowns = ("Procurement budget unstated in notice metadata",)
            uncertainty_acc += 0.1

        scores.append(MatchDimensionScore(
            dimension_name="budget_fit",
            raw_score=bud_score,
            weight=w_bud,
            weighted_score=bud_score * w_bud,
            explanation="Procurement budget evaluated from notice data.",
            strengths=bud_strengths,
            gaps=(),
            unknowns=bud_unknowns,
            evidence_refs=(),
            opportunity_field_refs=("compensation", "procurement_metadata"),
        ))

        # 5. Delivery & Geographic Jurisdiction
        buyer_loc = pm.buyer_country if pm else ""
        if not buyer_loc:
            deliv_score = 0.50
            deliv_strengths = ()
            deliv_gaps = ()
            deliv_unknowns = ("Buyer country unspecified in notice metadata",)
            uncertainty_acc += 0.1
        else:
            prohibited = getattr(self.policy, "prohibited_jurisdictions", ("North Korea", "Iran", "Syria", "Russia"))
            approved = getattr(self.policy, "approved_delivery_jurisdictions", ())
            if any(p.casefold() in buyer_loc.casefold() for p in prohibited):
                deliv_score = 0.0
                deliv_strengths = ()
                deliv_gaps = (f"Buyer country '{buyer_loc}' is in prohibited jurisdictions policy",)
                deliv_unknowns = ()
            elif approved and any(a.casefold() in buyer_loc.casefold() for a in approved):
                deliv_score = 1.0
                deliv_strengths = (f"Buyer country '{buyer_loc}' is on approved delivery list",)
                deliv_gaps = ()
                deliv_unknowns = ()
            else:
                deliv_score = 0.60
                deliv_strengths = ()
                deliv_gaps = ()
                deliv_unknowns = (f"Buyer country '{buyer_loc}' delivery compliance unconfirmed",)
                uncertainty_acc += 0.1

        w_deliv = weights.get("delivery", 0.10)
        scores.append(MatchDimensionScore(
            dimension_name="delivery_jurisdiction",
            raw_score=deliv_score,
            weight=w_deliv,
            weighted_score=deliv_score * w_deliv,
            explanation=f"Buyer country: '{buyer_loc or 'Unspecified'}'.",
            strengths=deliv_strengths,
            gaps=deliv_gaps,
            unknowns=deliv_unknowns,
            evidence_refs=(),
            opportunity_field_refs=("procurement_metadata.buyer_country",),
        ))

        # 6. Evidence Sufficiency
        verified_count = (
            sum(1 for a in truth_graph.assertions.values() if a.verification_status == VerificationStatus.VERIFIED)
            + sum(1 for m in truth_graph.metrics.values() if m.verification_status == VerificationStatus.VERIFIED)
        )
        if verified_count == 0:
            ev_score = 0.0
            ev_strengths = ()
            ev_gaps = ("Zero verified assertions in truth graph to substantiate proposal",)
            ev_unknowns = ()
            uncertainty_acc += 0.50
        elif verified_count < 3:
            ev_score = 0.40
            ev_strengths = ()
            ev_gaps = ()
            ev_unknowns = ("Sparse verified assertions in truth graph",)
            uncertainty_acc += 0.20
        else:
            ev_score = min(1.0, 0.60 + (verified_count * 0.05))
            ev_strengths = (f"{verified_count} verified truth graph assertions available for proposal substantiation",)
            ev_gaps = ()
            ev_unknowns = ()

        w_ev = weights.get("evidence_sufficiency", 0.05)
        scores.append(MatchDimensionScore(
            dimension_name="evidence_sufficiency",
            raw_score=ev_score,
            weight=w_ev,
            weighted_score=ev_score * w_ev,
            explanation=f"Evaluated proposal substantiation against {verified_count} verified graph nodes.",
            strengths=ev_strengths,
            gaps=ev_gaps,
            unknowns=ev_unknowns,
            evidence_refs=(),
            opportunity_field_refs=(),
        ))

        return scores, uncertainty_acc
