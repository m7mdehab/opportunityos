# Work order R4 — honest A-12/A-13 corpus measurement and bounded repair

## Authority and objective

BRIEF-FR-006 recovery Phases C/D. Replace stale A-12/A-13 evidence with deterministic
measurements over all 540 committed payloads, expose residuals by source, and make
only evidence-supported extraction/taxonomy repairs.

## Owned behavior seam

Raw committed payload -> adapter/native extraction -> conservative inference -> title
family -> founder-shaped evaluation -> metrics/evidence.

## Allowed files

- `scripts/corpus_metrics.py`
- `scripts/scoring_metrics.py`
- their direct tests
- `opportunity/extraction.py`
- directly relevant adapters and adapter tests under `opportunity/`
- `matching/title_families.yaml` and `matching/test_title_family.py` only after a
  residual/false-positive audit justifies a deterministic family
- `reports/evidence/FR-006/closure-current/a12-*`
- `reports/evidence/FR-006/closure-current/a13-*`

Corpus fixture payloads are read-only. Do not infer absent work mode/location facts,
lower thresholds, or add catch-all title regexes.

## Required output

- A-12 denominator, native/inference/none split, per-source missing distribution,
  country-or-scope, uncertain share, residual IDs/titles, and quantified honest signal
  ceiling.
- A-13 mapped/residual counts, every residual title/source/id, family histogram,
  false-positive holdout checks, score ordering, and proficiency semantics.
- Regression tests for every production rule changed.

## Acceptance

- `py -3.12 -m unittest scripts.test_corpus_metrics scripts.test_scoring_metrics matching.test_title_family matching.test_scorer matching.test_qualification matching.test_gold_set -v`
- deterministic current evidence files for A-12 and A-13.
- If a frozen threshold remains impossible without invention, return the exact
  quantitative ceiling and leave it `NOT_CLOSED`.

Commit changes and raw evidence on a dedicated branch/worktree. Report the commit.

