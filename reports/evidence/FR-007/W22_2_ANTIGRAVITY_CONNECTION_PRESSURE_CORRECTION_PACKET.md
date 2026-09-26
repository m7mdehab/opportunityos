# W22.2 — ANTIGRAVITY SUPABASE CONNECTION-PRESSURE CORRECTION PACKET

## ROLE

Continue the FR-007 runtime lane after W22.1 exposed a new real hosted-capacity defect. Preserve the accepted five-shard queue architecture, stale-lease recovery, incident behavior, and bounded worker semantics. This packet corrects database connection pressure; it does not authorize weakening acquisition cadence, queue-health thresholds, lease fencing, or worker count as a shortcut.

## CURRENT AUTHORITATIVE LIVE STATE

- Repository: `m7mdehab/opportunityos`
- Runtime lane: `work/fr007-antigravity-final-closure`
- Existing runtime head before this packet: `28f535d356a0ca8be3593f6a6d6bea3bba68420b`
- Overseer integration has advanced separately to W23.1 and live Supabase is now at `0015_hosted_founder_surface`.
- Do not claim terminal W22.1/W22.2 PASS against the obsolete 0014 revision.
- Do not merge.

## NEW LIVE DEFECT — VERIFIED BY OVERSEER

While a five-shard drain was active, hosted launch run `35513248430` failed its bootstrap before deployment with:

`FATAL: (EMAXCONNSESSION) max clients reached in session mode - max clients are limited to pool_size: 15`

At the same time, a direct live `pg_stat_activity` snapshot showed:

- Supavisor session-mode connections: **15**
- idle in transaction: **10**
- idle: **5**
- active worker drain: exactly **5 shards**

This is operationally significant. The five-shard design may clear the queue but must not monopolize the entire Supabase session pool and starve deploy/bootstrap/monitor/maintenance work.

The Overseer separately decoupled Cloudflare web deployment from bootstrap so worker pressure cannot block a known-good web release. That is only isolation, not a substitute for fixing the underlying connection footprint.

## REQUIRED DIAGNOSIS

Trace the actual connection lifecycle for one `poll_source` job across:

- `scripts/fr007_hosted_bootstrap.py`
- `storage/engine.py`
- `worker/runner.py`
- `worker/handlers.py`
- heartbeat sessions
- handler persistence/evaluation sessions
- any lazily-created production session factories/engines

Prove where the multiple session-mode connections per shard originate. Do not guess from pool defaults.

Pay special attention to:

1. long-lived SQLAlchemy sessions or transactions spanning network fetch / CPU evaluation;
2. a separate production engine/session factory being created inside handlers instead of reusing the worker process's existing engine/factory;
3. QueuePool retaining session-mode Supavisor connections after logical sessions close;
4. the heartbeat requiring a concurrent connection while the handler owns another;
5. transaction boundaries that leave connections `idle in transaction`;
6. repeated engine construction or unbounded/default pool behavior.

## FROZEN OUTCOME

Keep exactly five normal drain shards. Fix connection usage so five concurrent shards leave safe headroom for independent hosted operations.

Preferred properties:

- one deliberately bounded engine/pool per worker process;
- handlers use the injected process session factory rather than silently creating another production engine;
- no transaction remains open during remote network waiting unless strictly required;
- session/transaction scope is explicit and closes/rolls back on every path;
- heartbeat remains independent enough to renew leases safely;
- pool configuration is finite and appropriate for Supabase session-mode limits;
- engine disposal happens at process end;
- no direct manipulation of worker rows or leases to manufacture the proof.

You may use `NullPool`, a deliberately small `QueuePool`, shared injected session factories, transaction-boundary changes, or another SQLAlchemy-supported design only if tests and live evidence prove it preserves correctness.

Do not switch to a different provider or paid tier.

## REQUIRED TESTS

Add deterministic regression coverage proving:

1. `fr007_hosted_bootstrap` injects/reuses the intended session factory for default handlers.
2. Worker/handler construction cannot silently create an additional production engine when an explicit factory exists.
3. Every runner/heartbeat/handler session closes on success and failure.
4. No transaction remains open across a simulated slow network handler unless required by the lease protocol.
5. Five-worker concurrency still preserves `SKIP LOCKED`, lease fencing, retry/dead-letter behavior, and stale-lease recovery.
6. Pool limits are finite and tested/configured for the hosted worker path.
7. Existing W22/W22.1 tests remain green.

## REAL HOSTED PROOF

After implementation and after the Overseer integration head containing W23.1/0015 is the target runtime:

1. run a real five-shard drain;
2. concurrently run the hosted bootstrap or equivalent database-connectivity probe;
3. capture sanitized `pg_stat_activity` counts during peak worker activity;
4. prove no `EMAXCONNSESSION`;
5. prove no persistent idle-in-transaction leak;
6. prove expired leases remain 0;
7. prove queue work continues to complete;
8. rerun the FULL monitor against migration head `0015_hosted_founder_surface`.

Do not reduce the five-shard design merely to make the connection test pass unless measured evidence shows a hard provider limit makes the frozen capacity target impossible; if so return BLOCKED with the exact measured limit and alternatives.

## TERMINAL ACCEPTANCE

W22.2 may return PASS only when:

- five-shard worker execution remains functional;
- hosted bootstrap/monitor can connect concurrently;
- no `EMAXCONNSESSION` occurs in the proof;
- database connection usage has documented safe headroom below the session-mode limit;
- expired leases = 0;
- no persistent idle-in-transaction leak remains;
- the queue-health target from W22.1 is met;
- FULL monitor succeeds on **0015**;
- incident #137 closes through the normal RESOLVE path;
- no source cadence or monitor threshold was weakened.

Return a single W22.2 completion report with exact SHAs, files changed, test results, live connection counts before/after, queue metrics, monitor run ID, incident state, and READY FOR OVERSEER INTEGRATION YES/NO.
