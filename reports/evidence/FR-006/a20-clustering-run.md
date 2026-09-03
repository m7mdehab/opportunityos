# A2 evidence — near-duplicate clustering into families

Work order: `reports/evidence/FR-006/orders/A2-cluster.md`. Worktree branch:
`worktree-agent-af8faf3e1a167aeb8` (this worktree). Test DB:
`opportunityos_test_a2`.

## Corpus status (read first)

**No real `opportunity/fixtures/corpus/` set was present on this branch when
A2.3/A2.4 were run.** `git merge --no-edit feat/brief-fr-006-nothing-missed`
was run first, per the work order, and it did bring in `matching/title_family.py`
and migration `0004_founder_control`, but `ls opportunity/fixtures/corpus`
returns "No such file or directory" as of this run — the 540-payload corpus
(40 Cloudflare Greenhouse postings, 7 matching "customer engineer") had not
landed on this base at the time these acceptance rows were executed. Per the
work order's own instruction ("Build clustering and its unit tests against
fixtures you construct yourself... say clearly in your return whether a real
corpus was present"), A2.3 and A2.4 below run against a **24-posting
hand-built fixture corpus** defined in `opportunity/test_clustering.py`
(`_build_full_corpus`), not the real Cloudflare set. This hand-built corpus
reproduces the reported defect by construction: 14 "Senior Customer Engineer"
postings at Cloudflare differing only by location, plus distinct-employer,
distinct-title-family, distinct-seniority-level, "other"-bucket, and
singleton postings that must never be folded into that family. **A family
count of 14 from this fixture is a different number from whatever the real
40-posting/7-"customer engineer" Cloudflare set would produce** (the work
order's own note says 7 postings match "customer engineer" in the real
corpus, not the 14 built by hand here) — this report states the hand-built
number, not the real-corpus number, because the real corpus was not
available to run against.

`opportunity/clustering.py`'s `check_family_invariants` and `cluster_members`
are corpus-agnostic (pure functions of whatever `Opportunity`/`FamilyMember`
iterable is passed in), so once the real corpus lands, the same functions
exercised in `TestCorpusWideReport` can be pointed at it with no code change
— only the fixture-loading in the test needs to change.

## Title normalizer in effect

`matching.title_family.normalize_title` (work order B3) **was** on this base
after the merge and is what actually produced every number below —
confirmed via `opportunity.clustering.TITLE_NORMALIZER_SOURCE ==
"matching.title_family.normalize_title"` (printed in the A2.3 output below).
The same-signature fallback normalizer defined in `opportunity/clustering.py`
(`_fallback_normalize_title`) exists only for the case where B3 is absent
from a base and was not exercised for any of these numbers.

## Files changed

- `opportunity/clustering.py` (new) — `family_key`, `compute_family_key`,
  `normalized_title_key`, `FamilyMember`, `Family`, `cluster_members`,
  `cluster_opportunities`, `check_family_invariants`.
- `opportunity/test_clustering.py` (new) — 21 unit tests, including the
  A2.3/A2.4/A2.5/A2.7 printable evidence tests, against a hand-built corpus.
- `opportunity/persistence.py` — `_build_opp_data` now writes
  `family_key: compute_opportunity_family_key(opp)` (only field touched).
- `opportunity/test_persistence.py` — two new tests: the persisted record
  carries the deterministic family key, and it is unchanged (idempotent) on
  a re-run.
- `storage/repository.py` — `upsert_family`, `get_family`, `list_families`,
  `set_family_split_out` on `StorageRepository` (families table only).
- `storage/test_postgres_integration.py` — `test_case_t_family_upsert_and_split_out_round_trip`
  on `A1MFounderControlRoundTripTest` (A2.6), plus the
  `OpportunityFamilyRecord` top-level import it needs.
- `worker/handlers.py` — `backfill_family_keys` + `make_backfill_family_keys_handler`,
  registered as job type `"backfill_family_keys"` in `default_handler_registry`
  (a backfill handler only; `_reconstruct_opportunity` and every other
  existing handler are untouched).

## Assumptions named

