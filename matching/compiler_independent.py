"""Truth-Locked Independent Opportunity Compiler for OpportunityOS.

Compiles proposals, Expressions of Interest (EOI), capability statements, and RFP response
scaffolds for procurement and freelance opportunities. Historical assertions are locked to
TruthGraph EvidenceClaims. Forward-looking commitments (pricing, availability, delivery,
staffing, legal entity) must derive from explicit founder policy; unconfigured commitments
are marked UNRESOLVED (RED) and never fabricated.
"""
from __future__ import annotations

from typing import Any

from opportunity.models import Opportunity, Track
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


class IndependentArtifactCompiler:
    """Compiles truth-locked proposal and consulting artifacts for procurement/freelance tracks."""

    def __init__(self, policy: TailoringPolicy | None = None) -> None:
        self.policy = policy or TailoringPolicy()

    def compile_proposal(
        self,
        opp: Opportunity,
        truth_graph: TruthGraph,
        compiled_at: str = "2026-08-30",
    ) -> TailoredArtifact:
        """Compile a structured consulting proposal / capability statement for an opportunity."""
        sections: list[ArtifactSection] = []
        claims: list[GeneratedClaim] = []
        commitments: list[ForwardCommitment] = []

        pm = opp.procurement_metadata

        # 1. Understanding of Scope & Terms of Reference
        scope_text = (
            f"Technical response to {opp.organization} tender: '{opp.title}'. "
            f"This proposal establishes the technical approach, capability evidence, and delivery framework "
            f"for executing the published terms of reference."
        )
        sections.append(ArtifactSection(
            section_id="scope_understanding",
            heading="Understanding of the Assignment & Scope",
            content=scope_text,
            items=(),
            assertion_ids=(),
            evidence_ids=(),
        ))
        claims.append(GeneratedClaim(
            claim_id="claim-prop-scope",
            text=scope_text,
            section_id="scope_understanding",
            assertion_ids=(),
            evidence_ids=(),
        ))

        # 2. Institutional / Practitioner Capabilities & Relevant Services
        service_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == "service.name" and a.verification_status == VerificationStatus.VERIFIED
        ]
        srv_names = tuple(str(s.value) for s in service_assertions)
        srv_content = (
            f"Professional advisory and engineering services available for this assignment:\n" +
            "\n".join(f"- {s}" for s in srv_names)
        )
        sections.append(ArtifactSection(
            section_id="capabilities",
            heading="Verified Core Capabilities & Service Offerings",
            content=srv_content,
            items=srv_names,
            assertion_ids=tuple(s.id for s in service_assertions),
            evidence_ids=tuple(ev for s in service_assertions for ev in s.evidence_ids),
        ))
        for s in service_assertions:
            claims.append(GeneratedClaim(
                claim_id=f"claim-srv-{s.id}",
                text=str(s.value),
                section_id="capabilities",
                assertion_ids=(s.id,),
                evidence_ids=s.evidence_ids,
            ))

        # 3. Verified Portfolio & Case Studies
        portfolio_assertions = [
            a for a in truth_graph.assertions.values()
            if a.predicate == "portfolio.item" and a.verification_status == VerificationStatus.VERIFIED
        ]
        port_items = tuple(str(p.value) for p in portfolio_assertions)
        sections.append(ArtifactSection(
            section_id="case_studies",
            heading="Relevant Project Experience & Case Studies",
            content="\n".join(f"- {p}" for p in port_items) if port_items else "Case studies available upon request.",
            items=port_items,
            assertion_ids=tuple(p.id for p in portfolio_assertions),
            evidence_ids=tuple(ev for p in portfolio_assertions for ev in p.evidence_ids),
        ))
        for p in portfolio_assertions:
            claims.append(GeneratedClaim(
                claim_id=f"claim-port-{p.id}",
                text=str(p.value),
                section_id="case_studies",
                assertion_ids=(p.id,),
                evidence_ids=p.evidence_ids,
            ))

        # 4. Forward Commitments Checklist (Strict policy enforcement)
        # Commercial / Rate Commitment
        if self.policy.default_daily_rate is not None:
            commitments.append(ForwardCommitment(
                commitment_type="rate",
                description="Professional consulting daily fee",
                status=CommitmentStatus.RESOLVED,
                value=f"{self.policy.default_daily_rate} {self.policy.default_currency} / day",
                policy_source="TailoringPolicy.default_daily_rate",
            ))
        elif self.policy.default_hourly_rate is not None:
            commitments.append(ForwardCommitment(
                commitment_type="rate",
                description="Professional consulting hourly fee",
                status=CommitmentStatus.RESOLVED,
                value=f"{self.policy.default_hourly_rate} {self.policy.default_currency} / hour",
                policy_source="TailoringPolicy.default_hourly_rate",
            ))
        else:
            commitments.append(ForwardCommitment(
                commitment_type="rate",
                description="Professional consulting fee structure",
                status=CommitmentStatus.UNRESOLVED,
                value="UNRESOLVED (RED): Commercial rate not configured in policy",
                policy_source="",
            ))

        # Availability Commitment
        if self.policy.default_availability_hours_per_week is not None:
            commitments.append(ForwardCommitment(
                commitment_type="availability",
                description="Weekly delivery capacity",
                status=CommitmentStatus.RESOLVED,
                value=f"{self.policy.default_availability_hours_per_week} hours / week",
                policy_source="TailoringPolicy.default_availability_hours_per_week",
            ))
        else:
            commitments.append(ForwardCommitment(
                commitment_type="availability",
                description="Weekly delivery capacity",
                status=CommitmentStatus.UNRESOLVED,
                value="UNRESOLVED (RED): Availability capacity not configured in policy",
                policy_source="",
            ))

        # Legal Entity Status Commitment
        if self.policy.business_legal_name and self.policy.business_registration_country:
            commitments.append(ForwardCommitment(
                commitment_type="legal_status",
                description="Contracting business entity",
                status=CommitmentStatus.RESOLVED,
                value=f"{self.policy.business_legal_name} ({self.policy.business_registration_country})",
                policy_source="TailoringPolicy.business_legal_name",
            ))
        else:
            commitments.append(ForwardCommitment(
                commitment_type="legal_status",
                description="Contracting business entity structure",
                status=CommitmentStatus.UNRESOLVED,
                value="UNRESOLVED (RED): Registered business entity details not configured",
                policy_source="",
            ))

        # Warranties & Guarantees
        commitments.append(ForwardCommitment(
            commitment_type="guarantee",
            description="Professional performance warranty",
            status=CommitmentStatus.RESOLVED,
            value=self.policy.guarantees_policy,
            policy_source="TailoringPolicy.guarantees_policy",
        ))

        # 5. Commitments Section in Artifact
        com_items = tuple(f"[{c.status.value.upper()}] {c.commitment_type.title()}: {c.value}" for c in commitments)
        sections.append(ArtifactSection(
            section_id="commitments",
            heading="Commercial & Governance Commitments Checklist",
            content="\n".join(com_items),
            items=com_items,
            assertion_ids=(),
            evidence_ids=(),
        ))

        return TailoredArtifact(
            artifact_id=f"artifact-prop-{opp.id}",
            artifact_type=ArtifactType.FREELANCE_PROPOSAL if opp.track == Track.FREELANCE else ArtifactType.RFP_RESPONSE_SCAFFOLD,
            opportunity_id=opp.id,
            opportunity_content_hash=opp.content_hash,
            template_version="proposal-v1.0",
            policy_version=self.policy.version,
            title=f"Technical Response & Capability Scaffold — {opp.organization} ({opp.title})",
            sections=tuple(sections),
            generated_claims=tuple(claims),
            commitment_checklist=tuple(commitments),
            compiled_at=compiled_at,
        )
