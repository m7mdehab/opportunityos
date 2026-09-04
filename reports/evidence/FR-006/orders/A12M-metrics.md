# Work order A12M — The extraction and scoring metrics (claims A-12 and A-13)

**Brief:** BRIEF-FR-006 §7, claims **A-12** and **A-13**. **Wave:** 4.
**Depends on:** A1, A1C, A1M, B1, B2, B3 (all integrated).
**Worktree/branch:** `wt/fr006-a12m` **Test DB:** `opportunityos_test_a12m`
**Turn budget:** 60. **Spend at most 6 turns reading.**

**First action:** `git merge --no-edit feat/brief-fr-006-nothing-missed` from your worktree root.

## Why this order exists

Two mandatory claim rows are currently **unmeasured**, and three tests now fail because they
encoded the temporary absence of the fields that would measure them.

Work order A1C committed a 540-payload fixture corpus and wrote `scripts/corpus_metrics.py`
before work order A1's extraction fields existed. The script therefore reports every coverage
metric as `NOT AVAILABLE` — which was the correct and honest behaviour at the time, and A1C wrote
tests asserting exactly that:

    FAIL: scripts.test_corpus_metrics.WorkModeCoverageTests.test_missing_attribute_reports_not_available_not_zero
    FAIL: scripts.test_corpus_metrics.LocationCoverageTests.test_missing_attribute_reports_not_available
    FAIL: scripts.test_corpus_metrics.AdapterInferenceSplitTests.test_missing_attribute_reports_not_available

A1's fields now exist, so the attributes are present and those assertions are false. These are
tests that pass only against the old behaviour, and §1 of the brief authorises replacing them —
each replacement listed in the report. **Replace them; do not delete the coverage they provide.**
The "reports NOT AVAILABLE rather than 0%" property is still worth testing — it just has to be
tested by simulating a missing attribute rather than by relying on it being genuinely absent.

## What you must produce

### 1. Claim A-12 — extraction metrics, actually computed

`scripts/corpus_metrics.py` must print, **with denominators, not only percentages**:

- corpus size (expected 540 across 15 sources);
- share of rows whose work mode is **not** `unspecified`;
- share with a `location_country` **or** a non-unspecified `remote_scope`;
- the **adapter vs inference split** of work-mode values, read from `work_mode_source`;
- the qualification decision distribution.

The brief's thresholds are >= 90% work mode, >= 85% country-or-scope, and an *uncertain* share
below 25%. **Report the numbers you measure.** If one misses, that is the finding — say so with
the number. Do not filter, re-sample, or re-weight the corpus to move a percentage; that is the
same defect class as editing evidence and is an automatic FAIL.

### 2. The uncertain share must be measured against the founder-shaped pack

This is the part that was wrong before and it matters. A1C computed its decision distribution
against an **empty `TruthGraph`**, which produced `ineligible` 75.0% / `uncertain` 18.9%. That is
not comparable to what the founder saw — against an empty graph almost everything is `ineligible`
because nothing can match, and the brief's §0 observation ("every visible card said *Uncertain*")
is about a run with a real pack.

Compute the decision distribution against **`truth.fixtures.founder_shaped_graph()`** — the
founder-shaped synthetic pack, never the founder's own. Report the distribution twice if you can:
once against the founder-shaped pack (the figure that answers the claim) and once against the
empty graph (so the difference is visible and A1C's number is not silently contradicted).

### 3. Claim A-13 — scoring metrics over the corpus

A metrics run over the corpus with the founder-shaped pack, printing:

- **B1:** for a Staff, a Principal, a Lead, a Senior, a Mid and a Junior posting drawn from the
  corpus, the `seniority_and_experience` raw score and explanation. Staff/Principal/Lead must
  show **no** seniority strength for this pack; Mid and Junior must.
- **B2:** the count of corpus rows where a required-skill match at >= working proficiency produced
  a core-skill strength, versus rows where a `basic`/`foundations`/unknown proficiency produced a
  partial. Plus five sample reason strings taken from real corpus rows.
- **B2 ordering:** the "Senior Customer Engineer" family's best score against the best
  data-engineering score, **measured over the corpus** rather than over hand-built fixtures. Both
  numbers printed. The fixture-based figures are 46.08 and 82.5; the corpus figures may differ and
  the corpus ones are what the report quotes.
- **B3:** the share of the corpus's 540 titles that map to a title family, the share mapping to
  `other`, and the `other` titles split into (a) not a role posting and (b) a role title the
  taxonomy failed to place — the same two groups B3 established for its 67-title sample. The
  brief's threshold is >= 95% mapping to a family.

### 4. Replace the three failing tests

Rewrite them so the `NOT AVAILABLE` property is tested by **simulating** a missing attribute — a
stub object, a monkeypatched accessor, or a corpus record with the field stripped — rather than by
depending on the real model lacking it. Then add tests that the metrics compute correctly against
a small known-answer fixture, so the numbers themselves are covered and not merely the
unavailability path.

## Allowed files

`scripts/corpus_metrics.py` · `scripts/test_corpus_metrics.py` · `scripts/scoring_metrics.py`
(new, if the A-13 run wants its own entry point) and its test ·
`reports/evidence/FR-006/a12-extraction.txt` · `reports/evidence/FR-006/a13-scoring.txt`.

## Frozen — touching any of these is a FAIL

**`opportunity/fixtures/corpus/**`** — the corpus is committed evidence; you measure it, you do
not curate it · `opportunity/**` · `matching/**` · `truth/**` · `storage/**` · any migration ·
`api/**` · `web/**` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| A12M.1 | `py -3.12 scripts/corpus_metrics.py` | every metric printed **with its denominator**; the adapter/inference split; the decision distribution against the founder-shaped pack **and** the empty graph |
| A12M.2 | the A-13 scoring run | the B1 six-level table, the B2 strength/partial counts and five real reason strings, the B2 ordering pair, and the B3 family-mapping shares with the `other` split |
| A12M.3 | `py -3.12 -m unittest discover -s scripts -p "test_*.py" -v` | `OK`, count stated; the three `not_available` tests replaced, not deleted |
| A12M.4 | `py -3.12 scripts/check_guard.py --allow-missing-patterns` | exit 0 |

State plainly, for every one of the brief's four thresholds (90% work mode, 85% country-or-scope,
under 25% uncertain, 95% title family), whether it was met and by what margin. A missed threshold
reported honestly is a better result than a met one produced by touching the corpus.
