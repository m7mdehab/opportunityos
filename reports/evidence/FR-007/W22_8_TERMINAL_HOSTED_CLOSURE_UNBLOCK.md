# FR-007 W22.8 — Terminal Hosted Closure Unblock

## Status entering this packet

The W22.7 `BLOCKED` report is **not accepted as a terminal external blocker**.

The repository reached deterministic PostgreSQL proof, but the hosted closure stopped because the new branch-only workflow
`.github/workflows/fr007-final-runtime-closure.yml` is not registered on GitHub's default branch.

That registration rule is real, but it does **not** require merging this feature branch.

GitHub's workflow-dispatch contract is:

- a manually dispatched workflow must exist on the default branch;
- once a workflow is registered there, it may be dispatched against another branch with `--ref`;
- the workflow run uses the workflow version at the dispatched ref.

The repository already has a default-branch registered workflow path:

`.github/workflows/fr007-current-readiness-launcher.yml`

The Overseer has now added the same path to this feature branch and wired it to the branch-local final closure workflow. The branch-local final closure workflow now also exposes `workflow_call`.

Therefore the correct dispatch path is the **registered launcher**, not the branch-only closure file.

Do not merge merely to register a workflow.

---

# Authoritative branch

Continue exclusively on:

`work/fr007-overseer-storage-budget-correction-v2`

Fetch/reset to the remote branch before work.

The branch includes two Overseer commits after the W22.7 report:

- `4450ccc58f3a49b2a6a7c519ad8bcb17a1101a05` — expose the final closure as a reusable workflow;
- `a5291183531b6e2843e0fa2f3133f6d4b654b97e` — add a feature-branch version of the default-registered current-readiness launcher.

Read this packet and all W22.7 evidence before changing code.

---

# 1. Dispatch workaround — mandatory

Do **not** attempt to dispatch:

`fr007-final-runtime-closure.yml`

directly.

Dispatch the default-registered launcher against this branch:

```bash
gh workflow run fr007-current-readiness-launcher.yml \
  --ref work/fr007-overseer-storage-budget-correction-v2 \
  -f truth_pack_hash=83039de99306d1365ca4ebe474f7c172bfe891c55a648d4c15e93d2bc51d4619
```

Then locate and watch the dispatched run:

```bash
gh run list \
  --workflow fr007-current-readiness-launcher.yml \
  --branch work/fr007-overseer-storage-budget-correction-v2 \
  --event workflow_dispatch \
  --limit 5
```

Use `gh run watch <run-id> --exit-status` and `gh run view <run-id> --log-failed` as needed.

If GitHub CLI resolution by filename is ambiguous, resolve the registered workflow on `main` and dispatch that workflow ID/path with the same feature-branch `ref`.

The default-branch file is only the registration anchor. Do not run its old readiness target. The dispatched branch ref must be the W22.8 feature branch.

---

# 2. One remaining cold-state defect must be fixed before live maintenance

Independent Overseer review found a sustainability bug that the W22.7 report did not identify.

Current code:

`StorageRepository.hydrate_cold_opportunity()`

does all of the following:

- writes the archived description back into `opportunities`;
- restores provenance rows;
- rebuilds `search_tsv`;
- commits the hot-state restoration.

`evaluate_new` uses that method when an archived opportunity needs evaluation under a new truth-pack hash.

But the existing cold archive row remains. Maintenance eligibility excludes any opportunity that already has an archive row.

Therefore a truth-pack change can permanently re-expand cold rows into hot storage while simultaneously preventing them from becoming cold again.

That violates the zero-dollar steady-state invariant.

## Required correction

Do **not** use persistent hot hydration for cold re-evaluation.

Preferred design:

- add a checksum-verified archive loader that reconstructs the source truth in memory;
- construct the `Opportunity` used for scoring from the verified archive payload + compact hot identity fields;
- do not write description/provenance/search vector back to the hot database merely to evaluate;
- leave the row cold after scoring;
- update only the evaluation/projection state required by the new truth pack, respecting the cold-feed contract;
- corrupt/missing/stale archive fails closed.

An equivalent design that immediately and transactionally re-colds the row after successful scoring is acceptable only if it proves no durable hot expansion remains.

Required tests:

1. cold row before re-evaluation remains cold after successful new-pack evaluation;
2. database description remains the cold marker (or equivalent compact state);
3. provenance is not durably re-expanded;
4. archive hash remains verified/current;
5. corrupt archive persists no evaluation;
6. content-change still invalidates stale archive and restores actual new source truth;
7. a changed row can later become cold again;
8. repeated truth-pack changes do not produce monotonic hot-storage growth.

Run these on disposable PostgreSQL, not only SQLite.

---

# 3. The hosted workflow must support actual convergence, not one recovery wave

Current branch-local closure workflow has one five-shard `bounded-recovery` matrix followed immediately by a queue-age assertion.

That is not sufficient because the starting queue is known to be large.

Latest Overseer read-only queue snapshot before hosted maintenance:

- due runnable: **548**
- oldest due age: **127928 seconds**
- RUNNING: **5**
- expired RUNNING leases: **5**
- dead letters: **4**
- evaluate_new RUNNING: **5**
- evaluate_new pending/retry: **241**
- poll_source pending/retry: **307**

One bounded wave may legitimately make progress without reaching `oldest_due_age <900`.

The implementer must not return BLOCKED merely because one wave does not empty the backlog.

## Required workflow/dispatch modes

Make the registered-launcher path support at least these safe modes:

