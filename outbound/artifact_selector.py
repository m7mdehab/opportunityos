"""Application Artifact Selector & Validation Binder."""
from __future__ import annotations

from typing import Union
from matching.models import ArtifactType, TailoredArtifact, TailoringPolicy
from matching.validator import ArtifactClaimValidator
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from .models import BoundArtifact


class ApplicationArtifactSelector:
    """Validates and selects tailored CV/proposal artifacts with cryptographic binding and ownership."""

    def __init__(self, validator: ArtifactClaimValidator | None = None) -> None:
        self.validator = validator or ArtifactClaimValidator()

    def select_artifact(
        self,
        candidate_id: str,
        opportunity: Opportunity,
        artifact_type: ArtifactType,
        available_artifacts: tuple[Union[TailoredArtifact, BoundArtifact], ...],
        truth_graph: TruthGraph,
        policy: TailoringPolicy | None = None,
        workspace: str = "default",
    ) -> tuple[BoundArtifact | None, list[str]]:
        """Select exactly one validated BoundArtifact strictly bound to candidate, workspace, and opportunity."""
        errors: list[str] = []

        matching_type = [a for a in available_artifacts if a.artifact_type == artifact_type]
        if not matching_type:
            errors.append(f"No artifact found matching type '{artifact_type.value}'")
            return None, errors

        # 1. Non-bypassable BoundArtifact Ownership Checks
        owned_artifacts: list[BoundArtifact] = []
        for a in matching_type:
            if not isinstance(a, BoundArtifact):
                errors.append("Raw unowned TailoredArtifact rejected; BoundArtifact required")
                continue
            if a.candidate_id != candidate_id:
                errors.append(f"Artifact candidate '{a.candidate_id}' does not match requested candidate '{candidate_id}'")
                continue
            if a.workspace != workspace:
                errors.append(f"Artifact workspace '{a.workspace}' does not match requested workspace '{workspace}'")
                continue
            owned_artifacts.append(a)

        if not owned_artifacts:
            return None, errors

        # 2. Opportunity Binding
        bound_artifacts = [
            a for a in owned_artifacts
            if a.opportunity_id == opportunity.id and a.opportunity_content_hash == opportunity.content_hash
        ]

        if not bound_artifacts:
            stale_match = [a for a in owned_artifacts if a.opportunity_id == opportunity.id]
            if stale_match:
                errors.append(f"Artifact opportunity content hash '{stale_match[0].opportunity_content_hash}' is STALE compared to opportunity '{opportunity.content_hash}'")
            else:
                errors.append(f"No artifact bound to target opportunity ID '{opportunity.id}'")
            return None, errors

        if len(bound_artifacts) > 1:
            errors.append(f"Multiple ({len(bound_artifacts)}) plausible artifacts bound to opportunity; manual disambiguation required")
            return None, errors

        candidate_item = bound_artifacts[0]

        # 3. Truth Claim Validation
        val_result = self.validator.validate_artifact(
            candidate_item.artifact, truth_graph, opportunity=opportunity, policy=policy
        )
        if not val_result.is_valid:
            errors.extend([f"Claim validator rejected artifact: {err}" for err in val_result.errors])
            return None, errors

        return candidate_item, []
