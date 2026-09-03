# Work order C2 — Full-text search

**Brief:** BRIEF-FR-006 §2 Track C. **Wave:** 3. **Depends on:** A1 (integrated).
**Worktree/branch:** `wt/fr006-c2` **Test DB:** `opportunityos_test_c2`

**First action:** `git merge --no-edit feat/brief-fr-006-nothing-missed` from your worktree root.

## Why this exists

Search today matches title and organization only (`api/routes_api.py`, the `q` parameter on
`GET /opportunities`). The founder cannot find "the pytorch one" or exclude the twenty customer
engineer cards by typing.

## Deliverable text (verbatim from the brief)

> **C2 — Search.**
> - Full-text search over title, employer, description, requirements, and location with
>   PostgreSQL `tsvector` (GIN index, `0004`), phrase and negative terms
>   (`"data engineer" -customer`), ranked by relevance × fit; results respect facets; search terms
>   can be saved into a view.
> - **Acceptance:** searching `pytorch -"customer engineer"` on the fixture corpus returns only
>   rows whose text contains pytorch and none titled Customer Engineer; index built in migration;
>   p95 query < 200 ms on 20k rows locally.

## Facts established by the Master — do not re-derive

- **Migration `0004_founder_control` already exists** (work order A1) and already contains the
  `search_tsv` TSVECTOR column on `opportunities` and the GIN index
  `ix_opportunities_search_tsv`. **Do not write a migration.** A missing piece is a scope
  question, not a `0005`.
- PostgreSQL is 16.10. `websearch_to_tsquery` and `phraseto_tsquery` are both available; use
  them rather than hand-rolling a parser, and say which you used.
- Work order C1 is concurrently building the facet engine in `api/facets.py` and
  `api/saved_views.py`. Search must **compose** with facets, not bypass them. Keep the
  composition point to a single function the Master can merge; do not restructure C1's code.
- The existing `q` parameter's behaviour is what you are replacing. Its tests in `api/test_api.py`
  encode title/organization-only matching; replacing them is authorised and each replacement is
  named in your return.

## Required behaviour

1. **`search_tsv` populated** from title, employer/organization, description, requirements and
   location — on insert and on update, and backfilled for existing rows by an idempotent batch.
   Say explicitly whether population is a trigger, a generated column, or application-side, and
   why. Whichever it is, a row written by any path must end up indexed: a search that silently
   misses rows written by the backfill job is the failure mode here.
2. **Query language**: bare terms (AND), quoted phrases, and negative terms with a leading `-`,
   including negated phrases (`-"customer engineer"`). Unparseable input returns an empty result
   with a message, never a 500. Test the adversarial inputs: unbalanced quotes, a lone `-`, an
   empty query, a very long query, and characters that are `tsquery` operators.
3. **Ranking**: relevance × fit. State the exact formula in a comment and in your return. Ranking
   must **never** change a row's `decision` or `fit_score` — assert it.
4. **Facet composition**: results respect the active facets. A search plus an exclusion facet
   returns the intersection, and the excluded count is still reported so the row is one click away.
5. **Saved views** carry the search query (C1 owns the table; you write the field through C1's
   interface — coordinate by keeping your change additive).
6. **The performance claim**: synthesise **>= 20,000 rows**, run a representative query set, and
   print the sample size, the query set, and the **p95** figure. If p95 exceeds 200 ms, report the
   number you measured. A local Windows PostgreSQL is not a performance reference and an honest
   miss is a better outcome than a tuned benchmark.

## Allowed files

`api/search.py` (new) · `api/routes_api.py` (the `q` parameter and the search route only) ·
`api/serialization.py` (search-result fields only) · `api/test_api.py` and new search tests ·
`storage/repository.py` and `storage/test_postgres_integration.py` (the tsvector population and
backfill only) · `reports/evidence/FR-006/c2-search-run.md`.

## Frozen — touching any of these is a FAIL

Any migration · `storage/models.py` · `api/facets.py`, `api/saved_views.py`, `api/filters.py`
(work order C1 owns them this wave — additive composition only, and if you cannot avoid editing
them, stop and report it) · `matching/**` · `truth/**` · `opportunity/**` · `web/**` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| C2.1 | `py -3.12 -m unittest discover -s api -p "test_*.py" and py -3.12 -m unittest discover -s storage -p "test_*.py" -v` | `OK`, counts stated |
| C2.2 | `pytorch -"customer engineer"` over the fixture corpus | result count printed; **every** returned row inspected and shown to contain `pytorch`; **zero** returned rows titled Customer Engineer |
| C2.3 | `SELECT indexname FROM pg_indexes WHERE tablename='opportunities'` after `alembic upgrade head` | `ix_opportunities_search_tsv` present |
| C2.4 | the adversarial-input tests | unbalanced quote, lone `-`, empty, very long, and operator characters each return a result or an empty set — **never** a 500 |
| C2.5 | the 20k timing run | sample size, query set, and **p95** printed |
| C2.6 | the facet composition test | search ∩ facet exclusion returns the intersection; the excluded count is still reported |
| C2.7 | the no-re-judgement test | ranking changes order only; `decision` and `fit_score` byte-identical |
| C2.8 | the backfill-visibility test | a row written by the backfill path is findable by search |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim. Name every existing test you replaced
and what it used to assert.
