# FR-007 W22.7 — Final Runtime Closure Execution Packet

## Command intent

This is the final execution packet for the FR-007 runtime/capacity closure.

The implementer owns the complete inner loop from repository correction through hosted acceptance.

**Do not return an intermediate plan.**
**Do not stop at READY_FOR_LIVE_MAINTENANCE.**
**Do not ask the Founder/Overseer to run routine GitHub Actions or database commands that can be executed through the existing repository/environment.**

Return only:

- **PASS**, after every acceptance item below is actually complete; or
- **BLOCKED**, only for a genuinely external condition that remains after exhausting all already-authorized repository, GitHub Actions, Supabase SQL-session, and existing-secret execution paths.

For every ordinary failure:

`inspect -> diagnose -> fix -> strengthen coverage -> rerun`

Do not merge. Do not claim the seven-day soak.

---

# Authoritative starting state

Work exclusively on:

`work/fr007-overseer-storage-budget-correction-v2`

Read completely before editing:

1. `reports/evidence/FR-007/W22_4_CODEX_FINAL_RUNTIME_CLOSURE_BRIEF.md`
2. `reports/evidence/FR-007/W22_5_CODEX_RUNTIME_ACCEPTANCE_CORRECTION.md`
3. `reports/evidence/FR-007/W22_5_CODEX_RUNTIME_ACCEPTANCE_CORRECTION_REPORT.md`
4. `reports/evidence/FR-007/W22_6_ZERO_DOLLAR_DB_CAPACITY_CORRECTION.md`
5. `reports/evidence/FR-007/W22_6_ZERO_DOLLAR_DB_CAPACITY_CORRECTION_REPORT.md`
6. `reports/evidence/FR-007/W22_6A_OVERSEER_ACCEPTANCE_CORRECTION.md`
7. this packet.

Starting branch ancestry includes W22.5 accepted runtime fixes and W22.6 capacity work.

Known authoritative evidence:

- W22.5 final takeover SHA: `b0c64f43151cc66777001c4e7ff3159f585ff99c`
- W22.6 final SHA: `9db2d4ae3aa38c7a15c0dc03aaeddbab71d02545`
- W22.6A packet SHA: `308a68f2dcf5819f78cfbed5cfab8ff748302689`
- live Supabase project: `lrrcpwaapwynzdsxzwhy`
- live organization plan: Free
- Free Plan DB quota: 500 MB
- live DB entered provider read-only at ~1503 MiB
- live migration head: `0019_activity_view_access`
- Founder activity branch/head: `work/fr007-codex-founder-activity-correction` / `6150f73521911ec398f5fc3651bce40a1c8050af`
- W22.5 clean protected proof run: `35654469231`
- W22.5 proof remains accepted:
  - five shards PASS
  - max worker connections 10
  - persistent idle-in-transaction 0
  - unattributed 0
  - observer failures 0
- W22.5 connection/session correction must not regress.

Current live queue was left with expired RUNNING jobs after provider read-only prevented status writes.
Do not mutate those rows manually. Stale-first worker semantics must reclaim them.

---

# Existing authorized execution plane

Do not treat lack of a local Codex DB credential as a blocker.

The repository already has a GitHub Actions environment:

`fr007-staging`

Existing workflows prove that this environment exposes at least:

- `secrets.OPOS_TARGET_DB_URL`
- `secrets.CLOUD_DATABASE_URL`
- `secrets.STORAGE_SERVICE_KEY`
- `SUPABASE_URL=https://lrrcpwaapwynzdsxzwhy.supabase.co`

Use GitHub Actions as the authenticated hosted execution plane.

The existing `fr007-runtime-takeover-proof.yml`, `fr007-worker-drain.yml`, and
`fr007-zero-dollar-readiness.yml` demonstrate the pattern.

You are authorized to add a **workflow_dispatch-only** closure workflow on this branch using
the `fr007-staging` environment and the existing secrets.

Do not expose secret values in logs.

---

# Supabase read-only recovery facts

Official Supabase Free Plan behavior:

- Free projects enter read-only mode above 500 MB.
- Supabase documents a maintenance session override using:
  `SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE;`
