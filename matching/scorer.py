"""Explainable Dual-Track Matching & Ranking Scorer for OpportunityOS.

Implements multidimensional scoring separated into explicit dimensions for employment
versus independent consulting tracks. Emits comprehensive MatchEvaluation objects with
score breakdowns, supporting strengths, gaps, unknowns, and explicit links to TruthGraph
assertions without keyword dominance or false certainty.
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

from opportunity.models import (
    CompensationInterval,
    EmploymentType,
    Opportunity,
    RemotePolicy,
    SeniorityLevel,
    Track,
)
from opportunity.normalization import extract_skills_from_text
from truth import predicates
from truth.graph import TruthGraph
from truth.models import CertificationState, Polarity, VerificationStatus

from . import seniority
from . import skills as skill_matching
from .models import (
    HardConstraintResult,
    MatchDimensionScore,
    MatchEvaluation,
    QualificationDecision,
    ScoringPolicy,
)
from .requirements import RequirementPriority
from .requirements import classify_requirement_text
from .qualification import QualificationEngine
from .title_family import normalize_title

_CURRENCY_THRESHOLD_RE = re.compile(r"^\s*([\d,]+(?:\.\d+)?)\s*([A-Za-z]{3})\s*$")
_DEGREE_CUE_RE = re.compile(
    r"\b(?:degree|bachelor(?:'s|s)?|master(?:'s|s)?|mba|ph\.?d\.?|doctorate|doctoral|associate\s+degree)\b",
    re.IGNORECASE,
)
_CERTIFICATION_CUE_RE = re.compile(
    r"\b(?:certification|certificate|certified|licen[cs]e|pmp|cissp|cfa|cpa|ccna|cisa|aws\s+certified|"
    r"azure\s+certified|google\s+cloud\s+certified)\b",
    re.IGNORECASE,
)
_CREDENTIAL_NOISE_WORDS = frozenset({
    "a", "an", "and", "or", "the", "of", "in", "with", "for", "to", "from",
    "degree", "certification", "certificate", "certified", "license", "licence",
    "required", "preferred", "strongly", "highly", "minimum", "qualification",
    "qualifications", "hold", "held", "having", "equivalent", "plus", "desired",
})
_DEGREE_LEVEL_RANK = {"associate": 1, "bachelor": 2, "master": 3, "doctorate": 4}
_DEGREE_ALIASES = {
    "bachelor": "bachelor", "bachelors": "bachelor", "ba": "bachelor", "bs": "bachelor",
    "bsc": "bachelor", "bba": "bachelor", "master": "master", "masters": "master",
    "ma": "master", "ms": "master", "msc": "master", "mba": "master",
    "phd": "doctorate", "doctorate": "doctorate", "doctoral": "doctorate",
    "associate": "associate", "associates": "associate",
}

# Opportunity.seniority (opportunity/models.py's SeniorityLevel) has no
# separate "staff" member; industry usage treats "Staff" and "Lead" as the
# same tier, both below Principal, so LEAD maps to seniority.py's "staff"
# threshold row. SeniorityLevel.UNSPECIFIED is deliberately absent -- an
# unspecified requirement falls through to the "required_level is None"
# branch below rather than asserting a fabricated level.
_REQUIRED_LEVEL_BY_OPP_SENIORITY: dict[SeniorityLevel, str] = {
    SeniorityLevel.ENTRY: "junior",
    SeniorityLevel.MID: "mid",
    SeniorityLevel.SENIOR: "senior",
    SeniorityLevel.LEAD: "staff",
    SeniorityLevel.PRINCIPAL: "principal",
    SeniorityLevel.EXECUTIVE: "principal",
}

# Words that describe a level, not a role family, stripped from an
# opportunity's title before it is used as a `matching/seniority.py`
# `family_aliases` query. This is a title-family filter only -- it never
# feeds a seniority pass/fail decision, which is why it can safely stay a
# simple stoplist until BRIEF-FR-006 B3's `matching/title_families.yaml`
# replaces family derivation entirely.
_TITLE_LEVEL_WORDS = frozenset({
    "senior", "sr", "junior", "jr", "entry", "entry-level", "mid", "mid-level",
    "associate", "staff", "principal", "lead", "director", "head", "chief", "i", "ii", "iii", "iv", "v",
})
_TITLE_WORD_RE = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")


def _family_aliases_from_title(title: str) -> tuple[str, ...]:
    """Derive a simple, single-alias role-family query from an opportunity's
    title by stripping level words. Not a seniority signal itself -- see
    module note above and `matching/seniority.py`'s module docstring."""
    words = [w for w in _TITLE_WORD_RE.findall(title) if w.casefold() not in _TITLE_LEVEL_WORDS]
    if not words:
        return ()
    return (" ".join(words),)


def _parse_currency_threshold(value: Any) -> tuple[float, str] | None:
    """Parse a pack-supplied '<amount> <ISO currency>' monthly threshold string.

    Returns None if the value is absent or not in the expected currency-aware shape,
    so callers never mistake an unparseable threshold for a comparable one.
    """
    if value is None:
        return None
    match = _CURRENCY_THRESHOLD_RE.match(str(value))
    if not match:
        return None
    amount_str, currency = match.groups()
    try:
        amount = float(amount_str.replace(",", ""))
    except ValueError:
        return None
    return amount, currency.upper()


