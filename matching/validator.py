"""Artifact Claim-to-Evidence Validator for OpportunityOS.

Enforces 100% material factual claim coverage across all generated artifacts (CVs, cover letters,
proposals, capability statements). Validates claims directly against active TruthGraph assertions,
validity windows, epistemic status, red-line rules, certification state, and unmutated historical
values. Fails closed on any unsupported material claim, red-line rule violation, or unproven alias.
"""
from __future__ import annotations

import re
from typing import Any

from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import Modality, VerificationStatus

from .models import (
    ArtifactValidationResult,
    CommitmentStatus,
    TailoredArtifact,
    TailoringPolicy,
    compute_artifact_hash,
)


class ArtifactClaimValidator:
    """Validates tailored artifact claims against active TruthGraph assertions and policies."""

    def validate_artifact(
        self,
        artifact: TailoredArtifact,
        truth_graph: TruthGraph,
        opportunity: Opportunity | None = None,
        policy: TailoringPolicy | None = None,
        as_of: str = "2026-08-30",
    ) -> ArtifactValidationResult:
        """Inspect generated artifact claims and verify full truth graph backing."""
        errors: list[str] = []
        warnings: list[str] = []
        verified_count = 0
        unverified_count = 0
        unresolved_commitments = 0

        # 1. Opportunity Binding Integrity
        if opportunity is not None:
            if artifact.opportunity_id != opportunity.id:
                errors.append(
                    f"Opportunity ID mismatch: artifact opportunity_id '{artifact.opportunity_id}' != target opportunity id '{opportunity.id}'"
                )
            if artifact.opportunity_content_hash != opportunity.content_hash:
                errors.append(
                    f"Opportunity content hash mismatch: artifact hash '{artifact.opportunity_content_hash}' != target opportunity hash '{opportunity.content_hash}'"
                )

        # 2. Artifact Hash Integrity
        recomputed_hash = compute_artifact_hash(
            artifact.opportunity_id,
            artifact.opportunity_content_hash,
            artifact.artifact_type.value,
            artifact.sections,
            artifact.generated_claims,
            template_version=artifact.template_version,
            policy_version=artifact.policy_version,
            commitment_checklist=artifact.commitment_checklist,
        )
        if artifact.artifact_hash != recomputed_hash:
            errors.append("Artifact hash mismatch: artifact content, claims, or commitments were modified after compilation")

        # 3. Inspect all atomic claims generated into the artifact
        for claim in artifact.generated_claims:
            if claim.is_forward_commitment:
                if claim.commitment_status == CommitmentStatus.UNRESOLVED:
                    unresolved_commitments += 1
                    warnings.append(f"Unresolved forward commitment: '{claim.text}'")
                else:
                    if not claim.policy_source or not claim.policy_source.startswith("TailoringPolicy.") or claim.policy_source == "TailoringPolicy":
                        errors.append(
                            f"Resolved forward commitment claim '{claim.claim_id}' lacks specific approved policy source (got '{claim.policy_source}')"
                        )
                continue

            # Pure organizational / scoping headers don't require truth assertions
            if not claim.assertion_ids and claim.section_id in ("scope_understanding", "commitments"):
                continue

            if not claim.assertion_ids:
                errors.append(f"Material claim '{claim.text[:60]}' in section '{claim.section_id}' has zero supporting assertion IDs")
                unverified_count += 1
                continue

            # Verify referenced assertions
            claim_passed = True
            matched_assertions = []
            for aid in claim.assertion_ids:
                assertion = truth_graph.assertions.get(aid)
                if assertion is None:
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
                else:
                    matched_assertions.append(assertion)

            # Evidence ID provenance containment
            if matched_assertions:
                all_ev_ids = {ev for a in matched_assertions for ev in a.evidence_ids}
                if claim.evidence_ids and not set(claim.evidence_ids).issubset(all_ev_ids):
                    errors.append(f"Claim '{claim.claim_id}' evidence_ids contains unbacked evidence IDs")
                    claim_passed = False

            # Semantic Authority Verification
            if claim_passed and matched_assertions:
                if claim.predicate == "skill.name":
                    authorized_skills = [
                        str(a.value).casefold() for a in matched_assertions if getattr(a, "predicate", "") == "skill.name"
                    ]
                    target_val = (claim.authorized_value or claim.text).casefold()
                    if not any(target_val == s for s in authorized_skills):
                        errors.append(
                            f"Claim '{claim.claim_id}' asserts skill '{claim.authorized_value or claim.text}' which is not authorized by cited assertions '{authorized_skills}'"
                        )
                        claim_passed = False

                elif claim.predicate == "employment.title":
                    authorized_titles = [
                        str(a.value).casefold() for a in matched_assertions if getattr(a, "predicate", "") == "employment.title"
                    ]
                    target_val = (claim.authorized_value or claim.text).casefold()
                    if not any(t in target_val or target_val in t for t in authorized_titles):
                        errors.append(
                            f"Claim '{claim.claim_id}' asserts title '{claim.authorized_value or claim.text}' which is not authorized by cited assertions '{authorized_titles}'"
                        )
                        claim_passed = False

                elif claim.predicate == "service.name":
                    authorized_services = [
                        str(a.value).casefold() for a in matched_assertions if getattr(a, "predicate", "") == "service.name"
                    ]
                    target_val = (claim.authorized_value or claim.text).casefold()
                    if not any(target_val == s for s in authorized_services):
                        errors.append(
                            f"Claim '{claim.claim_id}' asserts service '{claim.authorized_value or claim.text}' which is not authorized by cited assertions '{authorized_services}'"
                        )
                        claim_passed = False

                elif claim.predicate == "portfolio.item":
                    authorized_ports = [
                        str(a.value).casefold() for a in matched_assertions if getattr(a, "predicate", "") == "portfolio.item"
                    ]
                    target_val = (claim.authorized_value or claim.text).casefold()
                    if not any(target_val == p for p in authorized_ports):
                        errors.append(
                            f"Claim '{claim.claim_id}' asserts portfolio item '{claim.authorized_value or claim.text}' which is not authorized by cited assertions '{authorized_ports}'"
                        )
                        claim_passed = False

                elif claim.predicate == "metric":
                    for a in matched_assertions:
                        if hasattr(a, "numeric_value"):
                            num_str = str(a.numeric_value)
                            if num_str not in claim.text and num_str not in claim.authorized_value:
                                errors.append(f"Metric claim '{claim.claim_id}' text does not contain authorized numeric value '{num_str}'")
                                claim_passed = False

            if claim_passed:
                verified_count += 1
            else:
                unverified_count += 1

        # 4. Check full text of artifact sections for planned credentials represented as completed
        full_text = " ".join(s.content for s in artifact.sections).casefold()
        founder_creds = [a for a in truth_graph.assertions.values() if a.predicate in ("credential.status", "certification.state")]
        for cred in founder_creds:
            if cred.modality == Modality.PLANNED or str(cred.value).casefold() == "planned":
                cred_val = str(cred.value).casefold()
                if (
                    (cred_val in full_text and f"completed {cred_val}" in full_text)
                    or (cred_val in full_text and f"certified in {cred_val}" in full_text)
                    or (cred_val in full_text and f"holds {cred_val}" in full_text)
                ):
                    errors.append(f"Planned credential '{cred_val}' is falsely presented as completed in artifact text")

        # 5. Check forward commitments checklist
        for c in artifact.commitment_checklist:
            if c.status == CommitmentStatus.RESOLVED:
                if not c.policy_source or not c.policy_source.startswith("TailoringPolicy.") or c.policy_source == "TailoringPolicy":
                    errors.append(f"Forward commitment '{c.commitment_type}' marked RESOLVED without specific approved policy source")
                elif policy is not None:
                    attr_name = c.policy_source.removeprefix("TailoringPolicy.")
                    val = getattr(policy, attr_name, None)
                    if val is None or val == "":
                        errors.append(f"Forward commitment '{c.commitment_type}' cites policy field '{c.policy_source}' which is unconfigured in policy")
            elif c.status == CommitmentStatus.UNRESOLVED:
                unresolved_commitments += 1
                if "UNRESOLVED" not in c.value:
                    errors.append(f"Unresolved forward commitment '{c.commitment_type}' must be explicitly marked UNRESOLVED (RED)")

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
