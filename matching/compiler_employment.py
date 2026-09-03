"""Truth-Locked Employment Artifact Compiler for OpportunityOS.

Compiles opportunity-specific tailored CVs, application narratives, and cover responses
from versioned templates and TruthGraph assertions. Master CVs are immutable. Every factual
statement is locked to an active AtomicAssertion or MetricAssertion without factual drift.
"""
from __future__ import annotations

import datetime
from typing import Any

from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import VerificationStatus

from .document_model import (
    CompiledDocument,
    build_achievements_section,
    build_certifications_section,
    build_education_section,
    build_experience_section,
    build_identity_block,
    build_languages_section,
    build_projects_section,
    build_skills_section,
    build_summary_section,
)
from .models import (
    ArtifactSection,
    ArtifactType,
    CommitmentStatus,
    ForwardCommitment,
    GeneratedClaim,
    TailoredArtifact,
    TailoringPolicy,
)


class EmploymentArtifactCompiler:
    """Compiles opportunity-specific employment application artifacts locked to truth graph."""

    def __init__(self, policy: TailoringPolicy | None = None) -> None:
        self.policy = policy or TailoringPolicy()

    def compile_tailored_cv(
        self,
        opp: Opportunity,
        truth_graph: TruthGraph,
        compiled_at: str = "2026-08-30",
    ) -> TailoredArtifact:
        """Compile an opportunity-specific tailored CV strictly from verified
        assertions. Assembly happens through `matching.document_model`'s
        section builders: this method only picks the order sections appear
        in and flattens the resulting `CompiledDocument` into the
        `TailoredArtifact` shape the exporters, `ats_quality`, and
        `artifact_validation` already consume."""
        identity = build_identity_block(truth_graph)
        document = CompiledDocument(
            title=f"Tailored Curriculum Vitae — {opp.organization} ({opp.title})",
            identity=identity,
            sections=(
                build_summary_section(truth_graph, opp),
                build_skills_section(truth_graph, opp, self.policy.max_skills_highlighted),
                build_experience_section(truth_graph, opp, self.policy.max_experience_bullets_per_role),
                build_achievements_section(truth_graph),
                build_education_section(truth_graph),
                build_certifications_section(truth_graph),
                build_projects_section(truth_graph),
                build_languages_section(truth_graph),
            ),
        )
        sections_flat, claims_flat, omitted_flat = document.flatten()
        sections: list[ArtifactSection] = [sec for sec in sections_flat if sec.items or sec.content]
        claims: list[GeneratedClaim] = list(claims_flat)

        # Forward commitments for employment (standard availability/notice)
        commitments = (
            ForwardCommitment(
                commitment_type="availability",
                description="Work schedule and notice period",
                status=CommitmentStatus.RESOLVED if self.policy.default_notice_period_days is not None else CommitmentStatus.UNRESOLVED,
                value=f"{self.policy.default_notice_period_days} days notice" if self.policy.default_notice_period_days is not None else "UNRESOLVED (RED): Unspecified notice period",
                policy_source="TailoringPolicy.default_notice_period_days" if self.policy.default_notice_period_days is not None else "",
            ),
        )

        return TailoredArtifact(
            artifact_id=f"artifact-cv-{opp.id}",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id=opp.id,
            opportunity_content_hash=opp.content_hash,
            template_version="cv-v1.0",
            policy_version=self.policy.version,
            title=f"Tailored Curriculum Vitae — {opp.organization} ({opp.title})",
            sections=tuple(sections),
            generated_claims=tuple(claims),
            commitment_checklist=commitments,
            compiled_at=compiled_at,
            omitted_items=omitted_flat,
        )

    def compile_cover_letter(
        self,
        opp: Opportunity,
        truth_graph: TruthGraph,
        compiled_at: str = "2026-08-30",
    ) -> TailoredArtifact:
        """Compile an opportunity-specific cover letter narrative locked to truth graph.

        ADR-0014 (revised after council review): every founder-specific fact
        is an atomic claim citing exactly the evidence that supports it.
        Connective prose -- the greeting, the expression of interest, and
        naming the target role/employer -- carries no founder-specific fact
        and is emitted as a NARRATIVE segment (`policy_source="NARRATIVE"`),
        which `ClaimValidator.validate_narrative` checks only for prohibited
        concepts and red lines, never for evidence coverage.

        An earlier revision combined the founder's title with the target
        role/employer name in one claim (admitting the opportunity's own
        words under an "opportunity-provenanced" term class). Independent
        council review found that class applied unconditionally to every
        claim in the document, not just the one that embedded an opportunity
        field, and was driven by scraped, third-party posting text -- see
        ADR-0014's "Residual exposure and review history". That class was
        removed entirely. The role/employer name now appears ONLY inside a
        NARRATIVE segment that carries no founder-specific value at all, so
        it needs no special admissibility rule; the founder's title, when
        known, is a separate atomic claim that never mentions the
        opportunity's own words.
        """
        sections: list[ArtifactSection] = []
        claims: list[GeneratedClaim] = []

        title_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == "employment.title" and a.verification_status == VerificationStatus.VERIFIED
        ]
        founder_skills = [
            a for a in truth_graph.assertions.values()
            if a.predicate == "skill.name" and a.verification_status == VerificationStatus.VERIFIED
        ]

        # --- Introduction: two NARRATIVE segments (zero founder-specific
        # values) plus, if a title is known, one separate atomic claim. -----
        greeting_text = "I am writing to express my interest in the following opportunity."
        role_text = f"Applying for the {opp.title} role at {opp.organization}."
        intro_parts = [greeting_text, role_text]
        claims.append(GeneratedClaim(
            claim_id="claim-cover-greeting",
            text=greeting_text,
            section_id="introduction",
            assertion_ids=(),
            evidence_ids=(),
            predicate="",
            authorized_value="",
            is_forward_commitment=False,
            policy_source="NARRATIVE",
        ))
        claims.append(GeneratedClaim(
            claim_id="claim-cover-role-narrative",
            text=role_text,
            section_id="introduction",
            assertion_ids=(),
            evidence_ids=(),
            predicate="",
            authorized_value="",
            is_forward_commitment=False,
            policy_source="NARRATIVE",
        ))

        intro_aids: tuple[str, ...] = ()
        intro_eids: tuple[str, ...] = ()
        if title_assertions:
            top_title = str(title_assertions[0].value)
            background_text = f"Background: {top_title}."
            intro_parts.append(background_text)
            intro_aids = (title_assertions[0].id,)
            intro_eids = title_assertions[0].evidence_ids
            claims.append(GeneratedClaim(
                claim_id="claim-cover-background",
                text=background_text,
                section_id="introduction",
                assertion_ids=intro_aids,
                evidence_ids=intro_eids,
                predicate="employment.title",
                authorized_value=top_title,
                is_forward_commitment=False,
            ))

        sections.append(ArtifactSection(
            section_id="introduction",
            heading="Introduction & Motivation",
            content=" ".join(intro_parts),
            items=(),
            assertion_ids=intro_aids,
            evidence_ids=intro_eids,
        ))

        # --- Alignment Body Section: one atomic claim per cited skill -------
        opp_skills_cf = {s.casefold() for s in opp.skills}
        relevant_skills = [s for s in founder_skills if str(s.value).casefold() in opp_skills_cf]

        alignment_items: tuple[str, ...] = ()
        alignment_aids: tuple[str, ...] = ()
        alignment_eids: tuple[str, ...] = ()

        if relevant_skills:
            lead_text = "My relevant competencies for this role include the following:"
            alignment_parts = [lead_text]
            claims.append(GeneratedClaim(
                claim_id="claim-cover-skills-lead",
                text=lead_text,
                section_id="alignment",
                assertion_ids=(),
                evidence_ids=(),
                predicate="",
                authorized_value="",
                is_forward_commitment=False,
                policy_source="NARRATIVE",
            ))
            alignment_items = tuple(str(s.value) for s in relevant_skills)
            alignment_aids = tuple(s.id for s in relevant_skills)
            alignment_eids = tuple(sorted(set(ev for s in relevant_skills for ev in s.evidence_ids)))
            for s in relevant_skills:
                claims.append(GeneratedClaim(
                    claim_id=f"claim-cover-skill-{s.id}",
                    text=str(s.value),
                    section_id="alignment",
                    assertion_ids=(s.id,),
                    evidence_ids=s.evidence_ids,
                    predicate="skill.name",
                    authorized_value=str(s.value),
                    is_forward_commitment=False,
                ))
        elif title_assertions:
            lead_text = "My background outlined above provides a foundation for this role."
            alignment_parts = [lead_text]
            claims.append(GeneratedClaim(
                claim_id="claim-cover-alignment-fallback",
                text=lead_text,
                section_id="alignment",
                assertion_ids=(),
                evidence_ids=(),
                predicate="",
                authorized_value="",
                is_forward_commitment=False,
                policy_source="NARRATIVE",
            ))
        else:
            lead_text = f"I look forward to discussing how my experience aligns with {opp.organization}'s goals."
            alignment_parts = [lead_text]
            claims.append(GeneratedClaim(
                claim_id="claim-cover-alignment-empty",
                text=lead_text,
                section_id="alignment",
                assertion_ids=(),
                evidence_ids=(),
                predicate="",
                authorized_value="",
                is_forward_commitment=False,
                policy_source="NARRATIVE",
            ))

        sections.append(ArtifactSection(
            section_id="alignment",
            heading="Relevant Experience & Value Proposition",
            content=" ".join(alignment_parts),
            items=alignment_items,
            assertion_ids=alignment_aids,
            evidence_ids=alignment_eids,
        ))

        if self.policy.default_availability_hours_per_week is not None:
            commitments = (
                ForwardCommitment(
                    commitment_type="availability",
                    description="Weekly engagement availability",
                    status=CommitmentStatus.RESOLVED,
                    value=f"{self.policy.default_availability_hours_per_week} hours / week availability",
                    policy_source="TailoringPolicy.default_availability_hours_per_week",
                ),
            )
        else:
            commitments = (
                ForwardCommitment(
                    commitment_type="availability",
                    description="Weekly engagement availability",
                    status=CommitmentStatus.UNRESOLVED,
                    value="UNRESOLVED (RED): Availability not configured in policy",
                    policy_source="",
                ),
            )

        return TailoredArtifact(
            artifact_id=f"artifact-cover-{opp.id}",
            artifact_type=ArtifactType.COVER_LETTER,
            opportunity_id=opp.id,
            opportunity_content_hash=opp.content_hash,
            template_version="cover-v1.0",
            policy_version=self.policy.version,
            title=f"Application Cover Narrative — {opp.organization} ({opp.title})",
            sections=tuple(sections),
            generated_claims=tuple(claims),
            commitment_checklist=commitments,
            compiled_at=compiled_at,
        )
