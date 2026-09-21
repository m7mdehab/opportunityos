# W22.3 — CODEX RUNTIME TAKEOVER / ANTIGRAVITY CAPACITY CLOSURE

## STATUS AND PURPOSE

Antigravity has exhausted its current weekly execution allowance. This packet transfers the unfinished FR-007 runtime lane to Codex without changing the frozen runtime architecture or acceptance contract.

This is an execution packet, not a redesign request. Work autonomously through implementation, testing, protected hosted proof, queue catch-up, monitoring, and remediation. Do not return for routine failures.

## REPOSITORY / BRANCH

Repository: `m7mdehab/opportunityos`

Work exclusively on:

`work/fr007-codex-runtime-takeover`

Base SHA:

`6d55549e2f97c835caa560552657efb49a661e7b`

Do not merge. Do not force-push.

Before editing, read completely:

- `AGENTS.md`
- `docs/STATE.md`
- `reports/evidence/FR-007/W22_ANTIGRAVITY_FINAL_CLOSURE_EXECUTION_PACKET.md` from `work/fr007-antigravity-final-closure`
- `reports/evidence/FR-007/W22_1_ANTIGRAVITY_CAPACITY_CORRECTION_PACKET.md` from that branch
- `reports/evidence/FR-007/W22_2_ANTIGRAVITY_CONNECTION_PRESSURE_CORRECTION_PACKET.md` from that branch
- `reports/evidence/FR-007/W22_2A_OVERSEER_EXECUTION_DIRECTIVE.md` from that branch

The Antigravity branch is now substantially diverged from integration. Do NOT merge it wholesale. Reconcile and port only accepted runtime changes against the current integration ancestry.

## WHAT ANTIGRAVITY ACTUALLY FINISHED

Preserve/reconcile these already-established behaviors:

1. Stale RUNNING leases are reclaimed before ordinary PENDING/RETRY work.
2. Reclaim uses PostgreSQL row locking / `SKIP LOCKED` and preserves retry/dead-letter semantics.
3. Lease-fenced completion/failure prevents a worker that lost ownership from overwriting a new owner's outcome.
4. Monitor queue age uses the durable due/run-after semantics rather than a misleading timestamp.
5. Incident publication has the accepted missing-label fallback while unrelated API/permission/network failures remain fail-closed.
6. The runtime capacity shape is frozen as:
   - one enqueue phase,
   - exactly five parallel drain shards,
   - unique worker IDs,
   - 30 jobs / 480 seconds per shard on the normal path,
   - adequate timeout headroom for long source handlers,
   - `cancel-in-progress: false`,
   - no source-specific in-memory sharding.
7. The existing Antigravity `.github/workflows/fr007-worker-drain.yml` demonstrates the intended five-shard workflow shape.
8. Expired-lease, retry, dead-letter, concurrency and workflow-contract regression coverage was added in the Antigravity lane.

These are accepted concepts/behaviors, not permission to blindly copy stale files over newer integration changes.

## WHAT ANTIGRAVITY DID NOT FINISH

W22.2 connection-pressure correction was never implemented. The Antigravity branch contains the W22.2 packet/directive but no connection-lifecycle code correction after the last accepted runtime implementation.

Do not continue the old pattern of repeatedly dispatching drain runs before fixing this.

## OVERSEER ROOT-CAUSE TRACE — VERIFY, THEN FIX

The current runtime code reveals a concrete connection-amplification path:

1. `scripts/fr007_hosted_bootstrap.py` creates one engine and one `session_factory`.
2. `_drain(factory, ...)` creates the `WorkerRunner` with that factory.
3. But it calls `default_handler_registry(...)` without passing `session_factory=factory`.
4. Handler closures therefore fall back to `worker.handlers._production_session_factory()`.
5. `_production_session_factory()` creates another SQLAlchemy engine and factory.
6. `storage.engine.get_engine()` currently uses SQLAlchemy's default pooled behavior for PostgreSQL.
7. The runner heartbeat intentionally needs a separate concurrent DB session while a handler is active.
8. A handler can also open persistence / poll-run sessions.

