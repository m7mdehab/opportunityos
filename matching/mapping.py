"""Requirement ↔ Evidence Mapping Engine for OpportunityOS.

Produces explicit requirement-to-evidence mappings for evaluated opportunities,
classifying each material requirement as SUPPORTED, PARTIALLY_SUPPORTED, GAP,
UNKNOWN, or NOT_APPLICABLE. Prevents laundering adjacent skills into claimed skills
or planned credentials into completed credentials.
"""
from __future__ import annotations

import re
from typing import Any

from opportunity.models import Opportunity
from opportunity.normalization import extract_skills_from_text
from truth import predicates
from truth.graph import TruthGraph
from truth.models import Polarity, VerificationStatus

from .models import (
    RequirementEvidenceMap,
    RequirementMapping,
    RequirementPriority,
    RequirementSupportStatus,
)
from .requirements import classify_requirement_text
from .skills import classify_skill_priorities


class RequirementMapper:
    """Maps opportunity requirements to verified TruthGraph assertions and evidence records."""

    def map_requirements(self, opp: Opportunity, truth_graph: TruthGraph) -> RequirementEvidenceMap:
        """Construct an explicit requirement-to-evidence map for an opportunity."""
        mappings: list[RequirementMapping] = []

        # 1. Map explicit skills from opportunity
        founder_skills = {
            str(a.value).casefold(): a
            for a in truth_graph.assertions.values()
            if a.predicate == predicates.SKILL_NAME
            and a.verification_status == VerificationStatus.VERIFIED
            and a.polarity == Polarity.POSITIVE
        }
        skill_names = opp.skills or extract_skills_from_text(opp.description)
        skill_priorities = classify_skill_priorities(opp.description, tuple(skill_names))
        for skill in skill_names:
            skill_cf = skill.casefold()
            priority = skill_priorities.get(skill_cf, RequirementPriority.UNKNOWN)
            if skill_cf in founder_skills:
                assertion = founder_skills[skill_cf]
                mappings.append(RequirementMapping(
                    requirement_text=f"Proficiency in {skill}",
                    requirement_type="skill",
                    status=RequirementSupportStatus.SUPPORTED,
                    supporting_assertion_ids=(assertion.id,),
                    supporting_evidence_ids=assertion.evidence_ids,
                    confidence=1.0,
                    rationale=f"Direct verified skill match in truth graph with {len(assertion.evidence_ids)} supporting evidence records.",
                    requirement_priority=priority,
                ))
            else:
                status = (
                    RequirementSupportStatus.NOT_APPLICABLE
                    if priority == RequirementPriority.CONTEXTUAL
                    else RequirementSupportStatus.UNKNOWN
                    if priority == RequirementPriority.UNKNOWN
                    else RequirementSupportStatus.GAP
                )
                mappings.append(RequirementMapping(
                    requirement_text=f"Proficiency in {skill}",
                    requirement_type="skill",
                    status=status,
                    supporting_assertion_ids=(),
                    supporting_evidence_ids=(),
                    confidence=0.5 if status == RequirementSupportStatus.UNKNOWN else 1.0,
                    rationale=(
                        "This is company or role context, not an applicant requirement."
                        if status == RequirementSupportStatus.NOT_APPLICABLE
                        else "The posting does not establish whether this skill mention is an applicant requirement."
                        if status == RequirementSupportStatus.UNKNOWN
                        else f"Skill '{skill}' is not attested in founder verified truth graph."
                    ),
                    requirement_priority=priority,
                ))

        # 2. Map structured requirements / responsibilities
        items_to_map = [
            *((req, "requirements") for req in opp.requirements),
            *((responsibility, "responsibilities") for responsibility in opp.responsibilities),
        ]
        if not items_to_map and opp.description:
            # Fallback: extract sentences from description
            sentences = re.split(r"(?<=[.!?])\s+", opp.description)
            items_to_map = [(s.strip(), None) for s in sentences if len(s.strip()) > 30][:6]

        for req, source_section in items_to_map:
            req_cf = req.casefold()
            priority = classify_requirement_text(req, source_section=source_section)
            # Filter candidate assertions strictly to type-compatible predicates
            matched_assertions = []
            for a in truth_graph.assertions.values():
                if a.verification_status != VerificationStatus.VERIFIED:
                    continue
                if a.predicate not in predicates.RESPONSIBILITY_SCOPE_PREDICATES:
                    continue
                val_str = str(a.value).casefold()
                if len(val_str) > 3 and val_str in req_cf:
                    matched_assertions.append(a)

            if matched_assertions:
                ev_ids: list[str] = []
                for a in matched_assertions:
                    ev_ids.extend(a.evidence_ids)
                mappings.append(RequirementMapping(
                    requirement_text=req,
                    requirement_type="responsibility",
                    status=RequirementSupportStatus.SUPPORTED if len(matched_assertions) >= 2 else RequirementSupportStatus.PARTIALLY_SUPPORTED,
                    supporting_assertion_ids=tuple(a.id for a in matched_assertions),
                    supporting_evidence_ids=tuple(sorted(set(ev_ids))),
                    confidence=0.85,
                    rationale=f"Substantiated by {len(matched_assertions)} verified truth graph assertion(s).",
                    requirement_priority=priority,
                ))
            else:
                # If it's a general corporate statement, mark as NOT_APPLICABLE or UNKNOWN
                if any(w in req_cf for w in ("equal opportunity", "benefits", "health insurance", "401k", "perks", "unlimited pto")):
                    mappings.append(RequirementMapping(
                        requirement_text=req,
                        requirement_type="other",
                        status=RequirementSupportStatus.NOT_APPLICABLE,
                        supporting_assertion_ids=(),
                        supporting_evidence_ids=(),
                        confidence=1.0,
                        rationale="Company policy / employment perk clause, not an applicant requirement.",
                        requirement_priority=RequirementPriority.CONTEXTUAL,
                    ))
                else:
                    mappings.append(RequirementMapping(
                        requirement_text=req,
                        requirement_type="responsibility",
                        status=RequirementSupportStatus.UNKNOWN,
                        supporting_assertion_ids=(),
                        supporting_evidence_ids=(),
                        confidence=0.5,
                        rationale="Requirement requires founder review or specific project alignment.",
                        requirement_priority=priority,
                    ))

        # Compute overall coverage score
        coverage_items = [
            m for m in mappings
            if m.requirement_priority in {
                RequirementPriority.MANDATORY,
                RequirementPriority.STRONGLY_PREFERRED,
                RequirementPriority.NICE_TO_HAVE,
            }
        ]
        if coverage_items:
            supported_count = sum(1 for m in coverage_items if m.status == RequirementSupportStatus.SUPPORTED)
            partial_count = sum(1 for m in coverage_items if m.status == RequirementSupportStatus.PARTIALLY_SUPPORTED)
            coverage = (supported_count + (partial_count * 0.5)) / len(coverage_items)
        else:
            coverage = 0.5

        return RequirementEvidenceMap(
            opportunity_id=opp.id,
            mappings=tuple(mappings),
            coverage_score=round(coverage, 3),
        )
