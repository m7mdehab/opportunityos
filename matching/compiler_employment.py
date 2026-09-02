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
        """Compile an opportunity-specific tailored CV strictly from verified assertions."""
        sections: list[ArtifactSection] = []
        claims: list[GeneratedClaim] = []

        # 1. Professional Summary Section
        title_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == "employment.title" and a.verification_status == VerificationStatus.VERIFIED
        ]
        founder_skills = [
            a for a in truth_graph.assertions.values()
            if a.predicate == "skill.name" and a.verification_status == VerificationStatus.VERIFIED
        ]
        # Prioritize skills appearing in opportunity requirements
        opp_skills_cf = {s.casefold() for s in opp.skills}
        relevant_skills = [s for s in founder_skills if str(s.value).casefold() in opp_skills_cf]
        other_skills = [s for s in founder_skills if str(s.value).casefold() not in opp_skills_cf]
        ordered_skills = (relevant_skills + other_skills)[:self.policy.max_skills_highlighted]

        if title_assertions:
            top_title = str(title_assertions[0].value)
            if ordered_skills:
                skill_str = ", ".join(str(s.value) for s in ordered_skills[:3])
                summary_text = f"Professional background as {top_title} with verified competencies in {skill_str}."
                summary_aids = (title_assertions[0].id,) + tuple(s.id for s in ordered_skills[:3])
                summary_eids = tuple(sorted(set(title_assertions[0].evidence_ids + tuple(ev for s in ordered_skills[:3] for ev in s.evidence_ids))))
            else:
                summary_text = f"Professional background as {top_title}."
                summary_aids = (title_assertions[0].id,)
                summary_eids = title_assertions[0].evidence_ids

            sec_summary = ArtifactSection(
                section_id="summary",
                heading="Professional Summary",
                content=summary_text,
                items=(),
                assertion_ids=summary_aids,
                evidence_ids=summary_eids,
            )
            sections.append(sec_summary)
            claims.append(GeneratedClaim(
                claim_id="claim-summary-title",
                text=summary_text,
                section_id="summary",
                assertion_ids=summary_aids,
                evidence_ids=summary_eids,
                predicate="summary",
                authorized_value=summary_text,
                is_forward_commitment=False,
            ))

        # 2. Selected Relevant Technical Skills Section
        if ordered_skills:
            skill_names = tuple(str(s.value) for s in ordered_skills)
            sec_skills = ArtifactSection(
                section_id="skills",
                heading="Technical Skills & Competencies",
                content=", ".join(skill_names),
                items=skill_names,
                assertion_ids=tuple(s.id for s in ordered_skills),
                evidence_ids=tuple(sorted(set(ev for s in ordered_skills for ev in s.evidence_ids))),
            )
            sections.append(sec_skills)
            for s in ordered_skills:
                claims.append(GeneratedClaim(
                    claim_id=f"claim-skill-{s.id}",
                    text=str(s.value),
                    section_id="skills",
                    assertion_ids=(s.id,),
                    evidence_ids=s.evidence_ids,
                    predicate="skill.name",
                    authorized_value=str(s.value),
                    is_forward_commitment=False,
                ))

        # 3. Relevant Professional Experience Section
        emp_records = {}
        for a in truth_graph.assertions.values():
            if a.verification_status != VerificationStatus.VERIFIED:
                continue
            if a.predicate.startswith("employment."):
                subj = a.subject_id
                emp_records.setdefault(subj, []).append(a)

        exp_items: list[str] = []
        exp_assertion_ids: list[str] = []
        exp_evidence_ids: list[str] = []

        for subj, assertions in emp_records.items():
            field_dict = {a.predicate.split(".", 1)[1]: str(a.value) for a in assertions}
            title = field_dict.get("title")
            org = field_dict.get("organization")
            start = field_dict.get("start_date")
            end = field_dict.get("end_date")

            if title and org:
                exp_header = f"{title} | {org}"
            elif title:
                exp_header = title
            elif org:
                exp_header = org
            else:
                exp_header = f"Experience Record ({subj})"

            if start and end:
                exp_header += f" ({start} – {end})"
            elif start:
                exp_header += f" ({start} – )"
            elif end:
                exp_header += f" ( – {end})"

            exp_items.append(exp_header)
            exp_assertion_ids.extend(a.id for a in assertions)
            for a in assertions:
                exp_evidence_ids.extend(a.evidence_ids)

            claims.append(GeneratedClaim(
                claim_id=f"claim-emp-{subj}",
                text=exp_header,
                section_id="experience",
                assertion_ids=tuple(a.id for a in assertions),
                evidence_ids=tuple(ev for a in assertions for ev in a.evidence_ids),
                predicate="employment.record",
                authorized_value=exp_header,
                is_forward_commitment=False,
            ))

        if exp_items:
            sec_exp = ArtifactSection(
                section_id="experience",
                heading="Professional Experience",
                content="\n".join(exp_items),
                items=tuple(exp_items),
                assertion_ids=tuple(exp_assertion_ids),
                evidence_ids=tuple(sorted(set(exp_evidence_ids))),
            )
            sections.append(sec_exp)

        # 4. Verified Metrics & Key Achievements Section
        metric_assertions = [
            m for m in truth_graph.metrics.values()
            if m.verification_status == VerificationStatus.VERIFIED
        ]
        metric_items: list[str] = []
        metric_assertion_ids: list[str] = []
        metric_evidence_ids: list[str] = []
        for m in metric_assertions:
            unit_str = f" {m.unit}" if m.unit and m.unit not in ("count", "number") else ""
            m_text = f"{m.context}: {m.numeric_value}{unit_str}"
            metric_items.append(m_text)
            metric_assertion_ids.append(m.id)
            metric_evidence_ids.extend(m.evidence_ids)

            claims.append(GeneratedClaim(
                claim_id=f"claim-metric-{m.id}",
                text=m_text,
                section_id="achievements",
                assertion_ids=(m.id,),
                evidence_ids=m.evidence_ids,
                predicate="metric",
                authorized_value=m_text,
                is_forward_commitment=False,
            ))

        if metric_items:
            sec_metrics = ArtifactSection(
                section_id="achievements",
                heading="Selected Quantified Achievements",
                content="\n".join(metric_items),
                items=tuple(metric_items),
                assertion_ids=tuple(metric_assertion_ids),
                evidence_ids=tuple(sorted(set(metric_evidence_ids))),
            )
            sections.append(sec_metrics)

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
        )

    def compile_cover_letter(
        self,
        opp: Opportunity,
        truth_graph: TruthGraph,
        compiled_at: str = "2026-08-30",
    ) -> TailoredArtifact:
        """Compile an opportunity-specific cover letter narrative locked to truth graph."""
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

        if title_assertions:
            top_title = str(title_assertions[0].value)
            intro_text = (
                f"I am writing to express my interest in the {opp.title} position at {opp.organization}. "
                f"My verified professional background as {top_title} aligns with the requirements of this role."
            )
            intro_aids = (title_assertions[0].id,)
            intro_eids = title_assertions[0].evidence_ids
        else:
            intro_text = f"I am writing to express my interest in the {opp.title} position at {opp.organization}."
            intro_aids = ()
            intro_eids = ()

        sections.append(ArtifactSection(
            section_id="introduction",
            heading="Introduction & Motivation",
            content=intro_text,
            items=(),
            assertion_ids=intro_aids,
            evidence_ids=intro_eids,
        ))
        claims.append(GeneratedClaim(
            claim_id="claim-cover-intro",
            text=intro_text,
            section_id="introduction",
            assertion_ids=intro_aids,
            evidence_ids=intro_eids,
            predicate="employment.title" if intro_aids else "",
            authorized_value=top_title if title_assertions else "",
            is_forward_commitment=False,
        ))

        # Alignment Body Section
        opp_skills_cf = {s.casefold() for s in opp.skills}
        relevant_skills = [s for s in founder_skills if str(s.value).casefold() in opp_skills_cf]
        if relevant_skills:
            skill_names = ", ".join(str(s.value) for s in relevant_skills)
            body_text = f"My verified competencies in {skill_names} directly correspond to {opp.organization}'s technical scope."
            body_aids = tuple(s.id for s in relevant_skills)
            body_eids = tuple(sorted(set(ev for s in relevant_skills for ev in s.evidence_ids)))
        elif title_assertions:
            body_text = f"My verified experience as {top_title} provides solid background for this position."
            body_aids = (title_assertions[0].id,)
            body_eids = title_assertions[0].evidence_ids
        else:
            body_text = f"I look forward to discussing how my experience aligns with {opp.organization}'s engineering goals."
            body_aids = ()
            body_eids = ()

        sections.append(ArtifactSection(
            section_id="alignment",
            heading="Relevant Experience & Value Proposition",
            content=body_text,
            items=(),
            assertion_ids=body_aids,
            evidence_ids=body_eids,
        ))
        claims.append(GeneratedClaim(
            claim_id="claim-cover-body",
            text=body_text,
            section_id="alignment",
            assertion_ids=body_aids,
            evidence_ids=body_eids,
            predicate="skill.name" if relevant_skills else ("employment.title" if title_assertions else ""),
            authorized_value=body_text,
            is_forward_commitment=False,
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
