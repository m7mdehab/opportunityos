# FR-007 W22.6 — Zero-Dollar Database Capacity Correction & Runtime Recovery

## Status entering this packet

W22.5 repository/runtime corrections are **accepted as useful but FR-007 remains BLOCKED**.

Authoritative starting runtime head:

- source branch: `work/fr007-codex-runtime-takeover`
- source SHA: `b0c64f43151cc66777001c4e7ff3159f585ff99c`
- this packet branch: `work/fr007-overseer-storage-budget-correction`
- PR #139 remains unmerged/draft; do not merge from this packet.

The W22.5 five-shard connection/session proof is valid. Queue convergence and final monitor acceptance are not.

## Overseer correction to the W22.5 blocker diagnosis

The database is not merely “possibly pointed at a read-only endpoint”. The live Supabase project itself has entered provider-enforced read-only mode because the **Free Plan database-size quota has been exceeded**.

Verified against the live project after the W22.5 report:

- Supabase organization plan: `free`.
- Project: `opportunityos-staging` (`lrrcpwaapwynzdsxzwhy`).
- Project status: `ACTIVE_HEALTHY`.
- PostgreSQL primary: `pg_is_in_recovery() = false`.
- Live database size: **1,576,176,787 bytes / 1503 MB**.
- `default_transaction_read_only = on`.
- its source is `/data/pgdata/postgresql.auto.conf`, not a role-local application setting.
- the same hosted target successfully committed worker/evaluation writes earlier in the run and became read-only mid-recovery, so a static wrong/read-replica `OPOS_TARGET_DB_URL` does not fit the evidence.
- Supabase documents that Free Plan projects enter read-only mode above **500 MB database size**:
  https://supabase.com/docs/guides/platform/database-size

Therefore:

> **Do not “fix” OPOS_TARGET_DB_URL unless independent endpoint evidence later proves it wrong.**
>
> The primary remediation is to bring the live database below the Free Plan storage ceiling and keep it there permanently.

The project retains the zero-recurring-spend rule. **Do not solve this by upgrading Supabase.**

## Current live footprint

At the Overseer snapshot:

| relation | total |
|---|---:|
| `feed_projection` | **865 MB** |
| `opportunities` | **330 MB** |
| `field_provenances` | **149 MB** |
| `match_evaluations` | **135 MB** |
| `founder_cv_selections` | 10 MB |

Important measured duplication:

### feed_projection

49,997 rows:

- `truth_pack_hash='active'`: 26,061 rows
- current authoritative pack: 23,936 rows

Large duplicated fields:

- `search_text`: ~199 MB total
- `search_tsv`: ~359 MB total
- current-pack `reasons_json`: ~21 MB

The synthetic `active` profile alone carries approximately:

- 104 MB `search_text`
- 188 MB `search_tsv`

### opportunities

26,078 rows:

- descriptions: ~103 MB
- raw payloads: ~12 MB
- `search_tsv`: ~133 MB

### current evaluation population

Current pack evaluation decisions:

- ineligible: 21,312
- uncertain: 2,226
- qualified: 398
- not yet current-pack evaluated: remainder of opportunity corpus

The database cannot sustain the present “full heavy state for every discovered posting plus duplicated projection search state” model on the mandated Free Plan.

## W22.5 proof that must be preserved

Run `35654469231` remains valid:

- deterministic: PASS
- enqueue: PASS
- five shard drains: PASS
- observer: PASS
- max tagged worker connections: 10
- persistent idle-in-transaction: 0
- unattributed connections: 0
- observer failures: 0
- post-run queue snapshot:
  - due runnable: 571
  - oldest due age: 120395 seconds
  - running: 0
  - expired leases: 0
  - dead letter: 4

Do not regress the accepted session lifecycle, bounded worker pool, commit-aligned identity race correction, atomic projection publication, or bounded/coalesced `evaluate_new` behavior.

## Read-only transition evidence

During run `35657785793`, workers successfully committed multiple 100-item `evaluate_new` batches before all shards began receiving `ReadOnlySqlTransaction` around 21:44 UTC.

Run `35659340353` then failed at enqueue with:

`cannot execute SELECT FOR UPDATE in a read-only transaction`.

This transition pattern is consistent with the provider quota event and inconsistent with a permanently misconfigured read replica.

Current queue after the failed write window is expected to contain expired RUNNING jobs because the runner could not persist failure/lease state. At the Overseer snapshot:

