# C1 — Facets, saved views, hidden-reasons audit (API side): evidence run

Order: `reports/evidence/FR-006/orders/C1-facets.md`. Branch:
`worktree-agent-aade18a7eb841b9b4` (worktree-per-agent naming; functionally
`wt/fr006-c1`). Test DB: `opportunityos_test_c1`
(`postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_c1`).

## Files changed

- `api/facets.py` (new) — the generic facet engine (`FACET_DEFINITIONS`,
  `apply_facets`, `facet_payload`), C4's hidden-reasons audit
  (`hidden_reasons_audit`, `unhide_by_reason`), and the 10%-of-a-poll warning
  (`poll_hide_fraction_warnings`).
- `api/saved_views.py` (new) — saved-view CRUD + default, round-tripping
  through `founder_saved_views`.
- `api/filters.py` — added two audit hooks only (`matched_red_line_rule`,
  `matched_excluded_industry`); the ten filters' semantics are untouched.
- `api/routes_api.py` — wired `GET/PUT /api/facets[/…]`,
  `GET/POST/PUT/DELETE /api/saved-views[/…]`, `GET /api/hidden-reasons`,
  `POST /api/hidden-reasons/unhide`; composed facets into
  `GET /api/opportunities` (`facet:<id>` entries appended to `hidden_by`).
- `storage/repository.py` — thin `FounderFacetRecord`/`FounderSavedViewRecord`
  wrappers (`get_facet`, `list_facets`, `upsert_facet`, `list_saved_views`,
  `get_saved_view`, `get_default_saved_view`, `delete_saved_view`).
- `api/test_api.py` — new imports; `FacetsTest`, `PollHideFractionWarningTest`,
  `B4ExerciseTest`.

Frozen files (per order) were not touched: no migration, `storage/models.py`,
`matching/**`, `truth/**`, `opportunity/**`, `web/**`, `private/`.

## Assumptions named

1. **"Plus the existing ten" (brief deliverable text) is superseded by the
   Master's decision.** The ten founder-controlled filters (`api/filters.py`)
   are *not* turned into facets and keep their own
   hide/rank_only/label_only vocabulary; `FACET_DEFINITIONS` is exactly the
   15 attributes the brief names as facets (`work_mode` … `language`), not
   ten additional ones. `founder_filter_settings` and `founder_facets` remain
   two separate tables per the order's "Master's decisions" section.
2. **`founder_facets` schema is one row per `facet_id`, not per
   `(facet_id, value)`.** `values_json` stores
   `{"include": [...], "exclude": [...]}` for that facet as a whole; the
   top-level `mode` column is derived/informational (`"off"` when both lists
   are empty, `"active"` otherwise) — the real state lives in the two lists.
   This was the only schema-compatible reading of "each facet supports
   include/exclude/off" given the frozen `0004` migration (one row per
   `facet_id`, primary key `facet_id`).
3. **`language` facet is declared but unavailable.** No code path anywhere
   persists a posting's language: `opportunity/models.py::Opportunity.languages`
   exists on the in-memory dataclass but is never written to
   `OpportunityRecord` or `field_provenances`. `PUT /api/facets/language`
   returns 422 with the reason; `GET /api/facets` reports
   `available: false`. This mirrors the existing `stale_postings` council
   pattern in `api/filters.py` exactly, and is a genuine finding, not an
   invented code path.
4. **`GET /api/facets` counts are computed independent of other currently
   active facets** (only against the base set of policy-visible rows), and
   `excluded_count` is how many of those rows a facet's *own* current
   selection hides. This is a documented simplification of "proper" faceted
   cross-filtering (excluding every *other* active facet per facet, an O(n²)
   combinatorial computation) given the turn budget; still gives an accurate
   `excluded_count` for "Show N excluded by `<facet>`".
5. **Unhide-all-by-reason for `red line: X` / `excluded industry: X`
   disables the whole `red_lines` / `excluded_industries` filter**, not just
   rule `X` — the frozen `0004` schema has no per-rule override column. A
   `facet: X` reason clears that facet back to off (a precise, per-facet
   action). Documented limitation, not silently narrowed scope.
6. **"Current window" for the C4 hidden-reasons audit is "every row
   currently hidden"** (not a time-bounded poll window) — the brief's C4 text
   doesn't define a window and the dashboard's HIDDEN number it links from is
   itself not time-windowed.
7. **The C1.8 10%-warning is tested as a pure function**
   (`api.facets.poll_hide_fraction_warnings`) against constructed contexts,
   not through a live HTTP endpoint — no endpoint was wired for it given the
   turn budget; the order only requires "a test that constructs exactly that
   condition", which this satisfies directly and deterministically.
8. **B4 `track_preference` / `premium_fulltime_onsite` fixture corpus** was
   built directly in the new `B4ExerciseTest` (not reusing a separate fixture
   file) — a founder-shaped truth graph via the existing
   `_graph_with_founder_preferences` helper plus 7 synthetic opportunities.

## Acceptance rows — raw output

### C1.1 — `py -3.12 -m unittest discover -s api -p "test_*.py" -v`

```
Ran 70 tests in 72.403s
OK
```

### C1.2 — the all-off equality test

```
C1.2: include_hidden total=5  SELECT count(*) FROM opportunities=5
```

Both numbers equal (5 == 5), with every filter explicitly disabled and every
facet at its default (no `founder_facets` row → off).

### C1.3 — every facet's include and exclude, through the API

