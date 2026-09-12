# BRIEF-FR-006 — Current closure ledger

Branch `fix/fr006-final-closure`, PR #78. Historical execution detail remains in `deviations.md`; this file is the current authoritative compact ledger.

**Final pre-report integration:** GitHub run `34724239556`: 1095 tests, zero failures/errors/skips; web build/lint/Playwright green.
**Registry:** 396 entries; 334 verified live relevant ATS boards. **Corpus:** 540 payloads / 15 sources.

## Deliverables

| Area | Status | Evidence |
|---|---|---|
| Extraction/location | INTEGRATED | 540/540 re-parsed; work 77.6% honest ceiling, geo 98.5%, uncertainty 10.4% |
| Title families/scoring | INTEGRATED | 98.5% mapped; Customer Engineer ranks below relevant data role |
| Clustering/search/facets/cards | INTEGRATED | full-corpus invariants, p95 16.14ms/20k, Playwright 22/22 |
| Documents/truth lock | INTEGRATED | 30 artifacts; ADR-0021 canonical validator facade; independent review PASS |
| Live poll | INTEGRATED | Himalayas 20 fetched/parsed/persisted/evaluated, zero fixtures |
| Source board discovery | INTEGRATED | 482 exact seeds, 309 live in probe, 286 new registrations, 334/300 total |
| Persisted new-source yield | NOT_CLOSED | 0/8 in bounded live session; no registry/probe count substituted |
| Stale reverification | INTEGRATED | durable first/<24h/>=24h/pending/retry/fresh-process cadence |
| Governance/State | INTEGRATED | A-6 historical deviation accepted; aliases deprecated; generated State fresh |

## Claim status

| Claim | State |
|---|---|
| A-0 | PASS |
| A-1 | PASS — 1095, failures=0, errors=0, skipped=0 |
| A-2 | PASS |
| A-3 | PASS — migration head `0005_widen_location_region` |
| A-4 | PASS |
| A-5 | PASS |
| A-6 | HISTORICAL_EXCEPTION — 739 expected / 740 observed, ADR-0020 |
| A-7 | PASS |
| A-8 | PASS — 22/22 |
| A-9 | PASS — 20/20/20/20, zero fixtures |
| A-10 | PASS |
| A-11 | PASS |
| A-12 | NOT_CLOSED — work 77.6%/90%; geo and uncertainty pass |
| A-13 | PASS — 532/540 = 98.5% |
| A-14 | PASS — unavailable language dimension remains explicit |
| A-15 | PASS — 20k p95 16.14ms |
| A-16 | PASS |
| A-17 | PASS |
| A-18 | PASS |
| A-19 | PASS |
| A-20 | HISTORICAL_EXCEPTION — exact frozen subset absent; full-corpus invariants pass |
| A-21 | PASS |
| A-22 | PASS |
| A-23 | NOT_CLOSED — boards 334/300; persisted new sources 0/8; Reddit BLOCKED_POLICY/manual-only |

## Boundary

All remediable engineering is complete. Merge after the reconciled evidence/State checkpoint is green, verify `main`, then stop. Founder Web Alpha validation is next; BRIEF-007 / Phase 6 remains blocked until personal Founder acceptance.
