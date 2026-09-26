# W22.1 — ANTIGRAVITY CAPACITY / HEALTHY-MONITOR CORRECTION PACKET

## ROLE

You are continuing the FR-007 runtime lane on the **same branch** after Overseer review of W22.

The Overseer accepts the code-level stale-lease and incident-pipeline fixes from W22, but **rejects the W22 terminal PASS claim** because the final real hosted monitor still failed and the live queue has since worsened. This is not a request to redesign the system. The remaining architecture and decisions are fixed below.

Your task is execution-heavy: implement the prescribed bounded parallel worker capacity, prove it under real staging conditions, drain the existing backlog through normal worker semantics, and do not return PASS until the actual FULL monitor returns non-FAIL from a healthy queue and the open incident resolves normally.

## REPOSITORY / BRANCH

- Repository: `m7mdehab/opportunityos`
- Continue branch: `work/fr007-antigravity-final-closure`
- W22 accepted implementation SHA before this correction packet: `d3f4463e50f0cfa1fb9a49ef6d144344fe77773a`
- Do not merge.
- Do not force-push.
- Read `AGENTS.md` and the existing W22 packet/evidence before editing.

## OVERSEER REVIEW — ACCEPTED W22 WORK

Preserve these changes unless a new test proves a correctness defect:

1. `worker/queue.py` stale RUNNING lease recovery before fresh PENDING/RETRY work.
2. Retry/dead-letter progression and `SKIP LOCKED` concurrency safety.
3. `scripts/process_incident_alert.py` missing-label fallback while non-label failures remain fail-closed.
4. `scripts/fr007_cloud_monitor.py` use of `next_due_at`.
5. `scripts/fr007_soak_snapshot.py` mapping of real monitor check names into canonical soak subsystem states.
6. Monitor dependency installation and report logging.
7. Existing W22 regression tests.

Do not undo or weaken them.

## WHY W22 IS NOT TERMINALLY CLOSED

The final W22 evidence itself recorded a remaining aged queue backlog. The Overseer independently re-checked the real provider after your completion report.

### Verified workflow facts

- `35485450062` — TEST_ALERT: **SUCCESS**.
- `35485941663` — final FULL cloud monitor: **FAILURE**, not PASS.
  - incident comment: `queue_health: Oldest due job age (14038s) exceeds FAIL threshold (3600s)`.
- `35485996299` — final worker drain attempt: **CANCELLED**.
- GitHub incident #137 remains **OPEN**.

### Fresh live Supabase snapshot from Overseer review

Project: `lrrcpwaapwynzdsxzwhy`

- Alembic: `0014_backup_heartbeat`
- RUNNING jobs: **1**
- PENDING jobs: **246**
- RETRY jobs: **10**
- DEAD_LETTER: **1**
- due runnable jobs: **256**
- oldest due runnable age: **35,792 seconds**
- expired RUNNING leases: **1**
- schedules: **343**
- due schedules: **340**
- newest successful poll timestamp observed: `2026-09-20 03:18:31.952585`
- current expired job is a generic `poll_source` lease owned by `hosted-bootstrap`; do not special-case its id/source.

### Measured workload

Current schedule distribution:

- 5 sources at 1-hour cadence
- 335 sources at 6-hour cadence
- 3 sources at 24-hour cadence

Expected steady poll arrival rate is therefore approximately:

`5/1 + 335/6 + 3/24 = 60.96 source polls/hour`.

Recent 24-hour completed-poll duration sample:

- n = 32
- p50 = 37.7 s
- p75 = 84.4 s
- p90 = 356.9 s
- p95 = 462.6 s
- max = 611.8 s
- mean ≈ 102.5 s

A single worker scheduled for only 300 seconds every 15 minutes provides roughly 20 worker-minutes/hour while the measured mean workload requires roughly 104 worker-minutes/hour for poll jobs alone. Therefore the existing scheduled capacity is structurally under-provisioned for the locked source cadences.

**Do not solve this by weakening queue-age monitoring or changing source cadence.**

## FROZEN CAPACITY DECISION

Implement **bounded parallel GitHub Actions drain capacity**.

### Required production scheduling shape

Refactor `.github/workflows/fr007-worker-drain.yml` into:

