# W22.4 — CODEX FINAL RUNTIME CLOSURE BRIEF

## EXECUTION DIRECTIVE

You are the implementation executor for the remaining FR-007 runtime closure work.

This brief has already done the diagnosis, sequencing, acceptance design, and most of the architectural decision-making. Your job is to execute the plan, test it, run the real protected hosted proof, remediate ordinary failures, and continue the inner loop until the runtime lane is genuinely PASS or an external blocker is proven.

Do not stop after analysis. Do not return a plan. Do not ask for routine confirmation. Do not merely describe commands that should be run. Run them.

Work autonomously in the repository, using the existing protected staging workflows and secrets. Treat failures as evidence: inspect the exact failing log/state, fix the root cause, add or tighten deterministic coverage, and rerun. Repeat until acceptance is met.

Return only when:
1. all deterministic/runtime gates are green;
2. the five-shard live connection proof passes;
3. the inherited queue backlog is caught up under normal durable semantics;
4. the FULL monitor is no longer FAIL/BLOCKED;
5. incident #137 resolves through the normal monitor RESOLVE path;
6. generated repository state is fresh;
7. the branch is ready for Overseer integration.

Do **not** merge.

---

## REPOSITORY / AUTHORITY

Repository:

`m7mdehab/opportunityos`

Work only on:

`work/fr007-codex-runtime-takeover`

Draft PR:

`#139 — FR-007 W22.3 runtime takeover: connection pressure correction`

Integration base:

`work/fr007-overseer-integration`

Base SHA:

`6d55549e2f97c835caa560552657efb49a661e7b`

Authoritative takeover head at the time this brief was written:

`9a4dc3e8eae31c80a0f7593dfc51c8fdedeefb44`

Before editing, read completely:

- `AGENTS.md`
- `docs/STATE.md`
- `reports/evidence/FR-007/W22_3_CODEX_RUNTIME_TAKEOVER_PACKET.md`
- this file
- `worker/queue.py`
- `worker/runner.py`
- `worker/handlers.py`
- `opportunity/persistence.py`
- `storage/repository.py`
- `storage/engine.py`
- `scripts/fr007_hosted_bootstrap.py`
- `.github/workflows/fr007-worker-drain.yml`
- `.github/workflows/fr007-runtime-takeover-proof.yml`
- `scripts/fr007_cloud_monitor.py`
- `scripts/process_incident_alert.py`

This brief supersedes W22.3 only where it contains fresher measured state or a more precise root-cause trace. The frozen architecture and safety constraints from W22.3 remain authoritative.

---

# 1. CURRENT STATUS — WHAT IS ALREADY DONE

Do not redo these items unless a regression proves they are broken.

## 1.1 Accepted runtime behavior already reconciled

The current takeover branch now contains:

- stale RUNNING lease priority over ordinary PENDING/RETRY backlog;
- PostgreSQL `FOR UPDATE SKIP LOCKED` stale-lease recovery;
- bounded retry/dead-letter progression;
- lease-fenced completion/failure;
- five-shard runtime workflow shape;
- one enqueue phase followed by exactly five drain shards;
- unique worker IDs per shard;
- normal defaults of 30 jobs / 480 seconds per shard;
- finite timeout headroom;
- `cancel-in-progress: false`;
- queue age monitoring based on due/run-after semantics;
- incident publication fallback for missing GitHub labels;
- deterministic stale-lease and workflow-contract tests.

## 1.2 W22.2 first connection-amplification defect is fixed

The branch already corrected the original 15-connection amplification path:

- hosted bootstrap creates one bounded process engine;
- hosted pool is `pool_size=2`, `max_overflow=0`;
- the exact same `session_factory` is injected into the default handler registry;
- handlers no longer create an unnecessary second production engine when an explicit factory exists;
- engine disposal occurs at process exit;
- hosted worker sessions are tagged for live observation.

This is materially proven: the latest real five-shard run observed a maximum of **10 tagged worker connections**, with **0 unattributed postgres connections** and **0 connection-probe failures**. The original 15/15 session-mode saturation pattern did not recur in that run.

## 1.3 Current deterministic / CI state

At branch head `9a4dc3e...`:

