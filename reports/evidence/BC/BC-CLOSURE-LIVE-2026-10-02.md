# BC live closure evidence — 2026-10-02

## Decision

The corrected BC recommendation semantics, bounded projection refresh, feed controls, and hosted UX fixes are merged and running in production. The original “supply stop” report remains as an accurate historical checkpoint, but it is superseded by this report: committed production evidence plus later safe source results supplied six clean candidates across three employers and three source families. No human-only blocker remains for the implementation work.

## Git, PRs, CI, and deployment

| Item | Result |
|---|---|
| PR #196 | Merged; merge SHA `e2c3c3dc55e46bfd74a9b213c52f87f5b9305fa3` |
| PR #197 | Merged; merge SHA `51dffe76a7117c98965215b2a62cbc0c73d04a90` |
| Current authoritative `main` at verification | `51dffe76a7117c98965215b2a62cbc0c73d04a90` |
| PR #197 head before merge | `40731aec6daa004dce621924072e961c9af7ca55` |
| PR #196 checks | Workflow run `36931003501`; mandatory backend/web/governance/canary checks passed |
| PR #197 checks | Workflow run `36934323011`; backend, web, governance, canary, Guard, State, Mirror, and reliability passed |
| PR #197 production deployment | Workflow run `36934888756`; migration, bounded refresh, Cloudflare deploy, and hosted smoke passed |
| Open PR count at last branch inspection | 0 before this evidence-only update |

After that deployment, explicit bounded runtime work used workflow `36937555252` to poll only `lever:vrchat` (`schedules=1`, `enqueued=1`, `processed=1`) and workflow `36937856169` to drain one pending evaluation. Both succeeded. The poll returned 13 raw / 9 unique records, inserted 7 and left 2 unchanged; the new records remain Review. The drain completed the evaluation without database growth. No other source was requested by these explicit runs.

The full backend run recorded 1,881 tests, 11 failures, 19 errors, and 22 skips. Current-main comparison showed the same failure/error counts (main had 1,879 tests), so the branch introduced no additional failure or error. Do not describe the repository-wide backend suite as entirely green; the existing baseline failures remain recorded. PR #197's first attempt had two additional stale migration-head assertion failures; both were corrected and the final run passed.

PR #196 production smoke exposed a five-second statement timeout on All Time and Sort overflow at 390px. PR #197 applied `0036_dashboard_all_time_timeout` and made the Sort control full width on narrow screens. The final deployed smoke passed for desktop and 390px mobile.

## Supply, replay, and production feed

The authoritative replay report is [`BC-REPLAY-AND-SOURCE-DECISION-2026-10-01.md`](BC-REPLAY-AND-SOURCE-DECISION-2026-10-01.md). It freezes six distinct clean candidates. Diversity is an actual BC release condition at the source-family level: the replay demonstrated Greenhouse, Lever, and Hacker News contribution. Three employers are also present; the employer count had been described as preferred, and the final live set satisfies it.

The authenticated production endpoint served these six For You cards during workflow `36934888756`:

| Title | Employer | Source family |
|---|---|---|
| Senior Data Scientist | VRChat | Lever |
| Engineering Manager - Data Platform | Canonical | Greenhouse |
| Lead Data Governance Engineer | Canonical | Greenhouse |
| Staff Engineer - Recommendations | VRChat | Lever |
| Software Engineer, Agents | LiveKit | Hacker News → Ashby application |
| MLOps Field Engineer | Canonical | Greenhouse |

Each served card passed the hosted assertions for For You state, core/approved-adjacent relevance, Egypt-eligible/likely-eligible geography, an actionable application route, and absence of `bad_match`, `irrelevant_role`, or `eligibility_wrong`. The live API smoke also checked the returned application URL. The separately frozen six-candidate replay records the job-specific location and credential reasoning; it found no known geography incompatibility or unresolved required credential.

The read-only live projection query for its latest truth pack returned:

| Projection state | Rows |
|---|---:|
| For You | 25 |
| Review | 12,958 |
| Excluded | 364 |

The authenticated endpoint composes and returns six currently surfaced cards. This is not a claim that all 25 projection rows were individually browser-rendered in the smoke.

## Hosted performance and UX

Hosted smoke run `36934888756`, job `110613486741`, passed two tests (desktop and 390px mobile):

| Measure | Desktop | 390px mobile |
|---|---:|---:|
| Warm feed total p95 | 815 ms | 669 ms |
| Warm feed TTFB p95 | 814 ms | 669 ms |
| First authenticated request | 571 ms | 630 ms |

