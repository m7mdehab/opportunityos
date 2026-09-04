# Work order A1S — The `target_roles` default revert, as a data migration

**Brief:** BRIEF-FR-006 §2 Track B node B3, second clause; Appendix decision 5.
**Wave:** 2. **Depends on:** A1M (integrated — `0004_founder_control` exists).
**Worktree/branch:** `wt/fr006-a1s` **Test DB:** `opportunityos_test_a1s`
**Turn budget:** 30. **Spend at most 5 turns reading. This is a small, precise change.**

**First action:** `git merge --no-edit feat/brief-fr-006-nothing-missed` from your worktree root.

## Why this order exists, and why it is a separate one

The brief's Appendix decision 5 reads, in full:

> 5. `target_roles` back to `rank_only`.

and §2 B3 states the mechanism:

> `target_roles` filter default reverts to `rank_only` (Overseer decision, FR-005 review §3.1)
> **via data migration**.

Background the implementer needs: during BRIEF-FR-005 a council review found the `target_roles`
filter demoting a high-fit opportunity below a low-fit one through substring matching, and the
FR-005 Master responded by shipping its default as `label_only`. The **Overseer reviewed that and
reversed it**, on the ground that `rank_only` is the Overseer's own decision and a Master may not
silently change it. This order carries out the Overseer's reversal.

`api/filters.py` already declares `default_mode = "rank_only"` (work order B3, integrated).
`storage/migrations/versions/0003_provenance_identity.py` carries a literal seed table
`_D3_FILTER_SEED` holding `label_only` for that filter, and `0003` is a **released revision that
is never edited**. So the seeded state and the declared default disagree, and a guard test in
`api/test_api.py` currently skips rather than passes because of it.

**This order exists as its own committed work order because the change was first routed to
work order A1M as a mid-task instruction, and A1M refused it as a suspected prompt injection.**
A1M's caution was reasonable in form — an instruction arriving mid-task that appears to reverse a
recorded safety decision is exactly what an agent should be suspicious of — and its refusal is
recorded as a non-defect in the report. The instruction is genuine, and the correct channel for a
genuine instruction is a committed work order, which is what you are reading.

**On the apparent contradiction:** A1M's order said "Do not drop or alter `founder_filter_settings`".
That prohibition is about the **table** — the brief asked for it to be *replaced* by `founder_facets`
and the Master ruled it must survive. Updating a **row's** value is not dropping or altering the
table. `founder_filter_settings` keeps its schema, its columns and its rows; one column value in
one row changes.

## Required behaviour

Add to `storage/migrations/versions/0004_founder_control.py`, after its existing schema changes:

1. **A module-level constant, with exactly this name:**

   ```python
   _D3_FILTER_SEED_OVERRIDES = {"target_roles": {"mode": "rank_only"}}
   ```

   The guard test in `api/test_api.py` composes `0003`'s `_D3_FILTER_SEED` with every later
   revision's `_D3_FILTER_SEED_OVERRIDES`. The name is a contract, not a preference; the guard
   skips today because it does not exist.

2. **In `upgrade()`**, after the schema work:
   `UPDATE founder_filter_settings SET mode = 'rank_only' WHERE filter_id = 'target_roles' AND mode = 'label_only'`

3. **In `downgrade()`**, before the schema teardown, the exact reverse:
   `UPDATE founder_filter_settings SET mode = 'label_only' WHERE filter_id = 'target_roles' AND mode = 'rank_only'`

Both guarded on the current value as written, so that re-running against an already-correct row is
a no-op and a downgrade does not clobber a mode the founder set by hand to something else.

4. **Do not** drop, rename, or alter the `founder_filter_settings` **table**, and do not touch
   `0003`. Do not change `api/filters.py` — its default is already `rank_only`.

## Allowed files

`storage/migrations/versions/0004_founder_control.py` · `storage/test_postgres_integration.py`
(a test for the data migration) · `api/test_api.py` (**only** if the guard test needs a fix to
stop skipping once the override constant exists — no other change to that file).

## Frozen — touching any of these is a FAIL

`storage/migrations/versions/0001|0002|0003` · any `0005+` revision · `storage/models.py` ·
`api/filters.py` · `matching/**` · `truth/**` · `opportunity/**` · `web/**` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| A1S.1 | on a scratch DB seeded through `0003`, then `alembic upgrade head`: `SELECT filter_id, mode FROM founder_filter_settings WHERE filter_id='target_roles'` | `rank_only`. Print the row. |
| A1S.2 | then `alembic downgrade -1` and the same SELECT | `label_only`. Print the row. |
| A1S.3 | `alembic upgrade head` twice in a row | second run is a no-op on the data; the row is still `rank_only`; exit 0 both times |
| A1S.4 | `py -3.12 -m unittest discover -s api -p "test_*.py" -v` | `OK`; the filter-seed guard test **passes** and no longer skips — quote its result line |
| A1S.5 | `py -3.12 -m unittest discover -s storage -p "test_*.py" -v` | `OK`, count stated |
| A1S.6 | `grep -n "_D3_FILTER_SEED_OVERRIDES" storage/migrations/versions/0004_founder_control.py` | the constant exists with exactly that name |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim.
