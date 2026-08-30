"""Deterministic Mock ATS Server and Harness for Testing."""
from __future__ import annotations

from typing import Any
from .models import (
    ConfirmationEvidence,
    DetectedFormField,
)
from .ontology import FieldClassifier


class MockATSHarness:
    """Simulates Greenhouse, Lever, Ashby, and Multi-Step Application workflows."""

    def __init__(self, platform: str = "greenhouse") -> None:
        self.platform = platform
        self.current_step = 0
        self.submitted = False
        self.captcha_barrier = False
        self.mfa_barrier = False
        self.bot_barrier = False
        self.require_receipt = True
        self.fields_state: dict[str, Any] = {}

    def get_fields_for_step(self, step: int) -> tuple[DetectedFormField, ...]:
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
        if self.platform == "multi_step" and self.current_step < 2:
            self.current_step += 1
            return True
        return False

    def submit(self) -> ConfirmationEvidence:
        if self.captcha_barrier:
            raise RuntimeError("CAPTCHA barrier triggered on submission")
        if self.mfa_barrier:
            raise RuntimeError("MFA barrier triggered on submission")
        if self.bot_barrier:
            raise RuntimeError("Bot challenge barrier triggered on submission")

        self.submitted = True
        receipt = "APP-987654" if self.require_receipt else ""
        return ConfirmationEvidence(
            confirmed=self.require_receipt,
            confirmation_text="Thank you for applying. Your application has been submitted." if self.require_receipt else "Submission pending confirmation.",
            application_id="app-12345" if self.require_receipt else "",
            receipt_reference=receipt,
            final_url="https://boards.greenhouse.io/cloudflare/jobs/101/confirmation" if self.require_receipt else "https://boards.greenhouse.io/cloudflare/jobs/101/status",
        )
