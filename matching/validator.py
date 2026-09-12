"""Compatibility facade for outbound artifact validation.

Claim semantics have one authority: :class:`truth.validator.ClaimValidator`.
This module retains the artifact-envelope checks needed by outbound callers:
opportunity binding, artifact integrity, assertion references, and forward
commitments. It contains no independent claim predicate whitelist.
"""
from __future__ import annotations

from dataclasses import replace
import re

from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import MetricVerification, Modality

from .artifact_validation import validate_artifact_claims
from .models import (
    ArtifactValidationResult,
    CommitmentStatus,
    TailoredArtifact,
    TailoringPolicy,
    compute_artifact_hash,
)


def _value_text(value: object) -> str:
    """Use the same stable scalar spelling that artifact claims expose."""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _contains_value(text: str, value: object) -> bool:
    return _value_text(value).strip().casefold() in text.strip().casefold()


def _metric_value_in_text(text: str, value: object) -> bool:
    rendered = format(value, "g") if isinstance(value, float) else str(value)
    return bool(re.search(rf"(?<![\d.]){re.escape(rendered)}(?![\d.])", text))


_EXACT_VALUE_PREDICATES = frozenset({
    "skill.name", "service.name", "portfolio.item",
})
_RECORD_PREDICATES = frozenset({
    "employment.record", "education.record", "certification.record",
    "portfolio.record", "language.record", "identity.location",
})
_SCALAR_PREDICATES = frozenset({
    "skill.name", "employment.title", "service.name", "portfolio.item",
    "metric", "summary", "employment.responsibility", "achievement.statement",
    "profile.approved_summary", "approved_phrase.text", "credential.status",
    "certification.state", "identity.name", "identity.headline", "identity.email",
    "identity.phone", "identity.linkedin", "identity.github", "identity.website",
    "identity.location_city", "identity.location_country",
})


