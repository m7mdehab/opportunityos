# Work order A1M — Migration `0004` and the storage layer

**Brief:** BRIEF-FR-006 §2 Track A (the schema half of A1). **Wave:** 1. **Depends on:** nothing.
**Worktree/branch:** `wt/fr006-a1m` **Test DB:** `opportunityos_test_a1m`
**Turn budget:** 60. **Spend at most 6 turns reading before you write the migration.**

**First action:** `git merge --no-edit feat/brief-fr-006-nothing-missed` from your worktree root.

**Why this order exists:** the original A1 order bundled the schema, the extraction path, and a
fixture corpus. It was too large and its implementer exhausted its budget without landing the
migration, which five other work orders wait on. The Master split it. This order is the blocker
and it is fully specified below — you should not need to design anything.

## What you build

**One** Alembic revision, `storage/migrations/versions/0004_founder_control.py`, with
`down_revision = "0003_provenance_identity"`, fully reversible, plus the matching ORM models and
repository persistence. It is the **only** `0004` in the brief; a second revision file is a FAIL.

### On table `opportunities`, add

| Column | Type | Null | Default |
|---|---|---|---|
| `work_mode` | String(16) | not null | `'unspecified'` |
| `work_mode_source` | String(16) | null | |
| `location_country` | String(2) | null | |
| `location_city` | String(128) | null | |
| `location_region` | String(64) | null | |
| `remote_scope` | String(24) | not null | `'unspecified'` |
| `remote_scope_regions` | Text (JSON array) | null | |
| `employment_type` | String(24) | not null | `'unspecified'` |
| `seniority_level` | String(24) | not null | `'unspecified'` |
| `compensation_min` | Integer | null | |
| `compensation_max` | Integer | null | |
| `compensation_currency` | String(8) | null | |
| `compensation_period` | String(16) | null | |
| `title_family` | String(64) | null | |
| `title_level` | String(24) | null | |
| `family_key` | String(64) | null | |
| `search_tsv` | TSVECTOR | null | |

Indexes: btree on `work_mode`, `location_country`, `title_family`, `family_key`; **GIN on
`search_tsv`**, named exactly `ix_opportunities_search_tsv`.

### New tables

- **`opportunity_families`** — `family_key` PK String(64), `employer` String(256),
  `normalized_title` String(256), `member_count` Integer, `best_member_id` String(64),
  `split_out` Boolean not null default false, `updated_at` DateTime.
- **`founder_facets`** — `facet_id` PK String(64), `mode` String(16) not null default `'off'`,
  `values_json` Text, `updated_at` DateTime.
- **`founder_saved_views`** — `id` PK String(64), `name` String(128) unique, `facets_json` Text,
  `search_query` Text, `is_default` Boolean not null default false, `created_at`, `updated_at`.
- **`artifact_cache`** — `cache_key` PK String(128), `opportunity_id` String(64),
  `truth_pack_hash` String(64), `template_id` String(32), `artifact_kind` String(32),
  `content_type` String(128), `payload` LargeBinary, `created_at` DateTime.
- **`founder_opportunity_views`** — `opportunity_id` PK String(64), `viewed_at` DateTime not null.

### Explicitly NOT part of this migration

**Do not drop or alter `founder_filter_settings`.** The brief says `0004` replaces it with
`founder_facets`; the Master has ruled otherwise and recorded the deviation. The ten policy
filters carry a `hide` / `rank_only` / `label_only` vocabulary that facet `include` / `exclude` /
`off` cannot express, and claim A-18 requires it to keep working. Both tables exist.

## Also required

1. **ORM models** in `storage/models.py` for every column and table above.
2. **`storage/repository.py`** persists and reads back every new column. A round-trip test per
   column: write a value, read it, assert equality, including the null cases.
3. **Backup completeness.** Adding tables to `Base.metadata` trips the BRIEF-FR-003
   backup-completeness invariant. Register the new tables in `scripts/backup_restore.py` and keep
   `scripts/test_backup_restore.py` green. This is a known consequence, declared in advance in
   `reports/evidence/FR-006/a6-expected-scope.md` §5.
4. **The `reextract_all` backfill handler** in `worker/handlers.py`: re-parses every stored
   `raw_payload_json` and updates the new columns in place. Batched, safe to interrupt, and
   **idempotent** — a second run changes zero rows, asserted. The extraction functions it calls
   are being written by a concurrent work order; call them behind a small interface and, if they
   are not on your base yet, make the handler a no-op that reports "0 rows, extractor
   unavailable" and say so in your return. Do not implement extraction yourself.
5. **Downgrade is real.** Every column, index, constraint and table above is dropped by
   `downgrade()`. Assert per object, not by exit code.

## Field-name contract

A concurrent work order is adding the same-named attributes to `Opportunity` in
`opportunity/models.py`. The spellings above are the contract; use them exactly. If the other
order reports a different spelling, the Master reconciles at integration — do not guess or rename.

## Allowed files

`storage/migrations/versions/0004_founder_control.py` (new) · `storage/models.py` ·
`storage/repository.py` · `storage/test_postgres_integration.py` · `scripts/backup_restore.py` ·
`scripts/test_backup_restore.py` · `worker/handlers.py` and `worker/test_*.py` (the
`reextract_all` handler only).

## Frozen — touching any of these is a FAIL

`storage/migrations/versions/0001|0002|0003` · any `0005+` revision · `opportunity/**` ·
`matching/**` · `truth/**` · `api/**` · `web/**` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| A1M.1 | on an empty scratch DB: `alembic upgrade head`, `alembic downgrade base`, `alembic upgrade head` | 4 / 4 / 4 revisions, exit 0 each; head is `0004_founder_control` |
| A1M.2 | a per-object presence check after upgrade and after downgrade | every column, index, constraint and table listed above present after upgrade and **absent** after downgrade — printed per object, not inferred from the exit code |
| A1M.3 | `SELECT indexname FROM pg_indexes WHERE tablename='opportunities'` | `ix_opportunities_search_tsv` present |
| A1M.4 | `py -3.12 -m unittest discover -s storage -p "test_*.py" -v` | `OK`, count stated |
| A1M.5 | `py -3.12 -m unittest scripts.test_backup_restore -v` | `OK` |
| A1M.6 | the `reextract_all` idempotency test | second run reports zero changed rows |
| A1M.7 | `ls storage/migrations/versions/` | exactly **one** `0004_*` file; `founder_filter_settings` still exists after upgrade |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim.
