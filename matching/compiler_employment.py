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
    OmittedItem,
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
        omitted_items: list = []

        identity = build_identity_block(truth_graph)
        if identity is not None:
            sections.append(identity.section.to_artifact_section())
            claims.extend(identity.section.claims)
            omitted_items.extend(identity.section.omitted)

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
        # BRIEF-FR-006 council review #2 MAJOR 8: `title_assertions[0]` was
        # dict insertion order, not recency, so a founder with an old
        # internship ingested first opened every cover letter with it. Prefer
        # `identity.headline` (the founder's own current, chosen headline --
        # already rendered and cited in the identity block above); fall back
        # to the most-recently-started verified title only if the pack has no
        # headline at all.
        headline_claim = None
        if identity is not None:
            headline_claim = next(
                (item.claim for item in identity.section.items if item.claim.predicate == "identity.headline"),
                None,
            )
        if headline_claim is not None:
            background_text = f"Background: {headline_claim.text}."
            intro_parts.append(background_text)
            intro_aids = headline_claim.assertion_ids
            intro_eids = headline_claim.evidence_ids
            claims.append(GeneratedClaim(
                claim_id="claim-cover-background",
                text=background_text,
                section_id="introduction",
                assertion_ids=intro_aids,
                evidence_ids=intro_eids,
                predicate="identity.headline",
                authorized_value=headline_claim.text,
                is_forward_commitment=False,
            ))
        elif title_assertions:
            most_recent_title = max(
                title_assertions, key=lambda a: (a.effective_from is not None, a.effective_from or datetime.date.min)
            )
            top_title = str(most_recent_title.value)
            background_text = f"Background: {top_title}."
            intro_parts.append(background_text)
            intro_aids = (most_recent_title.id,)
            intro_eids = most_recent_title.evidence_ids
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

        # --- Motivation: founder-authored `approved_phrases` used verbatim
        # only. If the pack carries none, the letter omits this paragraph
        # entirely rather than inventing motivation text (work order D1.6).
        approved_phrases = list(truth_graph.approved_phrases.values())
        if approved_phrases:
            motivation_phrases = [p for p in approved_phrases if "motivation" in p.tags] or approved_phrases
            closing_phrases = [p for p in approved_phrases if "closing" in p.tags]
            selected_phrases = motivation_phrases[:1] + closing_phrases[:1]
            motivation_items: list[str] = []
            motivation_aids: list[str] = []
            motivation_eids: list[str] = []
            for phrase in selected_phrases:
                motivation_items.append(phrase.text)
                # BRIEF-FR-006 council review #2 MAJOR 7: `phrase.id` (e.g.
                # "phrase-founder-motivation-1") is the `ApprovedPhrase`
                # ENTITY id, not the projected `approved_phrase.text`
                # assertion id `truth/graph.py` actually creates (a derived
                # "as_<subject>_<predicate>_<value>" id). Citing the entity id
                # made `ArtifactClaimValidator.validate_artifact` reject every
                # cover letter with "references non-existent assertion ID" --
                # cite the real projected assertion instead.
                phrase_assertion = next(
                    (
                        a for a in truth_graph.assertions.values()
                        if a.predicate == "approved_phrase.text" and a.subject_id == phrase.id
                    ),
                    None,
                )
                phrase_aid = phrase_assertion.id if phrase_assertion is not None else phrase.id
                phrase_eids = phrase_assertion.evidence_ids if phrase_assertion is not None else phrase.evidence_ids
                motivation_aids.append(phrase_aid)
                motivation_eids.extend(phrase_eids)
                claims.append(GeneratedClaim(
                    claim_id=f"claim-cover-phrase-{phrase.id}",
                    text=phrase.text,
                    section_id="motivation",
                    assertion_ids=(phrase_aid,),
                    evidence_ids=phrase_eids,
                    predicate="approved_phrase.text",
                    authorized_value=phrase.text,
                    is_forward_commitment=False,
                ))
            unused_phrases = [p for p in approved_phrases if p.id not in {ph.id for ph in selected_phrases}]
            omitted_items.extend(
                OmittedItem(
                    section_id="motivation",
                    text=p.text,
                    reason="not the selected motivation/closing phrase for this letter",
                    claim_id=f"claim-cover-phrase-{p.id}",
                )
                for p in unused_phrases
            )
            sections.append(ArtifactSection(
                section_id="motivation",
                heading="Motivation",
                content="",  # MAJOR 5: items already carries this text; avoid doubling it
                items=tuple(motivation_items),
                assertion_ids=tuple(motivation_aids),
                evidence_ids=tuple(sorted(set(motivation_eids))),
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
            omitted_items=tuple(omitted_items),
        )
