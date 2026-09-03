"""Shared claim-validation dispatch for compiled artifacts.

BRIEF-FR-005 D1 council remediation (defect 4b): the ADR-0014 dispatch --
NARRATIVE claims through `ClaimValidator.validate_narrative`, everything
else through `ClaimValidator.validate_claim` -- previously existed as three
independently hand-copied mirrors (`api/routes_api.py::_compile_and_export`,
`matching/test_artifacts_e2e.py`, `matching/test_compiler.py`), so the tests
exercised a copy of the production logic rather than the production logic
itself. This module is the single implementation all three now call.
"""
from __future__ import annotations

from typing import Any

from truth.validator import ClaimValidator

from .models import TailoredArtifact


def validate_artifact_claims(
    artifact: TailoredArtifact, validator: ClaimValidator
) -> list[dict[str, Any]]:
    """Validate every generated claim in `artifact` and return the findings.

    An empty list means every claim was allowed -- the caller (e.g.
    `api/routes_api.py::_compile_and_export`) is expected to treat a
    non-empty return as "do not export this artifact". Each finding has the
    same shape `_compile_and_export`'s HTTP 409 body has always used:
    `claim`, `assertion_type`, `rejection_reasons` (plus `claim_id`, which
    the HTTP layer does not currently surface but tests find useful).
    """
    findings: list[dict[str, Any]] = []
    for claim in artifact.generated_claims:
        if claim.policy_source == "NARRATIVE":
            # NARRATIVE segments (ADR-0014) assert no founder-specific fact
            # and cite no evidence; validate_narrative checks only that the
            # claim really is narrative-shaped (no assertion_ids,
            # evidence_ids, authorized_value, or parseable metric) plus the
            # prohibited-concept / red-line guards, run on the full text.
            result = validator.validate_narrative(
                claim.text,
                assertion_ids=claim.assertion_ids,
                evidence_ids=claim.evidence_ids,
                authorized_value=claim.authorized_value,
            )
        else:
            result = validator.validate_claim(claim.text, claim.evidence_ids)
        if not result.allowed:
            findings.append(
                {
                    "claim": claim.text,
                    "claim_id": claim.claim_id,
                    "assertion_type": result.assertion_type.value,
                    "rejection_reasons": list(result.reasons),
                }
            )
    return findings
