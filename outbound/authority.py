"""Central Action Authority & Multi-Dimensional Safety Evaluator."""
from __future__ import annotations

from typing import Union
from matching.models import (
    QualificationDecision,
    TailoredArtifact,
    TailoringPolicy,
)
from matching.validator import ArtifactClaimValidator
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from .models import (
    ActionAuthorityDecision,
    ActionStatus,
    AdapterLifecycleState,
    AnswerClass,
    ApplicationAnswer,
    BoundArtifact,
    ExecutionMode,
    FieldOntologyType,
    SourceActionPolicy,
)
from .registry import AdapterRegistry, SourceActionRegistry


class GlobalKillSwitch:
    """Process-level and system-wide kill switch for all outbound actions."""
    _enabled: bool = True

    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled

    @classmethod
    def disable(cls) -> None:
        cls._enabled = False

    @classmethod
    def enable(cls) -> None:
        cls._enabled = True


class ActionAuthority:
    """Multi-dimensional safety gate evaluating all 11 prerequisite dimensions fail-closed."""

    def __init__(
        self,
        registry: SourceActionRegistry | None = None,
        adapter_registry: AdapterRegistry | None = None,
        validator: ArtifactClaimValidator | None = None,
    ) -> None:
        self.registry = registry or SourceActionRegistry()
        self.adapter_registry = adapter_registry or AdapterRegistry()
        self.validator = validator or ArtifactClaimValidator()

    def evaluate_action(
        self,
        opportunity: Opportunity,
        artifact: Union[TailoredArtifact, BoundArtifact] | None,
        answers: tuple[ApplicationAnswer, ...],
        execution_mode: ExecutionMode,
        adapter_name: str,
        workspace: str = "default",
        candidate_id: str = "founder",
        qualification_decision: QualificationDecision = QualificationDecision.QUALIFIED,
        truth_graph: TruthGraph | None = None,
        policy: TailoringPolicy | None = None,
        is_duplicate: bool = False,
        captcha_detected: bool = False,
        mfa_detected: bool = False,
        unresolved_mandatory_count: int = 0,
    ) -> tuple[ActionAuthorityDecision, list[str]]:
        """Evaluate the 11 prerequisite dimensions of side-effect safety fail-closed."""
        reasons: list[str] = []

        # 1. Global Kill Switch
        if not GlobalKillSwitch.is_enabled():
            reasons.append("Global side-effect kill switch is ACTIVE; all outbound actions prohibited")
            return ActionAuthorityDecision.BLOCK, reasons

        # 2. CAPTCHA / Anti-bot Barriers -> Hard Block
        if captcha_detected:
            reasons.append("CAPTCHA challenge detected; automatic bypass is strictly prohibited")
            return ActionAuthorityDecision.BLOCK, reasons

        # 3. MFA / Interactive Challenges -> Pause for Review
        if mfa_detected:
            reasons.append("MFA challenge detected; pausing for human interactive login")
            return ActionAuthorityDecision.PAUSE_FOR_REVIEW, reasons

        # 4. Duplicate Submission Guard
        if is_duplicate:
            reasons.append("Duplicate submission detected in idempotency ledger")
            return ActionAuthorityDecision.BLOCK, reasons

        # 5. Hard Qualification Authority
        if qualification_decision == QualificationDecision.INELIGIBLE:
            reasons.append(f"Opportunity is marked {qualification_decision.value}; outbound action prohibited")
            return ActionAuthorityDecision.BLOCK, reasons

        if qualification_decision == QualificationDecision.UNCERTAIN:
            reasons.append("Opportunity qualification is UNCERTAIN; requires human review before action")
            return ActionAuthorityDecision.PAUSE_FOR_REVIEW, reasons

        # 6. Source Action Policy Positive Granularity Gate
        source_policy = self.registry.get_policy(opportunity.source)
        if source_policy == SourceActionPolicy.PROHIBITED:
            reasons.append(f"Source '{opportunity.source}' policy is PROHIBITED")
            return ActionAuthorityDecision.BLOCK, reasons

        if source_policy == SourceActionPolicy.MANUAL_ONLY and execution_mode != ExecutionMode.DRY_RUN:
            reasons.append(f"Source '{opportunity.source}' policy is MANUAL_ONLY; automated actions blocked")
            return ActionAuthorityDecision.BLOCK, reasons

        if source_policy == SourceActionPolicy.DISCOVERY_ALLOWED:
            reasons.append(f"Source '{opportunity.source}' policy is DISCOVERY_ALLOWED; prepare, fill, and submit prohibited")
            return ActionAuthorityDecision.BLOCK, reasons

        if execution_mode == ExecutionMode.ASSISTED and source_policy not in (
            SourceActionPolicy.BROWSER_FILL_ALLOWED,
            SourceActionPolicy.SUBMIT_ALLOWED,
            SourceActionPolicy.API_ACTION_ALLOWED,
        ):
            reasons.append(f"Source policy '{source_policy.value}' prohibits assisted fill")
            return ActionAuthorityDecision.BLOCK, reasons

        if execution_mode == ExecutionMode.CONTROLLED_SUBMIT and source_policy not in (
            SourceActionPolicy.SUBMIT_ALLOWED,
            SourceActionPolicy.API_ACTION_ALLOWED,
        ):
            reasons.append(f"Source policy '{source_policy.value}' prohibits controlled submit")
            return ActionAuthorityDecision.BLOCK, reasons

        # 7. Authoritative Adapter Graduation Resolution
        grad_rec = self.adapter_registry.get_graduation_record(adapter_name)
        if grad_rec is None:
            reasons.append(f"Adapter '{adapter_name}' is not registered in authoritative AdapterRegistry")
            return ActionAuthorityDecision.BLOCK, reasons

        prefix = opportunity.source.split(":")[0] if ":" in opportunity.source else opportunity.source
        if not any(c in opportunity.source or c in prefix for c in grad_rec.source_compatibility):
            reasons.append(f"Adapter '{adapter_name}' is incompatible with source '{opportunity.source}'")
            return ActionAuthorityDecision.BLOCK, reasons

        # 8. Non-Bypassable Artifact Ownership & Validation Checks
        if artifact is not None:
            if execution_mode in (ExecutionMode.ASSISTED, ExecutionMode.CONTROLLED_SUBMIT):
                if not isinstance(artifact, BoundArtifact):
                    reasons.append("Raw unowned TailoredArtifact prohibited; BoundArtifact with explicit candidate_id and workspace required")
                    return ActionAuthorityDecision.BLOCK, reasons

            if isinstance(artifact, BoundArtifact):
                if artifact.candidate_id != candidate_id:
                    reasons.append(f"Artifact candidate '{artifact.candidate_id}' does not match requested candidate '{candidate_id}'")
                    return ActionAuthorityDecision.BLOCK, reasons

                if artifact.workspace != workspace:
                    reasons.append(f"Artifact workspace '{artifact.workspace}' does not match requested workspace '{workspace}'")
                    return ActionAuthorityDecision.BLOCK, reasons

            if artifact.opportunity_id != opportunity.id:
                reasons.append(f"Artifact opportunity ID '{artifact.opportunity_id}' does not match target opportunity ID '{opportunity.id}'")
                return ActionAuthorityDecision.BLOCK, reasons

            if artifact.opportunity_content_hash != opportunity.content_hash:
                reasons.append(f"Artifact opportunity content hash '{artifact.opportunity_content_hash}' indicates stale artifact for target opportunity '{opportunity.content_hash}'")
                return ActionAuthorityDecision.BLOCK, reasons

            inner_art = artifact.artifact if isinstance(artifact, BoundArtifact) else artifact
            val_res = self.validator.validate_artifact(inner_art, truth_graph or TruthGraph(), opportunity=opportunity, policy=policy)
            if not val_res.is_valid:
                reasons.extend([f"Artifact validation failed: {err}" for err in val_res.errors])
                return ActionAuthorityDecision.BLOCK, reasons

        # 9. Execution Mode Safety
        if execution_mode == ExecutionMode.DRY_RUN:
            return ActionAuthorityDecision.ALLOW_PREPARE, ["Dry run plan allowed"]

        if execution_mode == ExecutionMode.ASSISTED:
            if unresolved_mandatory_count > 0:
                reasons.append(f"{unresolved_mandatory_count} mandatory question(s) unresolved")
                return ActionAuthorityDecision.PAUSE_FOR_REVIEW, reasons
            return ActionAuthorityDecision.ALLOW_FILL, ["Assisted fill allowed; submit prohibited"]

        if execution_mode == ExecutionMode.CONTROLLED_SUBMIT:
            if grad_rec.lifecycle_state != AdapterLifecycleState.SUBMIT_ENABLED or not grad_rec.submit_enabled_by_founder:
                reasons.append(
                    f"Adapter '{adapter_name}' requires SUBMIT_ENABLED lifecycle state and explicit founder authorization"
                )
                return ActionAuthorityDecision.BLOCK, reasons

            red_answers = [a for a in answers if a.answer_class == AnswerClass.RED]
            if red_answers:
                reasons.append(f"Found {len(red_answers)} Red answer(s); human review required")
                return ActionAuthorityDecision.PAUSE_FOR_REVIEW, reasons

            if unresolved_mandatory_count > 0:
                reasons.append(f"{unresolved_mandatory_count} mandatory question(s) unresolved")
                return ActionAuthorityDecision.PAUSE_FOR_REVIEW, reasons

            return ActionAuthorityDecision.ALLOW_SUBMIT, ["Controlled submission authorized"]

        reasons.append(f"Unsupported execution mode '{execution_mode}'")
        return ActionAuthorityDecision.BLOCK, reasons