```
facet_id | include_result_count | exclude_result_count
work_mode | 1 | 1
location_country | 1 | 1
location_city | 1 | 1
remote_scope | 1 | 1
employment_type | 1 | 1
seniority_level | 1 | 1
title_family | 1 | 1
track | 1 | 1
source_id | 1 | 1
employer | 1 | 1
posted_within | 1 | 1
compensation_stated | 1 | 1
decision | 1 | 1
fit_score | 1 | 1
language | n/a (unavailable: No language is ever persisted for an opportunity: `opportunity/models.py`'s `Opportunity.languages` tuple exists on the in-memory model, but nothing in `opportunity/persistence.py`, `storage/models.py::OpportunityRecord`, or `field_provenances` writes it to storage. This facet is declared (the brief requires it in the list) but has no data source to bucket by until a future brief persists it -- exactly the council `availability` pattern `api/filters.py::stale_postings` already established for a no-op filter.)
```

Two fixture opportunities (`opp-a`, `opp-b`) with disjoint attribute values
per facet; `include=[value_a]` and, separately, `exclude=[value_b]` each
narrow the default view to exactly the 1 matching opportunity (2 total minus
1 excluded row = 1 visible). `language` correctly refuses the PUT (422)
instead of silently accepting a selection with no data source.

### C1.4 — the no-re-judgement test

```
C1.4: decision='qualified' fit_score=88.0 unchanged across 14 facet exclusions
```

`opp-target` was excluded, one facet at a time, by all 14 available facets;
`decision` and `fit_score` were byte-identical (`'qualified'` / `88.0`) after
every single exclusion, asserted per facet inside the loop.

### C1.5 — the defaults test

```
C1.5: hidden_ids=['opp-industry', 'opp-redline'] hidden_count=2
```

Fresh database (every filter/facet at its migration-seeded default); of three
opportunities (`opp-redline` matching the red line, `opp-industry` matching
the excluded industry, `opp-clean` matching neither), exactly the two
red-line/excluded-industry rows are hidden.

### C1.6 — the saved-view round-trip

```
C1.6: saved view 'view-b4697be81c2342c9' round-tripped through a fresh session; is_default=True
```

Created via `POST /api/saved-views` (`is_default=True`); read back through a
brand-new `session_factory()` session (not `self.session`, not a cached
Python object) — `name`, `facets`, `search_query`, `is_default` all matched
the created payload; `GET /api/saved-views` also reported it as the sole,
default view.

### C1.7 — the hidden-reasons audit

```
reason | count
excluded industry: Gambling | 1
facet: work_mode | 1
red line: Never imply guaranteed employment outcomes. | 1
C1.7: unhide-all-by-reason('facet: work_mode') changed visible set from ['opp-clean'] to ['opp-clean', 'opp-facet-hidden']
```

`POST /api/hidden-reasons/unhide {"reason": "facet: work_mode"}` made exactly
`opp-facet-hidden` visible again and left `opp-redline`/`opp-industry` (hidden
by different reasons) untouched.

### C1.8 — the 10% warning test

```
C1.8 (>10% case): 2/10 onsite hidden by facet:work_mode -> warnings=[{'cause': 'facet: work_mode', 'hidden': 2, 'of': 10, 'fraction': 0.2}]
C1.8 (9% case): 9/100 onsite hidden by facet:work_mode -> warnings=[]
```

2/10 (20%, > 10%) raises the warning; 9/100 (exactly 9%) does not.

### C1.9 — the B4 exercise

```
B4 track_preference affected_count=2 (query: opp.track.casefold() != founder's preferred track 'employment', over 7 rows -- api/filters.py::_track_preference_matches)
B4 premium_fulltime_onsite affected_count=1 (query: compensation_fit dimension's signal_tags contains 'premium_shortfall', over 7 rows -- api/filters.py::_premium_fulltime_onsite_matches)
B4 stale_postings affected_count=0 (query: SELECT count(*) FROM opportunities WHERE is_stale = true -> 0; zero is correct -- nothing in opportunity/persistence.py or any worker handler ever writes is_stale=True; see api/filters.py::_STALE_POSTINGS_UNAVAILABLE_REASON)
```

`track_preference` (2) and `premium_fulltime_onsite` (1) are genuinely
non-zero on this fixture corpus. `stale_postings` is genuinely zero: the raw
`SELECT count(*) FROM opportunities WHERE is_stale = true` over the same
corpus is also `0`, confirmed by direct SQL query in the test, and
`api/filters.py::_STALE_POSTINGS_UNAVAILABLE_REASON` documents that no writer
in this codebase ever sets `is_stale = True` (`opportunity/persistence.py`
always writes `False`; `opportunity/reverification.py`'s results are computed
but never persisted by any worker). This order made no code-path change to
alter that — it is a finding, not a defect of this order.

### C1.10 — `py -3.12 -m unittest discover -s storage -p "test_*.py" -v`

```
Ran 40 tests in 30.313s
FAILED (errors=1)
```

The one failure,
`test_postgres_integration.PostgresProductionIntegrationTest.test_case_v_evaluate_new_persists_match_evaluations`,
is **pre-existing and unrelated to this order**:

```
TypeError: Opportunity.__init__() got an unexpected keyword argument 'remote_policy'
  File "worker/handlers.py", line 492, in _reconstruct_opportunity
    return Opportunity(
```

Verified by `git stash`-ing every C1 file (`api/facets.py`, `api/saved_views.py`,
and the diffs to `api/filters.py`, `api/routes_api.py`, `api/test_api.py`,
`storage/repository.py`) and re-running the same test in isolation against
the unmodified merge-base tree: it fails identically. `worker/handlers.py` and
`opportunity/models.py` are both frozen for this order (not in the allowed
files list) — the defect is in the interaction between A1's `Opportunity`
model and `worker/handlers.py::_reconstruct_opportunity`'s still-old
`remote_policy` keyword, upstream of and untouched by this order. Reported
here rather than fixed, per the order's frozen-files rule.