1. **"Normalized title" = title family id + seniority level, not family id
   alone.** `matching.title_family.normalize_title` returns
   `(family_id, level, matched_rule)` as three separate values. This module's
   `normalized_title_key(title)` combines `family_id` and `level` into one
   key (`f"{family_id}:{level}"`) because two postings for the same title
   family but a different seniority word ("Customer Engineer" vs. "Senior
   Customer Engineer") are a real distinction the founder should see, not a
   location/team variant of one another — only location and team suffixes
   collapse, per the work order's deliverable text.
2. **The "other" bucket needs extra key material.** `normalize_title` maps
   any unmatched title to `family_id == "other"`. Two unrelated titles that
   both fail to match a known family would otherwise collide under
   assumption 1 alone (same `"other"` id, maybe same level). So for
   `family_id == "other"` only, `normalized_title_key` additionally folds in
   the location/team-suffix-stripped title text itself
   (`_strip_location_team_suffix`), keeping the same collapse behaviour
   (location suffixes still stripped) without merging unrelated unmatched
   titles. This never applies to a matched family, so it can only make
   clustering more conservative (fewer merges), never cause a false
   employer/title merge.
3. **Location/team-suffix stripping heuristic.** `_strip_location_team_suffix`
   splits a raw title on a hyphen/en-dash/em-dash *surrounded by whitespace*,
   a comma, an opening parenthesis, a pipe, or a slash, keeping only the text
   before the first such delimiter. Deliberately conservative about hyphens
   (only " - " with surrounding spaces, not bare "-") so hyphenated compound
   words like "Full-Stack Engineer" are never split. Used only as
   assumption-2's "other"-bucket key material, never overriding a matched
   family's own id.
4. **`family_key` output length.** `compute_family_key` returns a full
   64-hex-character SHA-256 digest (not truncated), matching
   `OpportunityFamilyRecord.family_key` / `OpportunityRecord.family_key`
   (`Column(String(64))` in `storage/models.py`) exactly.
5. **Best-fit selection tie-break.** `_select_best` orders by
   `(has_no_fit_score, -fit_score, opportunity.id)` — highest `fit_score`
   wins; a member with no evaluation yet is deprioritized behind any
   evaluated sibling (never selected as best over an evaluated one); ties
   break on `opportunity.id` ascending, so the result is fully independent
   of input order (asserted in `test_best_fit_selection_is_deterministic_regardless_of_input_order`).
6. **`upsert_family` preserves `split_out` across a re-cluster.** Re-running
   clustering after new postings arrive for an existing family updates
   `employer`/`normalized_title`/`member_count`/`best_member_id` but never
   resets `split_out` to its column default — a founder's earlier "show
   separately" choice for that family must survive a re-cluster. Asserted in
   A2.6 (`test_case_t_family_upsert_and_split_out_round_trip`).
7. **Backfill needs no extractor.** Unlike `reextract_all` (which
   re-derives founder-control columns from `raw_payload_json` via an
   injectable extractor), `backfill_family_keys` computes `family_key`
   directly from `OpportunityRecord.organization`/`.title` — both already
   stored with full fidelity — so it takes no `extractor` argument and has
   no "extractor unavailable" no-op branch.

## Acceptance rows

### A2.1 — `py -3.12 -m unittest opportunity.test_clustering -v`

```
test_a2_3_family_report_over_hand_built_corpus (opportunity.test_clustering.TestCorpusWideReport.test_a2_3_family_report_over_hand_built_corpus) ... ok
test_a2_4_whole_corpus_invariant_check (opportunity.test_clustering.TestCorpusWideReport.test_a2_4_whole_corpus_invariant_check) ... ok
test_best_fit_selection_is_deterministic_regardless_of_input_order (opportunity.test_clustering.TestFamilyCard.test_best_fit_selection_is_deterministic_regardless_of_input_order) ... ok
test_family_carries_best_fit_members_score_not_average (opportunity.test_clustering.TestFamilyCard.test_family_carries_best_fit_members_score_not_average) ... ok
test_family_carries_location_list_and_member_count (opportunity.test_clustering.TestFamilyCard.test_family_carries_location_list_and_member_count) ... ok
test_compute_family_key_matches_family_key (opportunity.test_clustering.TestFamilyKeyDeterminism.test_compute_family_key_matches_family_key) ... ok
test_location_variation_does_not_change_key (opportunity.test_clustering.TestFamilyKeyDeterminism.test_location_variation_does_not_change_key) ... ok
test_recompute_over_corpus_twice_is_identical (opportunity.test_clustering.TestFamilyKeyDeterminism.test_recompute_over_corpus_twice_is_identical)
A2.5 determinism check: keys recomputed over the corpus twice are ... ok
test_same_opportunity_same_key (opportunity.test_clustering.TestFamilyKeyDeterminism.test_same_opportunity_same_key) ... ok
test_cloudflare_customer_engineer_set_is_one_family (opportunity.test_clustering.TestFamilyMembershipRules.test_cloudflare_customer_engineer_set_is_one_family) ... ok
test_different_employer_same_title_text_is_separate_family (opportunity.test_clustering.TestFamilyMembershipRules.test_different_employer_same_title_text_is_separate_family) ... ok
test_different_seniority_level_is_separate_family (opportunity.test_clustering.TestFamilyMembershipRules.test_different_seniority_level_is_separate_family) ... ok
test_other_bucket_distinct_titles_do_not_collide (opportunity.test_clustering.TestFamilyMembershipRules.test_other_bucket_distinct_titles_do_not_collide) ... ok
test_singleton_is_family_of_one_and_behaves_like_plain_card (opportunity.test_clustering.TestFamilyMembershipRules.test_singleton_is_family_of_one_and_behaves_like_plain_card) ... ok
test_zero_families_span_two_employers (opportunity.test_clustering.TestFamilyMembershipRules.test_zero_families_span_two_employers) ... ok
test_zero_families_span_two_normalized_titles (opportunity.test_clustering.TestFamilyMembershipRules.test_zero_families_span_two_normalized_titles) ... ok
test_clustering_never_changes_any_members_decision_or_fit_score (opportunity.test_clustering.TestNeverMergeAcrossDecisions.test_clustering_never_changes_any_members_decision_or_fit_score)
A2.7 no-re-judgement test: no member's decision or fit_score ... ok
test_ineligible_member_status_is_flagged_not_hidden (opportunity.test_clustering.TestNeverMergeAcrossDecisions.test_ineligible_member_status_is_flagged_not_hidden)
A family must never hide an ineligible member's status behind a ... ok
test_no_flag_when_all_members_share_one_decision (opportunity.test_clustering.TestNeverMergeAcrossDecisions.test_no_flag_when_all_members_share_one_decision) ... ok
test_level_word_changes_the_key (opportunity.test_clustering.TestNormalizedTitleKey.test_level_word_changes_the_key) ... ok
test_pure_function_of_title_text (opportunity.test_clustering.TestNormalizedTitleKey.test_pure_function_of_title_text) ... ok

----------------------------------------------------------------------
Ran 21 tests in 0.185s

OK

A2.3 corpus run: 24 postings -> 9 families (title normalizer: matching.title_family.normalize_title)
  family_key=17aa6ae61112... employer='Cloudflare' normalized_title='customer_solutions_engineering:staff' member_count=1
  family_key=1a33552659f3... employer='Cloudflare' normalized_title='other:unspecified:quantum flux herder' member_count=1
  family_key=1f761c0d5fb4... employer='Cloudflare' normalized_title='backend:senior' member_count=2
  family_key=5416d97cc257... employer='Cloudflare' normalized_title='customer_solutions_engineering:senior' member_count=14
  family_key=60354e531af1... employer='Nimbus Data' normalized_title='data_engineering:unspecified' member_count=1
  family_key=8741286d547c... employer='Acme Corp' normalized_title='customer_solutions_engineering:senior' member_count=1
  family_key=aec95779e6af... employer='Cloudflare' normalized_title='other:unspecified:zorbatron wrangler' member_count=1
  family_key=d939a4c23029... employer='Cloudflare' normalized_title='customer_solutions_engineering:unspecified' member_count=2
  family_key=f221ee77fe8a... employer='Acme Corp' normalized_title='product:unspecified' member_count=1
A2.3 result: the Cloudflare 'Senior Customer Engineer' set collapsed to ONE family with member_count=14

A2.4 whole-corpus invariant check: 24 postings, 9 families, cross_employer_violations=0, cross_title_violations=0
A2.5 determinism: 24 keys compared, identical=True
A2.7 no-re-judgement: 3 members compared before/after clustering, all decision/fit_score pairs unchanged=True
```

**Result: `Ran 21 tests in 0.185s` / `OK`** (>= 15 required).

- **A2.3**: the Cloudflare "Senior Customer Engineer" family (hand-built
  corpus, `family_key=5416d97cc257...`, `normalized_title='customer_solutions_engineering:senior'`)
  collapsed to **one** family with **printed member count = 14**.
- **A2.4**: whole-corpus invariant check over all 24 postings —
  **cross_employer_violations = 0**, **cross_title_violations = 0**.
- **A2.5**: determinism — 24 keys recomputed over the corpus twice (forward
  and reversed iteration order), compared as dicts: **identical = True**.
- **A2.7**: no-re-judgement — 3 members' `(fit_score, decision)` pairs
  compared before and after a `cluster_members` call: **all unchanged**.

### A2.2 — `py -3.12 -m unittest discover -s opportunity -p "test_*.py" -v` and `py -3.12 -m unittest discover -s storage -p "test_*.py" -v`

**opportunity:**

```
======================================================================
ERROR: test_hacker_news_who_is_hiring_adapter (test_adapters.AdapterTests.test_hacker_news_who_is_hiring_adapter)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "...\opportunity\test_adapters.py", line 203, in test_hacker_news_who_is_hiring_adapter
    result = adapter.parse_payload(payload, raw_pointer="fixture:hn", fetched_at="2026-09-03")
  File "...\opportunity\adapters\hacker_news.py", line 196, in parse_payload
    opp = Opportunity(
TypeError: Opportunity.__init__() got an unexpected keyword argument 'remote_policy'

----------------------------------------------------------------------
Ran 108 tests in 12.924s

FAILED (errors=1)
```

**storage** (with `OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_a2`):

```
test_case_t_family_upsert_and_split_out_round_trip (test_postgres_integration.A1MFounderControlRoundTripTest.test_case_t_family_upsert_and_split_out_round_trip)
A2.6 (BRIEF-FR-006 clustering): StorageRepository's ... ok
...
======================================================================
ERROR: test_case_v_evaluate_new_persists_match_evaluations (test_postgres_integration.PostgresProductionIntegrationTest.test_case_v_evaluate_new_persists_match_evaluations)
Case V: evaluate_new persists match_evaluations rows against real PostgreSQL.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "...\storage\test_postgres_integration.py", line 1400, in test_case_v_evaluate_new_persists_match_evaluations
    handler_v1({})
  File "...\worker\handlers.py", line 588, in handler
    opportunity = _reconstruct_opportunity(session, record)
  File "...\worker\handlers.py", line 493, in _reconstruct_opportunity
    return Opportunity(
TypeError: Opportunity.__init__() got an unexpected keyword argument 'remote_policy'

----------------------------------------------------------------------
Ran 41 tests in 33.787s

FAILED (errors=1)
```

**Both `errors=1` failures are pre-existing, unrelated to this clustering
work, and outside this order's allowed files.** `git log --oneline -1 --
opportunity/adapters/hacker_news.py` attributes that file to commit
`f9b3909` ("feat(FR-006 E23): recon aggregator/regional/freelance/tutoring
sources; HN adapter"), landed by the merge, before any change in this
worktree. `worker/handlers.py::_reconstruct_opportunity` (the second
failure's call site) is untouched by this work order's diff (`git diff HEAD
-- worker/handlers.py` shows no change to that function — only
`compute_family_key`'s import and the new `backfill_family_keys`/
`make_backfill_family_keys_handler` functions were added, appended after it).
Both failures share one root cause: `opportunity/models.py`'s `Opportunity`
dropped `remote_policy` as a constructor parameter (A1's Master decision #1,
documented in that file's own docstring: "deliberately not a constructor
parameter any more... a breaking change for any `Opportunity(remote_policy=...)`
call site outside this deliverable's allowed file set"), and neither
`opportunity/adapters/hacker_news.py` nor `worker/handlers.py::_reconstruct_opportunity`
was in that deliverable's allowed set to fix it. Per the coordinator's
note, a concurrent repair to `worker/handlers.py` is already in flight; both
are reported here, not fixed, since neither file's relevant lines are in
this order's allowed-file list.

Excluding those two pre-existing errors, every other test in both discovers
passes: 107/108 in `opportunity`, 40/41 in `storage`.

**Environment note:** `opportunityos_test_a2` was observed dropped between
some of the re-runs above (a shared local PostgreSQL server, plausibly
touched by a concurrent worktree/process running in parallel on this
machine) — each time, it was recreated exactly per the order's own
instructions (`psql ... -c "CREATE DATABASE opportunityos_test_a2"`) and the
suite re-run from a clean `alembic upgrade head`, with identical results
each time (`Ran 41 tests`, the same single `errors=1`). Never touched
`opportunityos_test` or `opportunityos_alpha`.

### A2.6 — split_out round-trip

Isolated re-run for clarity (same test as inside the A2.2 storage discover
above):

```
test_case_t_family_upsert_and_split_out_round_trip (test_postgres_integration.A1MFounderControlRoundTripTest.test_case_t_family_upsert_and_split_out_round_trip)
A2.6 (BRIEF-FR-006 clustering): StorageRepository's ... ok

----------------------------------------------------------------------
Ran 1 test in 1.675s

OK
A2.6 split_out round-trip row counts: after_insert=1 after_split=1 after_collapse=1
```

Row counts at each step: collapse (insert) -> 1 row; split (`split_out=True`)
-> 1 row (flag toggled in place, no row added); a re-cluster upsert while
split -> `member_count` updates but `split_out` stays `True` (preserved);
collapse again (`split_out=False`) -> 1 row. `list_families()` returns
exactly 1 family throughout. `set_family_split_out` on a non-existent
`family_key` returns `None` (no write), also asserted.

### A2.7 — no-re-judgement

Covered inside A2.1 above
(`test_clustering_never_changes_any_members_decision_or_fit_score`):
3 members' `(fit_score, decision)` pairs captured before calling
`cluster_members`, re-checked against the same members' live attributes
after, and independently checked that every member id that went into
clustering still appears in some family's `member_ids` — **all
`decision`/`fit_score` pairs unchanged, confirmed**.
