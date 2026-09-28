# BC For You Composition Checkpoint

**Status:** implementation ready for review; BC remains open pending deployed Founder acceptance.

## Change

PR #190 (`work/bc-feed-diversity`, implementation commit `98c2e09`) exposes the existing `opportunities.family_key` in a security-invoker feed view and composes eligible For You candidates before applying page offsets. The response collapses repeated families, applies the existing deterministic employer caps, and returns the family key to the card contract. Search, filter, and recommendation-state predicates remain in the hosted feed query.

## Evidence

- Current production main is `978a531`; Alembic revision is `0032_source_catalog_fastpath`.
- Live DB was `384,838,803` bytes (about `367.0 MiB`): above the `350 MiB` warning boundary and below the `400 MiB` heavy-work pause.
- Read-only projection contains 26 For You rows, 16 unique families, and six employers. The current rows have no recorded premium/manual-only application routes or stored explicit geo-ineligible state.
- There are 124 PENDING `poll_source` jobs, one PENDING `evaluate_new`, 1,545 completed polls, 153 completed evaluations, and 77 historical poll dead letters. No RETRY or RUNNING jobs were observed in this snapshot. The 124 active poll jobs represent 124 distinct sources; no duplicate active source polls were found.
- The existing `enqueue_poll_now` function locks each schedule and skips a source with a PENDING, RETRY, or RUNNING poll job. No queue rows or schedules were manually changed.
- Local checks: web production build, web lint, two For You composition Playwright tests, and 28 hosted-migration/Founder-surface contract tests passed. The local disposable PostgreSQL proof was skipped because no test database URL is configured; PR CI must run that gate.

## Remaining acceptance

1. PR #190 PostgreSQL/backend/governance/web/State/Guard/Mirror gates must pass and the migration must deploy as `0033_hosted_feed_family_key`.
2. Run the authenticated hosted smoke with the populated composed For You feed at desktop and 390px. Verify Source filters, real cards, detail and permitted actions, and hosted feed p95 at or below 1.5 seconds.
3. Inspect the served first 50 titles, family/employer distribution, historical-negative placement, application access, and geography; then recheck DB size and queue counts.

No source expansion, broad backfill, queue mutation, or Founder-history mutation is included in this checkpoint.
