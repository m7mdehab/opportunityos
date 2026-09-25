# FR-008 delivery progress

**As of:** 2026-09-25  
**State:** `PARTIAL / REVIEWABLE / NOT YET FOUNDER-TESTABLE`

## Progress

- **Implementation: approximately 15% (estimate).** The baseline/privacy guard, portfolio inventory, privacy-safe gold-review contract, canonical employment evidence, verified capability evidence, target-role predicate isolation, typed target-role tiers, and W2.1 structured geography rules are implemented. Focused geography, benchmark, corpus, and all 17 PostgreSQL queue durability tests pass; an integrated full-suite run is still required after test-fixture repairs. Waves 2–8 remain.
- **Founder-testable: 0%.** No new application surface from FR-008 is deployed to a Founder review environment. The current checkpoint is code and evidence review only.

These percentages measure the complete FR-008 scope, including the gold-set calibration, feed controls, job-state tracking, user experience, staging checks, and Founder validation. They are progress estimates, not acceptance results.

## Current checkpoint

**Checkpoint:** W0.2/W1.1–W1.4 reviewable backend foundation; W2.1 and queue test repairs integrated locally, R8 pending

**What changed:** In addition to the Wave 1 foundation, W2.1 now ignores legacy geography status/reason, uses structured remote and country evidence, and keeps relocation feasibility uncertain without an explicit verified Founder-side restriction. Its focused tests, repository check, and diff check pass.

**What can be tested now:** Review the local FR-008 branch and focused W2.1 evidence. No Founder-facing workflow has been deployed.

**Remaining:** Run the fresh integrated Wave 1 suite once after the queue timing repairs. W2.2 onward, feed controls, tracking workflows, Founder UX, performance/E2E proof, gold-set review, and terminal acceptance remain.

**Next:** Complete integrated Wave 1 R8 verification; if green, push W2.1 and proceed to W2.2 without waiting for review.

## Evidence

- Integrated Wave 1 R3 full suite: 1,586 tests passed, 22 documented skips, no failures/errors.
- Integrated Wave 1 R4 full suite at source base `7dd17b5`: 1,594 tests passed, 22 documented skips, no failures/errors.
- Repository integrity, mirror guard, migration, database preflight, and diff check passed for R4. One evidence-label wrapper command failed; the underlying acceptance commands and their exit markers were captured, as recorded in `DELIVERY-DEVIATIONS.md`.
- R1 and R2 failures and their test-only remediation remain documented in `DELIVERY-DEVIATIONS.md`; their raw logs remain unchanged.