This is consistent with the earlier live proof where five worker shards consumed all 15 Supavisor session-mode slots and caused `EMAXCONNSESSION`, including persistent idle / idle-in-transaction connections.

Treat this as a high-confidence diagnosis to prove, not as an instruction to code blindly.

## REQUIRED CONNECTION-LIFECYCLE OUTCOME

Keep exactly five normal drain shards.

Implement a deliberate hosted connection lifecycle that satisfies all of the following:

- one deliberately bounded engine/pool per worker process;
- the bootstrap-created session factory is explicitly injected into the default handler registry;
- handlers must not silently create a second production engine when an explicit factory exists;
- the heartbeat remains able to renew a lease concurrently with a running handler;
- no transaction is held open while remote HTTP/network work is waiting;
- all success and failure paths close or roll back sessions correctly;
- engine disposal occurs at process exit;
- hosted pool limits are finite and leave measured headroom below Supabase's 15-session-mode connection cap.

A small bounded QueuePool such as `pool_size=2, max_overflow=0` for this hosted worker process is a plausible design because the worker may legitimately need one handler/queue connection plus one heartbeat connection concurrently. `NullPool` or another SQLAlchemy-supported approach is also acceptable if measured evidence is stronger.

Do not adopt a specific pool value merely because this packet mentions it. Prove it under the five-shard live workload.

Do not lower worker count, cadence, queue thresholds, or lease guarantees to make the proof pass.

## FRESH LIVE BASELINE — 2026-09-21 OVERSEER VERIFICATION

Production Supabase project: existing FR-007 project.

Current Alembic head:

`0019_activity_view_access`

The runtime proof must therefore validate the legitimate current migration head. Do not downgrade to 0015 and do not hard-code an obsolete migration expectation.

Fresh queue state:

- COMPLETED: 270
- DEAD_LETTER: 2
- PENDING: 537
- RETRY: 43
- RUNNING: 1
- due runnable: 580
- oldest due runnable age: 90,852 seconds
- expired RUNNING leases: 1
- source schedules: 343
- due schedules at the snapshot: 98
- latest successful source poll: 2026-09-21 08:24:01 UTC

Current database activity while Antigravity is no longer actively running five shards:

- active: 1
- idle: 5
- other/null state: 1
- total observed: 7

The fact that the pool is not saturated while the worker wave is stopped is NOT acceptance evidence. The correction must be measured under real five-shard activity.

GitHub incident #137 remains OPEN.

The queue is materially worse than the last Antigravity report. There is no terminal runtime PASS.

## PARALLEL LANE BOUNDARIES

A separate Codex lane is correcting Founder activity/history:

`work/fr007-codex-founder-activity-correction`

Production is already at Alembic `0019_activity_view_access`.

Do not modify Founder activity migrations, activity API/UI behavior, CV files, or unrelated web UX in this runtime takeover.

If runtime proof exposes a defect in that lane, report it rather than editing across lane ownership.

## REQUIRED RECONCILIATION

Selectively port/reimplement the accepted Antigravity runtime behavior on this current integration-based branch.

Expected runtime write scope may include:

- `worker/queue.py`
- `worker/runner.py`
- `worker/handlers.py`
- `storage/engine.py`
- `scripts/fr007_hosted_bootstrap.py`
- `scripts/fr007_cloud_monitor.py`
- `scripts/fr007_soak_snapshot.py`
- `scripts/process_incident_alert.py`
- `.github/workflows/fr007-worker-drain.yml`
- `.github/workflows/fr007-cloud-observability.yml`
- directly related deterministic tests/evidence

Preserve newer integration changes not owned by this packet.

## DETERMINISTIC TEST CONTRACT

Add/retain tests proving at minimum:

