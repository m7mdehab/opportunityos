"""Multilateral Procurement RFP & Tender Package Adapter (Manual Deep-Link Only)."""
from __future__ import annotations

from typing import Any
from matching.models import TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from .base import BaseOutboundAdapter
from ..models import AdapterLifecycleState


class ProcurementPackageAdapter(BaseOutboundAdapter):
    def __init__(self) -> None:
        super().__init__(name="procurement_package", version="1.0.0", lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED)

    def prepare_procurement_dossier(
        self,
        opportunity: Opportunity,
        proposal_artifact: TailoredArtifact,
        truth_graph: TruthGraph,
        policy: TailoringPolicy | None = None,
    ) -> dict[str, Any]:
        """Construct structured tender response dossier without binding legal guarantees."""
        return {
            "notice_id": opportunity.source_id,
            "buyer": opportunity.organization,
            "proposal_artifact_id": proposal_artifact.artifact_id,
            "proposal_artifact_hash": proposal_artifact.artifact_hash,
            "deep_link_url": opportunity.source_url,
            "compliance_checklist": [c.commitment_type for c in proposal_artifact.commitment_checklist],
            "submission_mode": "manual_portal_upload_only",
            "legal_binding_acceptance_required": True,
        }
