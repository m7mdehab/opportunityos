# Wave 8 readiness — gold-set review, staging smoke, and closure

Decision: NOT READY — gated by external data and environment prerequisites
Order: `W8-GOLD-SET-REVIEW-AND-CLOSURE-ORDER.md`
Readiness checked: 2026-09-26

## Available

- W7.4 responsive/accessibility source and evidence checkpoints are pushed (`0d9bcb3` feature; `202b3bc` integrated source; `e4e03f4` integrated evidence).
- The feature and integration branches each passed lint, Next route type generation, TypeScript, 21 focused mock Chromium tests, repository integrity, and diff checks.
- The brief’s gold-set size, required strata, labels, thresholds, and closure conditions are captured unchanged in the order.

## Missing gates

- No approved reviewed sample of 150 or more real employment jobs and Founder labels was supplied through an authorized review source.
- No safe staging/Founder review environment is available to run the hosted smoke or let the Founder test this checkpoint.
- Full-corpus metrics, independent false-positive/false-negative review, and empirical score-band calibration cannot be proven by synthetic mock data.

## Decision

Do not start W8.1/W8.2 real-data evaluation or W8.3 staging smoke yet. The current local mock is not an acceptable substitute for the reviewed gold set or hosted Founder review. Do not access `private/`, Founder profile/CV/truth-pack data, a live database/provider, or corpus content. Do not run backfill, production calibration, migration, deployment, or terminal closure. Resume this order when the user/Founder supplies an authorized reviewed set and a safe staging target is available; retain the FR-008 state as `PARTIAL / REVIEWABLE / NOT YET FOUNDER-TESTABLE`, with Founder-testable at 0%.
