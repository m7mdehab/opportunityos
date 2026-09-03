# C2 — Search: evidence run

Work order: `reports/evidence/FR-006/orders/C2-search.md`. Test DB:
`opportunityos_test_c2` (`postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_c2`).
`py -3.12`, PostgreSQL 16.10.

## tsquery function used

`websearch_to_tsquery` (`api/search.py`), not `phraseto_tsquery`. Its input
grammar already is the brief's query language (bare terms -> implicit AND,
`"..."` -> phrase, leading `-` -> negation including on phrases), and unlike
`to_tsquery` it never raises a syntax error on malformed input -- see
`api/search.py` module docstring.

## Ranking formula

`rank_key(relevance, fit_score) = relevance * fit_component`, where
`relevance = ts_rank(search_tsv, websearch_to_tsquery(...))` and
`fit_component = fit_score/100` clamped to `[0,100]`, or `0.5` when
`fit_score is None` (no evaluation yet). Pure function, `api/search.py`.
Applied only when a search (`q`) is active; without `q`, sort order is
unchanged from before this work order.

## search_tsv population

Application-side, inside `StorageRepository.save_opportunity`
(`storage/repository.py::_refresh_search_tsv`), not a trigger or generated
column: migration `0004_founder_control` (frozen for this order) already
added `search_tsv` as a plain nullable `TSVECTOR` column, not
`GENERATED ALWAYS AS (...) STORED`, and adding a trigger outside a migration
would not be reproducible. `save_opportunity` is the only method that writes
an `OpportunityRecord`, so every insert/update path is covered.
`storage.repository.backfill_search_tsv` is the idempotent batch path for
rows written before this code existed (`only_missing=True` default; a
second run touches 0 rows). Document: `title`, `organization`, `description`,
`location_country`/`location_city`/`location_region` (no single `location`
column exists), and `requirements` via a correlated subquery over
`field_provenances` (currently always empty -- no adapter populates a
`requirements` field; named as an assumption below).

## C2.1 — narrow test suites

`py -3.12 -m unittest discover -s api -p "test_*.py" -v`:
```
Ran 81 tests in 58.416s

OK (skipped=1)
```
(the 1 skip is `SearchPerformanceTest`, guarded on
`OPPORTUNITYOS_RUN_SEARCH_PERF=1` -- see C2.5.)

`py -3.12 -m unittest discover -s storage -p "test_*.py" -v`:
```
Ran 41 tests in 21.334s

FAILED (errors=1)
```
The 1 error is **unrelated to search**:
`test_case_v_evaluate_new_persists_match_evaluations` ->
`TypeError: Opportunity.__init__() got an unexpected keyword argument
'remote_policy'` in `worker/handlers.py::_reconstruct_opportunity`. Neither
file is touched by this work order (both are outside the allowed-files
list); `git log --oneline -1 -- worker/handlers.py` attributes it to commit
`386905b feat(worker): add reextract_all backfill handler for A1M
founder-control columns`, a different, already-merged work order.

## C2.2 — `pytorch -"customer engineer"`

`opportunity/fixtures/corpus/` is **absent** on this worktree's base (the
A1C work order committing it had not landed here). Ran against **synthetic
rows**, not the real corpus -- printed explicitly by the test:
```
C2.2: opportunity/fixtures/corpus/ is ABSENT on this worktree's base -- running against SYNTHETIC rows of the same shape, NOT the real fixture corpus. The Master must re-run this row over the real corpus at integration.
C2.2: result count = 2
C2.2: inspected id='opp-pytorch-1' title='ML Engineer' contains_pytorch=True
C2.2: inspected id='opp-pytorch-2' title='Research Scientist' contains_pytorch=True
```
Both returned rows were inspected and contain `pytorch`; zero returned rows
are titled Customer Engineer (a seeded `Customer Engineer` row that also
mentions pytorch, and a plain `Customer Engineer` row, are both correctly
excluded by the negated phrase). **This is a different result than a run
over the real 540-row corpus would produce and must be re-run there at
integration.**

