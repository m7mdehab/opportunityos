# FR-007 Frozen Due-Source Overnight Catch-Up — 2026-10-03

## Result

The frozen starting manifest is reconciled. The finalizer passed production queue, Founder-owned state, lifecycle, cold archive, migration-head, and capacity checks. Of 342 frozen sources, 340 succeeded and two were deferred after bounded worker lease retries. No source result remains unresolved in the runner's terminal-state ledger.

## Code and CI

- Starting `main`: `c21d6a251b671bffe23efcb4e67d54e04e32c9c7` (PR #217's catch-up implementation was already merged).
- PR #218 fixed stale poll attribution so a previous successful poll cannot make a newer timed-out worker job appear successful.
- PR #218 commits: `4a9f1e87ce016f1554cec91068f1997d01f9561e`, `274a4c03c1b3a01241754f516ab0c1dede3979af`.
- Merge commit/final `main`: `929f03489b74d8258c2c171a7ed00f13900d6970`.
- Focused catch-up/bootstrap unit tests: 54 passed; `git diff --check` passed.
- CI for the PR head passed: backend PostgreSQL suite, governance, web build, ESLint, Playwright smoke, Guard, State, and Mirror. Supabase Preview was skipped because the PR had no Supabase branch. A first State run failed on stale generated state; `docs/STATE.md` was regenerated and the latest State check passed.
- PR #218: https://github.com/m7mdehab/opportunityos/pull/218

## Frozen manifest and processing

- Frozen at `2026-10-02T00:54:29.664405Z` (03:54 Cairo).
- Count: 342; SHA-256: `c9bf10fd536b8875b8aeb3d1bdf76878a34763b1f8e4e2f81982f80a97e42143`.
- Outcomes: 340 successful; 2 deferred; 0 unclassified.
- Deferred source IDs: `greenhouse:spacex` and `greenhouse:andurilindustries`. Both have `Lease expired without completion` after `retry_count=3` of `max_retries=3`; their older successful poll records predate this run and were not counted as success. These are source-specific worker timeouts; the evidence does not identify an HTTP/provider status. Their historical dead-letter rows were preserved.
- Six 50-source cohorts and one 42-source cohort; 43 explicit waves, with no more than five source workers per wave. The waves created 207 poll jobs and 42 evaluation jobs, with queue convergence between waves.
- The remaining manifest successes were observed as successful post-freeze normal scheduled polls before their bounded cohort wave needed to enqueue work. The catch-up finalizer counts each source once against the frozen manifest.
- Since freeze, 342 successful poll-run rows cover 340 distinct frozen sources; `hacker_news_who_is_hiring` had two additional routine cadence polls after its first success. One `lever:vrchat` poll was outside the frozen manifest and is recorded as ordinary scheduler activity, not catch-up scope.
- First post-freeze poll per successful manifest source: 676 inserted opportunities, 2,841 updated, 24,768 raw records. Including two later Hacker News cadence polls and the one outside-manifest routine poll, all post-freeze successful poll rows total 705 inserted, 2,856 updated, and 25,082 raw records.

## Capacity and maintenance

- DB at manifest freeze: 383,315,091 bytes (365.6 MiB).
- Final live DB: 404,171,923 bytes (385.4 MiB).
- Final distance to the 400 MiB pause (419,430,400 bytes): 15,258,477 bytes (14.55 MiB).
- Final distance to the overnight 390 MiB ceiling (408,944,640 bytes): 4,772,717 bytes (4.55 MiB).
- Final distance to the 425 MiB hard stop (445,644,800 bytes): 41,472,877 bytes (39.55 MiB).
- Maintenance-only run #23: `37037481252`; completed and reclaimed approximately 7,143,424 bytes. It reported a temporary 442,584,211-byte peak during the safe metadata rewrite, below the 500,000,000-byte provider quota.
- Maintenance-only run #24: `37060507058`; completed and reclaimed approximately 598,016 bytes. No further physical rewrite was run because the latest measured reclaim was small and the final DB remained below both the overnight 390 MiB ceiling and formal 400 MiB pause.
- Largest public relations at final measurement: `opportunities` 132,603,904 bytes; `match_evaluations` 86,859,776; `field_provenances` 84,000,768; `feed_projection` 36,462,592; `opportunity_cold_archive` 11,354,112.

## Final production invariants

- Queue: 2,263 COMPLETED (2,024 `poll_source`, 239 `evaluate_new`); 80 DEAD_LETTER `poll_source`; 0 PENDING, 0 RETRY, 0 RUNNING.
- Dead letters: 77 at freeze, 80 final (+3). The increase is exactly the two SpaceX lease-timeout jobs and one Anduril lease-timeout job. No historical row was reset or edited.
- Lifecycle: 32,145 opportunities = 12,477 HOT + 2,656 PROTECTED + 17,012 COLD. Cold archive rows: 17,012. Cold description, raw-payload, provenance, and verbose-evaluation leakage: 0 each. Maximum current projections/evaluations per opportunity: 1 each.
- Current migration head: `0036_dashboard_all_time_timeout`.
- Founder-owned aggregates are unchanged: identity 1; auth users 1; feedback 171 (24 `bad_match`, 5 `eligibility_wrong`, 2 `good_match`, 140 `irrelevant_role`); activity 647; triage 359; outbound actions 15; filter settings 10. Saved/rejected/applied/submitted counts are unchanged.
- `founder_cv_selections` is the evaluation-derived selector output, not manually edited Founder preference; it grew from 13,010 to 14,725 (+1,715) as new evaluations were persisted.
- Current source schedule snapshot: 344 schedules, 246 due, 0 cooling, 0 due with consecutive failures. These are recurring/future schedules and do not change the frozen 342-source completion count.
- Public application root and `/login` both returned HTTP 200. No application code was deployed or changed in this source-data operation.

## Workflow evidence

- Catch-up runs #18–#22 include `37028508324`, `37029831623`, `37037833641`, `37060917708`, and finalization run `37064231943`.
- Finalization uploaded artifact `fr007-overnight-catchup-state`, artifact ID `11252066303`, with final status `FINAL_MAINTENANCE_RECOMMENDED` because the database remains above the 380 MiB proactive-maintenance point. All final invariants passed; run #24 was the final maintenance-only reclaim and recovered only about 0.57 MiB.
- PR #218 checks: Guard `37063516344`; Mirror `37063516374`; State `37063516402`; combined Governance/Backend/Web/Playwright `37063516349`.
- At close: `main` only, PR #218 merged, zero open PRs.

## Follow-up

Continue ordinary scheduling conservatively with the existing bounded worker envelope. Do not widen this frozen manifest or create a broad recovery queue. Investigate SpaceX and Anduril only through a separately bounded source-specific retry if they become actionable under normal cadence; preserve the three dead-letter rows as history.
