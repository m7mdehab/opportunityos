# W23 — Capacity Policy Correction & Runtime Recovery

**Checkpoint:** `PASS_WITH_NOT_CLOSED — policy correction landed; runtime recovery evidence recorded; Owner/Overseer closure remains independent.`
**Date:** 2026-09-27 (Africa/Cairo)
**Authoritative implementation:** PR #162, merged as `78d80d2f64dd098525cb52ea5b8e24cc59a9438a`.
**Workflow serialization follow-up:** PR #163, merged as `7344e13d3ac7874236c81b35118852a319d5c717`.

## Policy and implementation

- Superseded the internal 200 MiB operating ceiling with `PREFERRED_BYTES=300 MiB`, `WARN_BYTES=350 MiB`, `BLOCK_BYTES=400 MiB`, and `HARD_STOP_BYTES=425 MiB`. Supabase Free's approximate 500 MB boundary remains a provider limit, not an operating target.
- Worker drains inspect capacity before claiming heavy jobs. Read-only/recovery and >=400 MiB pause without claiming. The deeper write guard remains defense in depth.
- Enqueueing respects the heavy-work boundary. Drain parallelism is five below 350 MiB and one from 350 to below 400 MiB; >=400 MiB starts no new heavy job. Bounded shard limits were retained.
- PR #163 serializes runtime-takeover and ordinary worker drains under one concurrency group.
- No Storage V3, forced compaction, opportunity deletion/demotion, scoring changes, or Founder-history changes were made. Storage V3 remains deferred.

## Verification and deployment

- Focused capacity/worker suite: **116 passed**; serialization regression suite: **31 passed**.
- PR #162 and #163 required checks passed, including governance/backend tests, frontend build/lint/Playwright, reliability proof, OCI smoke/queue durability, Guard, Mirror, and State.
- Main workflow run `36318284154` used the Cloudflare staging deployment workflow: migration and `DEPLOY_STAGING` steps succeeded; `SMOKE_STAGING` failed. This run does not establish a successful authenticated smoke or production deployment.
- A direct request to `https://opportunityos.m7mdehab.com/login` returned HTTP 200 with title `OpportunityOS — Founder Alpha` on 2026-09-27. Authenticated Founder behavior remains unverified because the hosted smoke did not establish a session.

## Live recovery

Post-merge baseline: **211,176,595 bytes** (~201.4 MiB), correctly classified as normal.

- Orphan-race recovery `36318389889`: 45 historical rows/sources matched, 0 malformed, 0 enqueued, 45 skipped because active work already represented those sources, 0 skipped-newer, 0 skipped-policy. Historical DEAD_LETTER rows were preserved.
- Drain `36323472317` completed successfully in 29m39s; completed `poll_source` advanced 632→651 (+19); database ended at **288,205,971 bytes**.
- Drain `36325306598` completed four shards; one shard exceeded the 35-minute limit and was cancelled. Completed polls advanced 651→781. The cancelled job was not directly edited; its lease later expired and the normal claim path reclaimed it.
- Drain `36327591385` completed four shards; one shard exceeded 35 minutes and was cancelled. Its snapshot was **314,993,811 bytes** (~300.4 MiB), 825 completed poll jobs, 140 completed evaluations, 1 pending evaluation, 1 pending poll, 1 RUNNING poll, 0 RETRY, and 76 DEAD_LETTER.
- Drain `36330202041` (`max_jobs=1`, 60-second worker budget per shard) completed all five shards successfully. Its long-running Stripe Greenhouse poll completed through the normal worker path: 18 inserted, 273 unchanged, 410 updated, 428 inline evaluations; persistence took 1,852.966 seconds and total handler time was 1,867.658 seconds. Capacity grew **6,651,904 bytes** during that poll; it completed with `MONITOR_CAPACITY`. No row was manually mutated.
- Final live DB size: **321,645,715 bytes** (~306.7 MiB), a **110,469,120-byte** increase from the post-merge 211,176,595-byte baseline. No new capacity-related DEAD_LETTER appeared after merge.

Current DEAD_LETTER classification is 45 orphan-race historical rows, 17 historical failures under the superseded 200 MiB capacity policy, 12 lease-expiry records, and 2 connection failures. Total: 76. The 45 historical orphan rows and the 17 capacity-policy records remain unchanged. Recovery-reason distribution: one `orphan_cleanup_race` job is COMPLETED; recovery enqueued zero new jobs because all 45 sources already had active work.