PASS:
- Mandatory Governance & Test Suite
- Guard
- Mirror
- FR-007 Reliability Proof Harness
- OCI Container Runtime Smoke
- takeover deterministic runtime suite
- enqueue phase
- all five live drain shards

Known failing gates:
- FR-007 Runtime Takeover Proof: connection observer only
- State: generated `docs/STATE.md` freshness only

The reliability harness previously exposed an A5 source-isolation fixture interaction with stale-first semantics. That fixture was corrected. The current reliability harness is green.

---

# 2. AUTHORITATIVE LIVE FINDINGS

## 2.1 Latest five-shard proof run

Run:

`35591708254`

Result by phase:

- deterministic: SUCCESS
- enqueue: SUCCESS
- five-shard drain: SUCCESS
- connection observer: FAILURE
- max tagged worker connections: **10**
- max persistent idle-in-transaction tagged workers (>30s): **5**
- max unattributed postgres connections: **0**
- observer connection failures: **0**
- connection proof pass: FALSE

This means the first W22.2 problem is solved, but one transaction remains open per worker while the handler is doing long work.

## 2.2 Latest queue snapshot from that proof

At the end of run `35591708254`:

- due runnable: **593**
- oldest due runnable age: **94,793 seconds**
- RUNNING: **1**
- expired RUNNING leases: **1**
- DEAD_LETTER: **4**
- Alembic revision: **0019_activity_view_access**
- latest successful poll: **2026-09-21 11:42:09 UTC**

Fresh later live inspection showed the backlog still unresolved:

- due runnable: **593**
- oldest due runnable age: approximately **107,774 seconds**
- RUNNING: **1**
- expired RUNNING leases: **1**
- DEAD_LETTER: **4**

Job distribution:

- `evaluate_new`: 284 PENDING, 16 RETRY, 3 COMPLETED
- `poll_source`: 262 PENDING, 31 RETRY, 290 COMPLETED, 4 DEAD_LETTER, 1 RUNNING
- due runnable `evaluate_new`: **300**
- due runnable `poll_source`: **293**
- source schedules: **343 total**
- source schedules currently due: **312**

No source currently has more than one active PENDING/RETRY/RUNNING `poll_source` job. That is good and must remain true.

## 2.3 Historical retry causes still present in the queue

Most RETRY rows still carry the earlier pre-fix Supavisor failure:

`EMAXCONNSESSION — max clients reached in session mode`

These are inherited historical failures. Do not delete or rewrite them. The proof requirement is that **no new EMAXCONNSESSION failures occur after the final fixed SHA**, and that inherited retries naturally complete or reach their normal bounded outcome.

## 2.4 Additional live persistence race exposed by parallel work

The queue now also contains real unique-constraint failures, including:

- `opportunities_pkey`
- `uq_field_provenances_identity`

Examples exist for sources such as:

- `greenhouse:point72`
- `greenhouse:later`
- `greenhouse:picoquantitativetrading`
- `greenhouse:redwoodmaterials`
- `greenhouse:legendcareers`

One Point72 job has already dead-lettered after repeated `opportunities_pkey` conflict.

This is consistent with the concurrency warning already documented in `opportunity/persistence.py`: `persist_batch` performs lookup-then-write idempotency at application level, and concurrent writers can both observe “not found” before one commits.

Do not dismiss this as test noise. It is now real hosted evidence.

## 2.5 Incident state

GitHub issue:

`#137 — [FR-007 Monitor] Cloud runtime incident`

State: **OPEN**

Do not close it manually.

The monitor's queue thresholds remain:

- WARN: oldest due age >= 900 seconds
- FAIL: oldest due age >= 3600 seconds
- any expired RUNNING lease: FAIL
- dead-letter rows alone: WARN

The incident processor normally resolves an open incident when the monitor returns PASS **or WARN**. Therefore historical dead-letter rows do not need to be deleted to close #137, as long as queue age and expired leases are healthy and the remaining WARN is honestly documented.

---

# 3. PRIMARY REMAINING DEFECT — FOREGROUND IDLE-IN-TRANSACTION LEAK

## 3.1 High-confidence root cause

Verify this trace, then implement the smallest robust correction.