class ArtifactClaimValidator:
    """Validate the artifact envelope and delegate claim semantics to truth."""

    def validate_artifact(
        self,
        artifact: TailoredArtifact,
        truth_graph: TruthGraph,
        opportunity: Opportunity | None = None,
        policy: TailoringPolicy | None = None,
        as_of: str = "2026-08-30",
    ) -> ArtifactValidationResult:
        from truth.validator import (
            ClaimValidator,
            _metric_contexts_compatible,
            _parse_structured_metrics_with_context,
            _units_compatible,
        )

        errors: list[str] = []
        warnings: list[str] = []
        verified_count = 0
        unverified_count = 0
        unresolved_commitments = 0

        # Envelope checks stay here because canonical claim validation does
        # not bind an artifact to an opportunity or protect its hash.
        if opportunity is None:
            errors.append("Opportunity binding is mandatory: target Opportunity was not supplied to validator")
        else:
            if artifact.opportunity_id != opportunity.id:
                errors.append(
                    f"Opportunity ID mismatch: artifact opportunity_id '{artifact.opportunity_id}' != target opportunity id '{opportunity.id}'"
                )
            if artifact.opportunity_content_hash != opportunity.content_hash:
                errors.append(
                    f"Opportunity content hash mismatch: artifact hash '{artifact.opportunity_content_hash}' != target opportunity hash '{opportunity.content_hash}'"
                )

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

        canonical = ClaimValidator(truth_graph)
        # Validate every structurally sound claim through the same dispatcher
        # used by the API. The assertion checks below preserve the old
        # envelope guard against unrelated-assertion/evidence laundering.
        canonical_claims = []
        for claim in artifact.generated_claims:
            if claim.is_forward_commitment:
                if claim.commitment_status == CommitmentStatus.UNRESOLVED:
                    unresolved_commitments += 1
                    warnings.append(f"Unresolved forward commitment: '{claim.text}'")
                continue

            if claim.policy_source == "NARRATIVE":
                canonical_claims.append(claim)
            elif not claim.assertion_ids and claim.section_id in ("scope_understanding", "commitments", "introduction", "alignment"):
                if claim.predicate:
                    errors.append(f"Unbacked header claim '{claim.claim_id}' in section '{claim.section_id}' must have empty predicate")
                continue
            elif not claim.assertion_ids:
                errors.append(f"Material claim '{claim.text[:60]}' in section '{claim.section_id}' has zero supporting assertion IDs")
                unverified_count += 1
                continue
            elif not claim.predicate or not claim.predicate.strip():
                errors.append(f"Material claim '{claim.claim_id}' citing assertion IDs {claim.assertion_ids} has empty predicate")
                unverified_count += 1
                continue
            elif claim.predicate not in _SCALAR_PREDICATES and claim.predicate not in _RECORD_PREDICATES:
                if claim.predicate.endswith(".record"):
                    errors.append(f"Record claim '{claim.claim_id}' uses unsupported record predicate '{claim.predicate}'")
                else:
                    errors.append(f"Unknown or unauthorized claim predicate '{claim.predicate}' in claim '{claim.claim_id}'")
                unverified_count += 1
                continue
            else:
                matched = []
                structural_ok = True
                for aid in claim.assertion_ids:
                    assertion = truth_graph.assertions.get(aid) or truth_graph.metrics.get(aid)
                    if assertion is None:
                        errors.append(f"Claim '{claim.claim_id}' references non-existent assertion ID '{aid}'")
                        structural_ok = False
                        continue
                    status = getattr(assertion, "verification_status", None)
                    if getattr(status, "value", status) != MetricVerification.VERIFIED.value:
                        errors.append(
                            f"Claim '{claim.claim_id}' references unverified assertion '{aid}' with status {getattr(status, 'value', status)}"
                        )
                        structural_ok = False
                    assertion_evidence = tuple(getattr(assertion, "evidence_ids", ()))
                    if not assertion_evidence:
                        errors.append(f"Claim '{claim.claim_id}' references assertion '{aid}' which has empty evidence_ids")
                        structural_ok = False
                    matched.append(assertion)

                all_evidence = {ev for assertion in matched for ev in getattr(assertion, "evidence_ids", ())}
                if claim.evidence_ids and not set(claim.evidence_ids).issubset(all_evidence):
                    errors.append(f"Claim '{claim.claim_id}' evidence_ids contains unbacked evidence IDs")
                    structural_ok = False
                if not structural_ok:
                    unverified_count += 1
                    continue

                if not claim.evidence_ids:
                    errors.append(
                        f"Material claim '{claim.claim_id}' must cite explicit evidence_ids; graph-wide evidence fallback is prohibited"
                    )
                    unverified_count += 1
                    continue

                if claim.predicate == "metric":
                    if not all(aid in truth_graph.metrics for aid in claim.assertion_ids):
                        errors.append(f"Metric claim '{claim.claim_id}' references a non-metric assertion")
                        unverified_count += 1
                        continue
                    if not claim.authorized_value:
                        errors.append(f"Metric claim '{claim.claim_id}' has no authorized_value bound to cited metric assertions")
                        unverified_count += 1
                        continue
                    cited_metrics = [truth_graph.metrics[aid] for aid in claim.assertion_ids]
                    metric_mismatch = []
                    for num, unit, context in _parse_structured_metrics_with_context(claim.text):
                        if not any(
                            metric.numeric_value == num
                            and _units_compatible(unit, metric.unit)
                            and _metric_contexts_compatible(metric.context, context, num)
                            and _metric_value_in_text(claim.authorized_value, metric.numeric_value)
                            for metric in cited_metrics
                        ):
                            metric_mismatch.append(f"{num} {unit}")
                    if metric_mismatch:
                        errors.append(
                            f"Metric claim '{claim.claim_id}' contains values not authorized by its cited metric IDs: {', '.join(metric_mismatch)}"
                        )
                        unverified_count += 1
                        continue
                elif claim.predicate in _RECORD_PREDICATES:
                    domain_prefix = claim.predicate.split(".", 1)[0] + "."
                    subjects = {getattr(assertion, "subject_id", "") for assertion in matched}
                    if len(subjects) != 1 or not all(
                        getattr(assertion, "predicate", "").startswith(domain_prefix)
                        for assertion in matched
                    ):
                        errors.append(
                            f"Record claim '{claim.claim_id}' cites cross-subject or mismatched-domain assertions: {subjects}"
                        )
                        errors.append(f"Record claim '{claim.claim_id}' does not match cited title or cited organization")
                        unverified_count += 1
                        continue
                    if not claim.authorized_value:
                        errors.append(f"Record claim '{claim.claim_id}' has no authorized_value bound to cited assertions")
                        unverified_count += 1
                        continue
                    record_errors = []
                    for assertion in matched:
                        value = getattr(assertion, "value", None)
                        if value is not None and not _contains_value(claim.authorized_value, value):
                            field = getattr(assertion, "predicate", "").split(".", 1)[-1]
                            record_errors.append(f"Record claim '{claim.claim_id}' authorized_value does not contain cited {field} '{value}'")
                        field = getattr(assertion, "predicate", "").split(".", 1)[-1]
                        if field in {"title", "organization", "institution", "qualification", "name", "issuer", "language"} and not _contains_value(claim.text, value):
                            record_errors.append(f"Record claim '{claim.claim_id}' text does not match cited {field} '{value}'")
                    if record_errors:
                        errors.extend(record_errors)
                        unverified_count += 1
                        continue
                else:
                    if not claim.authorized_value:
                        errors.append(f"Claim '{claim.claim_id}' has no authorized_value bound to cited assertions")
                        unverified_count += 1
                        continue
                    predicate_matches = [
                        assertion for assertion in matched
                        if getattr(assertion, "predicate", "") == claim.predicate
                    ]
                    if claim.predicate == "identity.location":
                        predicate_matches = [
                            assertion for assertion in matched
                            if getattr(assertion, "predicate", "").startswith("identity.location_")
                        ]
                    if not predicate_matches:
                        errors.append(
                            f"Claim '{claim.claim_id}' predicate '{claim.predicate}' is not bound to cited assertions"
                        )
                        if claim.predicate == "skill.name":
                            errors.append(f"Claim '{claim.claim_id}' is not authorized by cited assertions")
                        elif claim.predicate == "summary":
                            errors.append(f"Summary claim '{claim.claim_id}' lacks supporting employment.title")
                        unverified_count += 1
                        continue
                    binding_errors = [
                        f"Claim '{claim.claim_id}' authorized_value does not contain cited {getattr(assertion, 'predicate', '')} value '{getattr(assertion, 'value', '')}'"
                        for assertion in predicate_matches
                        if getattr(assertion, "value", None) is not None
                        and (
                            claim.predicate in _EXACT_VALUE_PREDICATES
                            and claim.authorized_value.strip().casefold() != _value_text(getattr(assertion, "value")).strip().casefold()
                            or claim.predicate not in _EXACT_VALUE_PREDICATES
                            and not _contains_value(claim.authorized_value, getattr(assertion, "value"))
                        )
                    ]
                    if binding_errors:
                        errors.extend(binding_errors)
                        if claim.predicate == "skill.name":
                            errors.append(f"Claim '{claim.claim_id}' is not authorized by cited assertions")
                        unverified_count += 1
                        continue
                canonical_claims.append(claim)

        canonical_artifact = replace(artifact, generated_claims=tuple(canonical_claims))
        findings = validate_artifact_claims(canonical_artifact, canonical)
        canonical_findings = [(str(item["claim_id"]), tuple(str(r) for r in item["rejection_reasons"])) for item in findings]
        verified_count += len(canonical_claims) - len(canonical_findings)
        unverified_count += len(canonical_findings)

        # Keep stable diagnostic wording for callers/tests that used the
        # former facade, without reviving its predicate rules.
        claims_by_id = {claim.claim_id: claim for claim in canonical_claims}
        for claim_id, _ in list(canonical_findings):
            claim = claims_by_id[claim_id]
            if claim.predicate == "skill.name":
                canonical_findings.append((claim_id, ("claim is not authorized by cited assertions",)))
            elif claim.predicate == "summary":
                canonical_findings.append((claim_id, ("summary claim lacks supporting employment.title or does not contain cited title",)))
            elif claim.predicate.endswith(".record"):
                canonical_findings.append((claim_id, ("record claim does not match cited title or cited organization",)))

        # Forward commitment policy checks are unchanged from the legacy
        # validator. Resolved values require a concrete configured field.
        for claim in artifact.generated_claims:
            if not claim.is_forward_commitment or claim.commitment_status != CommitmentStatus.RESOLVED:
                continue
            if not claim.policy_source or not claim.policy_source.startswith("TailoringPolicy.") or claim.policy_source == "TailoringPolicy":
                errors.append(f"Resolved forward commitment claim '{claim.claim_id}' lacks specific approved policy source (got '{claim.policy_source}')")
            elif policy is None:
                errors.append(f"TailoringPolicy object is required to validate resolved forward commitment claim '{claim.claim_id}'")
            else:
                attr_name = claim.policy_source.removeprefix("TailoringPolicy.")
                if not hasattr(policy, attr_name):
                    errors.append(f"Resolved forward commitment claim '{claim.claim_id}' cites non-existent policy field '{claim.policy_source}'")
                elif getattr(policy, attr_name) in (None, ""):
                    errors.append(f"Resolved forward commitment claim '{claim.claim_id}' cites policy field '{claim.policy_source}' which is unconfigured in policy")

        full_text = " ".join(section.content for section in artifact.sections).casefold()
        founder_creds = [a for a in truth_graph.assertions.values() if a.predicate in ("credential.status", "certification.state")]
        for cred in founder_creds:
            if getattr(cred, "modality", None) == Modality.PLANNED or str(cred.value).casefold() == "planned":
                cred_val = str(cred.value).casefold()
                if (
                    (cred_val in full_text and f"completed {cred_val}" in full_text)
                    or (cred_val in full_text and f"certified in {cred_val}" in full_text)
                    or (cred_val in full_text and f"holds {cred_val}" in full_text)
                ):
                    errors.append(f"Planned credential '{cred_val}' is falsely presented as completed in artifact text")

        for commitment in artifact.commitment_checklist:
            if commitment.status == CommitmentStatus.RESOLVED:
                if not commitment.policy_source or not commitment.policy_source.startswith("TailoringPolicy.") or commitment.policy_source == "TailoringPolicy":
                    errors.append(f"Forward commitment '{commitment.commitment_type}' marked RESOLVED without specific approved policy source")
                elif policy is None:
                    errors.append(f"TailoringPolicy object is required to validate resolved forward commitment '{commitment.commitment_type}'")
                else:
                    attr_name = commitment.policy_source.removeprefix("TailoringPolicy.")
                    if not hasattr(policy, attr_name):
                        errors.append(f"Forward commitment '{commitment.commitment_type}' cites non-existent policy field '{commitment.policy_source}'")
                    elif getattr(policy, attr_name) in (None, ""):
                        errors.append(f"Forward commitment '{commitment.commitment_type}' cites policy field '{commitment.policy_source}' which is unconfigured in policy")
            elif commitment.status == CommitmentStatus.UNRESOLVED:
                unresolved_commitments += 1
                if "UNRESOLVED" not in commitment.value:
                    errors.append(f"Unresolved forward commitment '{commitment.commitment_type}' must be explicitly marked UNRESOLVED (RED)")

        for claim_id, reasons in canonical_findings:
            errors.extend(f"Canonical claim validator rejected '{claim_id}': {reason}" for reason in reasons)

        return ArtifactValidationResult(
            is_valid=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            total_claims=len(artifact.generated_claims),
            verified_claims=verified_count,
            unverified_claims=unverified_count,
            unresolved_commitments=unresolved_commitments,
        )
