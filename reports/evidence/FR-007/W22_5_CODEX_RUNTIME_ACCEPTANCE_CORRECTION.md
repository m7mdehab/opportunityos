# W22.5 — CODEX RUNTIME ACCEPTANCE CORRECTION

## PURPOSE

W22.4 implemented meaningful corrections, but the runtime lane is **not accepted**.

This packet is a focused correction pass based on independent Overseer verification of:

- branch head and diff;
- PR #139 checks;
- protected hosted proof runs `35619944610` and `35620088135`;
- exact drain/observer logs;
- fresh production queue state;
- current production persistence state for the large Stripe and SpaceX sources;
- the implementation of the new advisory lock.

Do not restart architecture analysis from zero. Execute this packet as an inner remediation loop.

Return only after PASS or a genuine external blocker.

Do not merge.

---

# 1. REPOSITORY / START POINT

Repository:

`m7mdehab/opportunityos`

Branch:

`work/fr007-codex-runtime-takeover`

Verified branch head before this packet:

`157d3c79dbda21c1583fbfc3ba8d363d64055d32`

PR:

`#139`

Integration base remains:

`6d55549e2f97c835caa560552657efb49a661e7b`

Read, in order:

1. `AGENTS.md`
2. `reports/evidence/FR-007/W22_4_CODEX_FINAL_RUNTIME_CLOSURE_BRIEF.md`
3. `reports/evidence/FR-007/W22_4_CODEX_FINAL_RUNTIME_CLOSURE.md`
4. this packet
5. current implementations of:
   - `worker/runner.py`
   - `worker/queue.py`
   - `worker/handlers.py`
   - `opportunity/persistence.py`
   - `storage/repository.py`
   - `matching/evaluate_persist.py`
   - `scripts/fr007_hosted_bootstrap.py`
   - `.github/workflows/fr007-runtime-takeover-proof.yml`
   - `.github/workflows/fr007-worker-drain.yml`

---

# 2. OVERSEER ACCEPTANCE REVIEW OF W22.4

## 2.1 The foreground claim transaction correction is substantially proven

W22.4 reported the hosted connection proof as unavailable. That is too conservative.

Protected run `35619944610` produced a **clean observer PASS**:

- max tagged worker connections: **10**
- persistent idle-in-transaction >30s: **0**
- unattributed postgres connections: **0**
- observer probe failures: **0**
- connection proof: **true**

Therefore the original five-foreground-idle-transaction claim-refresh defect is independently verified as corrected at least once.

Preserve:

- worker runtime `expire_on_commit=False`;
- explicit fresh reads where lease fencing requires them;
- bounded pool size/overflow;
- injected shared handler factory.

Do not revert this.

## 2.2 A residual transaction appeared in the second run

Run `35620088135` observed:

- max worker connections: **10**
- max persistent idle-in-transaction: **1**
- unattributed: **0**
- probe failures: **0**

This is **not** the original five-session amplification signature.

Treat it as a separate residual handler/database-phase transaction to identify, not as evidence that the W22.4 claim fix failed wholesale.

Add enough sanitized per-worker observability to attribute the residual transaction to a specific worker/job/stage before changing semantics.

Preferred approach:

- tag worker DB sessions with a stable shard-specific suffix or otherwise expose worker identity safely;
- observer should report the application-name/worker bucket that reached persistent idle-in-transaction;
- add stage timing logs for `poll_source`: acquisition/parse, persistence, inline evaluation, poll finalization;
- never log payload content or secrets.

Do **not** relax the zero persistent-idle acceptance rule.

---

# 3. PRIMARY HOSTED BLOCKER — LARGE SOURCE JOBS EXCEED THE FROZEN 35-MINUTE SHARD WINDOW

This is now directly measured.

## 3.1 Run 35619944610

Observer: PASS.

Two shards timed out.

### Shard 1

- `greenhouse:schonfeld` completed in roughly 3.5 minutes.
- Next job: `greenhouse:stripe`.
- Stripe did not finish before the shard was killed at 35 minutes.

### Shard 2

- `greenhouse:seurat` completed in ~22 seconds.
- Next job: `greenhouse:spacex`.
- SpaceX did not finish before the shard was killed at 35 minutes.

## 3.2 Run 35620088135

Four of five drain shards completed successfully.

Stripe was reclaimed and **did finish**:

- source: `greenhouse:stripe`
- raw / unique opportunities: **671**
- successful poll duration: **1,348 seconds** (~22.5 minutes)
- final persisted state: 671 opportunities, 671 evaluations, 671 projections