Current `WorkerRunner.run_once()` does:

1. open one SQLAlchemy `Session`;
2. construct `BackgroundWorkerQueue` on that session;
3. call `claim_next_job()`;
4. `claim_next_job()` commits the claim;
5. return the ORM `WorkerJobRecord`;
6. `run_once()` immediately reads `job.id`, `job.job_type`, and `job.payload_json`;
7. default SQLAlchemy `sessionmaker` behavior is `expire_on_commit=True`;
8. after the claim commit, the returned ORM instance is expired;
9. reading those fields therefore causes a lazy refresh SELECT;
10. that SELECT opens a new transaction on the runner's foreground session;
11. the same foreground session is then retained for the entire handler execution;
12. network-bound `poll_source` work can take well over 30 seconds;
13. the transaction remains `idle in transaction` until completion/failure fencing reuses the session.

The live signature is exact: **five shards -> five persistent idle-in-transaction foreground sessions**.

The heartbeat legitimately uses a separate session concurrently. That is why the latest measured peak is 10 connections: roughly one foreground connection plus one heartbeat connection per worker.

## 3.2 Required outcome

After the fix:

- there must be **zero persistent (>30s) idle-in-transaction tagged worker sessions** during the five-shard run;
- no DB transaction may remain open while remote HTTP/network work is waiting;
- heartbeat lease renewal must continue to function;
- lease fencing must remain intact;
- five-shard count must remain unchanged;
- no connection limit/monitor thresholds may be weakened;
- no new `EMAXCONNSESSION` may occur.

## 3.3 Preferred implementation direction

Choose the smallest design that proves the invariant.

Preferred option:

- configure the **worker runtime session factory** with `expire_on_commit=False`, scoped to worker runtime use, so a committed claim can be read without SQLAlchemy lazily opening a new transaction;
- keep existing explicit `session.expire_all()` / fresh-read fencing where correctness requires a fresh lease read;
- do not silently change unrelated application session semantics unless tests prove that is safe and necessary.

Alternative acceptable option:

- change the queue/runner claim seam so `claim_next_job()` returns a detached immutable claim snapshot/DTO containing only the job fields required for dispatch, with the database transaction fully closed before the handler starts.

Do not “fix” the observer by relaxing the >30s rule. Fix the transaction lifecycle.

## 3.4 Mandatory regression coverage

Add deterministic coverage proving:

1. a claimed job can be dispatched without starting a second foreground transaction merely to read job fields;
2. immediately before a slow handler begins, the foreground session is not in an active transaction;
3. a simulated slow network handler does not hold an idle transaction;
4. heartbeat renewal still succeeds during that slow handler;
5. completion/failure fencing still rejects lost leases;
6. success, handler failure, malformed payload, unknown job type, and lease-loss paths close/rollback correctly.

Prefer a real PostgreSQL test for the transaction-state invariant where feasible. A skipped PostgreSQL test is not acceptance.

---

# 4. SECOND REMAINING DEFECT — CONCURRENT PERSISTENCE IDEMPOTENCY

## 4.1 Problem

The five-worker runtime has exposed the exact race already documented in `opportunity/persistence.py`.

Current pattern:

`get_opportunity(id) -> if missing -> save_opportunity()`

Two overlapping workers can both observe the row as missing and then both attempt to insert the same primary key/provenance identity.

The result is a retry/dead-letter rather than silent corruption, which is safe, but it is not operationally acceptable under normal five-shard recovery.

## 4.2 Required outcome

Parallel polling must not generate ordinary `UniqueViolation` retries/dead letters for identical opportunity/provenance identity.

Do not solve this by:
- reducing worker count;
- disabling constraints;
- swallowing IntegrityError and pretending the write succeeded;
- deleting failed production rows;
- serializing the entire worker fleet globally.

## 4.3 Preferred implementation direction

The narrowest low-risk correction is **same-source database serialization only around the persistence/evaluation DB phase**.

A strong design is:

1. perform remote source HTTP acquisition first, with no DB transaction held;
2. once the normalized batch exists and the persistence session is opened, acquire a PostgreSQL advisory transaction lock derived deterministically from `source_id`;
3. persist/evaluate/update source schedule within that protected database phase;
4. commit/release the transaction lock;
5. allow unrelated sources to continue fully in parallel.