## C2.3 — index present after `alembic upgrade head`

```
C2.3: pg_indexes for opportunities = ['ix_opportunities_content_hash', 'ix_opportunities_family_key', 'ix_opportunities_location_country', 'ix_opportunities_organization', 'ix_opportunities_search_tsv', 'ix_opportunities_source_id', 'ix_opportunities_title_family', 'ix_opportunities_track', 'ix_opportunities_work_mode', 'opportunities_pkey']
```
`ix_opportunities_search_tsv` present. (`storage/test_postgres_integration.py::PostgresProductionIntegrationTest::test_search_tsv_gin_index_exists_at_head`.)

## C2.4 — adversarial inputs, never a 500

```
C2.4 empty-query -> status=200 items=1 message=None
C2.4 lone-dash -> status=200 items=0 message='search query has no searchable terms'
C2.4 operator-characters -> status=200 items=0 message=None
C2.4 unbalanced-quote -> status=200 items=0 message=None
C2.4 very-long-query (16000 chars) -> status=200 items=1 message=None
```
Every case returns 200 with a list (empty or not); never 500.

## C2.5 — 20k-row timing run

`OPPORTUNITYOS_RUN_SEARCH_PERF=1 py -3.12 -m unittest api.test_search_performance -v`:
```
Ran 1 test in 15.239s

OK
C2.5: inserted 20000 rows in 6.44s; backfill_search_tsv indexed 20000 rows in 5.47s
C2.5: row_count=20000
C2.5: query_set=['pytorch', '"customer engineer"', 'pytorch -"customer engineer"', 'engineer -customer', 'python OR golang']
C2.5: sample_size=100 (queries x 20 reps each)
C2.5: p95=23.73ms
C2.5: p95 23.73ms < 200ms target
```
Row count measured over: **20,000**. Sample size: **100** (5 queries x 20
reps each). **p95 = 23.73ms** (< 200ms target). Local Windows PostgreSQL,
per the order's own caveat, is not a performance reference; this is what was
measured, honestly, not tuned.

## C2.6 — facet composition

```
C2.6: intersection ids=['opp-keep'] hidden_count=1
```
`api/facets.py` (concurrent work order C1) had not landed on this branch's
base at the time this order ran, so this composes with the founder-control
exclusion mechanism that does exist today, `api/filters.py`'s
`apply_filters`/`founder_filter_settings` (the `min_fit_score` filter,
`mode="hide"`). Search (`pytorch`) intersected with an active hide filter
returns only the row matching both; the excluded-but-search-matching row is
still counted in `hidden_count` (1) and surfaced via `include_hidden=True`
with `"min_fit_score"` in its `hidden_by`.

## C2.7 — no re-judgement

```
C2.7: decision/fit_score byte-identical before/after search: {'opp-x': ('qualified', 77.25), 'opp-y': ('uncertain', 12.5)}
```
`match_evaluations.qualification_decision`/`fit_score` read directly from
the database before and after a search request: identical. `rank_key`
(`api/search.py`) is a pure function over `(relevance, fit_score)`; it
returns a sort key only and writes nothing.

## C2.8 — backfill visibility

```
C2.8: backfill_search_tsv touched 1 row(s)
```
A row inserted directly via the ORM (bypassing `StorageRepository.
save_opportunity`, so `search_tsv` starts `NULL`) is confirmed absent from
search results, then found after `backfill_search_tsv` runs
(`api/test_search.py::BackfillVisibilityTest`). A second backfill run
touches 0 rows (idempotent).

## Files changed

