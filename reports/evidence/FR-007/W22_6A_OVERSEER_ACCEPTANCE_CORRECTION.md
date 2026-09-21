# FR-007 W22.6A — Overseer Acceptance Correction

## Status entering this packet

W22.6 remains **BLOCKED**.

The repository implementation on `work/fr007-overseer-storage-budget-correction` at
`9db2d4ae3aa38c7a15c0dc03aaeddbab71d02545` is not ready for live maintenance yet.

This packet preserves the W22.5 connection/session fixes and the W22.6 zero-dollar capacity direction, but corrects four acceptance-critical defects found by independent Overseer review.

Do not merge PR #139 or any capacity branch from this packet.

---

## 1. Migration conflict with the actually deployed production schema

The W22.6 branch adds:

- file: `storage/migrations/versions/0016_capacity_archive.py`
- revision: `0016_capacity_archive`
- down revision: `0015_hosted_founder_surface`

That is incompatible with the live project.

The live database currently reports:

`0019_activity_view_access`

The founder-activity correction branch already defines and has deployed:

- `0016_founder_activity`
- `0017_founder_activity_correction`
- `0018_activity_live_fix`
- `0019_activity_view_access`

Therefore the W22.6 migration cannot be applied to production as written.

### Required correction

Reconcile the capacity branch with:

`work/fr007-codex-founder-activity-correction`

Founder-activity head at Overseer review:

`6150f73521911ec398f5fc3651bce40a1c8050af`

Preserve all W22.5/W22.6 code while bringing the repository migration graph to the live schema.

The capacity migration must become the next revision after production, normally:

- filename: `0020_capacity_archive.py`
- revision: `0020_capacity_archive`
- down revision: `0019_activity_view_access`

Do not edit the already deployed founder-activity migrations.

The separate known `founder_activity_events` table-level RLS defect remains **out of this lane**. Do not fix it opportunistically.

---

## 2. Changed-content/archive invalidation is incomplete

Current W22.6 behavior:

- archive eligibility excludes any opportunity already present in `opportunity_cold_archive`;
- the archive primary key is only `opportunity_id`;
- normal opportunity persistence does not invalidate or replace the archive row when source content changes.

Result:

1. an ineligible opportunity is archived;
2. a later poll returns changed content;
3. hot opportunity description/provenance are restored by normal persistence;
4. the old cold archive row still exists with the old content hash;
5. future maintenance excludes that opportunity forever because an archive row exists.

This violates the W22.6 requirement that changed content invalidate stale suppression/archive state and causes hot-state growth to recur over time.

### Required correction

Implement one explicit content-version-safe contract.

Acceptable examples:

- on changed-content persistence, delete/invalidate the old archive row in the same correctness boundary, making the changed row eligible for future maintenance; or
- replace the single archive row atomically with the new content version when it becomes cold again.

Prove:

- unchanged same-hash cold rows stay cheap;
- changed content returns to full hot truth before re-evaluation;
- stale archive bytes are not treated as current truth;
- a changed row can be archived again later;
- archive integrity remains verifiable.

---

## 3. Truth-pack changes currently re-evaluate archived placeholder content

Current maintenance rewrites archived hot rows to:

- `description='[archived]'`
- `raw_payload_json=NULL`
- deletes `field_provenances`
- clears `opportunities.search_tsv`

Current `evaluate_new` reconstructs an Opportunity directly from the hot
`OpportunityRecord` + `field_provenances`.

When the founder truth-pack hash changes, every archived opportunity lacks an evaluation for the new pack and therefore becomes eligible for `evaluate_new`.

As currently implemented, those rows would be scored from:

- description `[archived]`;
- no archived provenance;
- no original responsibilities/requirements/skills recoverable from the hot row.

That would create invalid new-pack match evaluations from placeholder data.

This directly violates the frozen W22.6 requirement:

> truth-pack changes invalidate stale rejection decisions without losing source truth.

### Required correction

The evaluation path must hydrate authoritative archived source truth before scoring an archived row.

Requirements:

- archived rows are detectable without reading private payloads unnecessarily;
- `evaluate_new` uses a verified decompressed archive payload when the hot row is cold;
- SHA-256 verification occurs before archived payload use;
- invalid/corrupt archive fails closed;
- no placeholder text can enter a persisted match evaluation;
- current-pack changes cause real re-evaluation from original source truth;
- tests prove the scored Opportunity is semantically equivalent to the pre-archive source record for all archived fields needed by matching.

Do not permanently restore every archive into hot state merely to evaluate it unless measured evidence proves the resulting footprint still stays inside the zero-dollar budget.

---

## 4. Feed-search behavior is silently degraded for archived opportunities

W22.6 changes PostgreSQL feed search to use `opportunities.search_tsv`.

The maintenance operation simultaneously sets archived opportunities' `search_tsv=NULL`.

Therefore archived current-pack projection rows remain in the feed read model, but full-text search can no longer match them.

That is not equivalent existing search behavior and was not proved acceptable.

### Required correction

Choose and prove one explicit product behavior:

A. keep a compact authoritative searchable representation for cold opportunities; or

B. explicitly exclude cold opportunities from interactive feed/search under a documented archival-state contract while preserving Founder-actioned rows and all non-cold current feed semantics.

Whichever design is chosen:

- no silent disappearance caused solely by a NULL search vector;
- tests cover ordinary feed, include-hidden feed, filters, and search;
- search behavior after archive is deterministic and documented.

