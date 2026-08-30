"""Freelance Proposal & Statement of Work Package Adapter."""
from __future__ import annotations

from typing import Any
from matching.models import TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from .base import BaseOutboundAdapter
from ..models import AdapterLifecycleState


class FreelanceProposalAdapter(BaseOutboundAdapter):
    def __init__(self) -> None:
        super().__init__(name="freelance_proposal", version="1.0.0", lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED)

    def prepare_proposal_package(
        self,
        opportunity: Opportunity,
        proposal_artifact: TailoredArtifact,
        truth_graph: TruthGraph,
        policy: TailoringPolicy | None = None,
    ) -> dict[str, Any]:
        return {
            "opportunity_id": opportunity.id,
            "client": opportunity.organization,
            "proposal_artifact_id": proposal_artifact.artifact_id,
            "proposal_artifact_hash": proposal_artifact.artifact_hash,
            "estimated_budget": getattr(policy, "default_daily_rate", None),
            "submission_mode": "assisted_or_manual",
        }