This preserves five-shard concurrency while preventing two copies of the same source from racing the lookup/write seam.

A correct PostgreSQL `INSERT ... ON CONFLICT` / upsert design is also acceptable if it preserves all provenance/update/projection semantics, but it is a materially larger change. Prefer the smaller provable fix unless evidence requires otherwise.

Never hold the advisory lock across the remote HTTP request.

## 4.4 Required tests

Prove on real PostgreSQL:

- two simultaneous persistence attempts for the same source/opportunity do not produce `opportunities_pkey` violation;
- provenance natural-key uniqueness remains intact;
- two unrelated sources can still persist concurrently;
- identical repoll is unchanged/idempotent;
- changed-content repoll still updates/reverifies;
- existing A6 concurrency proof remains green.

After the fix, live proof must show **no new unique-constraint worker failure attributable to the final SHA**.

Historical rows may remain as documented evidence.

---

# 5. QUEUE CATCH-UP — DO NOT CONFUSE CORRECTNESS WITH CAPACITY

The branch now has a functioning five-shard worker but an inherited backlog of roughly 593 due jobs.

The queue is split almost evenly between:

- global `evaluate_new` safety-net jobs; and
- `poll_source` jobs.

Every successful `poll_source` currently enqueues an `evaluate_new` job unconditionally. The inline evaluator usually makes that backfill job a no-op, but the job still exists.

Do not change this behavior prematurely simply to make the queue number smaller. First fix transaction lifecycle + persistence concurrency, then measure actual catch-up throughput with the existing recovery envelope.

## 5.1 Recovery envelope already supported

Normal steady-state defaults must remain:

- 5 shards
- 30 jobs per shard
- 480 seconds per shard

The existing manual recovery workflow already caps an explicit recovery dispatch at:

- up to 150 jobs per shard
- up to 540 seconds per shard

After correctness is proven, Codex may use the existing bounded recovery inputs for catch-up. Do not change the normal defaults.

A high-cap recovery wave therefore has a theoretical maximum of 750 processed jobs, sufficient to materially reduce the current inherited backlog if handler throughput permits it.

## 5.2 Catch-up methodology

For every recovery wave, record before/after:

- due runnable total;
- due `poll_source`;
- due `evaluate_new`;
- oldest due age;
- RUNNING count;
- expired lease count;
- RETRY count by job type;
- DEAD_LETTER count;
- latest successful poll;
- max tagged worker connections;
- persistent idle-in-transaction count;
- count of new `EMAXCONNSESSION` failures;
- count of new `UniqueViolation` failures.

Continue bounded recovery only while metrics show real forward progress.

Acceptance:

- expired RUNNING leases = **0**
- oldest due runnable age < **900 seconds**
- no new connection saturation failures
- no new persistence race failures
- queue continues to converge under normal durable semantics

Never manually change:

- queue status;
- retry_count;
- run_after;
- lease_owner;
- lease_expires_at;
- source `next_due_at`;
- cadence;
- cooldown timestamps.

## 5.3 If the backlog does not converge

Only if measured recovery shows that unconditional `evaluate_new` creation prevents convergence, then implement a **coalesced global backfill** design.

Important semantic fact: `evaluate_new` is global — one job scans every opportunity missing evaluation/projection for the current truth-pack hash. Hundreds of simultaneous/queued copies are logically redundant.

If coalescing is needed, the design must preserve the safety-net guarantee. Do not simply “skip if one active job exists” without considering the race where a RUNNING evaluator takes its snapshot before a poll commits and the poll then declines to enqueue a successor.

A valid coalescing design must prove that work arriving during an active evaluator is eventually observed, for example via a durable singleton + successor/dirty mechanism or equivalent atomic logic.

Do not undertake this change unless capacity evidence after the primary fixes shows it is necessary.

---

# 6. EXPIRED LEASE AND DEAD-LETTER DISPOSITION

Current hosted state contains:

- 1 expired RUNNING job owned by the old proof worker;
- 4 DEAD_LETTER poll jobs.