The 1.5-second feed p95 target passes on both viewports. Login returned HTTP 200. The hosted flow verified session, populated feed, facets, source filter, sort including Fit Score directions, Today/Yesterday/Specific date/All Time selectors, checklist-filter interactions, selection toolbar, and mobile overflow/layout. Application and card assertions passed. The smoke intentionally did not write Save/Reject/Applied activity into the sole production Founder history; those transitions and batch confirmation/partial-failure behavior remain covered by the focused backend/Playwright test gates. No major browser console/runtime error was reported; the only runner output noted was a Node `url.parse` deprecation warning.

The All Time dashboard metric now completes under the migration's extended function timeout. Measurements were 10.4 seconds on the first cold desktop request and 3.8 seconds on a subsequent mobile request. This metric is slower than the feed path and is not included in the feed p95 result. It remains a measurable dashboard-performance follow-up; it no longer times out.

## Capacity, queue, lifecycle, and Founder state

Latest read-only production measurement after the bounded Lever poll and evaluation drain:

- Database: **383,069,331 bytes**, approximately **365.30 MiB**.
- 16,067,731 bytes (15.30 MiB) above the 350 MiB Warning threshold.
- 34,263,917 bytes (32.67 MiB) below the 398 MiB canary abort line.
- 36,361,069 bytes (34.67 MiB) below the 400 MiB heavy-work pause.
- 62,575,469 bytes (59.68 MiB) below the 425 MiB hard stop.
- 116,930,669 bytes below the 500,000,000-byte provider quota.

The PR #197 deterministic six-ID refresh inserted no new canonical opportunities and had zero measured database growth. The earlier bounded PR #196 reconciliation changed only the selected current feed projection rows; it measured +327,680 bytes and preserved Founder state. The later explicitly bounded `lever:vrchat` poll inserted seven canonical records and grew the database by 147,456 bytes; the one-job evaluation drain added zero measured bytes. Those seven records are Review, not recommendation candidates. No broad source activation, full-corpus projection rewrite, or manual queue mutation occurred.

Latest durable queue counts:

| Status | Job type | Count |
|---|---|---:|
| COMPLETED | evaluate_new | 166 |
| COMPLETED | poll_source | 1,681 |
| DEAD_LETTER | poll_source | 77 |
| PENDING / RETRY / RUNNING | any | 0 |

All 77 dead-letter rows are historical. There are no new capacity-related dead letters in this release. Lifecycle counts at last live check were 18,059 cold, 11,900 hot, and 1,447 protected.

Founder state after deployment remains: founder identity 1, feedback 171, activity events 647, triage states 359, CV selections 13,005, outbound actions 15. These counts match the pre/post bounded refresh snapshots. Founder history was not reset or seeded.

## Scheduler state and next bounded operation

The live `source_schedules` table has **341 due sources**. The two post-deployment worker runs processed exactly one explicitly selected Lever poll and one pending evaluation; after them, the queue is empty. At/above Warning, the deployed scheduler serializes its decision and allows at most one outstanding `poll_source` across the source set; repeated ticks can still consume the overdue set over time. Therefore do not restart the full overdue corpus as a single recovery wave. The existing explicit hosted bootstrap accepts a maximum five-source batch; begin future freshness recovery with one explicitly selected, already-permitted source, measure bytes and queue after it completes, and only then decide whether to proceed to the next small batch. Do not alter Founder data, capacity thresholds, or scheduler semantics to achieve faster catch-up.

This is a controlled backlog/freshness limitation, not a queue durability or capacity-triggered job failure. Keep Jobicy, Remotive, Teamtailor, Personio, Workable, and other source policy decisions in `docs/SOURCE_REGISTRY.yaml`; no extra source request is required to justify the live For You result. The post-deployment bounded source execution did not enable the regular scheduler or consume the 341-source due set.

## Closure boundary

Implementation is landed and production-verified. The product acceptance checks for a populated relevant For You feed, third-source contribution, preserved history, and the 1.5-second feed p95 pass. The persistent warnings are explicit: the database is in the 350 MiB warning band; 342 sources are overdue but the active queue is empty; All Time metrics are comparatively slow; and global backend baseline failures remain. The next project operation should be an explicitly bounded source-freshness cohort at one source per measured step, while maintaining the 398 MiB transaction abort reserve. No broad source wave is authorized by this evidence.
