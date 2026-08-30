"""Application Artifact Selector & Validation Binder."""
from __future__ import annotations

from matching.models import ArtifactType, TailoredArtifact, TailoringPolicy
from matching.validator import ArtifactClaimValidator
from opportunity.models import Opportunity
from truth.graph import TruthGraph


class ApplicationArtifactSelector:
    """Validates and selects tailored CV/proposal artifacts with cryptographic binding."""

    def __init__(self, validator: ArtifactClaimValidator | None = None) -> None:
        self.validator = validator or ArtifactClaimValidator()

    def select_artifact(
        self,
        candidate_id: str,
        opportunity: Opportunity,
        artifact_type: ArtifactType,
        available_artifacts: tuple[TailoredArtifact, ...],
        truth_graph: TruthGraph,
        policy: TailoringPolicy | None = None,
    ) -> tuple[TailoredArtifact | None, list[str]]:
        """Select exactly one validated artifact strictly bound to the target opportunity."""
        errors: list[str] = []

        matching_type = [a for a in available_artifacts if a.artifact_type == artifact_type]
        if not matching_type:
            errors.append(f"No artifact found matching type '{artifact_type.value}'")
            return None, errors

        bound_artifacts = [
            a for a in matching_type
            if a.opportunity_id == opportunity.id and a.opportunity_content_hash == opportunity.content_hash
        ]

        if not bound_artifacts:
            stale_match = [a for a in matching_type if a.opportunity_id == opportunity.id]
            if stale_match:
                errors.append(f"Artifact opportunity content hash '{stale_match[0].opportunity_content_hash}' is STALE compared to opportunity '{opportunity.content_hash}'")
            else:
                errors.append(f"No artifact bound to target opportunity ID '{opportunity.id}'")
            return None, errors

        if len(bound_artifacts) > 1:
            errors.append(f"Multiple ({len(bound_artifacts)}) plausible artifacts bound to opportunity; manual disambiguation required")
            return None, errors

        candidate_artifact = bound_artifacts[0]

        val_result = self.validator.validate_artifact(
            candidate_artifact, truth_graph, opportunity=opportunity, policy=policy
        )
        if not val_result.is_valid:
            errors.extend([f"Claim validator rejected artifact: {err}" for err in val_result.errors])
            return None, errors

        return candidate_artifact, []
