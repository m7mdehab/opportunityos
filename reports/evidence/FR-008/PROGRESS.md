# FR-008 delivery progress

**As of:** 2026-09-25  
**State:** `PARTIAL / REVIEWABLE / NOT YET FOUNDER-TESTABLE`

## Progress

- **Implementation: approximately 20% (estimate).** The baseline/privacy guard, portfolio inventory, privacy-safe gold-review contract, canonical employment evidence, verified capability evidence, target-role predicate isolation, typed target-role tiers, W2.1 structured geography rules, W2.2 hard-requirement evidence contract, and W2.3 requirement-priority extraction are implemented. Focused geography, benchmark, corpus, queue durability, and integrated full-suite checks pass at R8; W2.2 is green at R2 and W2.3's focused requirement/model/skill/scorer acceptance is green at R2.
- **Founder-testable: 0%.** No new application surface from FR-008 is deployed to a Founder review environment. The current checkpoint is code and evidence review only.

These percentages measure the complete FR-008 scope, including the gold-set calibration, feed controls, job-state tracking, user experience, staging checks, and Founder validation. They are progress estimates, not acceptance results.

## Current checkpoint

**Checkpoint:** W0.2/W1.1–W1.4 foundation, W2.1 geography, W2.2 evidence contract, and W2.3 requirement priority extraction; integrated Wave 1 R8 plus focused W2.2 R2 and W2.3 R2 green

**What changed:** W2.1 now ignores legacy geography status/reason, resolves only from structured remote/location data plus verified Founder evidence, and keeps relocation feasibility uncertain without an explicit verified Founder-side restriction. W2.2 gives each constraint a typed, persisted, API-visible evidence contract with source pointer, job evidence, Founder evidence, tri-state decision, confidence, mandatory status, and explanation. W2.3 adds mandatory, strongly preferred, nice-to-have, contextual, and unknown requirement classes. It reads the full description when the structured skill list is empty and keeps company technology mentions out of candidate-skill gaps and strengths.

**What can be tested now:** Review the pushed Wave 1 checkpoint, W2.2 contract tests, W2.3 priority tests, and privacy-safe corpus uncertainty measurement. No Founder-facing workflow has been deployed.

**Remaining:** W2.4 gold-set reevaluation before corpus backfill; W3–W8 scoring calibration, persistence, filters/sorts, tracker, Founder UX, performance/E2E proof, final gold-set review, and terminal acceptance remain.

**Next:** Re-evaluate the gold set against W2.1–W2.3 before any corpus-wide backfill; continue without waiting for review unless the Founder provides steering.

## Evidence

- Integrated Wave 1 R3 full suite: 1,586 tests passed, 22 documented skips, no failures/errors.
- Integrated Wave 1 R4 full suite at source base `7dd17b5`: 1,594 tests passed, 22 documented skips, no failures/errors.
- Repository integrity, mirror guard, migration, database preflight, and diff check passed for R4. One evidence-label wrapper command failed; the underlying acceptance commands and their exit markers were captured, as recorded in `DELIVERY-DEVIATIONS.md`.
- Integrated Wave 1 R8 full suite: 1,596 tests passed, 22 documented skips, no failures/errors. Guard, repository integrity, target preflight (`opportunityos_fr008_wave8`), Alembic migration, and diff check passed.
- W2.2-R2: all 37 focused matching model, qualification, persistence, and API serialization tests passed; repository integrity and diff check passed. The initial two-test failure is preserved and explained in `DELIVERY-DEVIATIONS.md`.
- W2.3-R2: all 51 focused requirement, matching model, skill, and scorer tests passed; repository integrity and diff check passed. The initial title-case expectation failure is preserved and explained in `DELIVERY-DEVIATIONS.md`.
- R1 and R2 failures and their test-only remediation remain documented in `DELIVERY-DEVIATIONS.md`; their raw logs remain unchanged.