1. **One enqueue phase** per workflow run:
   - executes `fr007_hosted_bootstrap.py --mode enqueue`;
   - durable PostgreSQL schedule/cooldown/idempotency remains authority;
   - never one enqueue phase per matrix shard.

2. **Five parallel drain shards** after the enqueue phase:
   - matrix shards: exactly **5** for the normal scheduled path;
   - each shard drains with normal `WorkerRunner` / `BackgroundWorkerQueue` semantics;
   - each shard has a distinct worker identity;
   - PostgreSQL `FOR UPDATE SKIP LOCKED` is the work-distribution mechanism;
   - no in-memory partition of source IDs and no provider-specific source sharding.

3. **Normal scheduled drain budget per shard**:
   - target time budget: **480 seconds**;
   - target max jobs: **30**;
   - workflow/job timeout must include sufficient headroom for one already-claimed long-tail source to finish safely. Observed max is >600 seconds, so do not use a 15-minute job timeout if an 8-minute budget can start a 10-minute handler near the end.
   - choose a finite timeout with at least ~12 minutes of post-budget headroom after setup (e.g. 25 minutes total is acceptable).

4. Keep workflow-level overlapping-run protection:
   - scheduled runs must not overlap each other indefinitely;
   - do not cancel an active drain run in a way that strands a valid lease;
   - retain `cancel-in-progress: false`.

5. Standard scheduled cadence remains **every 15 minutes** unless direct measured proof after the five-shard implementation shows it cannot sustain the locked workload. Do not increase polling source cadence or suppress due work.

### Unique worker identity

The current bootstrap hard-codes `worker_id="hosted-bootstrap"`.

Change this so every parallel shard has a unique bounded worker ID while keeping a safe default for local/tests.

Preferred contract:

- `scripts/fr007_hosted_bootstrap.py` reads `OPOS_WORKER_ID`;
- fallback remains a deterministic safe local/default value when unset;
- workflow supplies an ID derived only from non-secret GitHub metadata, e.g. run id + matrix shard;
- no secret/provider identifier enters the worker ID;
- add tests proving each workflow shard receives a unique worker identity.

Do not use one shared lease owner across five concurrent processes.

## WORKFLOW_DISPATCH CONTRACT

Preserve a manual recovery path, but make its behavior explicit.

- `mode=enqueue`: enqueue phase only; no drains.
- `mode=drain`: skip enqueue; execute the five drain shards.
- `mode=all`: enqueue once, then execute the five drain shards.
- Manual `max_jobs` and `time_budget_seconds` apply **per shard**.
- Keep finite conservative caps.
- Invalid manual input must fail closed or normalize to documented safe defaults; it must not create unbounded work.

Scheduled/push execution uses the normal production defaults above.

## IMPORTANT TIME-BUDGET SAFETY

`fr007_hosted_bootstrap._drain()` checks its time budget before starting the next job, but cannot interrupt a handler already claimed.

Therefore:

- do not set the GitHub job timeout only slightly above `time_budget_seconds`;
- the runner timeout must allow a long handler that begins immediately before budget expiry to complete and release its lease;
- do not add unsafe process killing merely to respect the soft drain budget;
- source/network handlers retain their own existing request timeouts.

Add a workflow contract test covering the timeout headroom so this does not regress.

## REQUIRED TESTS

Add/update deterministic tests for:

1. five-shard normal drain matrix exists;
2. enqueue executes once, not per shard;
3. drain shards depend on/coordinate with enqueue correctly for scheduled/`all`;
4. `mode=drain` can execute when enqueue is intentionally skipped;
5. `mode=enqueue` does not run drain shards;
6. unique `OPOS_WORKER_ID` per shard;
7. scheduled defaults are 30 jobs / 480 seconds **per shard**;
8. timeout headroom is sufficient and finite;
9. concurrency remains `cancel-in-progress: false`;
10. existing stale-lease, retry, dead-letter, and queue race tests remain green.

Run at minimum:

```bash
python -m unittest   worker.test_worker   worker.test_runner   worker.test_postgres_queue_durability   scripts.test_w17_runtime_workflows   scripts.test_fr007_cloud_monitor   -v

python -m py_compile   worker/queue.py   scripts/fr007_hosted_bootstrap.py   scripts/fr007_cloud_monitor.py   scripts/process_incident_alert.py

python scripts/check_repository.py
```

