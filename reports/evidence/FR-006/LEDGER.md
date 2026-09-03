# BRIEF-FR-006 — Master's ledger and DAG

Status: `ORDERED` `DISPATCHED` `DEFECT-n` `INTEGRATED` `NOT_CLOSED` `BLOCKED_POLICY`.
Branch `feat/brief-fr-006-nothing-missed`, base `main` = `bf25d93`.

**Suite:** 672 at baseline (skipped=2) → **958 at wave 3** (1 failure, 3 skipped).
**Registry:** 52 entries → **110**. **Corpus:** 540 payloads / 15 sources.

## Deliverables

| Node | Depends on | Status | Note |
|---|---|---|---|
| D0 protocol | — | INTEGRATED | |
| F2 dev_env | — | INTEGRATED | reportlab 5.0.1; `alpha.py` already used `sys.executable` |
| A1M migration `0004` | — | INTEGRATED | 17 cols, 5 indexes, 4 tables, reversible per object |
| A1S `target_roles` seed | A1M | INTEGRATED | data migration; guard test passes |
| A1B council-3 repairs | A1M | DISPATCHED (late — see deviation 82) | search backfill, backup seeding, index metadata |
| A1 extraction | — | INTEGRATED | 7 fields; repo-wide `remote_policy` sweep done |
| A1C corpus | A1 | INTEGRATED | 540 payloads, Cloudflare present |
| A12M metrics | A1, A1C, B* | INTEGRATED | the A-12/A-13 numbers |
| B1 seniority | — | INTEGRATED | ADR-0016; 20-month Team Lead regression test |
| B2 skills | A1, B3 | INTEGRATED | proficiency tiers; gold set 83.5 |
| B3 title families | — | DEFECT-3 | taxonomy broadened; awaiting the corpus re-measure |
| A2 clustering | A1 | INTEGRATED | **measured on a 24-posting hand fixture, not the corpus** |
| C1 facets + C4 + B4 | A1, B3 | INTEGRATED | 14/15 facets; `stale_postings=0` proven by SQL |
| C2 search | A1 | DEFECT-1 | tripwire fired; rewriting against the real corpus |
| C3 cards (web) | C1,B2,A2,E23 | DISPATCHED | components in, specs outstanding |
| D1 CV compiler | F1 | INTEGRATED | 30 artifacts, DOCX+PDF, mutation fails 2 suites |
| D1F pack shape | D1, F1 | INTEGRATED | 7/7 roles >= 2 bullets; lock still binds |
| ATS regex fix | D1F | INTEGRATED | `dates_parsed_count` 0 → 48 |
| D2 preview | D1, C3 | **ORDERED — blocked on C3** | |
| E1 discovery | — | INTEGRATED | 36 boards of 300; Ashby stays disabled |
| E23 sources | — | INTEGRATED | 25 `manual_only`; **HN bound path yields 0** |
| E5 policy repairs | E1, E23 | DISPATCHED | council-4 findings; finding 10 is the priority |
| E4F3 cadence + digest | E1, E23 | INTEGRATED | first writer of `is_stale=True`; **not yet invoked** |
| F1 identity | — | INTEGRATED | `identity` + `approved_phrases` |
| F4 matrix/STATE/report/merge | all | ORDERED | terminal gate |

## Councils

| # | Subject | Outcome |
|---|---|---|
| 1 | scoring semantics | RETURNED (5th attempt, on `sonnet`). 8 findings; all dispositioned. B2 not in the reviewed diff. |
| 2 | D1 document model + truth-lock | **NOT YET RUN** — D1F only just integrated |
| 3 | migration `0004` | RETURNED. 4 satisfied, 2 MAJOR, 3 MINOR, 1 NIT → A1B |
| 4 | source policy | RETURNED. 6 satisfied, 6 MAJOR, 8 MINOR, 2 NIT → E5 |

## Claim status

| Claim | State |
|---|---|
| A-0 fail-closed | **PASS** — 12/12 at wave 3 |
| A-1 full suite | 958 > 672. **NOT_CLOSED on the `0 skipped` clause** — 2 POSIX + 1 gated perf |
| A-2 module counts | not yet reconciled |
| A-3 migrations | upgrade to `0004` green; full round-trip re-run owed after A1B |
| A-4 guard + repository | **PASS** at wave 3, both exit 0 |
| A-5 STATE | owed, on `main` after merge |
| A-6 scope diff | owed against `a6-expected-scope.md` |
| A-7 web build/lint | owed with C3 |
| A-8 Playwright | owed with C3 |
| A-9 live poll | **owed — must not run until E5 closes finding 10** |
| A-10 documents | **PASS** — 30 artifacts, DOCX+PDF, zero rejections |
| A-11 truth-lock mutation | **PASS** — fails 2 suites, restore byte-identical, re-verified after D1F |
| A-12 extraction | **NOT_CLOSED** — 52.2% / 72.2% / 18.5% met / see A-13 |
| A-13 scoring | **NOT_CLOSED** — title family 20.6%, being re-measured |
| A-14 facets | 14 of 15; `language` permanently unavailable |
| A-15 search | tripwire fired; p95 23.73ms but **gated behind an env var** |
| A-16 source policy | 6 properties confirmed; 6 MAJOR open in E5 |
| A-17 predicates | green throughout |
| A-19 provenance idempotency | owed |
| A-20 clustering | **measured on a hand fixture, not the corpus** — re-run owed |
| A-21 cards | owed with C3 |
| A-22 preview | blocked on D2 |
| A-23 breadth | **NOT_CLOSED** — 36 boards of 300; **0** new read-allowed sources producing rows in the product |

## What will not close, and why

1. **A-23 breadth.** 36 of 300 boards; the HN bound path yields 0 until E5 wires it. Honest numbers, reported as reached.
2. **A-12 extraction.** 52.2% work-mode against 90%. Not fixable inside this brief — 47.8% of real postings state nothing a rule can read.
3. **A-1's zero-skip clause.** Two POSIX tests cannot run on Windows.
4. **The PR-head half of §8.** `gh` unauthenticated; recorded in `CLAIMS.md` before the work.

## Standing risks

1. Every implementer exhausts its 60-turn budget. Fourteen overruns. Orders are written for 90 where the harness allows 60 (deviation 58).
2. Worktrees branch from `main`; an unmerged worktree made one agent conclude a genuine review was fabricated (deviation 50 context).
3. One local PostgreSQL; orphaned suite processes leak connections and one agent's database was dropped underneath it.
4. `truth/validator.py` frozen everywhere. A-11 is the tripwire and the Overseer re-runs it.
5. The shared `create_test_graph()` fixture under-specifies what each honest dimension needs — two gold-set regressions, and B2 says other flat assertions have the same shape.