def _monthly_compensation(comp: Any) -> float | None:
    """Normalize stated compensation to a monthly figure, or None if not safely comparable.

    Only MONTHLY and YEARLY intervals are normalized; hourly/daily/project figures depend
    on hours worked, which the opportunity record does not reliably state, so those remain
    unresolved (UNKNOWN) rather than guessed at.
    """
    if comp is None or comp.min_amount is None:
        return None
    amount = comp.max_amount if comp.max_amount is not None else comp.min_amount
    if comp.interval == CompensationInterval.MONTHLY:
        return amount
    if comp.interval == CompensationInterval.YEARLY:
        return amount / 12.0
    return None


def _credential_kind(text: str) -> str | None:
    """Return the credential family only when the posting names one."""
    if _DEGREE_CUE_RE.search(text):
        return "education"
    if _CERTIFICATION_CUE_RE.search(text):
        return "certification"
    return None


def _credential_requirement_items(opp: Opportunity) -> tuple[tuple[str, str, RequirementPriority], ...]:
    """Extract explicit posting-side education/certification requirements.

    Structured requirements carry their source-section context. Free
    description text must state a priority itself or appear beneath an
    applicant-facing requirements/preferred heading; an incidental credential
    mention in company context is not promoted into a requirement.
    """
    items: list[tuple[str, str, RequirementPriority]] = []
    seen: set[tuple[str, str]] = set()
    applicable_priorities = {
        RequirementPriority.MANDATORY,
        RequirementPriority.STRONGLY_PREFERRED,
        RequirementPriority.NICE_TO_HAVE,
    }

    def add(text: str, source_section: str | RequirementPriority | None) -> None:
        kind = _credential_kind(text)
        if not kind:
            return
        priority = classify_requirement_text(text, source_section=source_section)
        if priority not in applicable_priorities:
            return
        key = (kind, " ".join(text.casefold().split()))
        if key not in seen:
            seen.add(key)
            items.append((kind, text.strip(" -*•\t"), priority))

    for requirement in opp.requirements:
        add(requirement, "requirements")

    section_priority: RequirementPriority | None = None
    for raw_line in (opp.description or "").splitlines():
        line = raw_line.strip().lstrip("-*• ").strip()
        if not line:
            continue
        heading = line.rstrip(":").casefold()
        if len(heading) <= 90 and not _credential_kind(line):
            if re.search(r"\b(?:strongly|highly) preferred\b", heading):
                section_priority = RequirementPriority.STRONGLY_PREFERRED
                continue
            if re.search(r"\b(?:preferred|nice to have|bonus|desired)\b", heading):
                section_priority = RequirementPriority.NICE_TO_HAVE
                continue
            if re.search(r"\b(?:requirements?|minimum qualifications?|what you(?:'ll| will) need|qualifications)\b", heading):
                section_priority = RequirementPriority.MANDATORY
                continue
            if line.endswith(":"):
                section_priority = None
                continue

        for sentence in re.split(r"(?<=[.!?])\s+", line):
            add(sentence, section_priority)

    return tuple(items)


def _credential_tokens(text: str) -> frozenset[str]:
    return frozenset(
        token for token in re.findall(r"[a-z0-9]+", text.casefold())
        if token not in _CREDENTIAL_NOISE_WORDS and len(token) > 1
    )


def _degree_level(text: str) -> str | None:
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    for token in tokens:
        level = _DEGREE_ALIASES.get(token)
        if level:
            return level
    return None