SpaceX was reclaimed again and timed out a second time after the 35-minute job window.

Current production evidence:

- `greenhouse:spacex`: **1,648 opportunities already persisted**
- latest aggregate check: **0 match evaluations**
- **1,647 feed projections**
- the poll job remains RUNNING with an expired lease after the killed shard

This proves the current handler can partially commit a very large source for more than 35 minutes without ever reaching a successful poll terminal record.

Do not increase the 35-minute runtime limit as the first response.

The required correction is to make the handler bounded enough to complete large-source work under the existing envelope.

---

# 4. PERFORMANCE ROOT CAUSE TO CORRECT

The current persistence/evaluation path performs excessive per-opportunity database round trips.

Important current behaviors:

1. `persist_batch` performs `repository.get_opportunity(id)` once per opportunity.
2. Existing unchanged rows therefore cost one database lookup each.
3. New/changed rows call `StorageRepository.save_opportunity()`.
4. `save_opportunity()` itself commits multiple times per opportunity:
   - opportunity/provenance write;
   - search vector refresh;
   - feed projection refresh.
5. `poll_source` then inline-evaluates every opportunity in the fetched batch, including unchanged opportunities.
6. evaluation/projection persistence adds additional commits/queries per opportunity.
7. every successful `poll_source` also unconditionally enqueues a global `evaluate_new` safety-net job.

This is acceptable on small feeds but not on 671/1,648-item sources over hosted Supabase latency.

SpaceX is the terminal proof that the current granularity is not operationally bounded.

---

# 5. REQUIRED LARGE-SOURCE OPTIMIZATION

Implement the narrowest changes that remove redundant hosted round trips while preserving correctness.

## 5.1 Bulk-prefetch existing identity/hash state

In the persistence seam, fetch existing state for all opportunity IDs in the batch using bounded bulk queries instead of one `SELECT` per opportunity.

Required semantics remain:

- absent ID -> insert path;
- same ID + same content hash -> unchanged;
- same ID + changed content hash -> update/reverify.

Chunk the `IN (...)` query if needed to keep parameter counts bounded.

Do not load full ORM graphs when only ID/content hash are needed for classification.

## 5.2 Do not inline-re-evaluate unchanged rows unnecessarily

After persistence classification:

- inline evaluation should target rows that were actually inserted/updated by this poll;
- an unchanged posting that already has a current evaluation/projection must not be re-evaluated merely because the source was repolled;
- an unchanged posting that lacks current evaluation must remain recoverable by the `evaluate_new` safety net.

Do not fabricate evaluation completeness.

Add deterministic tests for:
- unchanged + current evaluation -> no redundant inline evaluation;
- unchanged + missing evaluation -> eventually picked up by bounded `evaluate_new`;
- inserted/updated -> full-fidelity inline evaluation still occurs.

This should make a SpaceX retry, where the source is now mostly persisted, dramatically cheaper.

## 5.3 Bound `evaluate_new`

Current `evaluate_new` queries all missing records with `.all()` and can become an unbounded global job.

Change it to a finite batch size.

Use a default that is large enough for throughput but small enough to complete safely in the worker envelope; justify the value with measurement. A range such as 50–200 is acceptable for testing, but the final value must be evidence-based.

After one bounded batch:

- if eligible work remains, ensure a successor job exists;
- if no work remains, finish.

Never make one `evaluate_new` job responsible for an unbounded number of rows.

---

# 6. EVALUATE_NEW COALESCING — NOW REQUIRED

W22.4 said not to redesign this until capacity evidence existed.

That evidence now exists.

Fresh queue state after the hosted attempts:

- due runnable: **618**
- oldest due age: approximately **118,399 seconds**
- expired RUNNING leases: **1**
- dead-letter: **4**

The queue contains hundreds of `evaluate_new` jobs even though `evaluate_new` is a global sweep.

This is redundant work.

Implement future coalescing without manually deleting or rewriting the existing backlog.

## Required coalescing semantics

At steady state, allow at most:

- one RUNNING `evaluate_new`; and
- one PENDING/RETRY successor.

Why a successor is necessary:

If a poll commits new work while an evaluator is already RUNNING, simply saying “an evaluator already exists” can lose the new work if the running evaluator took its snapshot before the new opportunity committed.

Therefore:

- if a RUNNING evaluator exists and no PENDING/RETRY evaluator exists, a poll may create exactly one successor;
- if a PENDING/RETRY evaluator already exists, do not create another;
- if no evaluator exists, create one.

Serialize the check+insert on PostgreSQL so concurrent polls cannot create a successor storm.

