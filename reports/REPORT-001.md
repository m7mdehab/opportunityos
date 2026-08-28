# REPORT-001 — Source Reconnaissance

**Date:** 2026-08-28
**Version:** 1.4
**Codex CLI:** `0.150.0-alpha.8`

## Codex-complete work

- Mirror execution safety is implemented by ADR-0004 and publish-time workflow relocation; public mirror Actions are disabled.
- Geographic eligibility uses the stored, pure model; the legacy decision path is deleted. All mandated, generalization, stored-rule, region, and external-policy tests pass.
- ADR-0005 permits only unauthenticated TED `POST /v3/notices/search` as a read-only query. TED returned 100 parseable notices without credentials.
- The ATS watchlist contains 25 verified tokens. Substitutions: `hubspot` and `plaid` to Greenhouse `airbnb` and `affirm`; eight invalid Lever tokens to Lever `shyftlabs` and `RyzLabs`; nine invalid Ashby tokens to the verified Socket, Paires, Jellyfish, Adaptive Innovations, Bedrock Robotics, CUBE, BJAK, Farseer, Regard, and Tessera Labs boards. PostHog, OpenAI, and Linear remain verified Ashby boards.
- Final corpus: 3,113 raw records, 2,564 unique records; final audit population is `8 eligible / 30 excluded / 30 unclear` under ignored `out/audit-001.json`.

## Deterministic verification

- `python -m unittest discover -v`: 13 tests passed.
- Source invariants: 12 of 14 families reached HTTP, six independent families reached HTTP, and no `allowed_ok` source had zero records. Jobicy and the shared Ashby robots endpoint are the two family-level robots-unreachable outcomes.
- `docs/SOURCE_EVIDENCE.md` reports country views (`EG`, `AE`, `SA`, `DE`), per-source Egypt rates, the Remote OK inversion (0.0% against Remotive 38.9%), and zero unmapped phrases.

## Independent audit required

Claude Code must independently adjudicate each record in `out/audit-001.json` against its raw location and body. The audit file includes immutable record IDs, source, URL, raw evidence, extracted allow/deny tokens with strings, and Codex's derived Egypt verdict. It must not trust Codex labels.

The reviewer must measure extraction precision, derivation precision, and Egypt eligible precision; preserve every disagreement's matched string; and require eligible precision of at least 90% before an eligibility percentage is published.

## Decision

READY_FOR_INDEPENDENT_AUDIT

BRIEF-001 remains active. No PASS, eligibility percentage, BRIEF-002 advancement, mirror synchronization, or independent-acceptance claim is made until the separate audit and subsequent acceptance review are complete.

## Next phase prerequisites

- Claude Code independently adjudicates `out/audit-001.json` and records precision/disagreements.
- Codex remediates any audit finding, reruns invalidated evidence, and requests a fresh independent audit.
- Architect verifies every v1.4 acceptance criterion; only then may the branch merge and synchronize the mirror.
