# Work order R5 — A-20 on the committed corpus

## Authority and objective

BRIEF-FR-006 recovery Phase C. Measure and, only where required, repair deterministic
opportunity families on the full 540-payload committed corpus.

## Owned behavior seam

Committed payload -> normalized opportunity -> family key -> reversible presentation.

## Allowed files

- one new corpus clustering metrics runner under `scripts/`
- its direct tests
- `opportunity/clustering.py` and `opportunity/test_clustering.py` only if corpus
  evidence proves an implementation defect
- `reports/evidence/FR-006/closure-current/a20-*`

The corpus and title taxonomy are read-only. Do not substitute a hand fixture for a
missing required corpus subset or merge distinct jobs to satisfy a count.

## Required output

- corpus rows, family count, size histogram, largest families and raw-title diversity
- Cloudflare Senior Customer Engineer member count, or explicit `ABSENT` if the exact
  required set is absent
- zero cross-employer and zero cross-normalized-title violations
- byte-identical/deterministic second computation
- `show separately` reversibility
- semantic collision analysis for broad families; repair only proven false merges

## Acceptance

- runner/tests are deterministic and cover all 540 payloads.
- `py -3.12 -m unittest opportunity.test_clustering <new-test-module> -v` is green.
- named A-20 evidence is committed, with any irreducible fixture/contract mismatch
  classified honestly.

Commit changes and raw evidence on a dedicated branch/worktree. Report the commit.

