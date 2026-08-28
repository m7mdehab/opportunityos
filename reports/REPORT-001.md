# REPORT-001 — Source Reconnaissance

**Date:** 2026-08-28
**Version:** 1.4
**Codex CLI:** `0.150.0-alpha.8`

## Delivered work

- **Builder:** relocated mirrored workflow references to `ci-reference/`, added ADR-0004, and verified mirror Actions are disabled.
- **Mechanic:** implemented the stored geographic-rule model, removed the legacy classifier path, and pinned the mandated extraction and region coverage.
- **Mechanic:** added the semantic external-action allowlist and ADR-0005. TED now uses the documented unauthenticated `POST /v3/notices/search` request with only `query`, `fields`, `page`, and `limit`; metadata excludes payload contents and credentials.
- **Builder:** completed a fresh final corpus run: 2,659 raw records and 2,280 unique records. TED returned 100 parseable notices through its approved POST.

## Verification

- `python -m unittest discover -v`: 12 tests passed, including the fixed corpus, generalization cases, stored-rule cases, region assertions, and TED POST policy boundaries.
- 12 of 14 source families reached HTTP; six independent families reached HTTP; two family-level `robots_unreachable` outcomes remained. No `allowed_ok` source reported zero records.
- The final local audit set contains all 8 eligible records plus 30 excluded and 30 unclear records in ignored `out/audit-001.json`, with raw text retained locally for adjudication.

## Failures and known limitations

- The mandatory raw-text adjudication remains pending: the set was generated but extraction and derivation judgments were not independently completed. Egypt eligibility percentage and eligible precision are withheld.
- The ATS watchlist has unresolved token defects: all carried-forward Lever boards returned HTTP 404, `greenhouse:plaid` returned HTTP 404, and Ashby robots retrieval remained unreachable. No substitutions have been claimed.
- Because those gates remain open, the mirror was not synchronized from this incomplete branch and BRIEF-001 cannot advance.

## Falsification

- The corrected model reduced the final Egypt-eligible count to 8 of 2,280; broad company-description mentions are no longer treated as applicant geography. The v1.1 419 (22.9%) claim remains retracted.
- The result does not support a 37-source Phase 1 rollout or the regional moat hypothesis. It is a source-health measurement, not a validated supply figure.

## Decision

FAIL / remain in phase

No eligibility percentage is published. BRIEF-001 remains active until verified ATS substitutions, complete independent 30/30/30 raw-text adjudication, and post-merge mirror reconciliation satisfy the terminal gates.

## Next phase prerequisites

- Verify and substitute every non-resolving ATS board, then rerun the corpus.
- Complete a fresh independent raw-text adjudication and publish only aggregate precision results.
- Merge the completed phase, synchronize the relocated mirror tree, and verify mirror health and zero workflow runs.
