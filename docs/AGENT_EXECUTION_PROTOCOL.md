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


## 11. Terminal execution contract — no premature partial returns

Generic `PARTIAL` is not a terminal state for an executable brief.

Before returning control, the active executor must exhaust every approved execution surface that can close the remaining evidence gap without crossing a hard external boundary: local tools, isolated worktrees, disposable containers, repository CI, draft pull requests, workflow dispatch, browser automation, and approved connected tools. A limitation of the current shell or machine is not a blocker when another already-approved repository surface can execute the proof.

The execution ladder is:

`implement -> narrow tests -> integration-contract tests -> disposable/runtime proof -> CI/PR proof when required -> independent verification -> remediation -> final report`.

Rules:

1. Do not stop at “harness implemented” when the harness can be executed safely now.
2. Do not treat “no local DSN/runtime/browser” as terminal when CI, a disposable container, or another approved execution surface provides it.
3. Pull-request creation is an approved verification mechanism when CI is required. Executors may open a draft or normal task PR when their environment is authenticated and the brief does not forbid external repository writes. Merge authority remains with the Owner/Overseer.
4. If the executor cannot create the PR because its own GitHub surface is unauthenticated, that is an `OVERSEER_CI_HANDOFF`, not `PARTIAL`. Return the exact branch, head SHA, required workflow/proof, and continue every other independent requirement first.
5. Report repository completion and live/hosted completion on separate axes. A repository package may be `REPOSITORY_PASS` while a genuinely external criterion is `HOSTED_NOT_EXECUTED`; do not collapse those into generic `PARTIAL`.
6. The only terminal early return is `HARD_BLOCKED`: an unresolved boundary that requires Founder-only credentials/approval, payment, binding terms, inaccessible external ownership, production authority not granted, or another explicitly reserved action.
7. Work orders and waves should be milestone-sized. After a workstream passes, immediately continue into the next dependency-ready work inside the same authorized objective instead of returning merely because one subsystem is complete.
8. Unit-test success is not sufficient for glue code. Workflow/CLI/schema/artifact/browser/infrastructure contracts must be tested at the integration boundary that can actually fail.
9. After one focused remediation return, ordinary residual closure belongs to the Owner/Overseer. Do not create indefinite executor ping-pong for small, safely correctable gaps.

Preferred terminal vocabulary:

- `PASS` — all currently executable in-scope evidence is complete.
- `REPOSITORY_PASS / HOSTED_NOT_EXECUTED` — repository work is complete; only a genuine external hosted/live gate remains.
- `OVERSEER_CI_HANDOFF` — implementation is complete and the only remaining repository proof requires an Overseer-accessible PR/CI surface.
- `HARD_BLOCKED` — a true Founder/external authority boundary prevents further progress.

The Master/Overseer must reject a return that uses `PARTIAL` without naming an actual hard boundary and proving that all approved fallback execution surfaces were exhausted.


## 12. Pre-dispatch readiness gate — resolve known blockers before prompting a Master

A Master Agent is dispatched only after the Owner/Overseer has made the work order executable on the surfaces actually available to that agent.

A known blocker discovered before dispatch is an orchestration defect if it is simply passed downstream for the Master to rediscover.

Before issuing any Master prompt, the Owner/Overseer must complete a **Readiness Certificate** for that work order and resolve every known blocker according to ownership:

- **Overseer-resolvable:** execute it before dispatch.
- **Founder-only:** ask the Founder before dispatch, wait for completion, then re-check.
- **Executor-owned:** leave it in the work order only when the executor has the capability and authority to resolve it itself.
- **Out of scope / intentionally deferred:** remove it from the executor's end goal and state the boundary explicitly.

The pre-dispatch checklist is mandatory:

1. **Dependency closure** — every prerequisite branch/PR/migration/resource required by the task is actually landed or otherwise available, not merely planned.
2. **Fresh start point** — the target branch SHA is current and explicitly named; stale branches are reset or discarded before dispatch.
3. **External resource existence** — required projects, environments, buckets, databases, deployment targets, domains and provider-side objects already exist when the executor is expected to use them.
4. **Provider access** — the exact execution surface that will perform provider mutations is already authenticated. Do not assign provider work to an agent that cannot authenticate to that provider.
5. **Credential/secret path** — required secrets exist in the correct protected surface and there is a known injection path. Do not place secret values in prompts, Git, evidence, or chat.
6. **Cost/quota/terms** — any cost confirmation, quota release, subscription requirement, terms acceptance or protected-environment approval that is already knowable is settled before dispatch.
7. **Tool/runtime capability** — required CLI/runtime/browser/container/CI surfaces are either present for the executor or explicitly routed to another owner. Missing local tooling is acceptable only when a verified fallback is already available.
8. **Git/CI path** — branch and PR strategy are prepared; if CI is required and the executor cannot create PRs, create the PR before dispatch.
9. **Live endpoint readiness** — when a task requires testing a deployed service, the deployment dependency and safe endpoint are already available unless deployment itself is the executor's owned end goal.
10. **Capability-aligned end goal** — the task's terminal state must be achievable by the assigned Master. If not, split provider execution from repository preparation before dispatch.
11. **Known-blocker ledger** — every blocker discovered during preflight has an owner and resolution status. Dispatch is prohibited while any blocker marked PRE_DISPATCH remains unresolved.
12. **Return-state sanity** — if the prompt's most likely terminal result is already predictably `HARD_BLOCKED` from facts known before dispatch, do not dispatch it.

The Readiness Certificate should be persisted with the work order when the task is consequential or provider-dependent, for example:

`reports/evidence/<brief>/orders/<ID>-READINESS.md`

Minimum certificate fields:

- work-order ID;
- authoritative base SHA;
- dependency status;
- external resources and safe identifiers;
- execution surfaces per provider;
- secret-injection path by secret name only;
- cost/quota/terms status;
- PR/CI path;
- unresolved blocker ledger;
- `READY_TO_DISPATCH: YES|NO`.

Only `READY_TO_DISPATCH: YES` authorizes the Master prompt.

The goal is simple: **Masters should spend their context executing the end goal, not discovering environment facts the Overseer could have resolved beforehand.**