- after reducing size, reclaim physical space with VACUUM as appropriate;
- normal read-write operation must then be verified on a **fresh connection**.

Reference:

`https://supabase.com/docs/guides/platform/database-size`

Supabase also exposes a Management API endpoint that temporarily disables project read-only for 15 minutes.
If an already-configured Supabase Management API token is present in the GitHub environment, it may be used.
Do **not** require the Founder to create a new token if it is absent; the documented SQL maintenance-session path is the default fallback.

For maintenance that changes session state, use one persistent session/direct or session-mode connection.
Do not rely on transaction-pooler session-state persistence across unrelated connections.

---

# PHASE 1 — Reconcile the repository to production reality

Before any live write:

1. bring the Founder-activity correction history/code needed by production into this capacity branch;
2. preserve all W22.5 accepted runtime fixes;
3. preserve all valid W22.6 capacity work;
4. resolve conflicts semantically, not mechanically;
5. delete/replace the conflicting `0016_capacity_archive` migration;
6. create the capacity migration as the next real production revision:
   - expected filename: `0020_capacity_archive.py`
   - revision: `0020_capacity_archive`
   - down_revision: `0019_activity_view_access`
7. prove exactly one Alembic head.

Do not edit already-deployed migrations 0016-0019.

The known table-level RLS defect on `founder_activity_events` remains out of lane.
Do not fix it here.

---

# PHASE 2 — Make cold-state semantics permanently correct

The zero-dollar design must be sustainable, not just a one-time shrink.

## 2A. Archive invalidation

Fix the existing archive lifecycle so that:

- same identity + same content hash can remain cold and cheap;
- changed source content invalidates the old cold version;
- changed content is restored to authoritative hot truth before scoring;
- stale archive bytes can never be treated as current source truth;
- after the changed content is evaluated and becomes cold-eligible again, it can be archived again;
- archive integrity remains checksum-verifiable.

A pre-existing archive row must never permanently prevent future compaction of a changed opportunity.

## 2B. Truth-pack changes

An archived opportunity must never be evaluated from placeholder text such as `[archived]`.

When the active truth-pack hash changes and a cold opportunity requires re-evaluation:

- detect cold state explicitly;
- verify the archived payload SHA-256 before use;
- hydrate the authoritative archived fields needed by matching;
- fail closed on missing/corrupt archive;
- never persist a new match result derived from placeholder/missing archived source truth.

Do not permanently rehydrate the entire cold corpus into hot DB state merely to score it.

## 2C. Feed/search semantics

Do not silently retain a projection row while making it impossible to search because its only search vector was nulled.

Freeze and implement one explicit contract:

**Cold current-pack hard-ineligible opportunities with no Founder activity/feedback/outbound history are not part of the active interactive feed/search corpus.**

They remain:

- dedupe-identifiable;
- losslessly recoverable;
- eligible for re-evaluation when content or truth-pack changes.

Founder-actioned/feedback/history-bearing opportunities are never removed from the interactive/history surface by cold compaction.

Therefore the sustainable hot model is:

- hot actionable/current feed = full read model;
- cold terminal ineligible/no-Founder-state = compact identity + verified archive/suppression state;
- no duplicate heavyweight full-text corpus per truth-pack profile.

Update queries/tests accordingly.

## 2D. Archive storage choice

The implementation must remain within the zero-dollar envelope.

Prefer the smallest safe design.

If the compressed archive remains in PostgreSQL, measure its actual physical contribution and prove the final DB <=400 MiB with headroom.

If PostgreSQL archive bytes prevent that target, move cold payload bytes to a private Supabase Storage bucket and retain only compact DB metadata/hash/object identity.
The existing `fr007-staging` environment already has `STORAGE_SERVICE_KEY`; current Supabase object storage usage is only a few MB and the Free Plan has a separate storage quota.

Do not introduce a paid service.

The final choice must be evidence-driven and must pass the actual live size target.

---

# PHASE 3 — Real PostgreSQL deterministic proof

Create/extend CI so the capacity correction is tested on a disposable PostgreSQL 16 service container.