A transaction-scoped advisory lock is appropriate **for this short enqueue transaction**, because there is one check+insert+commit and no internal multi-commit operation.

Existing hundreds of evaluate jobs are historical durable rows. Do not delete them. They should naturally drain; once evaluation work is complete, redundant jobs become fast bounded no-ops and finish.

Add PostgreSQL concurrency tests proving:
- many concurrent poll enqueue attempts create at most one pending successor;
- work committed while one evaluator is running cannot be stranded;
- the existing RUNNING job is not mutated;
- retry/dead-letter semantics remain unchanged.

---

# 7. THE W22.4 SOURCE ADVISORY LOCK IS NOT YET A COMPLETE CONCURRENCY GUARANTEE

Current code does:

`SELECT pg_advisory_xact_lock(hashtext(:source_id)::bigint)`

before `persist_batch`.

However, `pg_advisory_xact_lock` is released at transaction end.

`StorageRepository.save_opportunity()` performs internal `commit()` calls while `persist_batch` is still processing the source.

Therefore the source-level transaction lock does **not** remain held across the full database phase described by the W22.4 comment.

Do not treat the current advisory lock as sufficient proof.

## Preferred correction

Protect the actual identity race at the opportunity write boundary instead of pretending one transaction lock spans internal commits.

A narrow safe approach:

1. bulk-prefetch ID/hash state;
2. unchanged IDs can skip without a write lock;
3. for an ID classified as insert/update:
   - acquire a PostgreSQL transaction advisory lock derived from the opportunity ID;
   - fresh-read that identity after acquiring the lock;
   - decide insert/unchanged/update again from authoritative current state;
   - perform the write;
   - the repository commit releases the transaction lock;
4. process the next write candidate.

This makes the lock lifetime match the actual commit boundary.

Equivalent PostgreSQL atomic upsert logic is acceptable if all opportunity/provenance/projection semantics are preserved and tested.

Remove or narrow the misleading source-wide lock if it no longer adds correctness.

## Required PostgreSQL tests

Run in CI/service-container PostgreSQL even if the local workstation has no DSN.

Prove:

- two concurrent writers for the same absent opportunity do not raise `opportunities_pkey`;
- provenance unique constraint does not fail under the same race;
- one writer updating while another observes the identity converges safely;
- unrelated opportunity/source writes remain concurrent;
- identical re-poll remains unchanged;
- changed re-poll still re-verifies.

A local missing DSN is not a blocker: wire these tests into an existing disposable PostgreSQL CI job.

---

# 8. FRESH FAILURE DELTA

The Overseer queried rows updated after the final W22.4 correction began.

No new updated rows in that inspected interval showed:

- `EMAXCONNSESSION`;
- `UniqueViolation`.

This is encouraging but **provisional**, because neither hosted run reached full terminal acceptance.

The final proof must compute failure deltas from the final correction SHA/run start, not rely on historical queue error text.

---

# 9. EXPIRED SPACEX LEASE — DO NOT TOUCH MANUALLY

Current SpaceX job:

- job id: `b20ba215a4115f9cc41aa35bf7074a6f`
- source: `greenhouse:spacex`
- status: RUNNING
- retry_count: 1
- lease owner: prior hosted proof shard
- lease is expired

Do not mutate this row.

After the large-source correction is deterministic-green, the next healthy stale-first worker wave should reclaim it naturally.

That reclaim is the best live test of the optimization.

Do not dispatch another blind wave before the performance correction is implemented.

---

# 10. HOSTED PROOF SEQUENCE AFTER CODE CORRECTION

Do not jump directly to backlog recovery.

## Step 1 — deterministic

Require:

- targeted persistence classification tests;
- bounded `evaluate_new` tests;
- evaluate enqueue coalescing tests;
- same-identity PostgreSQL concurrency tests;
- transaction/no-refresh runner test;
- all W22.4 runtime suites;
- reliability proof;
- guard;
- repository integrity;
- compile checks.

No relevant PostgreSQL concurrency test may be skipped in the CI service-container path.

## Step 2 — five-shard proof

Run the protected takeover proof.

Acceptance:

- exactly five shards;
- all five complete before timeout;
- SpaceX stale job completes naturally rather than timing out again;
- max tagged worker connections <= 10;
- persistent idle-in-transaction = 0;
- observer failures = 0;
- unattributed worker connections = 0;
- no new EMAXCONNSESSION;
- no new UniqueViolation;
- expired leases return to 0.

Capture per-stage timing for SpaceX and the slowest other source.

If persistent idle count is 1 again, use the new worker/stage attribution to identify and fix the exact path; do not waive it.

