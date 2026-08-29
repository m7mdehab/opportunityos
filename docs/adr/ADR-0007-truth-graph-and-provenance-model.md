# ADR-0007 — Professional Truth Graph and Provenance Model

- **Status:** accepted
- **Date:** 2026-08-29
- **Phase:** BRIEF-002
- **Supersedes:** none
- **Superseded by:** none

## Context

Opportunity matching, CV tailoring, and proposal generation require verifiable ground truth from founder career data and independent professional capabilities. Without an atomic provenance model, generative or heuristic systems risk hallucinating experience, exaggerating metrics, claiming planned credentials as held, or making commitments beyond business capacity, directly violating Product Constitution §2.1 and §2.5.

## Decision

Implement an atomic, dual-track Professional Truth Graph (`truth/` package):

1. **Field-Level Atomic Assertions (`AtomicAssertion`):** Every material domain fact or capability projection is represented as an atomic assertion (`id`, `subject_id`, `predicate`, `value`, `assertion_type`, `verification_status`, `evidence_ids`, `polarity`, `modality`, `qualifiers`, `effective_from`, `effective_to`, `supersedes`, `conflicts_with`).
2. **Explicit Typed Relations (`TypedRelation`):** Entity connections (e.g. `ACHIEVED_DURING`, `UTILIZES_SKILL`, `DELIVERED_SERVICE`) are explicitly represented as typed graph edges. Disconnected evidence records cannot be joined into relational claims without establishing relation provenance.
3. **Atomic Metric Assertions (`MetricAssertion`):** Performance metrics are modeled as atomic metric claims (`numeric_value`, `unit`, `context`, `modality`, `verification_status`, `evidence_ids`). Blanket entity verification cannot certify unrelated metrics inside the same evidence sentence.
4. **Structured Pre-Generation Intent Layer (`ClaimCandidate`):** Claim intents and generated text specify material assertion IDs and structured policy concepts (`concepts: frozenset[ProhibitedConceptCategory]`). Never-Claim policy evaluates structured concepts first: any intersection with prohibited categories immediately rejects the claim before or during generation.
5. **Polarity & Modality Bound Safety:** Polarity (`POSITIVE`, `NEGATIVE`) and Modality (`DEFINITE`, `APPROXIMATE`, `AT_LEAST`, `AT_MOST`, `CONDITIONAL`, `PLANNED`) are preserved. Negative evidence particles strictly reject positive claims; upper bounds (`at most N`) cannot be strengthened to exact or lower bounds (`at least N`); conditional assertions cannot become unconditional.
6. **Temporal Validity & Deterministic As-Of Semantics:** Validation accepts explicit `as_of: date | None` evaluation to determine whether credentials, work authorizations, or assertions are active or expired without relying on nondeterministic clock state.
7. **Strict Numeric & Ingestion Typing:** Integer-only fields (`hours_per_week`, `min_project_value`, `max_project_value`) strictly reject fractional strings (`"1.5"`, `"2.9"`), booleans, NaN, and infinity. Never-Claim ingestion strictly validates known concepts without silent default.
8. **Automated CI Merge Gating:** `.github/workflows/test.yml` runs the Truth suite, Recon regression suite, mirror tests, and repository integrity check on every pull request and push to `main`.
9. **Private Core Topology:** Core truth graph code resides in `truth/` and is strictly excluded from `.mirror-allowlist`, while founder private records remain confined to `private/`.

## Consequences

Downstream matching engines, CV compilers, and proposal generators can select, reorder, and summarize only verified facts. Hallucinated experience, unbacked metrics, relation laundering, modality strengthening, polarity inversions, or expired certifications fail closed at the validation boundary.

## Required tests and rollback

Maintain deterministic unit, adversarial, and property-based test suites covering model immutability, atomic assertions, typed relations, metric isolation, polarity/modality bounds, temporal as-of expiration, and 100% rejection of seeded Red Line / Never-Claim violations. Roll back by replacing the validation logic without discarding underlying evidence nodes.