- `api/search.py` (new) — query execution (`websearch_to_tsquery`), ranking formula.
- `api/routes_api.py` — `q` parameter now full-text search + ranking; response gains a `message` field.
- `api/test_api.py` — `seed_opportunity` now backfills `search_tsv` after seeding (see below).
- `api/test_search.py` (new) — C2.2, C2.4, C2.6, C2.7, C2.8, `rank_key` unit tests, `is_query_unparseable` unit tests.
- `api/test_search_performance.py` (new) — C2.5.
- `storage/repository.py` — `_refresh_search_tsv`, `backfill_search_tsv`, called from `save_opportunity`.
- `storage/test_postgres_integration.py` — C2.3 index test; one existing assertion updated (see below).

## Existing tests replaced

- **`api/routes_api.py`'s old `q` behaviour** (title/organization `ilike`):
  no existing test in `api/test_api.py` covered it (grepped for `q=`/`ilike`
  usage before starting: zero hits) — there was nothing to replace, only to
  add.
- **`storage/test_postgres_integration.py::A1MFounderControlRoundTripTest::
  test_every_nullable_new_column_round_trips_with_null`**: previously
  asserted `fetched.search_tsv is None` (correct at A1M time, before
  anything populated the column). Now asserts `fetched.search_tsv is not
  None`, since C2's whole job is to populate it on every
  `save_opportunity` call and the fixture opportunity has real
  title/organization/description text.

## Assumptions named

1. **No `requirements` column exists on `opportunities`**, and no adapter
   currently writes a `requirements` `field_provenances` row (grepped
   `opportunity/**`: zero hits). `search_tsv`'s document includes a
   correlated subquery over `field_provenances` for `field_name =
   'requirements'` so a future adapter that does populate it becomes
   searchable with no further change, but today that subquery is always
   empty.
2. **No single `location` column exists**; `location_country`,
   `location_city`, `location_region` are concatenated instead to satisfy
   "location" in the document definition.
3. **`api/facets.py`/`api/saved_views.py` (work order C1) had not landed on
   this branch's base.** "Facet composition" (C2.6) is implemented against
   `api/filters.py`'s existing founder-control exclusion mechanism instead,
   the closest analogue present today. Search does not write into
   `founder_saved_views.search_query` (C1's table, already has the column
   per migration `0004`) because `api/saved_views.py` does not exist yet to
   compose through additively; `api.search.search_opportunity_ids`/
   `is_query_unparseable` are the composition point the Master or C1 can
   call once it lands.
4. **`opportunity/fixtures/corpus/` was absent** on this worktree's base;
   C2.2 ran against synthetic rows of the same shape, explicitly flagged in
   test output and here. Must be re-run over the real corpus at
   integration.
5. Ranking formula's neutral fit multiplier for an unevaluated opportunity
   (no `match_evaluations` row) is **0.5**, chosen so it is neither buried
   (0) nor privileged above every evaluated match (1).
6. `search_tsv` population is **application-side** (in
   `StorageRepository.save_opportunity`), not a trigger or generated
   column, because migration `0004` (frozen) already defined the column as
   plain nullable `TSVECTOR`, and a trigger created outside a migration
   would not be reproducible across environments.

## Known non-search failure (unrelated, not fixed)

`storage.test_postgres_integration.PostgresProductionIntegrationTest::
test_case_v_evaluate_new_persists_match_evaluations` fails with
`TypeError: Opportunity.__init__() got an unexpected keyword argument
'remote_policy'` in `worker/handlers.py::_reconstruct_opportunity`
(commit `386905b`, a different work order, `opportunity/**` and
`worker/**` both outside this order's allowed files). Reported, not fixed,
per the coordinator's instruction to attribute rather than repair
concurrent work.

## Environment instability observed (not code-caused)

The shared local PostgreSQL instance (multiple concurrent worktree agents
on the same server) had `opportunityos_test_c2` disappear mid-suite twice
during this run (`FATAL: database "opportunityos_test_c2" does not exist` /
`server closed the connection unexpectedly`), consistent with another
agent's dev-environment reset script running against the same server, not
with anything this work order's code does. Recreating the database and
re-running produced the results recorded above.