## Step 3 — bounded backlog recovery

Only after Step 2 PASS:

- take a queue baseline;
- use existing bounded recovery controls;
- run recovery waves;
- record before/after metrics each time;
- require real convergence.

Stop and repair if:
- oldest due age does not decrease;
- due total grows materially across repeated waves;
- timeouts recur;
- new error classes appear.

Acceptance remains:

- expired leases = 0;
- oldest due runnable age < 900s.

No manual queue mutation.

## Step 4 — FULL monitor and incident

Run FULL monitor at schema head `0019_activity_view_access`.

Require no FAIL/BLOCKED.

WARN solely due to documented historical dead letters remains acceptable under the current monitor contract.

Issue #137 must close through the normal `RESOLVE` path.

Do not manually close it.

---

# 11. STATE FAILURE IS MECHANICAL, BUT DO IT LAST

Current PR head still fails State.

Reason:

Codex regenerated `docs/STATE.md`, then committed additional runtime evidence reports afterward.

`scripts/generate_state.py::source_head()` intentionally excludes `docs/STATE.md` itself but does **not** exclude the W22.4 evidence report.

Therefore those later evidence commits made State stale again.

At the absolute end, after code and evidence are stable:

```bash
STATE_PRESERVE_TIMESTAMP=1 python scripts/generate_state.py
git diff -- docs/STATE.md
```

Then commit **only** the generated `docs/STATE.md` update.

Because the state generator excludes `docs/STATE.md` from `source_head()`, that final state-only commit can remain fresh.

Do not add another non-excluded evidence/code commit after the final state commit.

---

# 12. CURRENT ACCEPTANCE POSITION

The Overseer does **not** accept W22.4 for integration yet.

However, preserve the progress:

- the original connection-amplification defect is fixed;
- one real hosted observer run proved 10 max connections and zero persistent idle transactions;
- Stripe proved a 671-opportunity source can complete;
- normal CI/reliability/governance is largely green.

The remaining critical path is now:

**large-source boundedness -> evaluate_new bounded/coalesced behavior -> robust identity concurrency -> clean five-shard terminal proof -> backlog convergence -> FULL monitor -> #137 RESOLVE -> final State commit.**

---

# 13. FINAL RETURN CONTRACT

Return one report only after the full inner loop.

## STATUS

`PASS` or genuine `BLOCKED`

## REPOSITORY

- W22.5 starting SHA
- final local SHA
- verified remote SHA
- PR #139 state

## PRESERVED W22.4 PROOF

- confirm run `35619944610` observer metrics
- confirm the original five-idle-transaction defect did not recur

## LARGE-SOURCE PERFORMANCE

For Stripe and SpaceX:

- raw/unique count
- acquisition/parse duration
- persistence duration
- inline evaluation duration
- total handler duration
- number of DB writes/round trips reduced where measurable
- whether each completed inside 35 minutes

## EVALUATE_NEW

- batch size
- concurrency/coalescing semantics
- PostgreSQL race test result
- maximum observed active evaluate jobs during live proof/recovery
- evidence no opportunity can be stranded behind a running evaluator

## PERSISTENCE CONCURRENCY

- exact final strategy
- same-identity PostgreSQL race proof
- provenance uniqueness proof
- unrelated-source concurrency proof
- new hosted UniqueViolation count after final SHA

## CONNECTION PROOF

- run ID
- all five shard results
- max worker connections
- persistent idle-in-transaction
- observer failures
- new EMAXCONNSESSION delta
- expired lease result

## QUEUE RECOVERY

- starting due count/oldest age
- every recovery run ID
- ending due count
- ending oldest due age
- ending expired lease count
- retry/dead-letter disposition
- latest successful source poll

## MONITOR / INCIDENT

- FULL monitor run ID
- overall result
- issue #137 final state
- evidence of normal RESOLVE path

## CI / STATE

- Mandatory Governance
- Reliability Proof Harness
- OCI smoke
- Guard
- repository integrity
- State
- any other required PR checks

## INVARIANTS

Confirm:

- exactly five shards;
- normal 30 jobs / 480 seconds unchanged;
- 35-minute shard timeout unchanged unless explicitly approved by Overseer after evidence;
- cadence unchanged;
- queue monitor thresholds unchanged;
- no manual queue mutation;
- no production data deletion;
- no hidden paid infrastructure.

## OUT-OF-LANE

Repeat the Founder activity RLS finding if still unresolved.

## READY FOR OVERSEER INTEGRATION

`YES` or `NO`

Do not claim the seven-day soak has elapsed.
