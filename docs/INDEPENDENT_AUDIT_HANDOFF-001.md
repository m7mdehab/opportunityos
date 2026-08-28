# BRIEF-001 Independent Audit Handoff

## Objective

Independently adjudicate the final BRIEF-001 v1.4 geographic classification
sample. Do not modify implementation, test expectations, or source evidence.

## Audit target

- **Commit:** `c8dc76c8559b5458db613e28f0e5d0e1e33db2da`
- **Private immutable sample:** `out/audit-001.json`
- **Sample shape:** all 8 `eligible` records, 30 `excluded`, and 30 `unclear`.
- **Raw fixtures:** `out/fixtures/`; the sample carries the fixture pointer,
  source, record ID, URL, raw location, and raw body for every record.

## Reviewer instructions

For every sampled record, inspect the raw location and body rather than trusting
Codex's fields. Independently decide whether each `geo_allow` token, `geo_deny`
token, and derived Egypt (`EG`) verdict is correct under ADR-0003 and
`briefs/BRIEF-001.md` §5. Preserve the matched source string for every
disagreement, including false positive, false negative, and insufficient-evidence
findings. Do not change a rule or test to fit a record.

Compute separately: extraction precision, derivation precision, and Egypt
eligible precision. The phase can publish an eligibility percentage only if the
derived Egypt eligible precision is at least 90%. Otherwise state the reason and
withhold the percentage.

## Deterministic evidence

- `python -m unittest discover -v`: 13 tests passed.
- `python scripts/check_guard.py` with derived founder patterns: passed.
- Final run: 3,113 raw records, 2,564 unique; 12/14 source families and 6
  independent families reached HTTP; source-health details and country views are
  in `docs/SOURCE_EVIDENCE.md`.
- The watchlist has 25 live-verified ATS tokens; source retrieval still honors
  robots policy, so the shared Ashby robots endpoint is reported separately from
  token verification.

## Remaining acceptance criteria

Unchecked until this audit completes: extraction/derivation precision, Egypt
eligible precision gate, final acceptance review, private workflow verification,
mirror synchronization and health reconciliation, and phase PASS/BRIEF-002
advancement. The reviewer must report any discovered implementation defect for a
Codex remediation loop followed by a fresh audit.
