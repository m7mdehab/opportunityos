# FR-008 delivery progress

**As of:** 2026-09-25  
**State:** `PARTIAL / REVIEWABLE / NOT YET FOUNDER-TESTABLE`

## Progress

- **Implementation: approximately 24% (estimate).** The baseline/privacy guard, portfolio inventory, privacy-safe gold-review contract, canonical employment evidence, verified capability evidence, target-role predicate isolation, typed target-role tiers, W2.1 structured geography rules, W2.2 hard-requirement evidence contract, W2.3 requirement-priority extraction, W3.1 capability dimensions, and W3.2 separate preference score are implemented in the FR-008 work branch. The synthetic W2.4 benchmark recheck is green, but the required 150-real-job Founder gold-set metrics remain pending. Focused geography, benchmark, corpus, queue durability, and integrated full-suite checks pass at R8; W2.2, W2.3, W2.4, W3.1, and the W3.2 focused candidate checks are green. W3.2 integration acceptance is still pending.
- **Founder-testable: 0%.** No new application surface from FR-008 is deployed to a Founder review environment. The current checkpoint is code and evidence review only.

These percentages measure the complete FR-008 scope, including the gold-set calibration, feed controls, job-state tracking, user experience, staging checks, and Founder validation. They are progress estimates, not acceptance results.

## Current checkpoint

**Checkpoint:** W0.2/W1.1–W1.4 foundation, W2.1 geography, W2.2 evidence contract, W2.3 requirement priority extraction, W2.4 synthetic gold-set recheck, W3.1 capability dimensions, and W3.2 preference score in the implementer branch; integrated Wave 1 R8 plus focused W2.2 R2, W2.3 R2, W2.4, W3.1, and W3.2 candidate checks green; W3.2 integration acceptance pending

**What changed:** W2.1 now ignores legacy geography status/reason, resolves only from structured remote/location data plus verified Founder evidence, and keeps relocation feasibility uncertain without an explicit verified Founder-side restriction. W2.2 gives each constraint a typed, persisted, API-visible evidence contract with source pointer, job evidence, Founder evidence, tri-state decision, confidence, mandatory status, and explanation. W2.3 adds mandatory, strongly preferred, nice-to-have, contextual, and unknown requirement classes. It reads the full description when the structured skill list is empty and keeps company technology mentions out of candidate-skill gaps and strengths. W2.4 rechecked the three synthetic benchmark items; the real Founder-label calibration and corpus-wide backfill gate remain pending. W3.1 exposes separate skills, role-family history, experience, seniority, responsibility, domain, and education/certification dimensions. W3.2 adds a separate nullable preference score from verified positive preferences and directly comparable structured job values, and keeps preference-only unknowns out of objective capability fit. Preference averaging is a transparent interim baseline and is not calibrated against real Founder labels.

**What can be tested now:** Review the pushed Wave 1 checkpoint, W2.2 contract tests, W2.3 priority tests, W2.4 synthetic benchmark, W3.1 dimension contract, W3.2 preference-score candidate, and privacy-safe corpus uncertainty measurement. No Founder-facing workflow has been deployed.

**Remaining:** Integrate and verify W3.2 on the FR-008 integration branch. The 150+ real-job Founder gold set and its acceptance metrics are still required before corpus backfill or weight calibration. W3.3–W3.5 confidence/order work, W4–W8 scoring/persistence/filters/tracker/Founder UX/performance/E2E proof, final gold-set review, and terminal acceptance remain.

**Next:** Integrate and run W3.2 acceptance, then proceed to W3.3 confidence work while the real gold labels remain pending; no corpus-wide backfill or weight calibration until the Founder-reviewed set is available.

## Evidence

- Integrated Wave 1 R3 full suite: 1,586 tests passed, 22 documented skips, no failures/errors.
- Integrated Wave 1 R4 full suite at source base `7dd17b5`: 1,594 tests passed, 22 documented skips, no failures/errors.
- Repository integrity, mirror guard, migration, database preflight, and diff check passed for R4. One evidence-label wrapper command failed; the underlying acceptance commands and their exit markers were captured, as recorded in `DELIVERY-DEVIATIONS.md`.
- Integrated Wave 1 R8 full suite: 1,596 tests passed, 22 documented skips, no failures/errors. Guard, repository integrity, target preflight (`opportunityos_fr008_wave8`), Alembic migration, and diff check passed.
- W2.2-R2: all 37 focused matching model, qualification, persistence, and API serialization tests passed; repository integrity and diff check passed. The initial two-test failure is preserved and explained in `DELIVERY-DEVIATIONS.md`.
- W2.3-R2: all 51 focused requirement, matching model, skill, and scorer tests passed; repository integrity and diff check passed. The initial title-case expectation failure is preserved and explained in `DELIVERY-DEVIATIONS.md`.
- W2.4 synthetic recheck: all 3 benchmark items met qualification, score-band, and constraint expectations; all 15 gold-set and review-contract tests passed. Real Founder calibration metrics were not claimed; `W2.4-GOLD-SET-REEVALUATION.md` records the backfill gate as closed.
- W3.1-R2 and integrated W3.1 acceptance: 136 focused synthetic scorer, seniority, title-family, and predicate tests passed; repository integrity and diff checks passed. The initial fixture-only failure remains in `orders/W3.1-test.txt`; R2 and integration raw outputs are preserved separately. New dimensions are visible, but their zero placeholder weights are not calibrated weights and the 150+ real Founder-reviewed gold set is still required.
- W3.2 candidate R4: 65 focused scorer, persistence, model, and predicate tests passed, along with repository integrity and diff checks. API R2 passed 6 tests with 19 environment skips; integration will repeat API and scorer compatibility acceptance. Initial five fixture setup errors and the later country-code case mismatch remain as unchanged red evidence; named R1/R3 remediation orders and green outputs accompany them. R4 also verifies that unrelated values under the legacy track-preference predicate are ignored. W3.2 uses no real gold labels, adds no migration, and does not change Founder-testable status. See `W3.2-PREFERENCE-SCORE-REPORT.md`.
- R1 and R2 failures and their test-only remediation remain documented in `DELIVERY-DEVIATIONS.md`; their raw logs remain unchanged.