Three dead letters are stale-lease exhaustion from earlier broken runtime waves.

One dead letter is a real `UniqueViolation` persistence failure.

Do not manually rewrite them.

The stale-first queue must naturally reclaim the expired RUNNING job on the next healthy worker wave.

Historical dead letters may remain. The monitor treats them as WARN, not FAIL.

Document each final dead-letter row in the completion report:
- source;
- terminal reason;
- whether the root cause is corrected;
- whether a later normal poll of that source succeeded.

If a source needs to be polled again, let the durable scheduler create the normal next job. Do not resurrect the dead-letter row by direct SQL.

---

# 7. STATE CI FAILURE — MECHANICAL FINAL STEP

The current State workflow failure is not a runtime defect.

It reports only that `docs/STATE.md` was generated at an older commit.

After all code/runtime corrections are complete and the final head is stable:

```bash
STATE_PRESERVE_TIMESTAMP=1 python scripts/generate_state.py
git diff -- docs/STATE.md
```

Commit the generated state update only if it is exactly generator output.

Do this near the end so every code commit does not immediately make STATE stale again.

---

# 8. FULL MONITOR / INCIDENT CLOSURE

When:

- connection proof passes;
- expired leases = 0;
- oldest due age < 900s;

run the existing FULL hosted monitor against current production schema:

`0019_activity_view_access`

Required:

- database connectivity: PASS
- queue health: PASS, or WARN solely because documented historical dead letters remain
- no FAIL/BLOCKED checks
- no weakened thresholds
- incident processor receives the healthy report
- issue #137 closes through the normal RESOLVE path

Do not close #137 manually.

Capture the monitor run ID and the issue closure event.

---

# 9. EXACT INNER LOOP

Use this sequence. Do not skip ahead.

## Phase A — preflight

1. fetch latest remote branch;
2. verify local HEAD == remote takeover HEAD;
3. inspect PR #139 and current checks;
4. run repository/agent instructions;
5. record a fresh queue + connection baseline.

## Phase B — foreground transaction correction

1. reproduce the idle-in-transaction mechanism deterministically;
2. implement the narrow session/claim-lifecycle fix;
3. add regression tests;
4. run targeted worker/queue tests;
5. run real PostgreSQL tests;
6. run compile + guard + repository checks.

Do not run another expensive five-shard proof until deterministic evidence is green.

## Phase C — persistence concurrency correction

1. reproduce the real duplicate identity race;
2. implement same-source DB-phase serialization or an equally strong narrower solution;
3. add concurrency tests on PostgreSQL;
4. preserve parallelism across unrelated sources;
5. run persistence + handler + reliability suites.

## Phase D — full deterministic gate

Run, at minimum, the suites invalidated by this lane:

- `worker.test_worker`
- `worker.test_runner`
- `worker.test_postgres_queue_durability`
- `scripts.test_w17_runtime_workflows`
- `scripts.test_fr007_cloud_monitor`
- `scripts.test_fr007_connection_pressure`
- `scripts.test_fr007_reliability_proof`
- relevant opportunity/storage PostgreSQL integration tests
- Python compile checks
- `scripts/check_guard.py --allow-missing-patterns`
- `scripts/check_repository.py`

Then ensure normal PR checks are green.

## Phase E — real five-shard proof

Run the protected takeover proof.

Required connection acceptance:

- all 5 shards succeed;
- max worker sessions stays safely below the 15-session cap;
- persistent (>30s) idle-in-transaction = 0;
- unattributed worker-related postgres sessions = 0;
- observer probe failures = 0;
- no `EMAXCONNSESSION`;
- no new unique-constraint failure;
- heartbeat/leases remain healthy.

If it fails, inspect exact logs and loop back. Do not weaken the observer.

## Phase F — backlog recovery

After Phase E PASS:

1. snapshot queue;
2. run bounded five-shard recovery using existing supported manual recovery caps as needed;
3. measure net progress after every wave;
4. continue until oldest due age < 900s and expired leases = 0;
5. stop if a new correctness failure appears; fix before resuming.

## Phase G — monitor + incident

1. run FULL monitor;
2. require no FAIL/BLOCKED state;
3. let normal incident processor resolve #137;
4. verify issue is actually closed.

