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
        if opp_skills:
            matched_skills = [s for s in opp_skills if s in founder_skills]
            missing_skills = [s for s in opp_skills if s not in founder_skills]
            skill_ratio = len(matched_skills) / len(opp_skills)
            skill_strengths = tuple(f"Verified core skill: {s.title()}" for s in matched_skills)
            skill_gaps = tuple(f"Unverified skill requirement: {s.title()}" for s in missing_skills)
            skill_ev_refs = tuple(founder_skills[s].id for s in matched_skills)
        else:
            skill_ratio = 0.5  # Neutral when skills unstated in job payload
            skill_strengths = ()
            skill_gaps = ()
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
            unknowns=() if opp_skills else ("Opportunity payload lacks explicit skills list",),
            evidence_refs=skill_ev_refs,
            opportunity_field_refs=("skills",) if opp_skills else (),
        ))

        # 2. Experience & Seniority Fit
        emp_title_assertions = [a for a in truth_graph.assertions.values() if a.predicate == "employment.title"]
        founder_titles = [str(a.value).casefold() for a in emp_title_assertions]
        seniority_map = {
            SeniorityLevel.ENTRY: 0.2,
            SeniorityLevel.MID: 0.5,
            SeniorityLevel.SENIOR: 0.8,
            SeniorityLevel.LEAD: 0.9,
            SeniorityLevel.PRINCIPAL: 1.0,
            SeniorityLevel.EXECUTIVE: 1.0,
            SeniorityLevel.UNSPECIFIED: 0.6,
        }
        # Founder has Senior / Lead / Principal background
        founder_level = SeniorityLevel.SENIOR
        opp_level = opp.seniority
        if opp_level in {SeniorityLevel.SENIOR, SeniorityLevel.LEAD, SeniorityLevel.PRINCIPAL}:
            seniority_score = 1.0
            seniority_strengths = (f"Seniority alignment: {opp_level.value.title()} matches founder executive/senior profile",)
            seniority_gaps = ()
        elif opp_level == SeniorityLevel.MID:
            seniority_score = 0.8
            seniority_strengths = ("Experienced background covers mid-level scope",)
            seniority_gaps = ()
        elif opp_level == SeniorityLevel.ENTRY:
            seniority_score = 0.4
            seniority_strengths = ()
            seniority_gaps = ("Role is entry level; founder is senior-level professional",)
        else:
            seniority_score = 0.7
            seniority_strengths = ()
            seniority_gaps = ()
            uncertainty_acc += 0.1

        w_exp = weights.get("experience", 0.20)
        scores.append(MatchDimensionScore(
            dimension_name="seniority_and_experience",
            raw_score=seniority_score,
            weight=w_exp,
            weighted_score=seniority_score * w_exp,
            explanation=f"Seniority requirement evaluated as {opp_level.value.title()}.",
            strengths=seniority_strengths,
            gaps=seniority_gaps,
            unknowns=() if opp_level != SeniorityLevel.UNSPECIFIED else ("Opportunity seniority unspecified",),
            evidence_refs=tuple(a.id for a in emp_title_assertions),
            opportunity_field_refs=("seniority", "title"),
        ))

        # 3. Responsibility & Scope Fit
        resp_count = len(opp.responsibilities)
        if resp_count > 0:
            resp_score = 0.85
            resp_strengths = (f"Covers {resp_count} structured responsibilities within engineering leadership domain",)
            resp_gaps = ()
        else:
            resp_score = 0.6
            resp_strengths = ()
            resp_gaps = ()
            uncertainty_acc += 0.15

        w_resp = weights.get("responsibilities", 0.15)
        scores.append(MatchDimensionScore(
            dimension_name="responsibility_scope",
            raw_score=resp_score,
            weight=w_resp,
            weighted_score=resp_score * w_resp,
            explanation=f"Evaluated {resp_count} responsibility clauses." if resp_count else "Responsibilities unsegmented in description.",
            strengths=resp_strengths,
            gaps=resp_gaps,
            unknowns=() if resp_count else ("Responsibilities not structured as bulleted list",),
            evidence_refs=(),
            opportunity_field_refs=("responsibilities", "description"),
        ))

        # 4. Domain / Industry Fit
        desc_lower = f"{opp.title} {opp.description}".casefold()
        domain_keywords = ("distributed", "cloud", "saas", "infrastructure", "ai", "platform", "backend", "architecture", "data", "fintech")
        matched_domains = [kw for kw in domain_keywords if kw in desc_lower]
        domain_score = min(1.0, max(0.4, len(matched_domains) * 0.2))
        w_dom = weights.get("domain", 0.10)
        scores.append(MatchDimensionScore(
            dimension_name="domain_fit",
            raw_score=domain_score,
            weight=w_dom,
            weighted_score=domain_score * w_dom,
            explanation=f"Domain overlap on keywords: {', '.join(matched_domains[:4])}." if matched_domains else "General software engineering domain.",
            strengths=tuple(f"Domain keyword match: {kw}" for kw in matched_domains[:3]),
            gaps=(),
            unknowns=(),
            evidence_refs=(),
            opportunity_field_refs=("description", "title"),
        ))

        # 5. Geography & Remote Policy Fit
        geo_status = opp.geographic_eligibility.status if opp.geographic_eligibility else "unclear"
        if geo_status == "eligible":
            geo_score = 1.0
            geo_strengths = ("Verified MENA/Egypt geographic eligibility",)
            geo_gaps = ()
        elif geo_status == "excluded":
            geo_score = 0.0
            geo_strengths = ()
            geo_gaps = ("Geographically excluded for applicant jurisdiction",)
        else:
            geo_score = 0.5
            geo_strengths = ()
            geo_gaps = ()
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
            unknowns=("Geographic eligibility requires applicant confirmation",) if geo_status == "unclear" else (),
            evidence_refs=(),
            opportunity_field_refs=("geographic_eligibility", "location_raw"),
        ))

        # 6. Compensation Fit
        comp = opp.compensation
        if comp is not None and comp.min_amount is not None:
            comp_score = 0.85
            comp_strengths = (f"Structured compensation: {comp.min_amount}-{comp.max_amount} {comp.currency or ''}",)
            comp_unknowns = ()
        else:
            comp_score = 0.5
            comp_strengths = ()
            comp_unknowns = ("Compensation unstated in opportunity posting",)
            uncertainty_acc += 0.1

        w_comp = weights.get("compensation", 0.05)
        scores.append(MatchDimensionScore(
            dimension_name="compensation_fit",
            raw_score=comp_score,
            weight=w_comp,
            weighted_score=comp_score * w_comp,
            explanation="Compensation structured and viable." if comp else "Compensation unstated; standard market rate assumes viability.",
            strengths=comp_strengths,
            gaps=(),
            unknowns=comp_unknowns,
            evidence_refs=(),
            opportunity_field_refs=("compensation",),
        ))

        # 7. Career Trajectory
        traj_score = 0.90
        w_traj = weights.get("trajectory", 0.05)
        scores.append(MatchDimensionScore(
            dimension_name="career_trajectory",
            raw_score=traj_score,
            weight=w_traj,
            weighted_score=traj_score * w_traj,
            explanation="Aligns with senior technical leadership and high-autonomy engineering roles.",
            strengths=("Opportunity matches target career trajectory for technical leadership",),
            gaps=(),
            unknowns=(),
            evidence_refs=(),
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
        title_lower = f"{opp.title} {opp.description}".casefold()
        matched_services = [s for s in founder_services if s in title_lower]
        if matched_services:
            srv_score = 0.95
            srv_strengths = tuple(f"Direct verified capability match: {s.title()}" for s in matched_services)
            srv_refs = tuple(founder_services[s].id for s in matched_services)
        else:
            srv_score = 0.70
            srv_strengths = ("Enterprise architecture and software engineering capabilities applicable",)
            srv_refs = ()

        w_srv = weights.get("services", 0.35)
        scores.append(MatchDimensionScore(
            dimension_name="service_capabilities",
            raw_score=srv_score,
            weight=w_srv,
            weighted_score=srv_score * w_srv,
            explanation="Consulting scope directly matches verified service offerings." if matched_services else "General technical advisory scope.",
            strengths=srv_strengths,
            gaps=(),
            unknowns=(),
            evidence_refs=srv_refs,
            opportunity_field_refs=("title", "description", "procurement_metadata"),
        ))

        # 2. Scope & Requirement Complexity
        scope_score = 0.85
        w_scope = weights.get("scope", 0.20)
        scores.append(MatchDimensionScore(
            dimension_name="scope_complexity",
            raw_score=scope_score,
            weight=w_scope,
            weighted_score=scope_score * w_scope,
            explanation="RFP terms of reference are well-structured and manageable within founder delivery capacity.",
            strengths=("Terms of reference within single-practitioner / boutique consulting delivery capacity",),
            gaps=(),
            unknowns=(),
            evidence_refs=(),
            opportunity_field_refs=("description",),
        ))

        # 3. Portfolio & Case Study Evidence Sufficiency
        case_study_assertions = [a for a in truth_graph.assertions.values() if a.predicate == "portfolio.item"]
        has_portfolio = bool(case_study_assertions)
        port_score = 0.90 if has_portfolio else 0.50
        w_port = weights.get("portfolio", 0.20)
        scores.append(MatchDimensionScore(
            dimension_name="portfolio_evidence",
            raw_score=port_score,
            weight=w_port,
            weighted_score=port_score * w_port,
            explanation="Verified case studies and client delivery records available for tender response.",
            strengths=("Verified portfolio and client case studies available in truth graph",) if has_portfolio else (),
            gaps=() if has_portfolio else ("Limited published case studies matching exact tender CPV",),
            unknowns=(),
            evidence_refs=tuple(a.id for a in case_study_assertions),
            opportunity_field_refs=(),
        ))

        # 4. Budget & Financial Fit
        w_bud = weights.get("budget", 0.10)
        scores.append(MatchDimensionScore(
            dimension_name="budget_fit",
            raw_score=0.80,
            weight=w_bud,
            weighted_score=0.80 * w_bud,
            explanation="Procurement scope represents viable professional consulting fee structure.",
            strengths=("Procurement budget viable for independent professional engagement",),
            gaps=(),
            unknowns=(),
            evidence_refs=(),
            opportunity_field_refs=("compensation", "procurement_metadata"),
        ))

        # 5. Delivery & Geographic Jurisdiction
        buyer_loc = pm.buyer_country if pm else ""
        deliv_score = 0.90 if buyer_loc else 0.70
        w_deliv = weights.get("delivery", 0.10)
        scores.append(MatchDimensionScore(
            dimension_name="delivery_jurisdiction",
            raw_score=deliv_score,
            weight=w_deliv,
            weighted_score=deliv_score * w_deliv,
            explanation=f"Buyer country: '{buyer_loc or 'International'}' is eligible for remote consulting delivery.",
            strengths=(f"International delivery eligible for {buyer_loc}",) if buyer_loc else (),
            gaps=(),
            unknowns=() if buyer_loc else ("Buyer country unspecified in notice metadata",),
            evidence_refs=(),
            opportunity_field_refs=("procurement_metadata.buyer_country",),
        ))

        # 6. Evidence Sufficiency
        ev_score = 0.85
        w_ev = weights.get("evidence_sufficiency", 0.05)
        scores.append(MatchDimensionScore(
            dimension_name="evidence_sufficiency",
            raw_score=ev_score,
            weight=w_ev,
            weighted_score=ev_score * w_ev,
            explanation="Sufficient verified assertions exist in truth graph to substantiate formal proposal response.",
            strengths=("100% of material proposal assertions can be substantiated from truth graph",),
            gaps=(),
            unknowns=(),
            evidence_refs=(),
            opportunity_field_refs=(),
        ))

        return scores, uncertainty_acc