Final queue counts: COMPLETED `poll_source` 827; COMPLETED `evaluate_new` 140; PENDING `evaluate_new` 1; PENDING `poll_source` 0; RETRY 0; RUNNING 0; DEAD_LETTER 76. Thus 967 completed jobs remain in the queue history. The previously-running Stripe poll completed normally and no lease recovery or manual queue edit was needed.

Current DEAD_LETTER classification is 45 orphan-race historical rows, 17 historical failures under the superseded 200 MiB capacity policy, 12 lease-expiry records, and 2 connection failures. Total: 76. The 45 historical orphan rows and the 17 capacity-policy records remain unchanged. No new capacity-related dead letters occurred during this sprint. Recovery-reason distribution: one `orphan_cleanup_race` job is COMPLETED; recovery enqueued zero new jobs because all 45 sources already had active work.

Final lifecycle counts: HOT 9,613; PROTECTED 391; COLD 19,078. Final largest measured relations: `opportunities` 94,683,136 bytes; `match_evaluations` 58,040,320; `field_provenances` 57,417,728; `storage.objects` 54,321,152 (19,110 rows); `feed_projection` 21,872,640; `opportunity_cold_archive` 15,523,840; `worker_jobs` 417,792; `source_poll_runs` 876,544. At this snapshot `storage.objects` accounts for about 16.9% of the database; monitor it as part of future aggregate growth checks. These are aggregate metadata/size snapshots, not a full-corpus scan.

Source-poll trend for the last four hours at the final aggregate query: 271 runs, 271 `ok`, 0 `error`, 519 inserted, 2,856 updated, 19,774 unchanged, and 23,209 raw ingested. The trend includes ongoing project activity and is not a causal per-poll measurement. Seven per-job database-growth samples from bounded poll work ranged from 212,992 to 9,814,016 bytes (median 1,081,344 bytes); concurrent writes mean this is an indicative workload range, not a fixed per-poll cost. The largest sample was `greenhouse:appian` (7 inserted, 3 unchanged, 164 updated, 171 inline evaluations), 9,814,016 bytes growth over 1,329.425 seconds total. The Stripe poll above added 6,651,904 bytes. Post-merge total DB growth also includes evaluation, lifecycle/read-model, and concurrent project activity, so it should not be divided by completed polls as a causal estimate.

## Capacity interpretation and remaining limits

At 321,645,715 bytes (~306.7 MiB), the database is in **Monitor** (>=300 MiB), not Warning. It is 7,072,915 bytes (6.75 MiB) above the preferred 300 MiB boundary; 45,355,885 bytes (43.25 MiB) below the 350 MiB warning; 97,784,685 bytes (93.25 MiB) below the 400 MiB new-work pause; 123,999,085 bytes (118.25 MiB) below the 425 MiB internal hard stop; and about 178.35 MB (170.09 MiB) below the approximate 500 MB provider boundary. The completed worker reported `MONITOR_CAPACITY`. Recovery is complete for the currently eligible backlog; do not start another broad wave until growth and the unusually long source fetch are reviewed.

Two different Greenhouse source polls showed unusually long in-fetch execution: the run #42 shard remained active until its 35-minute cancellation; the run #43 Stripe fetch eventually completed after ~31 minutes in the fetch stage and then persisted successfully. This is not a capacity error and produced no new capacity dead letter. It merits a separate diagnosis of end-to-end HTTP/read deadlines and large-source response behavior before more recovery work. This report does not claim that the transport cause has been proven.

The public login surface responds normally. In run `36318284154`, the staging smoke could not establish an authenticated session (one retry remained at `/login`); the desktop batch Save flow then lacked the expected `batch-action-status`. Mobile feed p95 was 2,885 ms against a 1,500 ms limit (retry: 1,849 ms). The desktop check also failed before the batch action status could be observed. These failures require separate live auth/feed-smoke and latency diagnosis; CI and public login status do not establish authenticated product health.

## Closure

Operational checkpoint only; FR-007 remains active and this is not an Owner/Overseer terminal PASS. There is no currently-running or retry queue work; one pending `evaluate_new` job remains ordinary backlog. Preserve queue history and distinguish it from the 76 historical defect/capacity/lease/connection dead letters. Storage V3 remains deferred unless measured growth approaches 350–400 MiB or storage metadata becomes dominant. Next operational action: diagnose Greenhouse fetch latency, then remeasure capacity and growth before authorizing another bounded recovery wave; authenticated Founder verification remains outstanding.