### `full`

- deterministic PostgreSQL proof;
- live preflight;
- capacity maintenance if still required;
- fresh-write proof;
- one bounded five-worker recovery wave;
- recovery snapshot.

### `recovery`

- no migration/compaction rerun unless capacity evidence requires it;
- capacity/read-only preflight;
- exactly five concurrent worker shards;
- unique worker IDs;
- normal 30 jobs / 480 sec limits;
- queue/capacity/error snapshot.

### `acceptance`

Run only after convergence:

- capacity preflight;
- protected exactly-five-shard proof;
- live connection observer;
- final queue/error snapshot;
- FULL monitor;
- normal issue #137 RESOLVE.

The launcher can call reusable workflows or contain these jobs directly. The implementation choice is yours.

Codex owns the outer execution loop over these modes:

1. dispatch `full`;
2. inspect evidence;
3. while oldest due >=900 or expired leases >0:
   - dispatch `recovery`;
   - inspect trend;
   - if trend stalls, diagnose/fix rather than blindly repeating;
4. once converged, dispatch `acceptance`.

Do not cap the number of normal recovery waves arbitrarily. Stop only for a real safety/error condition or terminal convergence.

---

# 4. Final acceptance must reproduce the W22.5 connection proof, not just a queue snapshot

The current W22.7 `final-proof` job checks queue age/size but does not reproduce the full accepted connection-pressure observer.

The final `acceptance` mode must include an observer equivalent to W22.5 and require:

- exactly 5 worker shards;
- max tagged worker connections <=10;
- persistent (>30s) idle-in-transaction = 0;
- unattributed PostgreSQL connections = 0;
- observer probe failures = 0;
- all five shards succeed;
- existing 35-minute job envelope unchanged;
- normal 30 jobs / 480 sec shard limits unchanged;
- expired leases = 0;
- oldest due <900 sec;
- DB <=400 MiB;
- no new `EMAXCONNSESSION`;
- no new `UniqueViolation`;
- no new `ReadOnlySqlTransaction`.

Capture a failure/error delta from the start of the final proof; do not infer “no new error” from an all-time aggregate.

---

# 5. Live maintenance behavior

Use only the repository-managed W22.7 path.

No manual worker-row edits.

No manual source-schedule edits.

No paid infrastructure.

No arbitrary truncation.

If the first maintenance pass leaves the live DB above 400 MiB:

`inspect -> diagnose -> correct structural footprint -> rerun maintenance`

Do not return BLOCKED simply because the first compaction estimate was wrong.

If PostgreSQL archive bytes prevent the target, the already-authorized fallback remains:

- store cold payload bytes in private Supabase Storage;
- keep only compact DB archive metadata/hash/object identity;
- use existing `STORAGE_SERVICE_KEY`;
- remain within Free Plan object-storage quota.

This fallback is evidence-driven, not mandatory if PostgreSQL compression already reaches the target.

---

# 6. Provider read-only recovery

Use the existing `fr007-staging` secrets through GitHub Actions.

Supabase Free Plan read-only maintenance is not a blocker by itself.

Use the documented write-capable maintenance-session path already encoded by W22.7.

After maintenance:

- close the maintenance session;
- use a fresh normal application connection;
- require non-recovery, normal write capability, and <=400 MiB;
- use bounded backoff if provider read-only state takes a short time to clear after reclaim.

Only a provider condition that persists after successful size recovery and bounded re-checks may be considered external.

---

# 7. FULL monitor / issue #137

After acceptance proof:

- run FULL monitor;
- require no FAIL/BLOCKED runtime condition;
- preserve historical dead-letter WARN behavior if that is the existing contract;
- issue #137 must close through `process_incident_alert.py` normal `RESOLVE`;
- never manually close the issue.

---

# 8. Evidence and State

Do not preserve the old W22.7 BLOCKED report as the terminal result.

Create the final PASS/BLOCKED continuation evidence with all run IDs and measured live data.

After all code/evidence commits are finished:

```bash
STATE_PRESERVE_TIMESTAMP=1 python scripts/generate_state.py
```

Commit **only** `docs/STATE.md`.

No non-excluded code/evidence commit may follow.

The two Overseer workflow-unblock commits mean the previous W22.7 State-only commit is no longer terminal; regenerate it at the real end.

---

# Terminal return contract

Return **PASS** only when all of these are actually true:

1. final branch/remote SHA confirmed;
2. one-head migration graph through `0020_capacity_archive`;
3. real PostgreSQL proof green on the final implementation;
4. cold re-evaluation does not durably rehydrate hot state;
5. hosted maintenance completed;
6. actual live DB <=400 MiB;
7. fresh normal connection writable;
8. five expired leases reclaimed naturally;
9. oldest due <900 seconds;
10. expired leases 0;
11. backlog materially converged;
12. final protected five-shard proof green;
13. connection observer metrics satisfy W22.5 thresholds;
14. no new connection/persistence/read-only errors;
15. FULL monitor accepted;
16. issue #137 resolved through normal RESOLVE;
17. final State-only commit is last;
18. no paid infrastructure;
19. no Founder history/source truth silently discarded;
20. no merge;
21. seven-day soak not claimed.

Return **BLOCKED** only for a genuinely external condition after exhausting:

- the default-registered launcher + feature-ref dispatch;
- repository fixes;
- GitHub Actions `fr007-staging` secrets;
- documented Supabase maintenance-session recovery;
- bounded recovery iterations.

Do not return another workflow-registration blocker.
