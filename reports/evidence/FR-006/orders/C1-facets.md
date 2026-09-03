# Work order C1 — Facets, saved views, and the hidden-reasons audit (API side)

**Brief:** BRIEF-FR-006 §2 Track C, nodes **C1 and C4**, plus the **B4** filter exercise.
**Wave:** 2/3. **Depends on:** A1, B3 (integrated).
**Worktree/branch:** `wt/fr006-c1` **Test DB:** `opportunityos_test_c1`

**First action:** `git merge --no-edit feat/brief-fr-006-nothing-missed` from your worktree root.

**Master's note on the merge:** C4's hidden-reasons audit is a query over the same filter/facet
state C1 owns, and B4 is an exercise of the same filters. Splitting them across worktrees would
have three agents editing `api/filters.py`. They are one order. Recorded as a deviation.

## The governing instruction

The founder, verbatim in spirit:

> *I can exclude something close that isn't right for me; I can't get back something suitable
> that was excluded before I saw it.*

Everything you build errs toward showing more. **Nothing hides by default except the founder's own
red lines and excluded industries.** A facet excludes only by founder action, and an excluded row
is always one click away.

## Deliverable text (verbatim from the brief)

> **C1 — Facets for everything.**
> - A generic facet engine replaces the fixed ten-filter table: every extracted attribute is a
>   facet with include/exclude lists and counts — `work_mode`, `location_country`,
>   `location_city`, `remote_scope`, `employment_type`, `seniority_level`, `title_family`,
>   `track`, `source_id`, `employer`, `posted_within`, `compensation_stated`, `decision`,
>   `fit_score` range, `language`, plus the existing ten. Each facet supports **include**,
>   **exclude**, and **off**; exclusions are visible as chips with counts; excluded items are
>   always one click away ("Show N excluded by Location").
> - Facet state persists server-side (`0004` replaces `founder_filter_settings` with
>   `founder_facets`), with **saved views** (named facet sets, e.g. "Remote data eng, EU/US, last
>   7 days") and a default view.
> - **Nothing hides by default except the founder's own red lines and excluded industries**,
>   unchanged from FR-005; hidden rows show *why* ("hidden by red line: gambling").
> - **Acceptance:** with every facet off, `include_hidden` total equals the row count; each
>   facet's include and exclude are tested through the API and one is exercised in Playwright; a
>   saved view round-trips.
>
> **C4 — Hidden-reasons audit.** The dashboard's HIDDEN number links to a table: reason -> count
> -> one-click "unhide all by this reason". Any facet or red line hiding more than 10% of new rows
> in a poll triggers a visible warning.
>
> **B4 — Exercise every filter against the founder-shaped pack.** `track_preference`,
> `premium_fulltime_onsite`, `stale_postings` must each show a non-zero affected count on the
> fixture corpus, or the report explains why zero is correct.

## Master's decisions — do not re-litigate these

1. **`founder_filter_settings` is NOT replaced.** The brief says `0004` replaces it; the Master
   has ruled otherwise and recorded the deviation. The ten policy filters carry a
   `hide` / `rank_only` / `label_only` vocabulary that facet `include` / `exclude` / `off` cannot
   express — including the Overseer's Appendix-5 decision that `target_roles` defaults to
   `rank_only`. Both tables exist. `/api/filters` survives unchanged in shape; `/api/facets` is new.
2. **Migration `0004_founder_control` already exists** (work order A1) with the
   `founder_facets` and `founder_saved_views` tables and every attribute column you need.
   **Do not write a migration.** A missing column is a scope question, not a `0005`.
3. **`stale_postings` was a guaranteed no-op in FR-005** — nothing in the codebase ever writes
   `is_stale = True`. B4 requires a non-zero affected count or an explanation of why zero is
   correct. Find out which it is and say so plainly; if the writer genuinely does not exist,
   that is a finding to report, and inventing a code path to make a count non-zero is out of
   scope for this order.

## Required behaviour

1. **`api/facets.py`** — a generic facet engine. Each facet declares: id, the attribute it reads,
   its value type (enum / string / range / date-window / boolean), and how counts are computed.
   Every attribute the brief lists is a facet. Adding a facet must be a declaration, not a new
   branch in a query builder.
2. **Modes `include` / `exclude` / `off`**, persisted in `founder_facets`, with counts returned
   for every value. Default for every facet is **`off`**.
3. **Excluded rows are never gone.** The response reports, per facet, how many rows that facet
   excluded, so the UI can render "Show N excluded by Location". `include_hidden=true` returns
   everything. **With every facet and filter off, the `include_hidden` total equals
   `SELECT count(*) FROM opportunities`** — this is claim A-18 and the verifier re-runs it.
4. **A facet never changes a `decision` or a `fit_score`.** Assert it: take a row, exclude it by
   every facet in turn, and confirm both values are byte-identical each time.
5. **Saved views** (`founder_saved_views`): create, read, update, delete, set-default; a view
   stores the facet set and the search query; round-trips through the database and survives a
   process restart (assert with a fresh session, not a cached object).
6. **Hidden-reasons audit** (C4): an endpoint returning reason -> count over the current window,
   where a reason names the specific cause (`red line: gambling`, `excluded industry: fraud`,
   `facet: location_country`), plus a one-click unhide-all-by-reason action. And a **warning
   signal** when any single facet or red line hides more than **10% of new rows in a poll** —
   computed from the poll's new-row count, with a test that constructs exactly that condition.
7. **B4 exercise**: run `track_preference`, `premium_fulltime_onsite` and `stale_postings`
   against the fixture corpus with the founder-shaped pack and **print each affected count**. For
   any that is zero, print the query and state why zero is the correct answer.
8. **Search integration seam**: work order C2 adds full-text search concurrently. Facets and
   search compose (results respect facets). Define the composition point and keep it small; the
   Master merges the two.

## Allowed files

`api/facets.py`, `api/saved_views.py` (new) · `api/filters.py` (the audit hooks and the affected
counts — **not** a rewrite of the ten filters' semantics) · `api/routes_api.py` ·
`api/serialization.py` · `api/settings.py` · `api/test_api.py` and new API tests ·
`storage/repository.py` and `storage/test_postgres_integration.py` (facets and saved views only) ·
`reports/evidence/FR-006/c1-facet-run.md`.

## Frozen — touching any of these is a FAIL

Any migration · `storage/models.py` (A1 already declared the tables) · `matching/**` ·
`truth/**` · `opportunity/**` · `web/**` (work order C3 owns the UI) · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| C1.1 | `py -3.12 -m unittest discover -s api -p "test_*.py" -v` | `OK`, count stated |
| C1.2 | the all-off equality test | `include_hidden` total **equals** `SELECT count(*) FROM opportunities`; both numbers printed |
| C1.3 | the per-facet include and exclude tests | **every** facet in the brief's list exercised in both directions — a table of facet id, include result count, exclude result count |
| C1.4 | the no-re-judgement test | `decision` and `fit_score` unchanged under every facet exclusion, asserted per facet |
| C1.5 | the defaults test | with a fresh database, the only rows hidden are red-line hits and excluded-industry hits; the counts are printed |
| C1.6 | the saved-view round-trip | create → restart session → read back identical; default view honoured |
| C1.7 | the hidden-reasons audit | reason → count table printed; unhide-all-by-reason changes the visible count and nothing else |
| C1.8 | the 10% warning test | a constructed poll where one facet hides >10% of new rows raises the warning; one at 9% does not |
| C1.9 | the B4 exercise | affected counts for `track_preference`, `premium_fulltime_onsite`, `stale_postings`, each printed with its query |
| C1.10 | `py -3.12 -m unittest discover -s storage -p "test_*.py" -v` | `OK` |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim. Report each B4 count as you found it.
