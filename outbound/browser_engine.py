"""Outbound Browser Automation & Form Execution Engine."""
from __future__ import annotations

import dataclasses
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
    """Executes governed outbound browser workflows across DRY_RUN, ASSISTED, and CONTROLLED_SUBMIT."""

    def __init__(
        self,
        authority: ActionAuthority | None = None,
        ledger: IdempotencyLedger | None = None,
    ) -> None:
        self.authority = authority or ActionAuthority()
        self.ledger = ledger or IdempotencyLedger()

    def execute_application(
        self,
        opportunity: Opportunity,
        artifact: TailoredArtifact | None,
        driver: BrowserDriver,
        execution_mode: ExecutionMode = ExecutionMode.DRY_RUN,
        adapter_state: AdapterLifecycleState = AdapterLifecycleState.EXPERIMENTAL,
        adapter_name: str = "greenhouse",
        workspace: str = "default",
        candidate_id: str = "founder",
        qualification_decision: QualificationDecision = QualificationDecision.QUALIFIED,
        truth_graph: TruthGraph | None = None,
        policy: TailoringPolicy | None = None,
        action_type: str = "job_application",
    ) -> OutboundActionRecord:
        """Coordinate form inspection, answering, authority checks, and governed execution."""
        tg = truth_graph or TruthGraph()
        pol = policy or TailoringPolicy()
        answer_engine = ApplicationAnswerEngine(tg, pol)

        idempotency_key = self.ledger.compute_idempotency_key(
            workspace, candidate_id, opportunity.id, action_type
        )
        action_id = f"act-{opportunity.id}-{execution_mode.value}"

        # 1. Inspect Form Fields
        fields = driver.inspect_fields()
        answers: list[ApplicationAnswer] = []
        unresolved_mandatory = 0

        for f in fields:
            ans = answer_engine.answer_field(f, opportunity, action_id, compiled_artifact=artifact)
            answers.append(ans)
            if f.required and (ans.answer is None or ans.disposition == "pause"):
                unresolved_mandatory += 1

        is_dup = self.ledger.is_duplicate(workspace, candidate_id, opportunity.id, action_type)
        captcha = driver.is_captcha_present()
        mfa = driver.is_mfa_present()

        # 2. Central Action Authority Gate
        decision, reasons = self.authority.evaluate_action(
            opportunity=opportunity,
            artifact=artifact,
            answers=tuple(answers),
            execution_mode=execution_mode,
            adapter_state=adapter_state,
            adapter_name=adapter_name,
            workspace=workspace,
            candidate_id=candidate_id,
            qualification_decision=qualification_decision,
            truth_graph=tg,
            policy=pol,
            is_duplicate=is_dup,
            captcha_detected=captcha,
            mfa_detected=mfa,
            unresolved_mandatory_count=unresolved_mandatory,
        )

        record = OutboundActionRecord(
            action_id=action_id,
            opportunity_id=opportunity.id,
            opportunity_content_hash=opportunity.content_hash,
            track=opportunity.track,
            source=opportunity.source,
            adapter_name=adapter_name,
            adapter_version="1.0.0",
            execution_mode=execution_mode,
            qualification_decision=qualification_decision,
            match_score_snapshot=1.0,
            artifact_ids=(artifact.artifact_id,) if artifact else (),
            artifact_hashes=(artifact.artifact_hash,) if artifact else (),
            answer_manifest_hash="hash_manifest",
            action_status=ActionStatus.PLANNED,
            idempotency_key=idempotency_key,
            created_at="2026-08-30T00:00:00Z",
            updated_at="2026-08-30T00:00:00Z",
            blocker_reason="; ".join(reasons) if decision in (ActionAuthorityDecision.BLOCK, ActionAuthorityDecision.PAUSE_FOR_REVIEW) else "",
        )

        # 3. Handle Decision Cases
        if decision == ActionAuthorityDecision.BLOCK:
            return dataclasses.replace(record, action_status=ActionStatus.BLOCKED)

        if decision == ActionAuthorityDecision.PAUSE_FOR_REVIEW:
            return dataclasses.replace(record, action_status=ActionStatus.AWAITING_REVIEW)

        if execution_mode == ExecutionMode.DRY_RUN:
            # DRY_RUN records preparation plan only
            return dataclasses.replace(record, action_status=ActionStatus.PREPARED)

        if execution_mode == ExecutionMode.ASSISTED:
            # ASSISTED populates fields and uploads artifact, but STRICTLY refrains from submit
            for f, ans in zip(fields, answers):
                if ans.answer is not None and ans.disposition == "auto_fill":
                    if f.ontology_type == FieldOntologyType.ATTACHMENT and artifact:
                        driver.upload_artifact(f.field_id, artifact)
                    else:
                        driver.fill_field(f.field_id, ans.answer)

            return dataclasses.replace(record, action_status=ActionStatus.PREPARED)

        if execution_mode == ExecutionMode.CONTROLLED_SUBMIT:
            # Pre-submission intent registration
            self.ledger.record_intent(
                dataclasses.replace(record, action_status=ActionStatus.SUBMITTING)
            )

            # Populate fields & Upload
            for f, ans in zip(fields, answers):
                if ans.answer is not None and ans.disposition == "auto_fill":
                    if f.ontology_type == FieldOntologyType.ATTACHMENT and artifact:
                        driver.upload_artifact(f.field_id, artifact)
                    else:
                        driver.fill_field(f.field_id, ans.answer)

            # Execute Submit & Detect Confirmation
            try:
                evidence = driver.submit_page()
                if evidence and evidence.confirmed:
                    record = self.ledger.transition_status(
                        idempotency_key=idempotency_key,
                        new_status=ActionStatus.CONFIRMED,
                        evidence=evidence,
                        external_reference_id=evidence.receipt_reference,
                    )
                else:
                    record = self.ledger.transition_status(
                        idempotency_key=idempotency_key,
                        new_status=ActionStatus.UNKNOWN_OUTCOME,
                        blocker_reason="Confirmation receipt not detected on final page",
                    )
            except Exception as e:
                record = self.ledger.transition_status(
                    idempotency_key=idempotency_key,
                    new_status=ActionStatus.UNKNOWN_OUTCOME,
                    blocker_reason=f"Submission execution exception: {str(e)}",
                )

            return record

        return record