---

## 5. Disposable PostgreSQL proof was required and did not run

W22.6 required disposable PostgreSQL proof.

The report states:

- no Docker/local PostgreSQL;
- SQLite/unit tests passed;
- offline Alembic SQL generation passed.

That is not sufficient for acceptance because the changed code depends on:

- PostgreSQL migration graph;
- `TSVECTOR` / GIN semantics;
- PostgreSQL joins/search;
- advisory/transaction behavior;
- provider-facing capacity queries.

### Required correction

Use GitHub Actions with a disposable PostgreSQL service container.

At minimum prove on the reconciled branch:

1. `alembic upgrade head` from a fresh DB;
2. upgrade from schema state `0019_activity_view_access` to `0020_capacity_archive`;
3. migration graph has a single head;
4. capacity archive constraints/indexes exist;
5. archive/apply transaction behavior;
6. changed-content invalidation;
7. archive hydration for truth-pack re-evaluation;
8. PostgreSQL feed search after compaction;
9. capacity guard behavior;
10. existing runtime/storage/matching regressions.

The CI test must execute, not skip.

---

## 6. Live dry-run evidence available to the Overseer

The live database is still read-only. No writes were performed during this review.

Verified live:

- migration version: `0019_activity_view_access`
- current authoritative truth-pack hash in runtime evidence:
  `83039de99306d1365ca4ebe474f7c172bfe891c55a648d4c15e93d2bc51d4619`
- current ineligible + no-founder-state maintenance candidates: **21,312**
- synthetic `active` projections: **26,061**
- current-pack projection rows for those candidates: **21,312**
- current-pack evaluation rows for those candidates: **21,312**
- provenance rows for those candidates: **241,383**

Measured logical payload among those 21,312 candidates:

- opportunity descriptions: ~84 MB
- raw payload JSON: ~9.8 MB
- opportunity search vectors: ~108 MB
- provenance text payload: ~24 MB
- match-evaluation JSON payload: ~84 MB
- current projection search/reason payload: ~257 MB

These are logical column sizes, not final physical reclaim estimates. Do not add them mechanically and call that the expected post-VACUUM database size.

### Required dry-run enhancement

The repository-managed `plan` command must report a realistic reclaim estimate by category and explicitly distinguish:

- logical bytes selected for compaction;
- relation/index/TOAST physical size;
- estimated reclaim before VACUUM;
- actual reclaim after controlled maintenance.

Acceptance remains actual `pg_database_size`, not an estimate.

---

## 7. Provider execution authority is not the terminal blocker for the Overseer

The W22.6 report says the lane lacks an authenticated Supabase maintenance connection.

That is true for the Codex lane, but not a terminal project blocker.

The Overseer has authenticated live Supabase query authority and can execute the controlled provider session once the repository implementation is safe and the migration graph is reconciled.

Therefore do not return BLOCKED merely because Codex cannot access the hosted credential.

Finish the repository correction and CI proof first.

The Overseer will then execute/authorize the live maintenance boundary from the accepted implementation.

---

# Execution order

## A. Reconcile branch/schema first

Before any additional live write:

1. bring founder-activity migration/code history into this capacity lane;
2. preserve W22.5/W22.6 accepted code;
3. rename/rebase capacity migration to `0020_capacity_archive` after `0019_activity_view_access`;
4. prove one Alembic head.

Do not touch production yet.

## B. Fix cold-state semantics

Implement:

- content-change archive invalidation/replacement;
- verified archive hydration for matching;
- explicit cold-feed/search semantics;
- realistic maintenance planning output.

## C. Real PostgreSQL CI

Run the non-skipped disposable PostgreSQL proof described above.

If any failure occurs:

`inspect -> diagnose -> fix -> strengthen coverage -> rerun`

Do not report back merely because a normal test fails.

## D. Return to Overseer before live mutation

Once A-C are green, return a short **READY_FOR_LIVE_MAINTENANCE** evidence report containing:

- final branch/SHA;
- migration graph/head proof;
- PostgreSQL CI run URL;
- candidate count/reclaim plan;
- archive hydration/invalidation proof;
- feed/search semantics;
- exact repository-managed live command to run.

Do **not** execute live maintenance from Codex unless the lane has newly obtained authorized provider execution.

Do not merge.

Do not claim queue recovery, monitor PASS, incident RESOLVE, or seven-day soak before they actually happen.

---

# After READY_FOR_LIVE_MAINTENANCE

The Overseer will perform the controlled provider maintenance session.

Only after actual size <=400 MiB and fresh normal connections are writable should the runtime sequence continue:

1. natural stale recovery of expired jobs;
2. bounded queue convergence to oldest due <900s and expired leases=0;
3. final five-shard proof;
4. FULL monitor;
5. issue #137 normal RESOLVE;
6. final State-only commit;
7. integration decision;
8. then the real seven-day soak begins.

---

# Return contract for this correction

Return only:

**READY_FOR_LIVE_MAINTENANCE** or **BLOCKED**

with:

1. final SHA / remote SHA;
2. reconciled migration graph and one-head proof;
3. disposable PostgreSQL CI evidence;
4. archive invalidation proof;
5. archived-truth hydration proof;
6. feed/search post-archive behavior proof;
7. dry-run/reclaim estimate;
8. exact live maintenance command;
9. unchanged no-paid-infrastructure confirmation;
10. unchanged no-manual-worker-row-mutation confirmation;
11. no seven-day soak claim.