## Phase H — state + final CI

1. update `docs/STATE.md` using the generator;
2. push;
3. wait for all PR checks;
4. if any check fails, fix it and repeat;
5. do not merge.

---

# 10. SAFETY / SCOPE

You are authorized to:

- modify the takeover branch;
- add/update directly related tests;
- use protected FR-007 staging secrets through existing GitHub workflows;
- run bounded staging drain/proof/monitor workflows;
- inspect sanitized production metrics;
- push the takeover branch;
- repair ordinary CI/runtime failures;
- repeat until PASS.

You are not authorized to:

- merge;
- force-push;
- change source cadence to manufacture queue health;
- weaken monitor thresholds;
- reduce five-shard worker count to hide the connection defect;
- manually mutate production queue rows;
- delete production data;
- delete dead-letter evidence;
- disable DB uniqueness constraints;
- expose secrets/DSNs;
- incur paid infrastructure cost;
- modify Founder activity/CV/UI lanes unless a runtime dependency makes it strictly necessary and is explicitly documented.

Separate known security finding remains out of this lane:

`public.founder_activity_events` has a Founder SELECT policy but table-level RLS was observed disabled. Report it; do not silently alter that migration from this runtime branch.

---

# 11. DONE DEFINITION

Do not claim PASS until all of these are true:

- [ ] foreground session transaction leak fixed
- [ ] persistent idle-in-transaction = 0 in live five-shard proof
- [ ] max worker connections safely < 15
- [ ] no new EMAXCONNSESSION after final fix SHA
- [ ] persistence concurrency race corrected
- [ ] no new unique-constraint worker failures after final fix SHA
- [ ] all five live shards succeed
- [ ] deterministic worker/postgres/reliability tests pass
- [ ] Guard passes
- [ ] repository integrity passes
- [ ] Mandatory Governance & Test Suite passes
- [ ] OCI runtime smoke passes
- [ ] FR-007 Reliability Proof Harness passes
- [ ] State passes
- [ ] expired RUNNING leases = 0
- [ ] oldest due runnable age < 900 seconds
- [ ] backlog demonstrably converged under durable semantics
- [ ] FULL monitor is PASS or WARN solely for documented historical dead letters
- [ ] issue #137 resolved automatically
- [ ] cadence unchanged
- [ ] queue thresholds unchanged
- [ ] worker count remains five
- [ ] branch remains unmerged

---

# 12. FINAL RETURN FORMAT

Return one concise but evidence-complete report:

## STATUS
`PASS` or genuinely `BLOCKED`

## REPOSITORY
- base SHA
- starting takeover SHA
- final local SHA
- verified remote SHA
- PR #139 status

## ROOT CAUSES
- original connection amplification
- foreground idle-in-transaction cause
- persistence concurrency cause
- any additional cause discovered

## CHANGES
- exact files changed
- reason for each change

## DETERMINISTIC EVIDENCE
- exact commands
- test counts/results
- PostgreSQL concurrency evidence
- guard/repository/state results

## LIVE CONNECTION PROOF
- run ID
- five shard job results
- max tagged worker connections
- max persistent idle-in-transaction
- unattributed connection count
- observer failures
- EMAXCONNSESSION count after final SHA

## LIVE PERSISTENCE PROOF
- new UniqueViolation count after final SHA
- same-source concurrency result
- unrelated-source concurrency result

## QUEUE RECOVERY
- before metrics
- each recovery run ID
- final due runnable count
- final oldest due age
- final expired lease count
- retry/dead-letter disposition
- latest successful poll

## MONITOR / INCIDENT
- FULL monitor run ID/result
- issue #137 final state
- proof it closed through RESOLVE, not manual action

## INVARIANT CONFIRMATION
- 5 shards unchanged
- cadence unchanged
- monitor thresholds unchanged
- no manual queue mutation
- no production data deletion

## OUT-OF-LANE FINDINGS
- include Founder activity RLS finding if still unresolved
- anything else discovered

## READY FOR OVERSEER INTEGRATION
`YES` or `NO`

Do not claim the seven-day soak has elapsed. That begins only after the runtime head is stable and accepted.
