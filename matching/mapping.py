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
from truth.graph import TruthGraph
from truth.models import VerificationStatus

from .models import (
    RequirementEvidenceMap,
    RequirementMapping,
    RequirementSupportStatus,
)


class RequirementMapper:
    """Maps opportunity requirements to verified TruthGraph assertions and evidence records."""

    def map_requirements(self, opp: Opportunity, truth_graph: TruthGraph) -> RequirementEvidenceMap:
        """Construct an explicit requirement-to-evidence map for an opportunity."""
        mappings: list[RequirementMapping] = []

        # 1. Map explicit skills from opportunity
        founder_skills = {
            str(a.value).casefold(): a
            for a in truth_graph.assertions.values()
            if a.predicate == "skill.name" and a.verification_status == VerificationStatus.VERIFIED
        }
        for skill in opp.skills:
            skill_cf = skill.casefold()
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
                ))
            else:
                mappings.append(RequirementMapping(
                    requirement_text=f"Proficiency in {skill}",
                    requirement_type="skill",
                    status=RequirementSupportStatus.GAP,
                    supporting_assertion_ids=(),
                    supporting_evidence_ids=(),
                    confidence=1.0,
                    rationale=f"Skill '{skill}' is not attested in founder verified truth graph.",
                ))

        # 2. Map structured requirements / responsibilities
        items_to_map = list(opp.requirements) + list(opp.responsibilities)
        if not items_to_map and opp.description:
            # Fallback: extract sentences from description
            sentences = re.split(r"(?<=[.!?])\s+", opp.description)
            items_to_map = [s.strip() for s in sentences if len(s.strip()) > 30][:6]

        for req in items_to_map:
            req_cf = req.casefold()
            # Filter candidate assertions strictly to type-compatible predicates
            matched_assertions = []
            for a in truth_graph.assertions.values():
                if a.verification_status != VerificationStatus.VERIFIED:
                    continue
                if a.predicate not in (
                    "responsibility.item",
                    "employment.role_description",
                    "service.name",
                    "experience.summary",
                    "achievement.description",
                ):
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
                    ))

        # Compute overall coverage score
        if mappings:
            supported_count = sum(1 for m in mappings if m.status in {RequirementSupportStatus.SUPPORTED, RequirementSupportStatus.NOT_APPLICABLE})
            partial_count = sum(1 for m in mappings if m.status == RequirementSupportStatus.PARTIALLY_SUPPORTED)
            coverage = (supported_count + (partial_count * 0.5)) / len(mappings)
        else:
            coverage = 0.5

        return RequirementEvidenceMap(
            opportunity_id=opp.id,
            mappings=tuple(mappings),
            coverage_score=round(coverage, 3),
        )
