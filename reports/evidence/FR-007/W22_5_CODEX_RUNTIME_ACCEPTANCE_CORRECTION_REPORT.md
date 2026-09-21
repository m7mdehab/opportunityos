# W22.5 Runtime Acceptance Correction Report

## Status

**BLOCKED** — repository corrections and deterministic proofs are complete, but the hosted target is currently read-only for write-capable worker operations. Queue recovery and the final five-shard acceptance cannot complete until the target endpoint/provider is restored to a write-capable primary. This report does not claim the seven-day soak.

## Repository

- Branch: `work/fr007-codex-runtime-takeover`
- Starting integration SHA: `157d3c79dbda21c1583fbfc3ba8d363d64055d32`
- Final commit: recorded after the final State-only commit
- Remote: `origin/work/fr007-codex-runtime-takeover`
- No merge performed.

## W22.4 correction preserved

Hosted run `35619944610` proved the claim-session correction:

- maximum worker connections: 10
- persistent idle-in-transaction: 0
- unattributed connections: 0
- observer failures: 0

The original five-idle-transaction defect remains corrected.

## Deterministic W22.5 implementation

The branch contains the following corrections:

- bulk opportunity identity/content-hash prefetch before persistence;
- unchanged/currently-evaluated rows are skipped without redundant evaluation;
- bounded `evaluate_new` batches (`100`) with safe successor scheduling;
- coalesced `evaluate_new` queue work;
- commit-aligned per-identity advisory locking with fresh-read/idempotent race fallback;
- atomic PostgreSQL feed projection publication, with cached projection expiration after commit;
- source-wide lock retained only as a compatibility no-op; identity locking is the correctness boundary.

The persistence race regression uses disposable PostgreSQL and verifies convergence at the commit boundary without duplicate evaluation state.

## Local verification

Passing local suites include:

- `python -m unittest opportunity.test_persistence matching.test_evaluate_persist worker.test_worker worker.test_runner -q`
- `python -m unittest storage.test_feed_projection_service matching.test_evaluate_persist -q` — 17 tests
- `python -m unittest scripts.test_w17_runtime_workflows -q` — 10 tests
- full runtime suite previously completed: 165 passed, 18 skipped (PostgreSQL-only tests skipped without a local DSN)
- compile, repository integrity, guard, and `git diff --check` passed before finalization.

## Hosted deterministic proof

Run `35654469231` (commit `96b8f68`) completed the protected five-shard proof:

- deterministic setup: success
- enqueue: success
- all five shard drains: success
- observer: success
- maximum tagged worker connections: 10
- maximum persistent idle-in-transaction: 0
- maximum unattributed connections: 0
- observer failures: 0
- queue snapshot: `due_runnable=571`, `oldest_due_age_seconds=120395`, `running_now=0`, `expired_running_leases=0`, `dead_letter=4`
- URL: https://github.com/m7mdehab/opportunityos/actions/runs/35654469231

This proves the corrected worker/session behavior on a clean sequential proof, but it does not prove queue convergence because the pre-existing backlog remained.

## Recovery and blocker evidence

A bounded recovery wave (`35656446270`, commit `c650286`) completed five drain jobs. A subsequent recovery attempt (`35659340353`, commit `915c378`) failed at enqueue before draining:

`psycopg2.errors.ReadOnlySqlTransaction: cannot execute SELECT FOR UPDATE in a read-only transaction`

The same hosted read-only state was observed in the attempted proof `35657785793` when `evaluate_new` persistence and `worker_jobs` failure updates attempted writes. This is external to the deterministic code correction: the supplied `OPOS_TARGET_DB_URL` currently resolves to a read-only transaction/database endpoint or provider state. No credentials are present locally to change the endpoint or provider role.

Required external remediation:

1. restore the staging target to a write-capable primary (or correct `OPOS_TARGET_DB_URL`);
2. rerun bounded recovery and require `oldest_due_age_seconds < 900` and `expired_running_leases=0`;
3. rerun the protected five-shard proof with no new `EMAXCONNSESSION`, `UniqueViolation`, or persistent idle transaction;
4. run the FULL monitor and resolve issue #137 through the normal `RESOLVE` path.

Because step 1 is unavailable from this lane, the final queue acceptance, FULL monitor, and issue #137 RESOLVE were not executed. The branch does not claim them as PASS.

## Final acceptance state

- Five-shard clean proof: PASS (`35654469231`).
- Persistent idle-in-transaction criterion: PASS on the clean proof.
- Connection ceiling criterion: PASS on the clean proof (10).
- Queue convergence: **BLOCKED** by hosted read-only target.
- Expired leases zero: observed in the clean proof, but final recovery acceptance remains blocked.
- FULL monitor: NOT RUN to acceptance because recovery is blocked.
- Issue #137 normal RESOLVE: NOT RUN.
- State freshness: finalized by the last State-only commit.
- Seven-day soak: not claimed; it begins only after this runtime head is accepted.

## External blocker

The sole terminal blocker is hosted database write capability/endpoint authority. The Overseer or provider owner must restore a writable primary connection for `OPOS_TARGET_DB_URL`, then execute the recovery and final monitor steps above. No repository implementation blocker remains for the W22.5 corrections.
