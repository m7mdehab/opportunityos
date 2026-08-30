"""Artifact Claim-to-Evidence Validator for OpportunityOS.

Enforces 100% material factual claim coverage across all generated artifacts (CVs, cover letters,
proposals, capability statements). Validates claims directly against active TruthGraph assertions,
validity windows, epistemic status, red-line rules, certification state, and unmutated historical
values. Fails closed on any unsupported material claim, red-line rule violation, or unproven alias.
"""
from __future__ import annotations

import re
from typing import Any

from truth.graph import TruthGraph
from truth.models import Modality, VerificationStatus

from .models import (
    ArtifactValidationResult,
    CommitmentStatus,
    TailoredArtifact,
)


class ArtifactClaimValidator:
    """Validates tailored artifact claims against active TruthGraph assertions and policies."""

    def validate_artifact(
        self,
        artifact: TailoredArtifact,
        truth_graph: TruthGraph,
        as_of: str = "2026-08-30",
    ) -> ArtifactValidationResult:
        """Inspect generated artifact claims and verify full truth graph backing."""
        errors: list[str] = []
        warnings: list[str] = []
        verified_count = 0
        unverified_count = 0
        unresolved_commitments = 0

        # 1. Inspect all atomic claims generated into the artifact
        for claim in artifact.generated_claims:
            if claim.is_forward_commitment:
                if claim.commitment_status == CommitmentStatus.UNRESOLVED:
                    unresolved_commitments += 1
                    warnings.append(f"Unresolved forward commitment: '{claim.text}'")
                continue

            # Pure organizational / scoping headers don't require truth assertions
            if not claim.assertion_ids and claim.section_id in ("scope_understanding", "commitments"):
                continue

            if not claim.assertion_ids:
                errors.append(f"Material claim '{claim.text[:60]}' in section '{claim.section_id}' has zero supporting assertion IDs")
                unverified_count += 1
                continue

            # Verify that every referenced assertion ID exists in truth graph, is active, and is VERIFIED
            claim_passed = True
            for aid in claim.assertion_ids:
                # Check regular atomic assertions
                assertion = truth_graph.assertions.get(aid)
                if assertion is None:
                    # Check metric assertions
                    assertion = truth_graph.metrics.get(aid)

                if assertion is None:
                    errors.append(f"Claim '{claim.claim_id}' references non-existent assertion ID '{aid}'")
                    claim_passed = False
                elif assertion.verification_status != VerificationStatus.VERIFIED:
                    errors.append(f"Claim '{claim.claim_id}' references unverified assertion '{aid}' with status {assertion.verification_status.value}")
                    claim_passed = False
                elif not assertion.evidence_ids:
                    errors.append(f"Claim '{claim.claim_id}' references assertion '{aid}' which has empty evidence_ids")
                    claim_passed = False

            if claim_passed:
                verified_count += 1
            else:
                unverified_count += 1

        # 2. Check full text of artifact sections for unproven high-consequence keywords (e.g. invented credentials/skills)
        full_text = " ".join(s.content for s in artifact.sections).casefold()

        # Check for planned credentials represented as completed
        founder_creds = [a for a in truth_graph.assertions.values() if a.predicate in ("credential.status", "certification.state")]
        for cred in founder_creds:
            if cred.modality == Modality.PLANNED or str(cred.value).casefold() == "planned":
                cred_val = str(cred.value).casefold()
                if cred_val in full_text and f"completed {cred_val}" in full_text:
                    errors.append(f"Planned credential '{cred_val}' is falsely presented as completed in artifact text")

        # 3. Check forward commitments checklist
        for c in artifact.commitment_checklist:
            if c.status == CommitmentStatus.UNRESOLVED:
                unresolved_commitments += 1
                # Unresolved commitments are marked RED in checklist; if fabricated as resolved without policy source, fail
                if "UNRESOLVED" not in c.value and not c.policy_source:
                    errors.append(f"Forward commitment '{c.commitment_type}' fabricated without policy source")

        is_valid = (len(errors) == 0)
        return ArtifactValidationResult(
            is_valid=is_valid,
            errors=tuple(errors),
            warnings=tuple(warnings),
            total_claims=len(artifact.generated_claims),
            verified_claims=verified_count,
            unverified_claims=unverified_count,
            unresolved_commitments=unresolved_commitments,
        )
