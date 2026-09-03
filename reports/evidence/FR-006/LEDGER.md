# BRIEF-FR-006 — Master's unresolved-task ledger and DAG

Maintained by the Master across the whole transaction. Status values: `ORDERED`, `DISPATCHED`,
`RETURNED`, `DEFECT-n`, `INTEGRATED`, `NOT_CLOSED`, `BLOCKED_ENV`, `BLOCKED_POLICY`.

Branch: `feat/brief-fr-006-nothing-missed`. Base `main` = `bf25d93`.

## Deliverable nodes

| Node | Order file | Depends on | Status | Notes |
|---|---|---|---|---|
| D0 protocol adoption | — (Master) | — | INTEGRATED | `824a809` |
| F2 dev_env | `F2-devenv.md` | — | **INTEGRATED** | rows F2.1-F2.6 pass; `alpha.py` already used `sys.executable`, so the sweep is a static-scan test. reportlab 5.0.1. |
| A1 extraction (split) | `A1-extract.md` | — | DEFECT-1 | 7 new fields + 155 inference rules + qualifier; `remote_policy` became a property and broke 6 test files repo-wide |
| A1M migration 0004 | `A1M-migration.md` | — | DISPATCHED | the unblocker for A2, C1, C2, D2, E4 |
| A1C corpus + metrics | `A1C-corpus.md` | A1 | ORDERED | |
| B1 seniority | `B1-seniority.md` | — | **INTEGRATED** | 15 new tests; ADR-0016; `is_senior` gone. Fixture encodes 9y, brief describes ~20mo — recorded in the ADR. |
| B3 title families | `B3-families.md` | — | **INTEGRATED** | 62 tests; 735 repo tests OK; `other` split 17 non-role / 9 unplaced; `domain_fit` 0.10->0.05 for the new dimension |
| F1 identity predicates | `F1-identity.md` | — | **INTEGRATED** | `identity`+`approved_phrases` sections, 9+1 predicates projected, leak test green. Could not reproduce FR-005's claimed silent-unknown-section defect. |
| E1 board discovery | `E1-discovery.md` | — | DISPATCHED | |
| E23 communities/freelance/tutoring | `E23-sources.md` | — | DISPATCHED | E2+E3 merged, deviation 2 |
| A2 clustering | `A2-cluster.md` | A1 | ORDERED | |
| B2 skills | `B2-skills.md` | A1, B3 | ORDERED | |
| C1 facets + C4 audit + B4 exercise | `C1-facets.md` | A1, B3 | ORDERED | merged, deviation 7 |
| C2 search | `C2-search.md` | A1 | ORDERED | |
| C3 cards (web) | `C3-cards.md` | C1, B2, A2, E23 | ORDERED | |
| D1 CV compiler | `D1-compiler.md` | F1 | ORDERED | headline deliverable |
| D2 preview | `D2-preview.md` | D1, C3 | ORDERED | |
| E4 cadence + F3 digest | `E4F3-worker.md` | E1, E23 | ORDERED | merged, deviation 8 |
| F4 matrix / STATE / report / merge | — (Master) | everything | ORDERED | terminal gate |

## Council reviews (fable, parallel, as diffs stabilise)

| # | Subject | Requires | Status |
|---|---|---|---|
| 1 | B1 + B3 scoring semantics (ADR-0016) | B1, B3 integrated | **DISPATCHED** (B2 not yet in; a second pass covers it) |
| 2 | D1 document model and truth-lock (ADR-0017) | D1 integrated | pending |
| 3 | Migration `0004` (A1/A2/C1/C2/D2 schema) | those integrated | pending |
| 4 | E0-E3 source policy compliance | E1, E23 integrated | pending |

## Verification

| Tier | Who | Status |
|---|---|---|
| baseline | evidence-runner (haiku) | DISPATCHED — pre-brief suite count, guard, repository, fail-closed |
| 2 | evidence-runners over `CLAIMS.md` | pending final integration |
| 3 | verifier (opus) | pending Tier 2 |

## Standing risks the Master is tracking

1. Sonnet implementers exhausting their 60-turn budget on exploration. Two so far (F2, B3).
   Mitigation now in every dispatch: an explicit read budget and "name your assumptions".
2. Agent worktrees branch from `main`, not from the session branch. Every dispatch prompt now
   opens with the merge command. Deviation 5.
3. One local PostgreSQL shared by every implementer. Each has its own database; the concurrency
   cap of four exists partly for this reason. FR-005 lost ten minutes to lock contention from a
   dead agent's idle-in-transaction connections.
4. `truth/validator.py` and `truth/connective_terms.txt` are frozen in every order that could
   plausibly want them. Claim A-11 is the tripwire and the Overseer re-runs it.
5. The PR-head half of §8 is not evidenceable from this host (`gh` unauthenticated, private repo).
   Recorded in `CLAIMS.md` before the work, not discovered late.
