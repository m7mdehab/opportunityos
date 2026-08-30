"""Outbound Browser Automation & Multi-Step Execution Engine."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Protocol

from matching.models import QualificationDecision, TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity
from truth.graph import TruthGraph

from .answer_engine import ApplicationAnswerEngine
from .authority import ActionAuthority, GlobalKillSwitch
from .confirmation import ConfirmationDetector
from .idempotency import IdempotencyLedger
from .mock_harness import MockATSHarness
from .models import (
    ActionAuthorityDecision,
    ActionStatus,
    AdapterLifecycleState,
    AnswerClass,
    ApplicationAnswer,
    ConfirmationEvidence,
    DetectedFormField,
    ExecutionMode,
    FieldOntologyType,
    OutboundActionRecord,
    PreSubmitManifest,
)
from .ontology import FieldClassifier
from .registry import AdapterRegistry, SourceActionRegistry


class BrowserDriver(Protocol):
    """Protocol for form inspection, population, and submission drivers."""
    def inspect_fields(self) -> tuple[DetectedFormField, ...]: ...
    def fill_field(self, field_id: str, value: Any) -> None: ...
    def upload_artifact(self, field_id: str, artifact: TailoredArtifact) -> None: ...
    def next_page(self) -> bool: ...
    def submit_page(self) -> ConfirmationEvidence: ...
    def is_captcha_present(self) -> bool: ...
    def is_mfa_present(self) -> bool: ...


class MockBrowserDriver:
    """Deterministic in-memory driver wrapping MockATSHarness."""
    def __init__(self, harness: MockATSHarness) -> None:
        self.harness = harness

    def inspect_fields(self) -> tuple[DetectedFormField, ...]:
        return self.harness.get_fields_for_step(self.harness.current_step)

    def fill_field(self, field_id: str, value: Any) -> None:
        self.harness.fill(field_id, value)

    def upload_artifact(self, field_id: str, artifact: TailoredArtifact) -> None:
        self.harness.fill(field_id, artifact.artifact_id)

    def next_page(self) -> bool:
        return self.harness.next_step()

    def submit_page(self) -> ConfirmationEvidence:
        return self.harness.submit()

    def is_captcha_present(self) -> bool:
        return self.harness.captcha_barrier

    def is_mfa_present(self) -> bool:
        return self.harness.mfa_barrier


class OutboundBrowserEngine:
    """Executes governed outbound browser workflows across multi-step forms and execution modes."""

    def __init__(
        self,
        authority: ActionAuthority | None = None,
        ledger: IdempotencyLedger | None = None,
        adapter_registry: AdapterRegistry | None = None,
    ) -> None:
        self.authority = authority or ActionAuthority()
        self.ledger = ledger or IdempotencyLedger()
        self.adapter_registry = adapter_registry or AdapterRegistry()

    def execute_application(
        self,
        opportunity: Opportunity,
        artifact: TailoredArtifact | None,
        driver: BrowserDriver,
        execution_mode: ExecutionMode = ExecutionMode.DRY_RUN,
        adapter_name: str = "greenhouse",
        workspace: str = "default",
        candidate_id: str = "founder",
        qualification_decision: QualificationDecision = QualificationDecision.QUALIFIED,
        truth_graph: TruthGraph | None = None,
        policy: TailoringPolicy | None = None,
        action_type: str = "job_application",
    ) -> OutboundActionRecord:
        """Coordinate multi-step form inspection, answering, authority checks, and TOCTOU-safe execution."""
        tg = truth_graph or TruthGraph()
        pol = policy or TailoringPolicy()
        answer_engine = ApplicationAnswerEngine(tg, pol)

        idempotency_key = self.ledger.compute_idempotency_key(
            workspace, candidate_id, opportunity.id, action_type
        )
        action_id = f"act-{opportunity.id}-{execution_mode.value}"

        grad_rec = self.adapter_registry.get_graduation_record(adapter_name)
        adapter_ver = grad_rec.version if grad_rec else "1.0.0"
        grad_ver = grad_rec.evidence_hash if grad_rec else "unregistered"

        # 1. Multi-Step Form Navigation & Field Population Loop
        all_answers: list[ApplicationAnswer] = []
        unresolved_mandatory = 0
        step = 0
        max_steps = 10

        while step < max_steps:
            # Check challenge barriers on every step
            if driver.is_captcha_present():
                return OutboundActionRecord(
                    action_id=action_id, opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    workspace=workspace, candidate_id=candidate_id, track=opportunity.track,
                    source=opportunity.source, adapter_name=adapter_name, adapter_version=adapter_ver,
                    execution_mode=execution_mode, qualification_decision=qualification_decision,
                    match_score_snapshot=1.0, artifact_ids=(artifact.artifact_id,) if artifact else (),
                    artifact_hashes=(artifact.artifact_hash,) if artifact else (),
                    manifest_hash="captcha_blocked", action_status=ActionStatus.BLOCKED,
                    idempotency_key=idempotency_key, created_at="2026-08-30T00:00:00Z",
                    updated_at="2026-08-30T00:00:00Z", blocker_reason="CAPTCHA barrier detected during form step",
                )

            if driver.is_mfa_present():
                return OutboundActionRecord(
                    action_id=action_id, opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    workspace=workspace, candidate_id=candidate_id, track=opportunity.track,
                    source=opportunity.source, adapter_name=adapter_name, adapter_version=adapter_ver,
                    execution_mode=execution_mode, qualification_decision=qualification_decision,
                    match_score_snapshot=1.0, artifact_ids=(artifact.artifact_id,) if artifact else (),
                    artifact_hashes=(artifact.artifact_hash,) if artifact else (),
                    manifest_hash="mfa_pause", action_status=ActionStatus.AWAITING_REVIEW,
                    idempotency_key=idempotency_key, created_at="2026-08-30T00:00:00Z",
                    updated_at="2026-08-30T00:00:00Z", blocker_reason="MFA challenge detected during form step",
                )

            step_fields = driver.inspect_fields()
            for f in step_fields:
                ans = answer_engine.answer_field(f, opportunity, action_id, compiled_artifact=artifact)
                all_answers.append(ans)
                if f.required and (ans.answer is None or ans.disposition == "pause"):
                    unresolved_mandatory += 1

                # Fill field if in ASSISTED or CONTROLLED_SUBMIT
                if execution_mode in (ExecutionMode.ASSISTED, ExecutionMode.CONTROLLED_SUBMIT):
                    if ans.answer is not None and ans.disposition == "auto_fill":
                        if f.ontology_type == FieldOntologyType.ATTACHMENT and artifact:
                            driver.upload_artifact(f.field_id, artifact)
                        else:
                            driver.fill_field(f.field_id, ans.answer)

            # Check if next step is available
            has_next = driver.next_page()
            if not has_next:
                break
            step += 1

        red_count = sum(1 for a in all_answers if a.answer_class == AnswerClass.RED)

        # 2. Build PreSubmitManifest
        answers_payload = [
            (a.field_type.value, a.original_label, str(a.answer), a.answer_class.value, a.answer_source)
            for a in all_answers
        ]
        answers_hash = hashlib.sha256(json.dumps(answers_payload, sort_keys=True).encode("utf-8")).hexdigest()

        manifest = PreSubmitManifest(
            workspace=workspace,
            candidate_id=candidate_id,
            opportunity_id=opportunity.id,
            opportunity_content_hash=opportunity.content_hash,
            action_type=action_type,
            adapter_name=adapter_name,
            adapter_version=adapter_ver,
            graduation_record_version=grad_ver,
            source_policy_version=pol.version,
            artifact_ids=(artifact.artifact_id,) if artifact else (),
            artifact_hashes=(artifact.artifact_hash,) if artifact else (),
            answers=tuple(all_answers),
            answers_hash=answers_hash,
            qualification_decision=qualification_decision,
            unresolved_mandatory_count=unresolved_mandatory,
            red_answers_count=red_count,
            idempotency_key=idempotency_key,
            compiled_at="2026-08-30T00:00:00Z",
        )

        record = OutboundActionRecord(
            action_id=action_id,
            opportunity_id=opportunity.id,
            opportunity_content_hash=opportunity.content_hash,
            workspace=workspace,
            candidate_id=candidate_id,
            track=opportunity.track,
            source=opportunity.source,
            adapter_name=adapter_name,
            adapter_version=adapter_ver,
            execution_mode=execution_mode,
            qualification_decision=qualification_decision,
            match_score_snapshot=1.0,
            artifact_ids=(artifact.artifact_id,) if artifact else (),
            artifact_hashes=(artifact.artifact_hash,) if artifact else (),
            manifest_hash=manifest.manifest_hash,
            action_status=ActionStatus.PLANNED,
            idempotency_key=idempotency_key,
            created_at="2026-08-30T00:00:00Z",
            updated_at="2026-08-30T00:00:00Z",
        )

        # 3. DRY_RUN & ASSISTED Return Points
        is_dup = self.ledger.is_duplicate(workspace, candidate_id, opportunity.id, action_type)
        decision, reasons = self.authority.evaluate_action(
            opportunity=opportunity,
            artifact=artifact,
            answers=tuple(all_answers),
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
            unresolved_mandatory_count=unresolved_mandatory,
        )

        if decision == ActionAuthorityDecision.BLOCK:
            return dataclasses.replace(record, action_status=ActionStatus.BLOCKED, blocker_reason="; ".join(reasons))

        if decision == ActionAuthorityDecision.PAUSE_FOR_REVIEW:
            return dataclasses.replace(record, action_status=ActionStatus.AWAITING_REVIEW, blocker_reason="; ".join(reasons))

        if execution_mode in (ExecutionMode.DRY_RUN, ExecutionMode.ASSISTED):
            # DRY_RUN and ASSISTED strictly refrain from submit
            return dataclasses.replace(record, action_status=ActionStatus.PREPARED)

        # 4. CONTROLLED_SUBMIT — TOCTOU-Safe Final Gate
        if execution_mode == ExecutionMode.CONTROLLED_SUBMIT:
            # Re-evaluate all authorities and kill switch immediately before submit call
            final_decision, final_reasons = self.authority.evaluate_action(
                opportunity=opportunity,
                artifact=artifact,
                answers=tuple(all_answers),
                execution_mode=execution_mode,
                adapter_name=adapter_name,
                workspace=workspace,
                candidate_id=candidate_id,
                qualification_decision=qualification_decision,
                truth_graph=tg,
                policy=pol,
                is_duplicate=self.ledger.is_duplicate(workspace, candidate_id, opportunity.id, action_type),
                captcha_detected=driver.is_captcha_present(),
                mfa_detected=driver.is_mfa_present(),
                unresolved_mandatory_count=unresolved_mandatory,
            )

            if final_decision != ActionAuthorityDecision.ALLOW_SUBMIT:
                new_status = ActionStatus.BLOCKED if final_decision == ActionAuthorityDecision.BLOCK else ActionStatus.AWAITING_REVIEW
                return dataclasses.replace(record, action_status=new_status, blocker_reason="; ".join(final_reasons))

            # Final check of kill switch immediately before irreversible call
            if not GlobalKillSwitch.is_enabled():
                return dataclasses.replace(record, action_status=ActionStatus.BLOCKED, blocker_reason="Global kill switch activated immediately before submission")

            # Atomic reservation in durable ledger
            try:
                self.ledger.reserve_submission(
                    dataclasses.replace(record, action_status=ActionStatus.SUBMITTING)
                )
            except Exception as e:
                return dataclasses.replace(record, action_status=ActionStatus.BLOCKED, blocker_reason=str(e))

            # Execute Submit
            try:
                evidence = driver.submit_page()
                if evidence and evidence.confirmed:
                    return self.ledger.transition_status(
                        idempotency_key=idempotency_key,
                        new_status=ActionStatus.CONFIRMED,
                        evidence=evidence,
                        external_reference_id=evidence.receipt_reference,
                    )
                else:
                    return self.ledger.transition_status(
                        idempotency_key=idempotency_key,
                        new_status=ActionStatus.UNKNOWN_OUTCOME,
                        blocker_reason="Confirmation receipt not detected on final page",
                    )
            except Exception as e:
                return self.ledger.transition_status(
                    idempotency_key=idempotency_key,
                    new_status=ActionStatus.UNKNOWN_OUTCOME,
                    blocker_reason=f"Submission execution exception: {str(e)}",
                )

        return record