def _credential_requirement_matches(kind: str, requirement: str, founder_credential: str) -> bool:
    """Match only directly named, verified credentials; unlisted facts stay unknown."""
    requirement_tokens = _credential_tokens(requirement)
    founder_tokens = _credential_tokens(founder_credential)
    if not requirement_tokens or not founder_tokens:
        return False

    if kind == "education":
        required_level = _degree_level(requirement)
        founder_level = _degree_level(founder_credential)
        if required_level:
            if not founder_level or _DEGREE_LEVEL_RANK[founder_level] < _DEGREE_LEVEL_RANK[required_level]:
                return False
            requirement_tokens = frozenset(
                token for token in requirement_tokens if token not in _DEGREE_ALIASES
            )
            founder_tokens = frozenset(
                token for token in founder_tokens if token not in _DEGREE_ALIASES
            )
            if not requirement_tokens:
                return True
        return requirement_tokens.issubset(founder_tokens)

    return requirement_tokens.issubset(founder_tokens)


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
            dim_scores, uncertainty = self._score_employment(opp, truth_graph, evaluated_at)

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

    def _score_employment(
        self, opp: Opportunity, truth_graph: TruthGraph, evaluated_at: str = "2026-08-30",
    ) -> tuple[list[MatchDimensionScore], float]:
        scores: list[MatchDimensionScore] = []
        uncertainty_acc = 0.0
        weights = self.policy.employment_weights

        # 1. Core Skill Fit (proficiency-aware, requirement-aware -- BRIEF-FR-006
        # B2). Name-only matching used to say "Verified core skill: Javascript"
        # for a skill the founder's own CV records as *basic* -- the product
        # telling the founder something untrue about themselves (AGENTS.md's
        # first hard rule). Fixed via `matching/skills.py`: proficiency below
        # `working` (or unrecognised/absent -- unknown must not be optimistic)
        # is always a *partial* match, never a strength, and a core-skill
        # strength additionally requires the posting to have listed that skill
        # as *required* (opportunity/inference_rules.yaml headed-list rules),
        # not merely nice-to-have.
        founder_skills_by_name = skill_matching.build_verified_skill_index(
            truth_graph.assertions.values(),
        )

        raw_skill_names = tuple(dict.fromkeys((
            *opp.skills,
            *extract_skills_from_text(opp.description),
        )))
        all_opp_skills = [
            normalized for raw in raw_skill_names
            if (normalized := skill_matching.normalize_skill_label(raw))
        ]
        all_skill_priorities = skill_matching.classify_skill_priorities(
            opp.description, tuple(raw_skill_names),
        )
        candidate_priorities = {
            RequirementPriority.MANDATORY,
            RequirementPriority.STRONGLY_PREFERRED,
            RequirementPriority.NICE_TO_HAVE,
        }
        skill_priorities = {
            skill: all_skill_priorities.get(skill, RequirementPriority.UNKNOWN)
            for skill in all_opp_skills
            if all_skill_priorities.get(skill, RequirementPriority.UNKNOWN) in candidate_priorities
        }
        opp_skills = tuple(skill_priorities)
        required_skills = frozenset(
            skill for skill, priority in skill_priorities.items()
            if priority == RequirementPriority.MANDATORY
        )
        if not founder_skills_by_name:
            if opp_skills:
                skill_ratio = 0.0
                skill_strengths = ()
                skill_gaps = tuple(f"Unverified skill requirement: {s.title()}" for s in opp_skills)
                skill_unknowns = ("Founder truth graph contains 0 verified skills",)
                skill_ev_refs = ()
                skill_explanation = "No explicit skills specified in posting."
                uncertainty_acc += 0.4
            else:
                skill_ratio = 0.5
                skill_strengths = ()
                skill_gaps = ()
                if all_opp_skills:
                    skill_unknowns = (
                        "Posting mentions skills without candidate requirement or preference evidence; priority is unknown or contextual.",
                    )
                else:
                    skill_unknowns = ("No explicit skills in opportunity or founder truth graph",)
                skill_ev_refs = ()
                skill_explanation = "No explicit skills specified in posting."
                uncertainty_acc += 0.3
        else:
            if opp_skills:
                skill_evals = skill_matching.evaluate_skill_matches(
                    tuple(opp_skills), required_skills, founder_skills_by_name,
                    priorities=skill_priorities,
                )
                strength_matches = [m for m in skill_evals if m.is_strength]
                partial_matches = [m for m in skill_evals if m.is_partial]
                gap_matches = [m for m in skill_evals if m.is_gap]

                skill_ratio = (
                    (len(strength_matches) + 0.5 * len(partial_matches)) / len(skill_evals)
                    if skill_evals else 0.5
                )
                skill_strengths = tuple(
                    f"Core skill match (required, {m.proficiency} proficiency): {m.name.title()}"
                    for m in strength_matches
                )
                skill_gaps = tuple(
                    (
                        f"Unverified skill requirement: {m.name.title()}" if m.required
                        else f"{m.priority.value.replace('_', ' ').title()} skill not in founder pack: {m.name.title()}"
                    )
                    for m in gap_matches
                )
                skill_unknowns = tuple(
                    (
                        f"Partial skill signal: {m.name.title()} ({m.proficiency or 'unknown'} proficiency; "
                        + (
                            "required, below working proficiency" if m.required
                            else f"{m.priority.value.replace('_', ' ')} match"
                        )
                        + ") -- not a core-skill strength"
                    )
                    for m in partial_matches
                )
                skill_ev_refs = tuple(dict.fromkeys(
                    ref for m in strength_matches + partial_matches for ref in m.evidence_refs
                ))
                skill_explanation = skill_matching.render_reason(skill_evals)
            else:
                skill_ratio = 0.5  # Neutral when skills unstated in job payload
                skill_strengths = ()
                skill_gaps = ()
                skill_unknowns = ("Opportunity payload lacks explicit skills list",)
                skill_ev_refs = ()
                skill_explanation = "No explicit skills specified in posting."
                uncertainty_acc += 0.2

        w_skill = weights.get("skills", 0.35)
        scores.append(MatchDimensionScore(
            dimension_name="core_skills",
            raw_score=skill_ratio,
            weight=w_skill,
            weighted_score=skill_ratio * w_skill,
            explanation=skill_explanation,
            strengths=skill_strengths,
            gaps=skill_gaps,
            unknowns=skill_unknowns,
            evidence_refs=skill_ev_refs,
            opportunity_field_refs=("skills", "description") if opp_skills else (),
        ))

        # 2. Relevant experience (verified employment tenure).
        opp_level = opp.seniority
        required_level = _REQUIRED_LEVEL_BY_OPP_SENIORITY.get(opp_level)
        posting_title_level = normalize_title(opp.title)[1]
        if required_level is None and posting_title_level in seniority.THRESHOLDS_BY_LEVEL:
            required_level = posting_title_level
        family_aliases = _family_aliases_from_title(opp.title)
        try:
            as_of = date.fromisoformat(evaluated_at)
        except ValueError:
            as_of = None
        assessment = seniority.assess(
            truth_graph,
            required_level=required_level,
            family_aliases=family_aliases,
            as_of=as_of,
        )
        family_label = family_aliases[0] if family_aliases else "the opportunity's role family"

        if assessment is None:
            experience_score = 0.5
            experience_strengths = ()
            experience_gaps = ()
            experience_unknowns = (
                "No verified employment record (title + start date) in founder truth graph",
            )
            experience_ev_refs = ()
            experience_explanation = (
                f"Experience requirement evaluated as {opp_level.value.title()}; founder truth graph has no "
                "verified employment record with both a title and a start date to compute tenure from."
            )
            uncertainty_acc += 0.3
        elif required_level is None:
            experience_score = 0.7
            experience_strengths = ()
            experience_gaps = ()
            experience_unknowns = ("Opportunity does not specify a seniority or years-of-experience threshold",)
            experience_ev_refs = assessment.tenure_evidence_refs
            experience_explanation = seniority.explain(assessment, family_label=family_label)
            uncertainty_acc += 0.1
        else:
            experience_ev_refs = assessment.tenure_evidence_refs
            experience_explanation = seniority.explain(assessment, family_label=family_label)
            if assessment.months_gap == 0:
                experience_score = 1.0
                experience_strengths = (
                    f"Verified professional experience: {assessment.total_months} month(s) meets the "
                    f"{assessment.requirement.level.title()} threshold of {assessment.requirement.months_floor} month(s).",
                )
                experience_gaps = ()
                experience_unknowns = ()
            else:
                experience_score = 0.35
                experience_strengths = ()
                experience_gaps = (
                    f"Role requires {assessment.requirement.level.title()} "
                    f"({assessment.requirement.months_floor}+ verified professional months); founder has "
                    f"{assessment.total_months}, a gap of {assessment.months_gap} month(s)",
                )
                experience_unknowns = ()

        w_exp = weights.get("experience", 0.20)
        scores.append(MatchDimensionScore(
            dimension_name="experience_fit",
            raw_score=experience_score,
            weight=w_exp,
            weighted_score=experience_score * w_exp,
            explanation=experience_explanation,
            strengths=experience_strengths,
            gaps=experience_gaps,
            unknowns=experience_unknowns,
            evidence_refs=experience_ev_refs,
            opportunity_field_refs=("seniority", "title"),
        ))

        # 3. Seniority level is a separate title/scope signal. Title level and
        # verified leadership may support a match; a lower or unspecified title
        # never proves the Founder cannot do the work.
        _seniority_rank = {"junior": 1, "mid": 2, "senior": 3, "staff": 4, "principal": 5}
        required_seniority_level = (
            _REQUIRED_LEVEL_BY_OPP_SENIORITY.get(opp_level)
            or (posting_title_level if posting_title_level in _seniority_rank else None)
        )
        founder_title_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate in {predicates.EMPLOYMENT_TITLE, predicates.EMPLOYMENT_MARKET_FACING_TITLE}
            and a.verification_status == VerificationStatus.VERIFIED
            and a.polarity == Polarity.POSITIVE
        ]
        founder_title_levels = [
            (a, normalize_title(str(a.value))[1])
            for a in founder_title_assertions
        ]
        founder_title_levels = [
            (a, level) for a, level in founder_title_levels if level in _seniority_rank
        ]
        if required_seniority_level is None:
            seniority_fit_score = 0.5
            seniority_fit_strengths = ()
            seniority_fit_gaps = ()
            seniority_fit_unknowns = ("Posting title and structured seniority do not state a level to compare",)
            seniority_fit_refs = ()
        elif not founder_title_levels:
            seniority_fit_score = 0.5
            seniority_fit_strengths = ()
            seniority_fit_gaps = ()
            seniority_fit_unknowns = (
                "Verified employment evidence does not state a comparable seniority level"
                if founder_title_assertions else
                "No verified employment-title evidence is available to compare seniority",
            )
            seniority_fit_refs = tuple(a.id for a in founder_title_assertions)
        else:
            highest_assertion, highest_level = max(
                founder_title_levels, key=lambda item: _seniority_rank[item[1]],
            )
            seniority_fit_refs = tuple(sorted(
                {
                    a.id for a, level in founder_title_levels
                    if _seniority_rank[level] == _seniority_rank[highest_level]
                }
                | (set(assessment.leadership_evidence_refs) if assessment else set())
            ))
            requires_leadership = required_seniority_level in {"staff", "principal"}
            level_meets = _seniority_rank[highest_level] >= _seniority_rank[required_seniority_level]
            leadership_verified = bool(assessment and assessment.has_leadership)
            if level_meets and (not requires_leadership or leadership_verified):
                seniority_fit_score = 1.0
                seniority_fit_strengths = (
                    f"Verified employment title level {highest_level.title()} aligns with the "
                    f"{required_seniority_level.title()} posting level"
                    + (" and verified leadership responsibilities" if requires_leadership else "")
                    + f" ({highest_assertion.id}).",
                )
                seniority_fit_gaps = ()
                seniority_fit_unknowns = ()
            else:
                seniority_fit_score = 0.5
                seniority_fit_strengths = ()
                seniority_fit_gaps = ()
                seniority_fit_unknowns = (
                    "Verified title and leadership evidence does not establish the requested seniority; review the role scope",
                )

        w_seniority = weights.get("seniority", 0.0)
        scores.append(MatchDimensionScore(
            dimension_name="seniority_fit",
            raw_score=seniority_fit_score,
            weight=w_seniority,
            weighted_score=seniority_fit_score * w_seniority,
            explanation=(
                f"Posting seniority level: {required_seniority_level or 'unspecified'}; "
                f"verified founder title level: {highest_level if founder_title_levels else 'unknown'}."
            ),
            strengths=seniority_fit_strengths,
            gaps=seniority_fit_gaps,
            unknowns=seniority_fit_unknowns,
            evidence_refs=seniority_fit_refs,
            opportunity_field_refs=("seniority", "title"),
        ))
        scores.append(MatchDimensionScore(
            dimension_name="seniority_and_experience",
            raw_score=(experience_score + seniority_fit_score) / 2.0,
            weight=0.0,
            weighted_score=0.0,
            explanation="Compatibility projection; use experience_fit and seniority_fit for separate evidence.",
            evidence_refs=tuple(sorted(set(experience_ev_refs) | set(seniority_fit_refs))),
            opportunity_field_refs=("seniority", "title"),
        ))

        # 4. Experience responsibility and scope alignment.
        founder_resp_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate in predicates.RESPONSIBILITY_SCOPE_PREDICATES
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
            if a.predicate in predicates.DOMAIN_FIT_PREDICATES
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

        # Rebalanced from 0.10 (see the title_family_fit dimension's weight
        # note below, dimension 8) to make room for that new dimension
        # without exceeding the employment_weights total of 1.0.
        w_dom = weights.get("domain", 0.05)
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
            if a.predicate in predicates.RESIDENCE_LOCATION_PREDICATES
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
        if comp is not None and comp.min_amount is not None:
            matching_target: float | None = None
            interval_name = comp.interval.value if hasattr(comp.interval, "value") else str(comp.interval)

            if comp.interval == CompensationInterval.YEARLY:
                matching_target = getattr(self.policy, "min_target_yearly_compensation", None) or getattr(self.policy, "min_target_compensation", None)
            elif comp.interval == CompensationInterval.HOURLY:
                matching_target = getattr(self.policy, "min_target_hourly_rate", None)
            elif comp.interval == CompensationInterval.DAILY:
                matching_target = getattr(self.policy, "min_target_daily_rate", None)
            elif comp.interval == CompensationInterval.PROJECT:
                matching_target = getattr(self.policy, "min_target_project_budget", None)

            if matching_target is not None:
                max_amt = comp.max_amount if comp.max_amount is not None else comp.min_amount
                if max_amt >= matching_target:
                    comp_score = 0.90
                    comp_strengths = (f"Opportunity compensation ({comp.min_amount}-{comp.max_amount or ''} {comp.currency or ''} {interval_name}) meets target ({matching_target})",)
                    comp_gaps = ()
                    comp_unknowns = ()
                else:
                    comp_score = 0.30
                    comp_strengths = ()
                    comp_gaps = (f"Opportunity compensation ({max_amt} {interval_name}) below founder target ({matching_target})",)
                    comp_unknowns = ()
            else:
                comp_score = 0.50
                comp_strengths = ()
                comp_gaps = ()
                comp_unknowns = (f"Opportunity compensation stated ({comp.min_amount} {comp.currency or ''} {interval_name}); compatible founder target economics unconfigured in policy",)
                uncertainty_acc += 0.1
        else:
            comp_score = 0.50
            comp_strengths = ()
            comp_gaps = ()
            comp_unknowns = ("Compensation unstated in opportunity posting",)
            uncertainty_acc += 0.1

        # Premium full-time/on-site rule: a RANKING signal only, never a hard constraint
        # and never a penalty for unstated compensation. It only ever adds a gap note and
        # nudges raw_score down when compensation is both stated and currency-comparable
        # to the founder's threshold; qualification is untouched (compensation_fit never
        # feeds a hard constraint).
        premium_ev_refs: tuple[str, ...] = ()
        # Stable marker tag (BRIEF-FR-005 D3 council repair, defect 6):
        # api/filters.py's premium_fulltime_onsite filter used to key off the
        # word "premium" inside comp_gaps' free-text sentence below -- a
        # reword of that sentence would silently disable the filter with no
        # test catching it. "premium_shortfall" is a code-owned tag, set only
        # on the one branch that actually finds a shortfall, and is not
        # prose: nothing about it is expected to change if the sentence's
        # wording changes.
        comp_signal_tags: tuple[str, ...] = ()
        if opp.employment_type == EmploymentType.FULL_TIME and opp.remote_policy == RemotePolicy.ON_SITE:
            premium_assertions = [
                a for a in truth_graph.assertions.values()
                if a.predicate == predicates.PREFERENCE_FULLTIME_ONSITE_PREMIUM_MONTHLY
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            threshold = _parse_currency_threshold(premium_assertions[0].value) if premium_assertions else None
            if threshold is not None:
                threshold_amount, threshold_currency = threshold
                monthly = _monthly_compensation(comp)
                if (
                    monthly is not None
                    and comp is not None
                    and comp.currency
                    and comp.currency.strip().upper() == threshold_currency
                ):
                    premium_ev_refs = (premium_assertions[0].id,)
                    if monthly < threshold_amount:
                        comp_gaps = comp_gaps + (
                            f"Full-time on-site compensation (~{monthly:.0f} {threshold_currency}/month) is below the "
                            f"founder's full-time on-site premium threshold ({threshold_amount:.0f} {threshold_currency}/month)",
                        )
                        comp_score = min(comp_score, 0.35)
                        comp_signal_tags = ("premium_shortfall",)
                # else: compensation unstated, non-monthly/yearly, or a different currency
                # than the threshold -> UNKNOWN for this rule, never a penalty.

        w_comp = weights.get("compensation", 0.05)
        scores.append(MatchDimensionScore(
            dimension_name="compensation_fit",
            raw_score=comp_score,
            weight=w_comp,
            weighted_score=comp_score * w_comp,
            explanation="Compensation evaluated against founder target policy.",
            strengths=comp_strengths,
            gaps=comp_gaps,
            unknowns=comp_unknowns,
            evidence_refs=premium_ev_refs,
            opportunity_field_refs=("compensation",),
            signal_tags=comp_signal_tags,
        ))

        # 7. Career Trajectory
        target_role_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == predicates.CAREER_TARGET_ROLE
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

        # 8. Target-role-family preference (B3, BRIEF-FR-006): compares the posting's
        # normalized title family (`matching/title_family.py`, driven by the
        # committed `matching/title_families.yaml`) against the families the
        # founder's verified CAREER_TARGET_ROLE assertions themselves. This is
        # a preference signal and is kept out of the capability title-history
        # dimension added below.
        # normalize onto. Distinguishes near-identical titles by family (not
        # only by score) -- e.g. "Senior Customer Engineer" postings no
        # longer read as a data-engineering match just because both titles
        # contain "Engineer".
        #
        # Weight note: this dimension is new, so `employment_weights` is
        # rebalanced to keep the total at 1.0 without touching any other
        # implementer's dimension in this concurrent wave: `domain` drops
        # from its 0.10 default to 0.05 (domain_fit's term-overlap check
        # already covers much of the same ground as title-family alignment,
        # so halving it is a reasonable reallocation) and the freed 0.05
        # funds `title_family` at 0.05. Every other default is unchanged.
        opp_family_id, opp_level, opp_family_rule = normalize_title(opp.title)
        target_role_family_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == predicates.CAREER_TARGET_ROLE
            and a.verification_status == VerificationStatus.VERIFIED
        ]
        if not target_role_family_assertions:
            title_family_score = 0.50
            title_family_strengths = ()
            title_family_gaps = ()
            title_family_unknowns = ("Founder has no verified career.target_role assertion to compare title families against",)
            title_family_ev_refs = ()
            uncertainty_acc += 0.1
        else:
            target_families = {
                normalize_title(str(a.value))[0]: a for a in target_role_family_assertions
            }
            if opp_family_id != "other" and opp_family_id in target_families:
                title_family_score = 1.0
                title_family_strengths = (
                    f"Posting title family '{opp_family_id}' matches a verified target role (rule: {opp_family_rule})",
                )
                title_family_gaps = ()
                title_family_unknowns = ()
                title_family_ev_refs = (target_families[opp_family_id].id,)
            elif opp_family_id == "other":
                title_family_score = 0.40
                title_family_strengths = ()
                title_family_gaps = ()
                title_family_unknowns = (f"Posting title did not normalize to a known family (rule: {opp_family_rule})",)
                title_family_ev_refs = ()
                uncertainty_acc += 0.05
            else:
                title_family_score = 0.20
                title_family_strengths = ()
                title_family_gaps = (
                    f"Posting title family '{opp_family_id}' does not match any of the founder's verified target-role families",
                )
                title_family_unknowns = ()
                title_family_ev_refs = tuple(a.id for a in target_role_family_assertions)

        w_title_family = weights.get("target_role_family_preference", 0.05)
        scores.append(MatchDimensionScore(
            dimension_name="target_role_family_preference",
            raw_score=title_family_score,
            weight=w_title_family,
            weighted_score=title_family_score * w_title_family,
            # Finding 8 (council review #1): normalize_title also computes a
            # level (migration 0004's title_level column is the storage side
            # of this, not scored here -- the requirement asks for the level
            # to be surfaced, not for a scoring effect this dimension's
            # acceptance criteria never specified). Surfaced here in the
            # explanation so it is observable per-evaluation.
            explanation=f"Posting title normalized to family '{opp_family_id}', level '{opp_level}' (rule: {opp_family_rule}).",
            strengths=title_family_strengths,
            gaps=title_family_gaps,
            unknowns=title_family_unknowns,
            evidence_refs=title_family_ev_refs,
            opportunity_field_refs=("title",),
        ))

        # 9. Capability role-family history. A target-role preference assertion
        # is deliberately not reused as evidence that the Founder has done the
        # work before.
        founder_role_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate in {predicates.EMPLOYMENT_TITLE, predicates.EMPLOYMENT_MARKET_FACING_TITLE}
            and a.verification_status == VerificationStatus.VERIFIED
            and a.polarity == Polarity.POSITIVE
        ]
        matched_role_history = [
            a for a in founder_role_assertions
            if opp_family_id != "other" and normalize_title(str(a.value))[0] == opp_family_id
        ]
        if matched_role_history:
            role_history_score = 1.0
            role_history_strengths = (
                f"Verified employment role history matches posting family '{opp_family_id}' "
                f"(rule: {opp_family_rule}).",
            )
            role_history_unknowns = ()
            role_history_refs = tuple(a.id for a in matched_role_history)
        else:
            role_history_score = 0.5
            role_history_strengths = ()
            role_history_unknowns = (
                "No verified employment-title evidence establishes a direct match to the posting's role family",
            )
            role_history_refs = tuple(a.id for a in founder_role_assertions)

        w_role_family = weights.get("title_family", 0.0)
        scores.append(MatchDimensionScore(
            dimension_name="title_family_fit",
            raw_score=role_history_score,
            weight=w_role_family,
            weighted_score=role_history_score * w_role_family,
            explanation=(
                f"Posting family '{opp_family_id}' compared with "
                f"{len(founder_role_assertions)} verified employment-title assertion(s)."
            ),
            strengths=role_history_strengths,
            gaps=(),
            unknowns=role_history_unknowns,
            evidence_refs=role_history_refs,
            opportunity_field_refs=("title",),
        ))

        # 10. Education/certification. Only explicit applicant-facing posting
        # requirements are compared, and missing Founder records stay unknown.
        credential_requirements = _credential_requirement_items(opp)
        education_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == predicates.EDUCATION_QUALIFICATION
            and a.verification_status == VerificationStatus.VERIFIED
            and a.polarity == Polarity.POSITIVE
        ]
        certification_states = {
            a.subject_id: (str(a.value).casefold().split(".")[-1], a)
            for a in truth_graph.assertions.values()
            if a.predicate == predicates.CERTIFICATION_STATE
            and a.verification_status == VerificationStatus.VERIFIED
            and a.polarity == Polarity.POSITIVE
        }
        certification_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == predicates.CERTIFICATION_NAME
            and a.verification_status == VerificationStatus.VERIFIED
            and a.polarity == Polarity.POSITIVE
            and a.subject_id in certification_states
            and certification_states[a.subject_id][0] == CertificationState.COMPLETED.value
        ]
        available_credentials: list[tuple[str, str, tuple[str, ...]]] = [
            ("education", str(a.value), (a.id,))
            for a in education_assertions
        ]
        available_credentials.extend(
            (
                "certification",
                str(a.value),
                (a.id, certification_states[a.subject_id][1].id),
            )
            for a in certification_assertions
        )
        if not credential_requirements:
            credential_score = 0.5
            credential_strengths = ()
            credential_unknowns = (
                "Posting does not state an explicit applicant-facing education or certification requirement",
            )
            credential_refs = ()
        else:
            matched_credentials: list[tuple[str, str, tuple[str, ...]]] = []
            unresolved_credentials: list[str] = []
            for kind, requirement, priority in credential_requirements:
                match = next((
                    candidate for candidate in available_credentials
                    if candidate[0] == kind
                    and _credential_requirement_matches(kind, requirement, candidate[1])
                ), None)
                if match:
                    matched_credentials.append((requirement, priority.value, match[2]))
                else:
                    unresolved_credentials.append(
                        f"No verified matching {kind} record for {priority.value.replace('_', ' ')} posting credential: {requirement}"
                    )
            credential_score = 1.0 if not unresolved_credentials else 0.5
            credential_strengths = tuple(
                f"Verified {priority.replace('_', ' ')} credential match: {requirement}"
                for requirement, priority, _ in matched_credentials
            )
            credential_unknowns = tuple(unresolved_credentials)
            credential_refs = tuple(sorted({
                ref for _, _, refs in matched_credentials for ref in refs
            }))

        w_credential = weights.get("education_certification", 0.0)
        scores.append(MatchDimensionScore(
            dimension_name="education_certification_fit",
            raw_score=credential_score,
            weight=w_credential,
            weighted_score=credential_score * w_credential,
            explanation=(
                f"Compared {len(credential_requirements)} explicit education/certification requirement(s) "
                f"with {len(available_credentials)} verified held credential record(s)."
            ),
            strengths=credential_strengths,
            gaps=(),
            unknowns=credential_unknowns,
            evidence_refs=credential_refs,
            opportunity_field_refs=("requirements", "description") if credential_requirements else (),
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
            if a.predicate == predicates.SERVICE_NAME and a.verification_status == VerificationStatus.VERIFIED
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
        desc_and_reqs = (opp.description or "") + " " + " ".join(opp.requirements)
        req_team_match = re.search(r"(\d+)\s*(?:[-+]?\s*person|consultants?|engineers?|team\s*members?|specialists?|staff|delivery\s*team)", desc_and_reqs, re.IGNORECASE)
        req_team_size = int(req_team_match.group(1)) if req_team_match else None
        turnover_req = pm.turnover_required if (pm and pm.turnover_required is not None and pm.turnover_required > 0) else None

        team_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == predicates.CAPACITY_TEAM_SIZE
            and a.verification_status == VerificationStatus.VERIFIED
        ]
        turnover_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == predicates.CAPACITY_ANNUAL_TURNOVER_USD
            and a.verification_status == VerificationStatus.VERIFIED
        ]

        if req_team_size is not None:
            if team_assertions:
                try:
                    founder_team = int(team_assertions[0].value)
                except (ValueError, TypeError):
                    founder_team = 1
                if founder_team >= req_team_size:
                    scope_score = 0.85
                    scope_strengths = (f"Founder delivery team size ({founder_team}) meets opportunity requirement ({req_team_size} staff)",)
                    scope_gaps = ()
                    scope_unknowns = ()
                    scope_refs = (team_assertions[0].id,)
                else:
                    scope_score = 0.15
                    scope_strengths = ()
                    scope_gaps = (f"Opportunity requires delivery team of {req_team_size} staff, exceeding founder team size ({founder_team})",)
                    scope_unknowns = ()
                    scope_refs = (team_assertions[0].id,)
            else:
                scope_score = 0.50
                scope_strengths = ()
                scope_gaps = ()
                scope_unknowns = (f"Opportunity requires delivery team of {req_team_size}; founder team size unasserted in truth graph",)
                scope_refs = ()
                uncertainty_acc += 0.20

        elif turnover_req is not None:
            if turnover_assertions:
                try:
                    founder_turnover = float(turnover_assertions[0].value)
                except (ValueError, TypeError):
                    founder_turnover = 0.0
                if founder_turnover >= turnover_req:
                    scope_score = 0.85
                    scope_strengths = (f"Founder annual turnover ({founder_turnover}) meets opportunity requirement ({turnover_req})",)
                    scope_gaps = ()
                    scope_unknowns = ()
                    scope_refs = (turnover_assertions[0].id,)
                else:
                    scope_score = 0.15
                    scope_strengths = ()
                    scope_gaps = (f"Opportunity requires annual turnover ({turnover_req}), exceeding founder turnover ({founder_turnover})",)
                    scope_unknowns = ()
                    scope_refs = (turnover_assertions[0].id,)
            else:
                scope_score = 0.50
                scope_strengths = ()
                scope_gaps = ()
                scope_unknowns = (f"Opportunity requires annual turnover ({turnover_req}); founder turnover unasserted",)
                scope_refs = ()
                uncertainty_acc += 0.20

        else:
            # Opportunity has no explicit scope/team/turnover threshold to compare against
            scope_score = 0.50
            scope_strengths = ()
            scope_gaps = ()
            scope_unknowns = ("Opportunity terms do not specify explicit team/capacity thresholds for comparison",)
            scope_refs = ()
            uncertainty_acc += 0.10

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
            if a.predicate == predicates.PORTFOLIO_TITLE and a.verification_status == VerificationStatus.VERIFIED
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
        comp = opp.compensation
        if comp is not None and comp.min_amount is not None:
            matching_target: float | None = None
            interval_name = comp.interval.value if hasattr(comp.interval, "value") else str(comp.interval)

            if comp.interval == CompensationInterval.PROJECT:
                matching_target = getattr(self.policy, "min_target_project_budget", None)
            elif comp.interval == CompensationInterval.DAILY:
                matching_target = getattr(self.policy, "min_target_daily_rate", None)
            elif comp.interval == CompensationInterval.HOURLY:
                matching_target = getattr(self.policy, "min_target_hourly_rate", None)
            elif comp.interval == CompensationInterval.YEARLY:
                matching_target = getattr(self.policy, "min_target_yearly_compensation", None) or getattr(self.policy, "min_target_compensation", None)

            if matching_target is not None:
                max_amt = comp.max_amount if comp.max_amount is not None else comp.min_amount
                if max_amt >= matching_target:
                    bud_score = 1.0
                    bud_strengths = (f"Procurement compensation ({comp.min_amount}-{comp.max_amount or ''} {comp.currency or ''} {interval_name}) meets founder target ({matching_target})",)
                    bud_gaps = ()
                    bud_unknowns = ()
                else:
                    bud_score = 0.20
                    bud_strengths = ()
                    bud_gaps = (f"Procurement compensation ({max_amt} {interval_name}) below founder target ({matching_target})",)
                    bud_unknowns = ()
            else:
                bud_score = 0.50
                bud_strengths = ()
                bud_gaps = ()
                bud_unknowns = (f"Procurement budget stated ({comp.min_amount} {comp.currency or ''} {interval_name}); compatible founder {interval_name} target economics unconfigured in policy",)
                uncertainty_acc += 0.1
        else:
            bud_score = 0.50
            bud_strengths = ()
            bud_gaps = ()
            bud_unknowns = ("Procurement budget unstated in notice metadata",)
            uncertainty_acc += 0.1

        scores.append(MatchDimensionScore(
            dimension_name="budget_fit",
            raw_score=bud_score,
            weight=w_bud,
            weighted_score=bud_score * w_bud,
            explanation="Procurement budget evaluated against founder economic policy.",
            strengths=bud_strengths,
            gaps=bud_gaps,
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
            prohibited = getattr(self.policy, "prohibited_jurisdictions", ())
            approved = getattr(self.policy, "approved_delivery_jurisdictions", ())
            if prohibited and any(p.casefold() in buyer_loc.casefold() for p in prohibited):
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
