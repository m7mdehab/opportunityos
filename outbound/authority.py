"""Central Action Authority & Authoritative Global Kill Switch."""
from __future__ import annotations

import threading
from typing import Any

from matching.models import QualificationDecision, TailoredArtifact, TailoringPolicy
from matching.validator import ArtifactClaimValidator
from opportunity.models import Opportunity
from truth.graph import TruthGraph

from .models import (
    ActionAuthorityDecision,
    AdapterLifecycleState,
    AnswerClass,
    ApplicationAnswer,
    ExecutionMode,
    SourceActionPolicy,
)
from .registry import SourceActionRegistry


class GlobalKillSwitch:
    """Authoritative global kill switch checked immediately before side effects."""
    _lock = threading.Lock()
    _enabled: bool = True

    @classmethod
    def is_enabled(cls) -> bool:
        with cls._lock:
            return cls._enabled

    @classmethod
    def enable(cls) -> None:
        with cls._lock:
            cls._enabled = True

    @classmethod
    def disable(cls) -> None:
        with cls._lock:
            cls._enabled = False


class ActionAuthority:
    """Central non-bypassable policy evaluator for all outbound actions."""

    def __init__(
        self,
        registry: SourceActionRegistry | None = None,
        validator: ArtifactClaimValidator | None = None,
    ) -> None:
        self.registry = registry or SourceActionRegistry()
        self.validator = validator or ArtifactClaimValidator()

    def evaluate_action(
        self,
        opportunity: Opportunity,
        artifact: TailoredArtifact | None,
        answers: tuple[ApplicationAnswer, ...],
        execution_mode: ExecutionMode,
        adapter_state: AdapterLifecycleState,
        adapter_name: str,
        workspace: str,
        candidate_id: str,
        qualification_decision: QualificationDecision,
        truth_graph: TruthGraph,
        policy: TailoringPolicy | None = None,
        is_duplicate: bool = False,
        captcha_detected: bool = False,
        mfa_detected: bool = False,
        unresolved_mandatory_count: int = 0,
    ) -> tuple[ActionAuthorityDecision, list[str]]:
        """Evaluate all safety dimensions and return an authoritative action decision."""
        reasons: list[str] = []

        # 1. Global Kill Switch
        if not GlobalKillSwitch.is_enabled():
            return ActionAuthorityDecision.BLOCK, ["Global side-effect kill switch is ACTIVE"]

        # 2. CAPTCHA / MFA / Anti-bot defenses
        if captcha_detected:
            return ActionAuthorityDecision.BLOCK, ["CAPTCHA human verification challenge detected (fail-safe stop)"]
        if mfa_detected:
            return ActionAuthorityDecision.PAUSE_FOR_REVIEW, ["MFA authentication challenge requires interactive founder login"]

        # 3. Duplicate Prevention
        if is_duplicate:
            return ActionAuthorityDecision.BLOCK, ["Duplicate submission detected for this candidate, opportunity, and action type"]

        # 4. Qualification Authority
        if qualification_decision == QualificationDecision.INELIGIBLE:
            return ActionAuthorityDecision.BLOCK, ["Opportunity is disqualified / INELIGIBLE"]

        # 5. Source Action Policy
        source_policy = self.registry.get_policy(opportunity.source)
        if source_policy == SourceActionPolicy.PROHIBITED:
            return ActionAuthorityDecision.BLOCK, [f"Source '{opportunity.source}' is PROHIBITED for outbound actions"]

        if source_policy == SourceActionPolicy.MANUAL_ONLY and execution_mode == ExecutionMode.CONTROLLED_SUBMIT:
            return ActionAuthorityDecision.BLOCK, [f"Source '{opportunity.source}' policy is MANUAL_ONLY; automated submission forbidden"]

        # 6. Execution Mode Authority
        if execution_mode == ExecutionMode.DRY_RUN:
            return ActionAuthorityDecision.ALLOW_PREPARE, ["DRY_RUN execution permitted (no external mutation)"]

        if execution_mode == ExecutionMode.ASSISTED:
            # ASSISTED allows navigation and form filling, but strictly forbids submit
            if unresolved_mandatory_count > 0:
                reasons.append(f"{unresolved_mandatory_count} mandatory fields are unresolved")
                return ActionAuthorityDecision.PAUSE_FOR_REVIEW, reasons
            return ActionAuthorityDecision.ALLOW_FILL, ["ASSISTED form population permitted; submission strictly forbidden"]

        # 7. CONTROLLED_SUBMIT Requirements
        if execution_mode == ExecutionMode.CONTROLLED_SUBMIT:
            # Adapter graduation state
            if adapter_state != AdapterLifecycleState.SUBMIT_ENABLED:
                return ActionAuthorityDecision.BLOCK, [
                    f"Adapter '{adapter_name}' is in lifecycle state '{adapter_state.value}' (requires SUBMIT_ENABLED)"
                ]

            if source_policy not in (SourceActionPolicy.SUBMIT_ALLOWED, SourceActionPolicy.API_ACTION_ALLOWED):
                return ActionAuthorityDecision.BLOCK, [
                    f"Source policy '{source_policy.value}' does not permit automated submission"
                ]

            # Artifact Validation & Binding
            if artifact is None:
                return ActionAuthorityDecision.BLOCK, ["Required tailored artifact is missing"]

            if artifact.opportunity_id != opportunity.id:
                return ActionAuthorityDecision.BLOCK, [
                    f"Artifact opportunity_id '{artifact.opportunity_id}' does not match target '{opportunity.id}'"
                ]

            if artifact.opportunity_content_hash != opportunity.content_hash:
                return ActionAuthorityDecision.BLOCK, [
                    f"Artifact opportunity_content_hash '{artifact.opportunity_content_hash}' does not match current opportunity hash '{opportunity.content_hash}'"
                ]

            art_val = self.validator.validate_artifact(artifact, truth_graph, opportunity=opportunity, policy=policy)
            if not art_val.is_valid:
                return ActionAuthorityDecision.BLOCK, [f"Artifact claim validation failed: {'; '.join(art_val.errors)}"]

            # Unresolved questions & RED question policy
            red_answers = [a for a in answers if a.answer_class == AnswerClass.RED]
            if red_answers:
                reasons.append(f"{len(red_answers)} RED questions require manual founder authorization ({', '.join(a.field_type.value for a in red_answers)})")
                return ActionAuthorityDecision.PAUSE_FOR_REVIEW, reasons

            if unresolved_mandatory_count > 0:
                reasons.append(f"{unresolved_mandatory_count} mandatory fields are unresolved")
                return ActionAuthorityDecision.PAUSE_FOR_REVIEW, reasons

            return ActionAuthorityDecision.ALLOW_SUBMIT, ["All pre-submit authorities satisfied for controlled submission"]

        return ActionAuthorityDecision.BLOCK, ["Unhandled action state"]
