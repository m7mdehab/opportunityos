# REPORT-001 — Source Reconnaissance

**Date:** 2026-08-27
**Version:** 1.1

## Scope completed

- Added the read-only `recon/` harness with one flat record contract, 14 public-source families, a 27-company ATS watchlist, deterministic classification, and fingerprint deduplication.
- Added network-free synthetic tests for Egypt inclusion, remote ambiguity, individual/entity signals, and the required Anywhere-plus-US-work-authorization exclusion.
- Ran the permitted GET-only measurement, generated the aggregate evidence and source registry, and retained raw third-party payloads and CSV rows only in ignored `out/`.
- Added `recon/**` to the mirrored boundary. `out/**` is ignored and was not committed or mirrored.

## Test evidence

- `python -m unittest recon.test_classification -v` passed all five synthetic tests without network or fixtures.
- The final run fetched 2,161 raw records, wrote 1,829 deduplicated CSV rows, and classified every row with eligibility and individual-eligibility reasons.
- The run produced 12 raw fixtures for 12 HTTP 200 responses; all 16 prohibited platforms have registry entries marked deliberately not fetched.
- `python scripts/check_repository.py`, `python scripts/check_guard.py`, and `python scripts/check_mirror.py` passed. PR #23 and main each ran State, Guard, and Mirror successfully; the post-Mirror Heartbeat reported `HEALTHY` and current at `20430d0`.

## Failures and known limitations

- Only Remote OK and the Greenhouse watchlist yielded normalized employment records. Himalayas, Jobicy, Remotive, We Work Remotely, UNGM, World Bank, AfDB, and Ashby were stopped by the robots gate; TED returned HTTP 405 because its Search API does not permit GET; the selected Lever boards returned HTTP 404.
- Freelancer and Etimad returned HTTP 200 but no records through the conservative parsers. No independent record was classified individual-eligible in this pass.
- The 22.9% Egypt-eligible figure is a deterministic first measurement, not a validated market estimate or a claim of availability beyond this run date.

## Outcome evidence

- `docs/SOURCE_EVIDENCE.md` records 419 Egypt-eligible records out of 1,829 unique records (22.9%), 15.4% duplicates, zero cross-source overlaps, and 58.8% with no stated geography.
- The source registry records the observed status and disables all future prepare/submit actions; no account, credential, write request, submission, or listing fetch from a prohibited platform occurred.

## What this changes about the plan

The evidence contradicts a plan to build all 37 Phase 1 adapters before proving permitted access and Egypt eligibility. The regional-eligibility moat remains a hypothesis: the first pass shows useful signal in Greenhouse and Remote OK, but broad source coverage is not yet demonstrated and independent individual-eligible supply is unmeasured. Any next adapter must first pass a source-specific permission and parser review.

## Decision

PASS

All BRIEF-001 v1.1 acceptance criteria pass. The evidence is suitable for founder review and BRIEF-002 selection.

## Deferred acceptance items

- None.

## Next phase prerequisites

- Review `docs/SOURCE_EVIDENCE.md` and select the limited, policy-reviewed source families for BRIEF-002; do not infer permission from coverage.