Run PostgreSQL integration proof with a real disposable PostgreSQL service where the test contract supports it. Do not claim it passed if skipped.

## REAL STAGING EXECUTION — REQUIRED, NO ESCAPE HATCH

After pushing the corrected implementation:

1. execute `mode=all` against protected FR-007 staging with the five-shard workflow;
2. inspect live queue metrics after the run;
3. repeat bounded **drain** runs as necessary until the initial backlog is genuinely caught up;
4. do not directly alter worker job status, `run_after`, lease timestamps, source schedule timestamps, or monitor thresholds;
5. it is acceptable for poll handlers to return real errors/retries/dead-letters according to existing semantics;
6. continue until all of the following are simultaneously true:
   - expired leases = **0**;
   - oldest due runnable job age < **900 seconds** for the healthy target, not merely <3600;
   - queue is not monotonically growing under normal enqueue/drain execution;
   - no unexplained worker cancellation leaves a stale lease;
   - normal source scheduling continues to enqueue due sources.

A large initial backlog is **not** a terminal blocker for W22.1. It is exactly the workload this correction exists to clear.

If one specific external source remains pathologically slow or permanently failing, allow existing retry/dead-letter policy to classify it. Do not let one source keep the whole queue unhealthy indefinitely.

## FULL MONITOR — TERMINAL PASS CONDITION

You may not return PASS until a **real FULL/MONITOR workflow run** on your final branch completes with GitHub conclusion **SUCCESS** or the repository's explicitly accepted non-failure conclusion, with:

- overall monitor state non-FAIL;
- `web_liveness`: PASS;
- `api_liveness`: PASS;
- `database_connectivity`: PASS at 0014;
- `queue_health`: PASS (not hidden);
- `source_freshness`: PASS or only an explicitly documented non-failing WARN if the acceptance code permits WARN;
- `backup_heartbeat`: PASS;
- expired leases = 0;
- queue age below the healthy target.

The earlier TEST_ALERT success remains valid. You do not need to manufacture another synthetic issue unless your new code changes incident publication behavior.

## INCIDENT #137 RESOLUTION — REQUIRED

Issue #137 is currently open because the runtime remains unhealthy.

Once a healthy FULL monitor run occurs:

- allow the existing normal `RESOLVE` path to close #137;
- verify the issue is actually closed by the workflow;
- do not close it manually just to satisfy this packet.

This proves detection + publication + recovery + resolution end-to-end.

## SOAK EVIDENCE

The successful healthy monitor run must upload a canonical soak snapshot artifact.

Verify that:

- `queue_state` maps from `queue_health`;
- `database_state` maps from `database_connectivity`;
- scheduler/source freshness state is represented;
- the healthy snapshot itself is not backdated and does not rewrite prior failed snapshots.

Do not claim the 7-day soak. This packet only establishes the **startable healthy runtime**.

## OUT-OF-SCOPE PERFORMANCE NOTE

W22 identified N+1 WAN query behavior in `storage/feed_projection_service.py`.

Do not optimize it in this packet unless a direct queue handler failure proves it is the primary blocker to achieving the required healthy monitor state. If it becomes necessary, stop and report exact profiling evidence before broad refactoring.

## GIT / FINAL REPORT

Stay on `work/fr007-antigravity-final-closure`.

Push clean commits and verify the remote SHA.

Final output must be one **W22.1 MASTER COMPLETION REPORT** with:

- STATUS PASS/BLOCKED;
- start SHA;
- final local and remote SHA;
- exact files changed;
- capacity implementation summary;
- deterministic test commands/results;
- PostgreSQL proof result;
- before/after queue metrics;
- at least one five-shard run ID and per-shard conclusions;
- final healthy FULL monitor run ID/conclusion;
- issue #137 final state;
- healthy soak artifact ID/name;
- any dead-letter jobs created and why;
- measured post-fix throughput / queue trend;
- unresolved issues;
- READY FOR OVERSEER INTEGRATION YES/NO.

**Do not return PASS while the final FULL monitor is failing, while #137 remains open, or while the live queue remains older than the healthy threshold.**
