# Work order A1B — Council review #3's findings on migration `0004`

**Brief:** BRIEF-FR-006 §4, council review 3. **Wave:** 4.
**Depends on:** A1M, A1S, C1, C2 (all integrated on the brief branch).
**Worktree/branch:** `wt/fr006-a1b` **Test DB:** `opportunityos_test_a1b`
**Turn budget:** 60. **At most 6 read/grep calls.**

**First action, and it is not optional:** `git merge --no-edit feat/brief-fr-006-nothing-missed`
from your worktree root. **Everything below refers to code that exists only after that merge.**
Your worktree is branched from `main` and is many work orders behind. If you check for a symbol
named in this order *before* merging, you will not find it, and you will draw the wrong conclusion.

## Why this order exists as its own file

Council review #3 audited migration `0004` by running base → `0003` → head → `-1` → head against
a fresh database and comparing catalog snapshots at each step. It confirmed four properties as
genuinely satisfied and raised five findings.

Those findings were first sent to the migration's original implementer as a message. It had not
merged, checked its own worktree for the symbols the findings cite, correctly found them absent
**there**, and concluded the review was fabricated. Its caution was reasonable in form; its
conclusion was wrong, and the cause was the unmerged worktree, not a bad review.

**The Master has verified the disputed symbols directly on the integrated brief branch:**

```
storage/repository.py:43   _SEARCH_TSV_UPDATE_SQL = """
storage/repository.py:70   def backfill_search_tsv(session: Session, *, only_missing: bool = True) -> int:
storage/repository.py:95   def _refresh_search_tsv(session: Session, opportunity_id: str) -> None:
```

They were added by the full-text-search work order and merged. They are real. Merge first and you
will see them.

## The findings to fix

### Finding 6 — MAJOR. Pre-existing rows are invisible to search.

`storage/migrations/versions/0004_founder_control.py` adds `search_tsv` as a nullable column with
**no backfill**, and `backfill_search_tsv` has no caller outside `api/test_*.py`. Every
opportunity written before `0004` therefore has a NULL `search_tsv` and is **absent from every
full-text search result** — not an error, not an empty result, simply gone. That is the founder's
entire existing database.

Fix: in `upgrade()`, after the column and its GIN index are created, execute an
`UPDATE opportunities SET search_tsv = ... WHERE search_tsv IS NULL` built from the same document
body as `_SEARCH_TSV_UPDATE_SQL` in `storage/repository.py`. The council preferred this over
calling the Python helper from an entrypoint because it is transactional with the column add.

Test: insert a row at `0003`, `alembic upgrade head`, and assert the row is findable by search.

### Finding 5 — MAJOR. The backup round-trip test cannot fail.

`scripts/test_backup_restore.py::test_full_backup_and_restore_cycle` seeds **zero** rows in
`opportunity_families`, `founder_facets`, `founder_saved_views` and `artifact_cache`, and sets
none of the 17 new `opportunities` columns. With zero rows, `_check_dump_row_counts` passes
`0 == 0` whether or not the dump and restore loops are correct, and the base64 `payload` path and
the `datetime.fromisoformat` paths in the restore sections never execute. The test's own comment
explains why zero-row seeding is worthless for exactly this class of bug.

Fix: seed one row per new table — with a non-empty `payload` and real `created_at`/`updated_at` —
and one opportunity with **every** new column populated. After restore, assert row-for-row
equality for all five tables.

### Finding 7 — MINOR, consequential.

`storage/models.py` declares none of `0004`'s five indexes, so `compare_metadata` reports five
`remove_index` operations at head. Consequences: `storage/engine.py::init_db()`'s `create_all`
produces a schema **without the GIN index**, and `alembic revision --autogenerate` would propose
dropping all five.

Fix: declare `Index('ix_opportunities_search_tsv', 'search_tsv', postgresql_using='gin')` and
`index=True` on `work_mode`, `location_country`, `title_family`, `family_key`. Leave the
pre-existing `founder_notifications` / `reconciliation_records` nullable diffs alone.

### Finding 9 — MINOR.

`storage/repository.py` — `backfill_search_tsv` returns 0 and `_refresh_search_tsv` returns
silently on a non-PostgreSQL bind. The council checked this specifically against the FR-002
fail-closed invariant and confirmed it is **not** a violation: `storage/engine.py` still refuses
SQLite without the explicit opt-in, and `Text().with_variant(TSVECTOR(), "postgresql")` is a type
annotation introducing no fallback engine. It is nonetheless a fail-open skip.

Fix: raise, or at minimum log at WARNING, so a misconfigured bind is not invisible.

### Finding 10 — NIT.

`scripts/backup_restore.py`: `import base64` sits above `import argparse`, breaking the
alphabetical block. Move it.

## A consequence to state, not to solve

You are amending a migration that other worktrees have already applied. Every developer database
already at `0004` must be dropped and recreated. Say so in your return. The previous brief lost
time twice to an in-place amendment of `0003`, and this is written down so the next person meets
a note rather than a mystery.

## Allowed files

`storage/migrations/versions/0004_founder_control.py` · `storage/models.py` ·
`storage/repository.py` · `storage/test_postgres_integration.py` · `scripts/backup_restore.py` ·
`scripts/test_backup_restore.py`.

## Frozen — touching any of these is a FAIL

`storage/migrations/versions/0001|0002|0003` · any `0005+` revision · `truth/**` · `matching/**` ·
`opportunity/**` · `api/**` · `web/**` · `worker/**` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| A1B.1 | on an empty scratch DB: `alembic upgrade head`, `downgrade base`, `upgrade head` | 4 / 4 / 4, exit 0 each; head `0004_founder_control` |
| A1B.2 | the search-backfill test | a row inserted at `0003` is findable by search after `upgrade head` |
| A1B.3 | `py -3.12 -m unittest scripts.test_backup_restore -v` | `OK`; the cycle test now seeds >= 1 row in each new table and asserts row-for-row equality |
| A1B.4 | `py -3.12 -m unittest discover -s storage -p "test_*.py" -v` | `OK`, count stated |
| A1B.5 | `alembic check` or a `compare_metadata` run | **zero** `remove_index` operations at head |
| A1B.6 | `py -3.12 -m unittest discover -s api -p "test_*.py" -v` | `OK`, count stated |
| A1B.7 | `ls storage/migrations/versions/` | exactly one `0004_*`; no `0005` |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim.