- due runnable: 548
- oldest due age: 121335 seconds
- RUNNING: 5
- expired RUNNING leases: 5
- dead letters: 4
- evaluate_new RUNNING: 5
- evaluate_new pending/retry: 241

**Do not edit these rows manually.** Once write capability is restored, stale-first recovery must reclaim them naturally.

---

# Frozen product / architecture decisions

## 1. Zero-dollar storage is now a runtime acceptance invariant

OpportunityOS must fit its normal hosted staging workload inside the Supabase Free Plan database quota with meaningful safety headroom.

Acceptance target after correction and recovery:

- `pg_database_size(current_database()) <= 400 MiB`
- preferred steady-state target: <= 350 MiB
- no ordinary poll/evaluation cycle may push the database above 425 MiB without the capacity guard stopping additional heavy writes.

These are additive safety constraints; they do not weaken any existing correctness threshold.

## 2. No silent source-truth destruction

A capacity fix may compact, archive, normalize, or remove **derived/reconstructable duplication**, but it must not silently destroy source truth, founder activity, application history, or evidence required by the product.

If heavy opportunity/evaluation/provenance content is removed from hot relational state, it must be losslessly recoverable from a private zero-cost representation with integrity metadata.

Founder-actioned opportunities (Applied, Dismissed, Snoozed, or any historical founder activity/feedback) must not lose their inspectable history.

## 3. The hot database must stop storing the same heavy search/source content multiple times

The current duplication is not acceptable:

- full opportunity text/search state in `opportunities`;
- another heavy searchable copy in the synthetic `active` projection;
- another heavy searchable copy in the current truth-pack projection.

There must be one authoritative searchable representation per opportunity, not one per projection profile.

The `feed_projection` table should remain a **lean founder-feed read model**, not a second/third full-text corpus.

## 4. Synthetic `active` projections may not grow unbounded

The current per-opportunity `truth_pack_hash='active'` projection is a major storage amplifier.

Correct this so normal operation does not retain an unbounded second full projection corpus. Preserve degraded/fallback behavior through a lean path rather than duplicating descriptions/search vectors for every opportunity.

## 5. Cold/rejected state must have a bounded representation

The current corpus stores full heavy state for >21k current-pack ineligible postings.

Implement a bounded, lossless strategy for hard-ineligible/no-founder-activity opportunities. Acceptable designs include:

- a compact hot summary/suppression record plus lossless compressed private archive;
- an equivalent lossless compact relational representation;
- another design that demonstrably preserves product truth and founder history while meeting the <=400 MiB target.

Do **not** simply delete rejected jobs and call the size problem solved.

A repeated poll of an unchanged already-rejected opportunity under the same truth-pack hash must be able to skip expensive full persistence/evaluation. Content-hash or truth-pack changes must make it eligible for re-evaluation.

## 6. Capacity correction must be deterministic and repository-managed

No ad-hoc production row surgery.

Implement a repository-managed maintenance path with:

- dry-run mode;
- before/after row counts;
- before/after database/relation sizes;
- integrity checks/hashes for any archived payload;
- explicit keep/archive eligibility rules;
- idempotent rerun behavior;
- rollback/failure semantics;
- tests on disposable PostgreSQL.

If a migration is required, create the next migration cleanly. Do not rewrite migration 0019.

## 7. Add a database-capacity guard

Before hosted enqueue/drain can launch heavy work, check:

- current database size;
- transaction read-only status.

Behavior:

- if read-only: fail fast with a sanitized capacity/read-only diagnostic; do not start a five-shard wave.
- if >425 MiB: block new heavy ingestion/evaluation and emit a capacity failure.
- if >350 MiB: emit a warning but allow bounded work only if the correction proves projected growth remains safe.
- record the measured size in runtime proof/monitor evidence.

This prevents another multi-minute wave from discovering quota exhaustion only after several jobs have started.

---

# Execution order

## A. Deterministic repository correction

1. Preserve all W22.5 accepted changes.
2. Implement the measured storage-footprint correction.
3. Add PostgreSQL tests proving:
   - no duplicate heavy search corpus per projection profile;
   - synthetic/fallback projection behavior is bounded;
   - cold/ineligible handling is lossless and idempotent;
   - founder-actioned opportunities are preserved;
   - changed content invalidates a suppression/archive hit;
   - truth-pack changes invalidate stale rejection decisions;
   - current feed/search behavior remains correct;
   - capacity guard blocks read-only / over-budget execution.
