"""Governed Outbound Browser Automation Engine with TOCTOU-Safe Pre-Submit Gate."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, Union
from matching.models import (
    QualificationDecision,
    TailoredArtifact,
    TailoringPolicy,
    Track,
)
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from .answer_engine import ApplicationAnswerEngine
from .authority import ActionAuthority, GlobalKillSwitch
from .confirmation import ConfirmationDetector
from .idempotency import (
    DuplicateSubmissionError,
    IdempotencyLedger,
    UnknownOutcomeFrozenError,
)
from .mock_harness import MockATSHarness
from .models import (
    ActionAuthorityDecision,
    ActionStatus,
    AdapterLifecycleState,
    AnswerClass,
    ApplicationAnswer,
    BoundArtifact,
    ConfirmationEvidence,
    DetectedFormField,
    ExecutionMode,
    FieldOntologyType,
    OutboundActionRecord,
    PreSubmitManifest,
    SourceActionPolicy,
)
from .registry import AdapterRegistry, SourceActionRegistry


class BrowserDriver(Protocol):
    """Protocol for browser drivers driving application form workflows."""
    def inspect_page_fields(self, step_index: int = 0) -> tuple[DetectedFormField, ...]:
        ...
    def fill_field(self, field: DetectedFormField, value: Any) -> bool:
        ...
    def attach_artifact(self, field: DetectedFormField, artifact: BoundArtifact) -> bool:
        ...
    def advance_step(self) -> bool:
        ...
    def submit_page(self) -> ConfirmationEvidence:
        ...
    def is_captcha_present(self) -> bool:
        ...
    def is_mfa_present(self) -> bool:
        ...


class MockBrowserDriver:
    """Mock implementation of BrowserDriver driven by MockATSHarness."""
    def __init__(self, harness: MockATSHarness) -> None:
        self.harness = harness
        self.current_step = 0

    def inspect_page_fields(self, step_index: int = 0) -> tuple[DetectedFormField, ...]:
        return self.harness.get_fields_for_step(step_index)

    def fill_field(self, field: DetectedFormField, value: Any) -> bool:
        self.harness.fill(field.field_id, value)
        return True

    def attach_artifact(self, field: DetectedFormField, artifact: BoundArtifact) -> bool:
        self.harness.fill(field.field_id, artifact.artifact_id)
        return True

    def advance_step(self) -> bool:
        advanced = self.harness.next_step()
        if advanced:
            self.current_step += 1
        return advanced

    def submit_page(self) -> ConfirmationEvidence:
        return self.harness.submit()

    def is_captcha_present(self) -> bool:
        return self.harness.captcha_barrier

    def is_mfa_present(self) -> bool:
        return self.harness.mfa_barrier


class OutboundBrowserEngine:
    """Executes multi-step browser automation with cryptographic manifest binding and TOCTOU safety."""

    def __init__(
        self,
        authority: ActionAuthority | None = None,
        ledger: IdempotencyLedger | None = None,
        adapter_registry: AdapterRegistry | None = None,
        source_registry: SourceActionRegistry | None = None,
    ) -> None:
        if authority is not None:
            if adapter_registry is not None and adapter_registry is not authority.adapter_registry:
                raise ValueError("Split adapter registry rejected: adapter_registry must be identity-equal to authority.adapter_registry")
            if source_registry is not None and source_registry is not authority.registry:
                raise ValueError("Split source registry rejected: source_registry must be identity-equal to authority.registry")
            self.authority = authority
            self.adapter_registry = authority.adapter_registry
            self.source_registry = authority.registry
        else:
            self.adapter_registry = adapter_registry or AdapterRegistry()
            self.source_registry = source_registry or SourceActionRegistry()
            self.authority = ActionAuthority(
                registry=self.source_registry,
                adapter_registry=self.adapter_registry,
            )

        self.ledger = ledger or IdempotencyLedger()
        self.confirmation_detector = ConfirmationDetector()

    def compute_answers_hash(self, answers: tuple[ApplicationAnswer, ...]) -> str:
        """Compute SHA-256 hash across all material answer fields."""
        serialized = [
            {
                "field_type": a.field_type.value,
                "original_label": a.original_label,
                "normalized_question": a.normalized_question,
                "answer": a.answer,
                "answer_class": a.answer_class.value,
                "answer_source": a.answer_source,
                "assertion_ids": list(a.assertion_ids),
                "policy_source": a.policy_source,
                "generated_claim_ids": list(a.generated_claim_ids),
                "artifact_ids": list(a.artifact_ids),
                "confidence": a.confidence,
                "disposition": a.disposition,
            }
            for a in sorted(answers, key=lambda x: (x.field_type.value, x.original_label))
        ]
        return hashlib.sha256(json.dumps(serialized, sort_keys=True).encode("utf-8")).hexdigest()

    def prepare_manifest(
        self,
        opportunity: Opportunity,
        artifact: Union[TailoredArtifact, BoundArtifact] | None,
        driver: BrowserDriver,
        adapter_name: str = "greenhouse",
        workspace: str = "default",
        candidate_id: str = "founder",
        qualification_decision: QualificationDecision = QualificationDecision.QUALIFIED,
        truth_graph: TruthGraph | None = None,
        policy: TailoringPolicy | None = None,
        action_id: str = "",
    ) -> tuple[PreSubmitManifest, tuple[ApplicationAnswer, ...], int, int]:
        """Inspect form and construct a genuine system-generated PreSubmitManifest snapshot."""
        act_id = action_id or f"act-{uuid.uuid4().hex[:12]}"
        action_type = "application"
        created_at = datetime.now(timezone.utc).isoformat()
        idempotency_key = IdempotencyLedger.compute_idempotency_key(
            workspace, candidate_id, opportunity.id, action_type
        )
        tg = truth_graph or TruthGraph()
        pol = policy or TailoringPolicy()
        answer_engine = ApplicationAnswerEngine(tg, pol)

        bound_artifact: BoundArtifact | None = None
        if artifact is not None:
            if isinstance(artifact, BoundArtifact):
                bound_artifact = artifact
            else:
                bound_artifact = BoundArtifact(artifact=artifact, candidate_id=candidate_id, workspace=workspace)

        step = 0
        max_steps = 10
        all_answers: list[ApplicationAnswer] = []
        unresolved_mandatory_count = 0
        has_more_steps = True

        while has_more_steps and step < max_steps:
            fields = driver.inspect_page_fields(step)
            for fld in fields:
                ans = answer_engine.answer_field(fld, opportunity, action_id=act_id, artifact=bound_artifact)
                all_answers.append(ans)
                if fld.required and (ans.answer is None or ans.answer_class == AnswerClass.RED):
                    unresolved_mandatory_count += 1
            has_more_steps = driver.advance_step()
            step += 1

        answers_tuple = tuple(all_answers)
        answers_hash = self.compute_answers_hash(answers_tuple)
        red_count = sum(1 for a in all_answers if a.answer_class == AnswerClass.RED)
        grad_rec = self.adapter_registry.get_graduation_record(adapter_name)
        grad_ver = grad_rec.version if grad_rec else "1.0.0"
        grad_evidence_hash = grad_rec.evidence_hash if grad_rec else ""
        source_policy_ver = self.source_registry.get_policy_version(opportunity.source)

        manifest = PreSubmitManifest(
            workspace=workspace,
            candidate_id=candidate_id,
            opportunity_id=opportunity.id,
            opportunity_content_hash=opportunity.content_hash,
            action_type=action_type,
            adapter_name=adapter_name,
            adapter_version=grad_ver,
            graduation_record_version=grad_ver,
            graduation_evidence_hash=grad_evidence_hash,
            source_policy_version=source_policy_ver,
            tailoring_policy_version=pol.version,
            artifact_ids=tuple([bound_artifact.artifact_id]) if bound_artifact else (),
            artifact_hashes=tuple([bound_artifact.artifact_hash]) if bound_artifact else (),
            answers=answers_tuple,
            answers_hash=answers_hash,
            qualification_decision=qualification_decision,
            unresolved_mandatory_count=unresolved_mandatory_count,
            red_answers_count=red_count,
            idempotency_key=idempotency_key,
            compiled_at=created_at,
        )
        return manifest, answers_tuple, red_count, unresolved_mandatory_count

    def execute_application(
        self,
        opportunity: Opportunity,
        artifact: Union[TailoredArtifact, BoundArtifact] | None,
        driver: BrowserDriver,
        execution_mode: ExecutionMode = ExecutionMode.DRY_RUN,
        adapter_name: str = "greenhouse",
        workspace: str = "default",
        candidate_id: str = "founder",
        qualification_decision: QualificationDecision = QualificationDecision.QUALIFIED,
        truth_graph: TruthGraph | None = None,
        policy: TailoringPolicy | None = None,
        match_score_snapshot: float = 0.0,
        prepared_manifest: PreSubmitManifest | None = None,
    ) -> OutboundActionRecord:
        """Orchestrate multi-step application workflow with non-bypassable pre-submit gate."""
        action_id = f"act-{uuid.uuid4().hex[:12]}"
        action_type = "application"
        created_at = datetime.now(timezone.utc).isoformat()
        idempotency_key = IdempotencyLedger.compute_idempotency_key(
            workspace, candidate_id, opportunity.id, action_type
        )
        tg = truth_graph or TruthGraph()
        pol = policy or TailoringPolicy()
        answer_engine = ApplicationAnswerEngine(tg, pol)

        # Snapshot initial environment state
        initial_source_policy_ver = self.source_registry.get_policy_version(opportunity.source)
        initial_grad_rec = self.adapter_registry.get_graduation_record(adapter_name)
        initial_grad_ver = initial_grad_rec.version if initial_grad_rec else "1.0.0"
        initial_grad_evidence_hash = initial_grad_rec.evidence_hash if initial_grad_rec else ""

        bound_artifact: BoundArtifact | None = None
        if artifact is not None:
            if isinstance(artifact, BoundArtifact):
                bound_artifact = artifact
            else:
                if execution_mode in (ExecutionMode.ASSISTED, ExecutionMode.CONTROLLED_SUBMIT):
                    return OutboundActionRecord(
                        action_id=action_id,
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        workspace=workspace,
                        candidate_id=candidate_id,
                        track=opportunity.track,
                        source=opportunity.source,
                        adapter_name=adapter_name,
                        adapter_version="1.0.0",
                        execution_mode=execution_mode,
                        qualification_decision=qualification_decision,
                        match_score_snapshot=match_score_snapshot,
                        artifact_ids=(),
                        artifact_hashes=(),
                        manifest_hash="",
                        action_status=ActionStatus.BLOCKED,
                        idempotency_key=idempotency_key,
                        created_at=created_at,
                        updated_at=created_at,
                        blocker_reason="Raw unowned TailoredArtifact prohibited; BoundArtifact required",
                    )
                bound_artifact = BoundArtifact(artifact=artifact, candidate_id=candidate_id, workspace=workspace)

        is_dup = self.ledger.is_duplicate(workspace, candidate_id, opportunity.id, action_type)

        dec, reasons = self.authority.evaluate_action(
            opportunity=opportunity,
            artifact=bound_artifact,
            answers=(),
            execution_mode=execution_mode,
            adapter_name=adapter_name,
            workspace=workspace,
            candidate_id=candidate_id,
            qualification_decision=qualification_decision,
            truth_graph=tg,
            policy=pol,
            is_duplicate=is_dup,
            captcha_detected=driver.is_captcha_present(),
            mfa_detected=driver.is_mfa_present(),
            unresolved_mandatory_count=0,
        )

        if dec == ActionAuthorityDecision.BLOCK:
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version="1.0.0",
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=tuple([bound_artifact.artifact_id]) if bound_artifact else (),
                artifact_hashes=tuple([bound_artifact.artifact_hash]) if bound_artifact else (),
                manifest_hash="",
                action_status=ActionStatus.BLOCKED,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
                blocker_reason="; ".join(reasons),
            )

        if dec == ActionAuthorityDecision.PAUSE_FOR_REVIEW:
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version="1.0.0",
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=tuple([bound_artifact.artifact_id]) if bound_artifact else (),
                artifact_hashes=tuple([bound_artifact.artifact_hash]) if bound_artifact else (),
                manifest_hash="",
                action_status=ActionStatus.AWAITING_REVIEW,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
                blocker_reason="; ".join(reasons),
            )

        # Form Inspection & Population Loop
        step = 0
        max_steps = 10
        all_answers: list[ApplicationAnswer] = []
        unresolved_mandatory_count = 0
        has_more_steps = True
        observed_fields: list[DetectedFormField] = []

        while has_more_steps and step < max_steps:
            if driver.is_captcha_present():
                return OutboundActionRecord(
                    action_id=action_id,
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    workspace=workspace,
                    candidate_id=candidate_id,
                    track=opportunity.track,
                    source=opportunity.source,
                    adapter_name=adapter_name,
                    adapter_version="1.0.0",
                    execution_mode=execution_mode,
                    qualification_decision=qualification_decision,
                    match_score_snapshot=match_score_snapshot,
                    artifact_ids=tuple([bound_artifact.artifact_id]) if bound_artifact else (),
                    artifact_hashes=tuple([bound_artifact.artifact_hash]) if bound_artifact else (),
                    manifest_hash="",
                    action_status=ActionStatus.BLOCKED,
                    idempotency_key=idempotency_key,
                    created_at=created_at,
                    updated_at=created_at,
                    blocker_reason="CAPTCHA challenge detected on step",
                )

            if driver.is_mfa_present():
                return OutboundActionRecord(
                    action_id=action_id,
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    workspace=workspace,
                    candidate_id=candidate_id,
                    track=opportunity.track,
                    source=opportunity.source,
                    adapter_name=adapter_name,
                    adapter_version="1.0.0",
                    execution_mode=execution_mode,
                    qualification_decision=qualification_decision,
                    match_score_snapshot=match_score_snapshot,
                    artifact_ids=tuple([bound_artifact.artifact_id]) if bound_artifact else (),
                    artifact_hashes=tuple([bound_artifact.artifact_hash]) if bound_artifact else (),
                    manifest_hash="",
                    action_status=ActionStatus.AWAITING_REVIEW,
                    idempotency_key=idempotency_key,
                    created_at=created_at,
                    updated_at=created_at,
                    blocker_reason="MFA challenge detected on step",
                )

            fields = driver.inspect_page_fields(step)
            for fld in fields:
                observed_fields.append(fld)
                ans = answer_engine.answer_field(fld, opportunity, action_id=action_id, artifact=bound_artifact)
                all_answers.append(ans)

                if fld.required and (ans.answer is None or ans.answer_class == AnswerClass.RED):
                    unresolved_mandatory_count += 1

                if execution_mode in (ExecutionMode.ASSISTED, ExecutionMode.CONTROLLED_SUBMIT):
                    if ans.disposition == "auto_fill" and ans.answer is not None:
                        if fld.ontology_type == FieldOntologyType.ATTACHMENT and bound_artifact:
                            driver.attach_artifact(fld, bound_artifact)
                        else:
                            driver.fill_field(fld, ans.answer)

            has_more_steps = driver.advance_step()
            step += 1

        answers_tuple = tuple(all_answers)
        answers_hash = self.compute_answers_hash(answers_tuple)
        red_count = sum(1 for a in all_answers if a.answer_class == AnswerClass.RED)

        current_manifest = PreSubmitManifest(
            workspace=workspace,
            candidate_id=candidate_id,
            opportunity_id=opportunity.id,
            opportunity_content_hash=opportunity.content_hash,
            action_type=action_type,
            adapter_name=adapter_name,
            adapter_version=initial_grad_ver,
            graduation_record_version=initial_grad_ver,
            graduation_evidence_hash=initial_grad_evidence_hash,
            source_policy_version=initial_source_policy_ver,
            tailoring_policy_version=pol.version,
            artifact_ids=tuple([bound_artifact.artifact_id]) if bound_artifact else (),
            artifact_hashes=tuple([bound_artifact.artifact_hash]) if bound_artifact else (),
            answers=answers_tuple,
            answers_hash=answers_hash,
            qualification_decision=qualification_decision,
            unresolved_mandatory_count=unresolved_mandatory_count,
            red_answers_count=red_count,
            idempotency_key=idempotency_key,
            compiled_at=created_at,
        )

        manifest = prepared_manifest or current_manifest

        if execution_mode == ExecutionMode.DRY_RUN:
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version=initial_grad_ver,
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=manifest.artifact_ids,
                artifact_hashes=manifest.artifact_hashes,
                manifest_hash=manifest.manifest_hash,
                action_status=ActionStatus.PREPARED,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
            )

        if execution_mode == ExecutionMode.ASSISTED:
            status = ActionStatus.AWAITING_REVIEW if (red_count > 0 or unresolved_mandatory_count > 0) else ActionStatus.PREPARED
            reason = f"{red_count} Red question(s) or {unresolved_mandatory_count} mandatory question(s) unresolved" if status == ActionStatus.AWAITING_REVIEW else ""
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version=initial_grad_ver,
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=manifest.artifact_ids,
                artifact_hashes=manifest.artifact_hashes,
                manifest_hash=manifest.manifest_hash,
                action_status=status,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
                blocker_reason=reason,
            )

        # CONTROLLED_SUBMIT: Final Pre-Submit Staleness and Authority Re-evaluation Gate
        fresh_answers: list[ApplicationAnswer] = []
        fresh_unresolved_count = 0
        fresh_answer_engine = ApplicationAnswerEngine(tg, pol)
        for fld in observed_fields:
            fa = fresh_answer_engine.answer_field(fld, opportunity, action_id=action_id, artifact=bound_artifact)
            fresh_answers.append(fa)
            if fld.required and (fa.answer is None or fa.answer_class == AnswerClass.RED):
                fresh_unresolved_count += 1

        fresh_answers_tuple = tuple(fresh_answers)
        fresh_answers_hash = self.compute_answers_hash(fresh_answers_tuple)
        fresh_red_count = sum(1 for a in fresh_answers if a.answer_class == AnswerClass.RED)
        fresh_grad_rec = self.adapter_registry.get_graduation_record(adapter_name)
        fresh_source_policy_ver = self.source_registry.get_policy_version(opportunity.source)
        fresh_grad_ver = fresh_grad_rec.version if fresh_grad_rec else "1.0.0"
        fresh_grad_evidence_hash = fresh_grad_rec.evidence_hash if fresh_grad_rec else ""

        fresh_manifest = PreSubmitManifest(
            workspace=workspace,
            candidate_id=candidate_id,
            opportunity_id=opportunity.id,
            opportunity_content_hash=opportunity.content_hash,
            action_type=action_type,
            adapter_name=adapter_name,
            adapter_version=fresh_grad_ver,
            graduation_record_version=fresh_grad_ver,
            graduation_evidence_hash=fresh_grad_evidence_hash,
            source_policy_version=fresh_source_policy_ver,
            tailoring_policy_version=pol.version,
            artifact_ids=tuple([bound_artifact.artifact_id]) if bound_artifact else (),
            artifact_hashes=tuple([bound_artifact.artifact_hash]) if bound_artifact else (),
            answers=fresh_answers_tuple,
            answers_hash=fresh_answers_hash,
            qualification_decision=qualification_decision,
            unresolved_mandatory_count=fresh_unresolved_count,
            red_answers_count=fresh_red_count,
            idempotency_key=idempotency_key,
            compiled_at=created_at,
        )

        if fresh_manifest.manifest_hash != manifest.manifest_hash:
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version=fresh_grad_ver,
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=fresh_manifest.artifact_ids,
                artifact_hashes=fresh_manifest.artifact_hashes,
                manifest_hash=fresh_manifest.manifest_hash,
                action_status=ActionStatus.BLOCKED,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
                blocker_reason="Manifest staleness detected: environment, policy, or provenance changed after preparation",
            )

        is_dup_final = self.ledger.is_duplicate(workspace, candidate_id, opportunity.id, action_type)
        final_dec, final_reasons = self.authority.evaluate_action(
            opportunity=opportunity,
            artifact=bound_artifact,
            answers=fresh_answers_tuple,
            execution_mode=execution_mode,
            adapter_name=adapter_name,
            workspace=workspace,
            candidate_id=candidate_id,
            qualification_decision=qualification_decision,
            truth_graph=tg,
            policy=pol,
            is_duplicate=is_dup_final,
            captcha_detected=driver.is_captcha_present(),
            mfa_detected=driver.is_mfa_present(),
            unresolved_mandatory_count=fresh_unresolved_count,
        )

        if final_dec != ActionAuthorityDecision.ALLOW_SUBMIT:
            status = ActionStatus.AWAITING_REVIEW if final_dec == ActionAuthorityDecision.PAUSE_FOR_REVIEW else ActionStatus.BLOCKED
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version=fresh_grad_ver,
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=fresh_manifest.artifact_ids,
                artifact_hashes=fresh_manifest.artifact_hashes,
                manifest_hash=fresh_manifest.manifest_hash,
                action_status=status,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
                blocker_reason="; ".join(final_reasons),
            )

        record_to_reserve = OutboundActionRecord(
            action_id=action_id,
            opportunity_id=opportunity.id,
            opportunity_content_hash=opportunity.content_hash,
            workspace=workspace,
            candidate_id=candidate_id,
            track=opportunity.track,
            source=opportunity.source,
            adapter_name=adapter_name,
            adapter_version=fresh_grad_ver,
            execution_mode=execution_mode,
            qualification_decision=qualification_decision,
            match_score_snapshot=match_score_snapshot,
            artifact_ids=fresh_manifest.artifact_ids,
            artifact_hashes=fresh_manifest.artifact_hashes,
            manifest_hash=fresh_manifest.manifest_hash,
            action_status=ActionStatus.PLANNED,
            idempotency_key=idempotency_key,
            created_at=created_at,
            updated_at=created_at,
        )

        try:
            self.ledger.reserve_submission(record_to_reserve)
        except (DuplicateSubmissionError, UnknownOutcomeFrozenError) as e:
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version=fresh_grad_ver,
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=fresh_manifest.artifact_ids,
                artifact_hashes=fresh_manifest.artifact_hashes,
                manifest_hash=fresh_manifest.manifest_hash,
                action_status=ActionStatus.BLOCKED,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
                blocker_reason=str(e),
            )

        # FINAL Side-Effect Authority Check immediately adjacent to irreversible external submit call
        if not GlobalKillSwitch.is_enabled():
            self.ledger.transition_status(
                idempotency_key=idempotency_key,
                new_status=ActionStatus.BLOCKED,
                blocker_reason="Global kill switch disabled after reservation; submit aborted",
            )
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version=fresh_grad_ver,
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=fresh_manifest.artifact_ids,
                artifact_hashes=fresh_manifest.artifact_hashes,
                manifest_hash=fresh_manifest.manifest_hash,
                action_status=ActionStatus.BLOCKED,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
                blocker_reason="Global kill switch disabled after reservation; submit aborted",
            )

        # Re-check source policy
        current_source_pol = self.source_registry.get_policy(opportunity.source)
        if current_source_pol not in (SourceActionPolicy.SUBMIT_ALLOWED, SourceActionPolicy.API_ACTION_ALLOWED):
            self.ledger.transition_status(
                idempotency_key=idempotency_key,
                new_status=ActionStatus.BLOCKED,
                blocker_reason=f"Source policy changed after reservation to {current_source_pol.value}; submit aborted",
            )
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version=fresh_grad_ver,
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=fresh_manifest.artifact_ids,
                artifact_hashes=fresh_manifest.artifact_hashes,
                manifest_hash=fresh_manifest.manifest_hash,
                action_status=ActionStatus.BLOCKED,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
                blocker_reason=f"Source policy changed after reservation to {current_source_pol.value}; submit aborted",
            )

        # Re-check adapter graduation
        current_grad_post = self.adapter_registry.get_graduation_record(adapter_name)
        if (
            not current_grad_post
            or current_grad_post.lifecycle_state != AdapterLifecycleState.SUBMIT_ENABLED
            or not current_grad_post.evidence_hash
            or current_grad_post.evidence_hash != fresh_manifest.graduation_evidence_hash
        ):
            self.ledger.transition_status(
                idempotency_key=idempotency_key,
                new_status=ActionStatus.BLOCKED,
                blocker_reason="Adapter graduation state or evidence invalidated after reservation; submit aborted",
            )
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version=fresh_grad_ver,
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=fresh_manifest.artifact_ids,
                artifact_hashes=fresh_manifest.artifact_hashes,
                manifest_hash=fresh_manifest.manifest_hash,
                action_status=ActionStatus.BLOCKED,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
                blocker_reason="Adapter graduation state or evidence invalidated after reservation; submit aborted",
            )

        # FINAL Challenge Check
        if driver.is_captcha_present() or driver.is_mfa_present():
            self.ledger.transition_status(
                idempotency_key=idempotency_key,
                new_status=ActionStatus.BLOCKED,
                blocker_reason="Challenge detected immediately before submit call",
            )
            return OutboundActionRecord(
                action_id=action_id,
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                workspace=workspace,
                candidate_id=candidate_id,
                track=opportunity.track,
                source=opportunity.source,
                adapter_name=adapter_name,
                adapter_version=fresh_grad_ver,
                execution_mode=execution_mode,
                qualification_decision=qualification_decision,
                match_score_snapshot=match_score_snapshot,
                artifact_ids=fresh_manifest.artifact_ids,
                artifact_hashes=fresh_manifest.artifact_hashes,
                manifest_hash=fresh_manifest.manifest_hash,
                action_status=ActionStatus.BLOCKED,
                idempotency_key=idempotency_key,
                created_at=created_at,
                updated_at=created_at,
                blocker_reason="Challenge detected immediately before submit call",
            )

        try:
            evidence = driver.submit_page()
        except Exception as err:
            return self.ledger.transition_status(
                idempotency_key=idempotency_key,
                new_status=ActionStatus.UNKNOWN_OUTCOME,
                blocker_reason=f"Submission error: {err}",
            )

        if evidence and evidence.confirmed:
            return self.ledger.transition_status(
                idempotency_key=idempotency_key,
                new_status=ActionStatus.CONFIRMED,
                evidence=evidence,
            )

        return self.ledger.transition_status(
            idempotency_key=idempotency_key,
            new_status=ActionStatus.UNKNOWN_OUTCOME,
            evidence=evidence,
            blocker_reason="Submission completed but receipt not detected",
        )
