"""Base Outbound Action Adapter Interface."""
from __future__ import annotations

from typing import Any
from matching.models import TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from ..models import (
    AdapterLifecycleState,
    DetectedFormField,
    ExecutionMode,
    OutboundActionRecord,
    SourceActionPolicy,
)


class BaseOutboundAdapter:
    """Base class for all outbound employment and independent engagement adapters."""

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        lifecycle_state: AdapterLifecycleState = AdapterLifecycleState.EXPERIMENTAL,
    ) -> None:
        self.name = name
        self.version = version
        self.lifecycle_state = lifecycle_state

    def can_submit(self) -> bool:
        return self.lifecycle_state == AdapterLifecycleState.SUBMIT_ENABLED

    def prepare_package(
        self,
        opportunity: Opportunity,
        artifact: TailoredArtifact,
        truth_graph: TruthGraph,
        policy: TailoringPolicy | None = None,
    ) -> dict[str, Any]:
        """Prepare local application payload/package."""
        return {
            "adapter": self.name,
            "version": self.version,
            "opportunity_id": opportunity.id,
            "opportunity_title": opportunity.title,
            "artifact_id": artifact.artifact_id,
            "artifact_hash": artifact.artifact_hash,
            "lifecycle_state": self.lifecycle_state.value,
        }