4. Run the full relevant runtime/API/storage/matching suites against disposable PostgreSQL.

## B. Maintenance dry run while provider read-only is active

Use read-only queries to print:

- database size;
- relation size breakdown;
- rows eligible for compaction/archive;
- expected post-maintenance hot-row counts;
- expected reclaim estimate.

Do not launch recovery.

## C. Controlled capacity recovery

Supabase officially documents using a **session-scoped read-write maintenance session** while a Free Plan database is read-only so size can be reduced.

Use that capability only for the repository-managed maintenance operation.

Requirements:

- no queue-status edits;
- no manual completion/failure of worker jobs;
- no source schedule manipulation;
- no arbitrary deletion outside the encoded maintenance rules;
- capture exact before/after evidence;
- reclaim physical space as needed using supported PostgreSQL maintenance;
- verify `pg_database_size(current_database()) <= 400 MiB`.

Do not merely turn read-only off while leaving a 1.5 GB footprint.

## D. Fresh-connection write-capability proof

After size recovery:

- on a fresh connection, verify primary/non-recovery;
- verify new transactions are write-capable;
- verify provider/default read-only state is no longer blocking normal application connections;
- verify migration head remains `0019_activity_view_access` unless W22.6 legitimately adds a new migration.

Only then resume runtime queue recovery.

## E. Natural stale recovery + bounded backlog convergence

Resume through the existing worker semantics.

The five expired RUNNING jobs must be reclaimed naturally.

Track each recovery wave:

- due runnable count;
- oldest due age;
- RUNNING;
- expired leases;
- dead letters;
- database size;
- new `EMAXCONNSESSION`;
- new `UniqueViolation`;
- new `ReadOnlySqlTransaction`.

Stop and fix if:

- database size crosses the capacity guard;
- due age is not converging;
- a wave times out;
- connection/persistence defects recur.

Acceptance:

- oldest due age < 900 seconds;
- expired leases = 0;
- backlog materially converged;
- database <= 400 MiB.

## F. Final protected five-shard proof

Exactly the frozen five shards.

Require:

- all five complete within existing 35-minute job envelope;
- max tagged worker connections <= 10;
- persistent idle-in-transaction = 0;
- unattributed = 0;
- observer failures = 0;
- no new `EMAXCONNSESSION`;
- no new `UniqueViolation`;
- no new `ReadOnlySqlTransaction`;
- post-run database <= 400 MiB.

Do not weaken normal 30 jobs / 480 sec shard defaults.

## G. FULL monitor + incident

Run FULL monitor against the accepted head.

Require:

- no FAIL/BLOCKED runtime condition;
- capacity status acceptable;
- expired leases = 0;
- issue #137 resolves through the normal incident `RESOLVE` path only.

Historical dead letters may remain WARN if that is already the monitor contract.

## H. State

At the absolute end:

`STATE_PRESERVE_TIMESTAMP=1 python scripts/generate_state.py`

Commit **only** `docs/STATE.md` after all other code/evidence commits.

No non-excluded commit may follow it.

---

# Prohibited shortcuts

Do not:

- upgrade Supabase or add recurring spend;
- change `OPOS_TARGET_DB_URL` merely because the report guessed it might be wrong;
- manually rewrite worker statuses or delete backlog rows;
- delete opportunity/source truth without a lossless bounded representation;
- truncate tables solely to make the acceptance snapshot look green;
- weaken connection/queue/monitor thresholds;
- remove full-text/search behavior without equivalent tested behavior;
- claim the seven-day soak;
- merge PR #139 or this branch.

---

# Return contract

Return only PASS or BLOCKED with:

1. final branch/SHA and remote confirmation;
2. exact storage design implemented;
3. disposable PostgreSQL proof;
4. before/after live database size;
5. before/after top relation sizes;
6. archive/compaction counts and integrity proof;
7. fresh-connection read/write proof;
8. natural recovery of the five expired jobs;
9. every recovery wave and queue-size trend;
10. final five-shard metrics;
11. FULL monitor result;
12. issue #137 normal RESOLVE result;
13. State freshness evidence;
14. confirmation that no paid infrastructure was introduced;
15. confirmation that no founder history/source truth was silently discarded;
16. explicit statement that the seven-day soak has not yet elapsed.

For every ordinary failure:

`inspect -> diagnose -> fix -> strengthen coverage -> rerun`

Do not return a plan. Execute until PASS or a genuinely external blocker remains.
