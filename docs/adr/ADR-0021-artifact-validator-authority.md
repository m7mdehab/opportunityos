# ADR-0021 — Canonical Artifact Claim Validation Boundary

- **Status:** Accepted
- **Date:** 2026-09-13
- **Related:** BRIEF-FR-006 R2, ADR-0014, ADR-0018

## Decision

`truth.validator.ClaimValidator` is the sole authority for claim semantics.
The API and outbound artifact paths use the shared
`matching.artifact_validation.validate_artifact_claims` dispatcher. The
historical `matching.validator.ArtifactClaimValidator` remains as a
compatibility facade for outbound integrations, but delegates claim decisions
to that dispatcher.

The facade retains only envelope responsibilities that claim validation does
not own: opportunity ID/content-hash binding, artifact hash integrity,
assertion-reference and evidence containment checks, and forward-commitment
policy checks. It fails closed on those checks and does not maintain a
predicate whitelist.

## Consequences

Changes to claim admissibility, metrics, red lines, modality, or provenance
are made in `truth/validator.py` and are exercised by API and outbound paths
through the same dispatcher. Envelope protections remain independently
testable without creating a second semantic validator.