This proof must run on the final branch and must not skip.

Required evidence:

1. fresh `alembic upgrade head`;
2. simulated existing-production upgrade from `0019_activity_view_access` to `0020_capacity_archive`;
3. exactly one migration head;
4. archive schema/constraints/indexes;
5. archive idempotency;
6. changed-content invalidation;
7. verified cold hydration for truth-pack re-evaluation;
8. corrupt archive fail-closed behavior;
9. post-archive feed/search semantics;
10. Founder-state preservation;
11. PostgreSQL search behavior;
12. capacity guard behavior;
13. W22.5 persistence-race/concurrency tests;
14. runtime/storage/matching regressions.

Use a GitHub Actions service container if local Docker/Postgres is unavailable.

A local “no PostgreSQL available” result is not BLOCKED.

---

# PHASE 4 — Build one final hosted closure workflow

Add a temporary, workflow-dispatch-only workflow, for example:

`.github/workflows/fr007-final-runtime-closure.yml`

It must use:

- environment: `fr007-staging`
- `secrets.OPOS_TARGET_DB_URL`
- `secrets.CLOUD_DATABASE_URL`
- `secrets.STORAGE_SERVICE_KEY` if archive storage requires it
- sanitized output only.

The workflow must provide distinct jobs/stages for:

1. deterministic PostgreSQL proof;
2. live preflight/dry-run;
3. controlled maintenance;
4. fresh normal-connection write proof;
5. bounded recovery;
6. final protected five-shard proof;
7. FULL monitor / incident resolution evidence.

Do not put live maintenance on a push trigger or schedule.

---

# PHASE 5 — Live preflight and dry-run

Before mutation, capture:

- migration revision;
- `pg_is_in_recovery()`;
- `default_transaction_read_only`;
- `pg_database_size`;
- top relation/index/TOAST sizes;
- archive/cold candidate counts;
- Founder-state exclusions;
- expected logical bytes selected by category;
- queue snapshot;
- current dead letters;
- current truth-pack hash.

The maintenance planner must distinguish:

- logical bytes selected;
- physical relation/index/TOAST size;
- estimated reclaim;
- actual reclaim after maintenance.

Do not claim an estimated post-size as acceptance.

---

# PHASE 6 — Controlled live capacity correction

Use the documented temporary write-capable maintenance session.

Within the repository-managed path:

1. verify live revision is exactly the expected predecessor;
2. set the maintenance session to read-write;
3. apply the 0020 schema change using the same repository-managed migration semantics;
4. execute the cold-compaction rules;
5. remove obsolete synthetic `truth_pack_hash='active'` heavyweight projection state according to the final design;
6. eliminate duplicated projection search state;
7. compact/archive eligible cold current-pack ineligible/no-Founder-state rows;
8. preserve all Founder history and protected rows;
9. verify archive hashes/integrity before destructive hot compaction;
10. commit in bounded transactions so a failure is diagnosable/restartable;
11. run supported physical reclaim on the affected large relations.

Because normal VACUUM does not necessarily shrink relation files, use `VACUUM FULL` on the specific heavy relations when necessary to reach the actual size target.
This is staging and a maintenance lock is acceptable for this closure run.

Never:

- truncate tables to fake success;
- delete Founder history;
- manually alter worker status rows;
- modify source cadence rows;
- weaken acceptance thresholds.

After maintenance, require actual:

`pg_database_size(current_database()) <= 400 MiB`

Preferred <=350 MiB.

If still >400 MiB:

- inspect the new top relations;
- fix the remaining structural duplication;
- rerun maintenance;
- do not return BLOCKED merely because the first shrink was insufficient.

---

# PHASE 7 — Fresh normal-connection write proof

After physical reclaim:

1. close the privileged/maintenance connection;
2. open a fresh normal connection using the same application path as workers;
3. require:
   - `pg_is_in_recovery() = false`
   - transaction/default read-only no longer blocks normal writes;
   - DB <=400 MiB;
4. perform a harmless transactional write/rollback proof against a dedicated temporary proof object or transaction, leaving no durable product-row mutation;
5. remove the proof artifact if one is used.

