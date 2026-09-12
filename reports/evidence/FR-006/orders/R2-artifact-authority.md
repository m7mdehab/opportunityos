# Work order R2 — one artifact-validation authority and phone proof

## Authority and objective

BRIEF-FR-006 recovery Phase B, high consequence. Remove divergent production
artifact-validation semantics while preserving every outbound envelope, integrity,
commitment, truth-lock, and 409/no-bytes protection. Add end-to-end proof that a
synthetic Egyptian `+20` phone survives compilation and export without weakening
numeric-metric guards.

## Owned behavior seam

Compiled artifact -> canonical validation -> API rejection/bytes -> outbound gate.

## Allowed files

- a new accepted ADR under `docs/adr/`
- `matching/artifact_validation.py`
- `matching/validator.py`
- `matching/__init__.py`
- `matching/document_model.py`
- `api/routes_api.py`
- `outbound/authority.py`
- `outbound/artifact_selector.py`
- directly relevant tests under `matching/`, `outbound/`, `api/`, and `truth/`
- `reports/evidence/FR-006/closure-current/r2-*` (raw evidence)

Do not loosen `truth/validator.py`, its connective-term guard, claim coverage,
unsupported-number behavior, or action authority. If canonical claim validation
cannot absorb the legacy envelope checks safely, implement a compatibility facade
that delegates claim semantics while retaining those checks; do not simply delete
them.

## Required diagnosis and repair

1. Document the single authority boundary and migration in an ADR.
2. Preserve opportunity/content binding, artifact hash integrity, commitment-policy
   checks, and all claim validation.
3. Route API and both outbound callers through the same production entrypoint; no
   outbound import may retain an independent static predicate whitelist.
4. Add parity, unsupported-claim, tampered-envelope, and 409/no-document-byte tests.
5. Prove `+20-555-0101` (or the existing synthetic fixture phone) is present in the
   compiled artifact, extracted DOCX/PDF text, and passes the canonical gate, while
   true unsupported metrics still fail.

## Acceptance

- `py -3.12 -m unittest truth.test_validator matching.test_compiler matching.test_artifacts_e2e matching.test_adversarial outbound.test_authority outbound.test_artifact_selector -v`
- directly relevant API artifact tests, including 409/no-bytes, are green.
- repository search shows one claim-semantics authority and no outbound dependency on
  a divergent validator implementation.
- focused guard-neutralisation proof is left for an independent verifier after merge.

Commit changes and raw evidence on a dedicated branch/worktree. Report the commit.

