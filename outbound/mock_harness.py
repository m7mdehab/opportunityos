"""Deterministic Mock ATS Server and Harness for Testing."""
from __future__ import annotations

from typing import Any, Sequence
from .models import (
    ConfirmationEvidence,
    DetectedFormField,
)
from .ontology import FieldClassifier


class MockATSHarness:
    """Simulates Greenhouse, Lever, Ashby, and Multi-Step Application workflows."""

    def __init__(
        self,
        platform: str = "greenhouse",
        steps: Sequence[Sequence[DetectedFormField]] | None = None,
        captcha_barrier: bool = False,
        mfa_barrier: bool = False,
        bot_barrier: bool = False,
        require_receipt: bool = True,
        network_error_on_submit: bool = False,
        missing_receipt_on_submit: bool = False,
    ) -> None:
        self.platform = platform
        self.custom_steps = [list(s) for s in steps] if steps is not None else None
        self.current_step = 0
        self.submitted = False
        self.submits_count = 0
        self.captcha_barrier = captcha_barrier
        self.mfa_barrier = mfa_barrier
        self.bot_barrier = bot_barrier
        self.require_receipt = require_receipt and not missing_receipt_on_submit
        self.network_error_on_submit = network_error_on_submit
        self.fields_state: dict[str, Any] = {}

    @property
    def fields_filled(self) -> dict[str, Any]:
        return self.fields_state

    def get_fields_for_step(self, step: int) -> tuple[DetectedFormField, ...]:
        if self.custom_steps is not None:
            if step < len(self.custom_steps):
                return tuple(self.custom_steps[step])
            return ()

        if self.platform == "greenhouse":
            return (
                FieldClassifier.classify_field(label="First Name", name="first_name", field_id="first_name", required=True),
                FieldClassifier.classify_field(label="Last Name", name="last_name", field_id="last_name", required=True),
                FieldClassifier.classify_field(label="Email", name="email", field_id="email", required=True),
                FieldClassifier.classify_field(label="Resume/CV", name="resume", field_type="file", field_id="resume", required=True),
                FieldClassifier.classify_field(label="Notice Period", name="notice_period", field_id="notice", required=False),
            )
        if self.platform == "lever":
            return (
                FieldClassifier.classify_field(label="Full Name", name="name", field_id="name", required=True),
                FieldClassifier.classify_field(label="Email", name="email", field_id="email", required=True),
                FieldClassifier.classify_field(label="Resume", name="resume", field_type="file", field_id="resume", required=True),
                FieldClassifier.classify_field(label="Need sponsorship?", name="sponsorship", field_id="sponsorship", required=True),
            )
        if self.platform == "ashby":
            return (
                FieldClassifier.classify_field(label="Name", name="name", field_id="name", required=True),
                FieldClassifier.classify_field(label="Email", name="email", field_id="email", required=True),
                FieldClassifier.classify_field(label="Expected Compensation", name="comp", field_id="compensation", required=False),
                FieldClassifier.classify_field(label="Resume", name="resume", field_type="file", field_id="resume", required=True),
            )
        if self.platform == "multi_step":
            if step == 0:
                return (
                    FieldClassifier.classify_field(label="First Name", name="first_name", field_id="first_name", required=True),
                )
            if step == 1:
                return (
                    FieldClassifier.classify_field(label="Email", name="email", field_id="email", required=True),
                )
            return (
                FieldClassifier.classify_field(label="Resume", name="resume", field_type="file", field_id="resume", required=True),
            )
        return ()

    def fill(self, field_id: str, value: Any) -> None:
        self.fields_state[field_id] = value

    def next_step(self) -> bool:
        if self.custom_steps is not None:
            if self.current_step < len(self.custom_steps) - 1:
                self.current_step += 1
                return True
            return False

        if self.platform == "multi_step" and self.current_step < 2:
            self.current_step += 1
            return True
        return False

    def submit(self) -> ConfirmationEvidence:
        if self.network_error_on_submit:
            raise ConnectionError("Network dropped during submission")
        if self.captcha_barrier:
            raise RuntimeError("CAPTCHA barrier triggered on submission")
        if self.mfa_barrier:
            raise RuntimeError("MFA barrier triggered on submission")
        if self.bot_barrier:
            raise RuntimeError("Bot challenge barrier triggered on submission")

        self.submitted = True
        self.submits_count += 1
        receipt = "APP-987654" if self.require_receipt else ""
        return ConfirmationEvidence(
            confirmed=self.require_receipt,
            confirmation_text="Thank you for applying. Your application has been submitted." if self.require_receipt else "Submission pending confirmation.",
            application_id="app-12345" if self.require_receipt else "",
            receipt_reference=receipt,
            final_url="https://boards.greenhouse.io/cloudflare/jobs/101/confirmation" if self.require_receipt else "https://boards.greenhouse.io/cloudflare/jobs/101/status",
        )