If provider read-only remains briefly after falling below quota, retry with bounded backoff and re-check provider/database state before declaring an external blocker.

---

# PHASE 8 — Natural queue recovery to convergence

Only after Phase 7 passes.

Do not manually change the expired RUNNING jobs.

Run the existing stale-first worker path and let them be reclaimed naturally.

Use bounded recovery waves.

After every wave capture:

- DB size;
- due runnable;
- oldest due age;
- RUNNING;
- expired leases;
- dead letters;
- evaluate_new running/pending;
- new `ReadOnlySqlTransaction`;
- new `EMAXCONNSESSION`;
- new `UniqueViolation`;
- source poll progress.

Stop, inspect, fix and rerun if:

- DB exceeds 425 MiB;
- due age fails to trend downward;
- a shard times out;
- a prior concurrency defect returns.

Continue until:

- oldest due age <900 seconds;
- expired leases = 0;
- backlog materially converged;
- DB remains <=400 MiB.

Do not stop after one recovery wave if those conditions are not met.

---

# PHASE 9 — Final protected five-shard proof

Run the exact protected five-shard acceptance proof on the final code/head.

Require all of:

- exactly 5 shards;
- every shard completes inside the existing 35-minute workflow envelope;
- normal shard defaults remain 30 jobs / 480 seconds;
- max tagged worker connections <=10;
- persistent idle-in-transaction = 0;
- unattributed = 0;
- observer failures = 0;
- no new `EMAXCONNSESSION`;
- no new `UniqueViolation`;
- no new `ReadOnlySqlTransaction`;
- expired leases = 0;
- post-run DB <=400 MiB.

Do not weaken cadence, thresholds, job counts, timeouts, or observer criteria.

---

# PHASE 10 — FULL monitor and issue #137

Run the FULL cloud monitor against the accepted final head.

Require:

- no FAIL/BLOCKED runtime condition;
- queue age within acceptance;
- expired leases 0;
- capacity acceptable;
- normal source/runtime health contract.

Issue #137 must resolve through the ordinary incident processor `RESOLVE` path.

Do not manually close it.

Historical dead letters may remain WARN only if that is already the monitor contract.

---

# PHASE 11 — Evidence and final State-only commit

After all hosted acceptance is complete:

1. write one final W22.7 evidence report with:
   - deterministic CI run IDs;
   - live maintenance workflow/run IDs;
   - before/after DB size;
   - before/after top relation sizes;
   - archive counts/integrity results;
   - fresh write proof;
   - recovery-wave table;
   - final queue snapshot;
   - five-shard proof metrics;
   - FULL monitor result;
   - issue #137 RESOLVE evidence;
   - final branch/head;
   - no-paid-infrastructure confirmation;
   - no Founder-history/source-truth loss confirmation;
   - explicit statement that the seven-day soak has not elapsed.

2. ensure all code/evidence commits are complete.

3. run:

`STATE_PRESERVE_TIMESTAMP=1 python scripts/generate_state.py`

4. commit **only** `docs/STATE.md`.

5. no non-excluded code/evidence commit may follow the State-only commit.

6. push and confirm remote SHA.

---

# PASS contract

Return **PASS** only if every item below is true:

- final remote branch SHA confirmed;
- migration graph reconciled through 0020 with one head;
- disposable PostgreSQL CI executed and passed;
- archive invalidation/hydration/search semantics passed;
- live maintenance actually executed;
- actual live DB <=400 MiB;
- normal fresh connection writable;
- expired jobs recovered naturally;
- queue oldest due <900s;
- expired leases 0;
- backlog converged;
- final five-shard proof passed;
- max connections <=10;
- persistent idle tx 0;
- no new connection/UniqueViolation/read-only failures;
- FULL monitor accepted;
- issue #137 normal RESOLVE completed;
- final State-only commit is last;
- no paid infrastructure introduced;
- no Founder history/source truth silently discarded;
- no merge performed;
- seven-day soak not claimed.

If a normal implementation/test/runtime failure occurs, fix it and continue.

Do not return another partial “repository done, hosted not run” report when the existing GitHub Actions execution plane can perform the hosted work.