1. stale leases are reclaimed before fresh backlog;
2. two workers cannot both reclaim the same stale lease;
3. lost lease owners cannot complete/fail another worker's job;
4. retry/dead-letter progression remains bounded;
5. five-shard normal workflow exists;
6. enqueue occurs once, not once per shard;
7. each shard has a unique worker identity;
8. normal defaults remain 30 jobs / 480 seconds per shard;
9. timeout headroom is finite and sufficient;
10. `cancel-in-progress: false` remains;
11. bootstrap injects the intended session factory into all default handlers;
12. explicit handler factory injection cannot create an extra production engine;
13. runner/heartbeat/handler sessions close on success and failure;
14. no DB transaction remains open across simulated slow network fetch;
15. hosted pool size/overflow behavior is deliberately bounded;
16. current monitor and incident tests remain green.

Run all invalidated unit/integration/workflow tests, Python compile checks, repository integrity, guard, and real disposable PostgreSQL integration where the repository supports it. A skipped PostgreSQL test is not a pass.

## REAL HOSTED PROOF — REQUIRED

After code + tests pass:

1. deploy/run the exact takeover branch through the existing protected FR-007 staging workflow;
2. run the real five-shard drain;
3. concurrently run hosted bootstrap/database connectivity and Founder feed/API probes;
4. capture sanitized `pg_stat_activity` during peak worker activity;
5. prove no `EMAXCONNSESSION`;
6. prove no persistent idle-in-transaction leak;
7. prove safe connection headroom below the 15-session cap;
8. prove expired leases return to 0;
9. prove queue work continues through normal worker semantics;
10. after the connection fix is proven, continue bounded normal drain runs as necessary to catch up the inherited backlog;
11. do not manually rewrite queue status, `run_after`, lease timestamps, schedule timestamps, or source cadence;
12. continue until oldest due runnable age is < 900 seconds and expired leases = 0;
13. run FULL monitoring against the current legitimate migration head;
14. incident #137 must resolve/close through the normal RESOLVE path, not manual closure;
15. verify source cadence and monitor thresholds were not weakened.

A live queue with 2 dead-letter rows is not automatically a runtime failure if they are legitimate bounded outcomes; document them and prove they are not a hidden capacity failure.

## CURRENT INCIDENT

Issue #137:

`[FR-007 Monitor] Cloud runtime incident`

It is still open. Its most recent recorded monitor comments remain queue-health failures. Do not close it manually.

## OUT-OF-LANE SECURITY FINDING — REPORT, DO NOT FIX IN THIS RUNTIME BRANCH

The Overseer found that `public.founder_activity_events` currently has an authenticated-Founder SELECT policy but table-level RLS itself is disabled.

This is a real security defect in the separate Founder-activity lane. Do not change its migration from this runtime branch. Record it prominently in your completion report so the activity-correction lane cannot be accepted until the Founder explicitly approves the RLS enablement/policy change.

## AUTONOMY

You are authorized to:

- inspect and modify the runtime branch;
- use protected FR-007 staging secrets through repository workflows;
- push this branch;
- run bounded staging drain/monitor/proof workflows;
- repair ordinary code/test/workflow failures;
- repeat the inner loop until PASS or a genuine external blocker.

You are not authorized to:

- merge;
- force-push protected history;
- weaken cadence/monitor thresholds/security;
- manually mutate production queue rows to manufacture health;
- delete production data;
- disclose secrets;
- incur paid-provider cost.

## FINAL REPORT CONTRACT

Return one structured report only after the inner loop is complete:

- STATUS: PASS or genuinely BLOCKED
- base SHA
- final local SHA
- verified remote SHA
- accepted Antigravity runtime changes reconciled
- exact root cause of connection amplification
- exact files changed
- deterministic test commands/results
- PostgreSQL integration proof
- before/peak/after connection counts by state
- max observed session-mode connections
- idle-in-transaction before/after
- concurrent hosted probe evidence
- before/after queue metrics
- stale-lease evidence
- drain run IDs
- FULL monitor run ID/result
- issue #137 final state
- confirmation cadence/thresholds were unchanged
- any out-of-lane findings
- READY FOR OVERSEER INTEGRATION: YES/NO

Do not claim FR-007 closed and do not claim the seven-day soak has elapsed. Those remain Overseer acceptance decisions.
