# Agent Execution Protocol v2 — Fast, Parallel, Verified

**Status:** Adopted 2026-09-03 by the Overseer at the founder's direction. Applies to BRIEF-FR-006 and every brief after it. Supersedes the "Master loop" sections of FR-003/004/005 where they conflict. AGENTS.md references this file.

## 0. The one-sentence rule

**The Master orchestrates; it never implements and never personally re-executes what a runner can execute.** Its turns are spent on four things only: turning the brief into work orders, dispatching everything that is ready *at once*, judging captured outputs, and returning numbered defects.

## 1. Roles, models, effort

| Role | Model | Effort | Concurrency | Does | Never does |
|---|---|---|---|---|---|
| **Master** (main session) | `opus` | high | 1 | work orders, DAG dispatch, integration, judgement, defect lists, report | implement; run suites by hand; read subagent summaries in place of raw output |
| **implementer** | `sonnet` | `high` for engine/API/web logic; `medium` for docs, fixtures, registry entries, ADR-from-template | up to **4** in parallel, each in its own worktree with its own test DB | one work order end-to-end with tests; pastes raw acceptance output | merge; touch files outside its work order; edit evidence/fixtures to make a claim pass |
| **evidence-runner** | `haiku` | low | up to **4** in parallel, background | executes claim commands verbatim; writes evidence files; reports exit code + first/last line | interpret; retry with variations |
| **verifier** | `opus` | high | 1 (may spawn haiku runners) | reads evidence vs expected for every claim; **re-executes** every high-consequence claim and any claim whose evidence looks inconsistent; PASS/FAIL table | be told the Master's verdict first |
| **council-reviewer** | `fable` | high | parallel, one per named review | reviews one diff against one requirement; numbered findings with severity | read implementer/Master reasoning |
| **Explore** | `haiku` | low | many | read-only search | edit |

Budget guards: implementer `maxTurns` 60 (90 for web work orders), evidence-runner 25, verifier 40, council 30. A subagent that hits its budget returns what it has; the Master does not extend budgets silently — it records the overrun and re-dispatches a narrower order.

## 2. Work orders (written once, before any dispatch)

For each deliverable the Master writes `reports/evidence/<brief>/orders/<ID>.md` containing only: the deliverable text, the acceptance rows (command → expected → evidence file), the allowed file list, the frozen list, the test DB name, and the worktree name. Subagents receive the work order, not the brief. This is what keeps subagent context small and turns cheap.

## 3. DAG dispatch

The brief's §3 is a dependency graph. The Master:
1. Marks every node whose dependencies are met as *ready*.
2. Dispatches **all ready nodes in a single message** as background implementers (up to the concurrency cap), each with `isolation: worktree`.
3. While they run, dispatches any council review whose diff is already stable, and any evidence capture for already-integrated nodes.
4. On each return: judges (see §5), integrates (see §4), recomputes readiness, dispatches the next wave immediately. No wave waits for the slowest node in the previous wave unless it depends on it.

Idle Master turns while waiting are wasted money; the Master should always have something dispatched.

## 4. Isolation and integration

- Every implementer worktree gets its own PostgreSQL database: `opportunityos_test_<order-slug>`, created by `python scripts/dev_env.py testdb <slug>` and exported as `OPPORTUNITYOS_DB_URL` in the work order. Two implementers never share a database.
- Web work orders get their own port range (`3100+n`, `8100+n`).
- Integration is **per wave**, not per deliverable: the Master merges each returned worktree branch into the brief branch, resolves conflicts itself (this is the one place it edits code), then dispatches *one* full-suite evidence run for the wave. Narrow suites during loops; the full suite once per wave and once at the end.
- Environment is pre-warmed **before wave 1**: `python scripts/dev_env.py up` verifies Python ≥ 3.12, Node, PostgreSQL, Playwright browsers, the PDF renderer, and creates the test databases. An implementer that discovers a broken environment is a protocol failure, not a deviation.

## 5. Judgement and the defect loop

- The Master judges from **raw captured output** (the `Ran N tests … OK` lines, the acceptance command outputs), never from a subagent's summary sentence.
- A returned work order is accepted only if every acceptance row's raw output matches its expected result. Otherwise the Master sends a **numbered defect list** (expected / observed / file:line) and **resumes the same subagent** — context preserved, nothing re-read.
- Loop cap: **3**. On the third failure the Master dispatches the verifier for a diagnosis, then one fresh implementer with the defect history. Still failing → `NOT_CLOSED` with history. The Master never patches a subagent's deliverable to make it pass.

## 6. Verification tiers (all parallel where possible)

| Tier | Who | When | What |
|---|---|---|---|
| 1 | implementer | before return | narrow tests + its acceptance rows, raw output pasted |
| 2 | evidence-runners (haiku ×4) | after each wave integrates | every claim in `CLAIMS.md` executed once into evidence files |
| 3 | verifier (opus) | after final integration | reads all evidence vs expected; **re-executes** A-0, the full suite, migrations, document generation, the guard-neutralisation mutation, and any claim whose evidence is inconsistent or depends on machine-local state; returns PASS/FAIL per claim |
| council | fable, parallel | as soon as each named diff is stable, not at the end | findings → fixed or dispositioned with reason |

A claim is "done" only with Tier 2 evidence and a Tier 3 PASS. This is the same independence guarantee as before with one-third of the execution cost, because the Master no longer re-runs things itself.

## 7. Evidence discipline (unchanged, restated)

- An expected result must state every property the report will later assert about it.
- Evidence that depends on a gitignored or machine-local artifact is not evidence.
- Editing evidence, fixtures, or templates so that a claim validates is an automatic FAIL of the deliverable.
- No number in the report is typed from memory; every quantitative statement is a claim row.

## 8. Report discipline

- `REPORT-<brief>.md` is ≤ 400 lines. Deviations are **one table row each** (id, what, why, authorised-by, consequence). Council findings are one row each with disposition. Prose is limited to §1 summary, §6 council dispositions, §8 deviations-that-matter (≤ 5 paragraphs), §9 founder packet, §10 recommendation.
- Evidence files carry the detail. The report links; it does not restate.

## 9. Hard stops (unchanged)

Credential exposure; any external mutation; frozen-policy contradiction unresolvable from repository evidence; absent required tool with no fallback (`BLOCKED_ENV` for that deliverable only, continue the rest); reading `private/`; any request to a source that has returned 403/429 this session.

## 10. Cost model this protocol assumes

Opus for judgement only (Master + verifier). Sonnet for all volume. Haiku for all mechanical execution. Fable for the few high-consequence reviews, run in parallel so they don't extend the critical path. The expensive failure mode this protocol removes is Opus turns spent waiting, re-running, or narrating.
