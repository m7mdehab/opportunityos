# FR-008 delivery progress

**As of:** 2026-09-25  
**State:** `PARTIAL / REVIEWABLE / NOT YET FOUNDER-TESTABLE`

## Progress

- **Implementation: approximately 18% (estimate).** The baseline/privacy guard, portfolio inventory, privacy-safe gold-review contract, canonical employment evidence, verified capability evidence, target-role predicate isolation, typed target-role tiers, and W2.1 structured geography rules are implemented. Focused geography, benchmark, corpus, queue durability, and integrated full-suite checks pass at R8. Waves 2–8 remain.
- **Founder-testable: 0%.** No new application surface from FR-008 is deployed to a Founder review environment. The current checkpoint is code and evidence review only.

These percentages measure the complete FR-008 scope, including the gold-set calibration, feed controls, job-state tracking, user experience, staging checks, and Founder validation. They are progress estimates, not acceptance results.

## Current checkpoint

**Checkpoint:** W0.2/W1.1–W1.4 foundation and W2.1 structured geography repair; integrated Wave 1 R8 green

**What changed:** W2.1 now ignores legacy geography status/reason, resolves only from structured remote/location data plus verified Founder evidence, and keeps relocation feasibility uncertain without an explicit verified Founder-side restriction. Synthetic matching fixtures and timing-sensitive queue test setups were aligned to the new evidence and lease contracts.

**What can be tested now:** Review the pushed code, focused W2.1 evidence, full-suite run, and privacy-safe corpus uncertainty measurement. No Founder-facing workflow has been deployed.

**Remaining:** W2.2–W2.4 requirement evidence, extraction repair, and gold-set reevaluation; W3–W8 scoring, persistence, filters/sorts, tracker, Founder UX, performance/E2E proof, final gold-set review, and terminal acceptance remain.

**Next:** Implement W2.2 hard-requirement evidence contract; continue without waiting for review unless the Founder provides steering.

## Evidence

- Integrated Wave 1 R3 full suite: 1,586 tests passed, 22 documented skips, no failures/errors.
- Integrated Wave 1 R4 full suite at source base `7dd17b5`: 1,594 tests passed, 22 documented skips, no failures/errors.
- Repository integrity, mirror guard, migration, database preflight, and diff check passed for R4. One evidence-label wrapper command failed; the underlying acceptance commands and their exit markers were captured, as recorded in `DELIVERY-DEVIATIONS.md`.
- Integrated Wave 1 R8 full suite: 1,596 tests passed, 22 documented skips, no failures/errors. Guard, repository integrity, target preflight (`opportunityos_fr008_wave8`), Alembic migration, and diff check passed.
- R1 and R2 failures and their test-only remediation remain documented in `DELIVERY-DEVIATIONS.md`; their raw logs remain unchanged.
