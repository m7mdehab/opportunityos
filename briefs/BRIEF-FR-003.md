# BRIEF-FR-003 — Reality Refresh and Runtime Closure

**Version:** 1.0
**Date:** 2026-09-02
**Overseer:** external independent auditor (author of `OPPORTUNITYOS_INDEPENDENT_REALITY_AUDIT_v2_VERIFIED_2026-09-01`)
**Master:** Claude Code main session, model `opus`
**Status:** ACTIVE (highest-numbered brief without a report)
**Starting main:** `889dee1cf4acdc3a38abf2e634bfce38453ae2ee`
**Supersedes:** the provisional "FR-003 = FastAPI + Next.js" naming in the 2026-09-01 handoff. The web/API slice becomes **BRIEF-FR-004** and must not be started in this brief.

---

## 0. Why this brief exists

An independent audit re-executed the FR-002 runtime on real PostgreSQL 16 and confirmed the engine (414/414 tests, Alembic, fail-closed persistence at all seven boundaries). It also found a set of defects that are individually small but collectively mean the project's *reports* are less trustworthy than its *code*. Every one of those defects is closed here, before any founder-facing layer is built on top of them.

This brief is **fully autonomous**. The Master owns it from receipt to a single final report. There is no progress-report contract. The Master stops only for a hard-stop condition in §9.

---

## 1. Scope and non-goals

**In scope:** every finding in audit v2 §2.1, §2.2, §1 item 7, and §6 Step 1; the worker runner from §6 Step 2; a regenerated, mechanically-reconciled readiness matrix.

**Out of scope (hard):** FastAPI, Next.js, auth, Docker/Caddy, any founder page, any change to frozen BRIEF-002…006 or FR-002 *semantics*, any new source adapter beyond re-recon of three existing registry entries, any change to `docs/MASTER_PLAN.md`, any live submission or outbound action, any credential use.

**Frozen-brief rule:** FR-002 persistence semantics stay frozen. Changes to `storage/`, `worker/`, `scripts/backup_restore.py` are permitted only where a deliverable below names them, and every such change must leave the fail-closed probe (§7, A-0) passing.

---

## 2. Deliverables

Each deliverable has an ID, an owner role (§4), acceptance criteria that are commands with expected outputs, and a council flag. "Test" means a test that runs under `python -m unittest discover -v` from the repo root in the Mandatory workflow, unless stated otherwise.

### D0 — Agent topology committed
- Create `.claude/agents/` with the five definitions in Appendix A, byte-for-byte except for the system-prompt bodies, which may be refined but not weakened.
- Create `.claude/settings.json` from Appendix B.
- Add `.claude/**` to nothing public: confirm `.mirror-allowlist` does not match it (it must not be mirrored).
- Note: Claude Code watches `.claude/agents/` only if the directory existed when the session started. The founder pre-creates the empty folder before launching; the Master writes the five files as its first action and then delegates by name (`implementer`, `evidence-runner`, `verifier`, `council-reviewer`). If a named agent does not resolve, fall back to per-invocation `model` routing with the Appendix A role prompt pasted into the delegation, and say so in the report.

**Acceptance:** `ls .claude/agents` lists five files; `python scripts/check_repository.py` passes; `python scripts/sync_mirror.py --dry-run` (or equivalent allowlist test) shows no `.claude` path. Owner: Master directly (trivial). Council: no.

### D1 — Public CI verdict includes the test suite
- `scripts/generate_ci_status.py`: `WORKFLOWS` becomes `("Mandatory Governance & Test Suite", "State", "Guard", "Mirror")`. `checks_green` requires all four. Output table lists all four.
- Add `scripts/test_generate_ci_status.py` covering: all-success → HEALTHY; Mandatory failure with others success → not HEALTHY; `unavailable` → not HEALTHY.
- `docs/CI_STATUS.md` will regenerate on the next heartbeat; do not hand-edit it.

**Acceptance:** new tests pass; `grep -c "Mandatory" scripts/generate_ci_status.py` ≥ 1. Owner: implementer. Council: no.

### D2 — `STATE.md` source-status counts
- `scripts/generate_state.py::source_counts()` reads `docs/SOURCE_REGISTRY.yaml` with `yaml.safe_load` (PyYAML is already a dependency) and counts `observed.status` per source. Remove the regex on `observed_status:`.
- Extend `scripts/test_generate_state.py` with a fixture registry containing at least two statuses and assert the rendered section.

**Acceptance:** after `python scripts/generate_state.py`, `docs/STATE.md` "Source Status Counts" lists non-empty counts summing to 52 (or the current registry length). Owner: implementer. Council: no.

### D3 — `STATE.md` "Next:" line
- The generator renders the first complete sentence (or the whole first paragraph, ≤ 300 chars) of the active report's prerequisites section, never a fragment ending in `:` or `:.`.
- Test with a fixture whose first line ends with a colon.

**Acceptance:** `grep '^Next:' docs/STATE.md` ends with a period and contains no trailing `:` fragment. Owner: implementer. Council: no.

### D4 — Backup script test actually runs, and runs on PostgreSQL
- Add `scripts/__init__.py` so `unittest discover` collects `scripts/test_*.py`. Confirm this does **not** double-run `test_sync_mirror.py` / `test_generate_state.py` in CI (remove the explicit invocations from `.github/workflows/test.yml` if it does, or keep them and accept duplication — Master decides and records).
- Rewrite `scripts/test_backup_restore.py` to use `OPPORTUNITYOS_DB_URL` when it is a PostgreSQL URL (two schemas or two databases in the same server are both acceptable), and to **fail** (not skip) when `CI` is set and the URL is missing or non-PostgreSQL. Outside CI without PostgreSQL it may skip with a visible reason.

**Acceptance:** CI log for the branch contains `test_backup_restore` collected and `ok`; `env -u OPPORTUNITYOS_DB_URL CI=true python -m unittest scripts.test_backup_restore` exits non-zero with a clear message. Owner: implementer. Council: no.

### D5 — Restore is Alembic-aware; backup is complete
- `restore_database()` no longer calls `init_db()`/`create_all()`. It runs the Alembic upgrade to head programmatically against the target URL (use `alembic.config.Config("alembic.ini")` + `alembic.command.upgrade`, honouring `OPPORTUNITYOS_DB_URL` override the same way `alembic/env.py` does), then loads data.
- `dump_database()` derives its table list from `Base.metadata.sorted_tables` and raises `BackupCompletenessError` if any model table is missing from the dump order or vice-versa. Hand-maintained table lists are removed.
- Extend Case M (`storage/test_postgres_integration.py::test_case_m_backup_wipe_restore_postgres_cycle`) to assert: after wipe + restore, `alembic_version.version_num == <head>`, and the restored table set equals `Base.metadata.tables` keys.
- The backup remains unencrypted; state this in the script docstring and leave `REQ-SEC-003` MISSING.

**Acceptance:** Case M passes on real PostgreSQL with the new assertions; `grep -n "create_all\|init_db" scripts/backup_restore.py` returns nothing. Owner: implementer. **Council: YES (migration/restore path).**

### D6 — Integration suite fails loudly in CI without PostgreSQL
- `storage/test_postgres_integration.py::setUpClass`: if `os.environ.get("CI")` is truthy and the DSN is missing or non-PostgreSQL, `raise AssertionError` (fail), else `SkipTest` with the existing message. Remove the `"sqlite:///opportunityos.db"` default string entirely.

**Acceptance:** `CI=true env -u OPPORTUNITYOS_DB_URL python -m unittest storage.test_postgres_integration` reports ERROR/FAIL, not skipped; with a valid PostgreSQL DSN all 15 cases pass. Owner: implementer. Council: no.

### D7 — REPORT-FR-002 erratum
- Append a section `## Erratum (2026-09-02, BRIEF-FR-003)` to `reports/REPORT-FR-002.md`. Do not rewrite the original body.
- Contents: (a) the real per-module test counts from the Mandatory run at `889dee1` — truth 99, outbound 81, recon 67, opportunity 60, matching 52, inbox 25, storage 19, core 4, worker 3, security 3, feedback 1, total 414 — with the CI run ID `33550202403`; (b) a corrected requirement-delta table using real matrix IDs: `REQ-P0C-002` PostgreSQL → DONE; `REQ-RUN-002`/`REQ-RUN-003` were already DONE and are removed from the delta; `REQ-INB-006` removed (it is analytics); founder-feedback backend is recorded against the acceptance-script step 13 line, not a matrix row; `REQ-P0C-003` → PARTIAL (queue only, no runner); `REQ-SRC-003` → REQUIRES_LIVE_INTEGRATION_OR_CREDENTIALS; `REQ-SRC-011…016` → REQUIRES_LIVE_INTEGRATION_OR_CREDENTIALS; `REQ-SRC-017…020` → PARTIAL; (c) a note that `scripts/test_backup_restore.py` was not executed in that run; (d) a note that the FastAPI/Next.js slice named as "BRIEF-FR-003" in that report is renumbered **BRIEF-FR-004** (so `docs/STATE.md` "Next Prerequisites" stops describing FR-003 as the web brief once REPORT-FR-003 exists).

**Acceptance:** section present; every req ID in it exists in `FOUNDER_READINESS_MATRIX.json` (test in D8 enforces this). Owner: implementer (docs). Council: no.

### D8 — Readiness matrix regenerated and mechanically reconciled
- Update `reports/FOUNDER_READINESS_MATRIX.json` statuses to reflect `889dee1` + this brief's closures (D10 flips `REQ-P0C-003` to DONE only if D10 passes). Apply exactly the status changes listed in D7(b) plus the FR-002 credits the audit accepted: `REQ-RUN-001`, `REQ-P0C-005`, `REQ-SEC-007`, `REQ-ART-004`, `REQ-ART-005`, `REQ-SRC-004`, `REQ-OPP-008`, `REQ-SEC-005` (scope-limited note) → DONE. Add a `status_history` list per row with `{brief, from, to, date}`.
- Add `scripts/generate_readiness_matrix.py` that renders `reports/FOUNDER_READINESS_MATRIX.md` **from** the JSON: totals by status/criticality/phase/bucket, and the full table. Hand-edits to the `.md` are prohibited from now on (add this to AGENTS.md "Where Things Live").
- Add `scripts/test_readiness_matrix.py`: (i) every `req_id` unique; (ii) every status in the allowed set; (iii) rendered totals equal JSON counts; (iv) every `REQ-` ID mentioned in `reports/REPORT-FR-002.md` erratum and `reports/REPORT-FR-003.md` exists in the JSON.
- Add a note to `REQ-P0C-002`: "workspace column present on 2 of 11 tables; multi-tenant scoping deferred to the Phase 6 gate (ADR-0012)".

**Acceptance:** `python scripts/generate_readiness_matrix.py --check` exits 0 (md is up to date); tests pass; totals sum to 143. Owner: implementer. Council: no.

### D9 — ADR-0012 single-founder tenancy
- `docs/adr/ADR-0012-single-founder-tenancy.md` (template format): decision that Phase 0–5 persistence is single-workspace; enumerates the 9 tables without a workspace key; states that Phase 6 entry requires a tenancy migration brief; status Accepted.

**Acceptance:** file exists, follows `docs/adr/TEMPLATE.md`, `check_repository.py` passes. Owner: implementer (docs). Council: no.

### D10 — Worker runner (closes "queue with no consumer")
- `worker/runner.py`: `WorkerRunner(session_factory, handlers: Mapping[str, Callable[[dict], None]], *, worker_id, lease_seconds=60, poll_interval=1.0, stop_event: threading.Event | None = None)`.
  - `run_once() -> bool`: claim one job via `BackgroundWorkerQueue.claim_next_job`, dispatch by `job_type`, `complete_job` on success, `fail_job(error)` on exception; unknown `job_type` → `fail_job` with a distinctive message; returns whether a job was processed.
  - `run_forever(max_jobs: int | None = None)`: loops until `stop_event` is set or `max_jobs` reached; sleeps `poll_interval` when idle; handles `SIGINT`, and `SIGTERM` where the platform provides it, by setting the stop event (only when running as the main thread; Windows delivers `SIGINT` via Ctrl+C only).
  - Structured logging via the existing `core` logging/redaction utilities; never logs payload secrets.
- `worker/__main__.py`: `python -m worker` reads `OPPORTUNITYOS_DB_URL` through `get_production_db_url()` (fail closed), builds the default handler registry, and runs forever. `--once` and `--max-jobs N` flags for tests/ops.
- `worker/handlers.py`: exactly two handlers: `noop` (for smoke) and `poll_source` — which takes `{"source_id": ...}`, checks `SourceRegistry.is_read_allowed` (refuse otherwise, recording the refusal), and invokes the existing governed acquisition path for that source with an injectable fetcher. **No network in tests**; the handler's fetcher is injected with fixture data.
- Tests:
  - `worker/test_runner.py` (unit, explicit SQLite injection allowed per the existing unit-test convention): dispatch, unknown type, exception → fail_job, retry → dead letter after `max_retries`, stop_event honoured, `max_jobs` honoured.
  - `storage/test_postgres_integration.py::test_case_s_worker_runner_end_to_end`: real PostgreSQL; enqueue 5 jobs (3 noop, 1 poll_source with fixture, 1 always-failing with `max_retries=1`); run two `WorkerRunner`s concurrently in threads with `max_jobs`; assert each job completed exactly once, the failing job reaches `DEAD_LETTER`, no job is processed twice, and the `poll_source` job for a read-disabled source (`ashby:openai`) records a refusal rather than fetching.
- `AGENT_PERMISSIONS.yaml` is unchanged; the runner performs reads only.

**Acceptance:** all new tests pass; `python -m worker --once` with a valid DSN exits 0 and logs one idle poll; with the DSN unset it exits non-zero with `ProductionDatabaseConfigurationError`. Owner: implementer. **Council: YES (concurrency / background jobs).**

### D11 — Robots re-recon for `ashby:*`, `jobicy`, `afdb`
- Using the existing recon tooling only (no new crawlers), re-check `robots.txt` and the documented access policy for the Ashby posting API host, jobicy, and afdb. Obey AGENTS.md hard rules: stop on 403/429/CAPTCHA/anti-bot; never work around.
- Update each entry's `observed` block and `last_policy_reviewed` in `docs/SOURCE_REGISTRY.yaml`. Flip `automation.read` to `allowed` **only** if the recon result and the registry's own policy rules permit it; otherwise leave `disabled` and record the reason. Append findings to `docs/SOURCE_EVIDENCE.md` under a dated heading.
- If the session has no outbound network, record `BLOCKED_ENV` for D11 in the report with the exact error; do not fabricate observations.

**Acceptance:** `last_policy_reviewed` for all 15 entries ≥ 2026-09-02, or a `BLOCKED_ENV` entry; recon test suite still 67 passing. Owner: implementer (Sonnet, with WebFetch). Council: no.

### D12 — CI hygiene
- Bump `actions/checkout` and `actions/setup-python` to their current latest majors (verify on GitHub; do not guess).
- Workflow keeps exact-main semantics, PostgreSQL 16 service, `alembic upgrade head`, single `unittest discover`, guard and integrity checks.
- `CI=true` is set by GitHub automatically; do not add it manually.

**Acceptance:** `Mandatory Governance & Test Suite` green on the PR branch; no `Node.js 20 is deprecated` warning in its log. Owner: implementer. Council: no.

### D13 — Provider-name policy (Overseer decision, default applies unless the founder overrides before merge)
- New documents written in this brief and after are vendor-neutral (roles, not product names: "Master", "implementer", "verifier", "council reviewer"). Existing history is not rewritten.
- Add one line to AGENTS.md: "Reports and ADRs name roles, not model vendors."

**Acceptance:** `grep -rniE "antigravity|chatgpt|codex|copilot|gemini" reports/REPORT-FR-003.md docs/adr/ADR-0012*.md` returns nothing. Owner: Master. Council: no.

### D14 — Generated state, report, evidence, PR
- `python scripts/generate_state.py` → commit `docs/STATE.md`.
- `reports/REPORT-FR-003.md` in the §10 format.
- `reports/evidence/FR-003/` containing `CLAIMS.md` and one captured output file per claim (see §7). Evidence files are plain text; secrets redacted by construction (they must not exist). Note `reports/**` is on the public mirror allowlist, so evidence files are published: they must contain only command output, never environment dumps or absolute home paths (the CI test-DB password is already public in the workflow and is acceptable; nothing else is).
- Branch `feat/brief-fr-003-reality-refresh`; PR to `main` titled `BRIEF-FR-003: reality refresh and runtime closure`; PR body = the report's §1 summary + the claim ledger table.

**Acceptance:** PR open, all four workflows green on the PR head, report and evidence present. Owner: Master. Council: no.

---

## 3. Execution order and parallelism

**Pre-flight (mandatory, before D0):**

```
git fetch origin
git checkout main
git pull --ff-only origin main
git rev-parse HEAD            # expected: 889dee1cf4acdc3a38abf2e634bfce38453ae2ee
git status --porcelain        # expected: only the untracked briefs/BRIEF-FR-003.md and empty .claude/
```

If `HEAD` is not `889dee1`, list the intervening commits with `git log --oneline 889dee1..HEAD`. Proceed only if every one is a docs/STATE sync or otherwise doc-only; record the actual starting SHA in the report header as a deviation. If any intervening commit touches a `.py` file or a workflow, stop and return `BLOCKED` with that list — the audit baseline no longer holds. If `git status` shows other modified tracked files, do not proceed on a dirty tree; report what is dirty.

Then create the working branch: `git checkout -b feat/brief-fr-003-reality-refresh`, and commit `briefs/BRIEF-FR-003.md` as the first commit on it.

```
D0 (Master, 10 min)
  ├─ Batch A (parallel, worktrees): D1, D2, D3, D8-script, D9, D12       → implementer ×3 (Sonnet)
  ├─ Batch B (parallel, worktrees): D4+D5+D6 (one implementer, same files), D10 (one implementer)
  └─ Batch C (sequential after B): D7, D8-data (needs D10 result), D11, D13
Integrate → A-0 fail-closed probe → full suite on real PG → verifier (Opus) over CLAIMS.md
  → council (Fable) on D5 and D10 diffs → remediate → re-verify only failed claims
  → D14
```

Worktrees are mandatory for any two implementers writing at the same time. The Master integrates; implementers never merge.

---

## 4. Roles and model routing

| Role | Model | Effort | Tools | Used for | Budget guard |
|---|---|---|---|---|---|
| **Master** (main session) | `opus` | high | all | owns the brief; writes acceptance commands before delegating; runs every acceptance command itself before accepting a deliverable; integrates; writes the report | one session |
| **implementer** | `sonnet` | high | Read, Edit, Write, Bash, Grep, Glob, WebFetch (D11 only) | code + tests for one deliverable at a time | `maxTurns: 60` per delegation |
| **evidence-runner** | `haiku` | — | Bash, Read, Grep, Glob (no Write outside `reports/evidence/`) | runs the exact commands in CLAIMS.md and captures outputs; reports numbers verbatim; no judgment | `maxTurns: 25` |
| **verifier** | `opus` | high | Read, Grep, Glob, Bash (no Edit/Write) | fresh context; re-executes every acceptance command; returns PASS/FAIL per claim with the observed output; never told what the implementer concluded | once over the full ledger, then only on re-submitted claims |
| **council-reviewer** | `fable` | high | Read, Grep, Glob, Bash (no Edit/Write) | independent first-pass review of the D5 and D10 diffs against their requirement text only; returns numbered findings with severity | **exactly two invocations** in this brief; a third requires a hard-stop justification in the report |
| Explore (built-in override) | `haiku` | — | read-only | codebase search | — |

Rationale: Opus carries the judgment (ownership, integration, verification). Sonnet carries the volume. Haiku carries the mechanical capture. Fable is used only where the OS §13.2 high-consequence list applies (migrations, concurrency) and the information value of a stronger independent reader is highest. Per-token, Fable is roughly double Opus; two narrow read-only reviews are the right amount.

---

## 5. Master loop (the review-and-return contract)

For each deliverable:

1. **Before delegating**, the Master writes the acceptance commands into `reports/evidence/FR-003/CLAIMS.md` under that deliverable's ID (command, expected result, evidence filename).
2. Delegate to one implementer with: the deliverable text, the acceptance commands, the frozen-brief rule, and the instruction "return a diff summary and the raw output of each acceptance command; do not summarise test results — paste the `Ran N tests` line and the final `OK`/`FAILED` line."
3. **On return, the Master runs every acceptance command itself.** If any fails or differs from the implementer's claim, the Master sends the implementer a **numbered defect list** (what was expected, what was observed, file:line where known) and resumes the same implementer. The Master never patches an implementer's deliverable to make it pass; it returns it.
4. Loop 3 up to **five times** per deliverable. On the fifth failure: spawn the verifier on that deliverable alone for a diagnosis, then one more implementer cycle. If still failing → the deliverable is reported `NOT_CLOSED` with the defect history; it is not silently dropped and the brief is not called PASS.
5. After all deliverables are accepted by the Master: evidence-runner captures every claim's output to its evidence file; verifier re-executes the whole ledger in a fresh context. Any verifier FAIL reopens step 3 for that deliverable.
6. Council review for D5 and D10 (diff + requirement text only). Each finding is either fixed (back to step 3) or dispositioned in the report with a reason. "Won't fix" without a reason is not a valid disposition.
7. Only claims marked PASS by **both** the Master and the verifier may appear as "done" in the report.

Subagents do not spawn subagents (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`).

---

## 6. Environment requirements

- Execution host: the founder's Windows machine, Claude Code in VS Code, repository cloned locally. Use the Bash tool (Git Bash) for the acceptance commands as written; they are POSIX-shell commands.
- Python 3.12, `pip install -e .`.
- **Line endings:** before any edit, run `git config core.autocrlf` and, if it is not `false` or `input`, set `git config core.autocrlf input` for this repository only. A-6 must show no line-ending-only diffs; if `git diff --stat` reports whole files changed with no semantic change, fix the line-ending setting and re-check out those files.
- **Real PostgreSQL 16 in the session** is required for D4, D5, D6, D10 acceptance. Try, in order, and record which one worked in the report:
  1. An existing local server: `pg_isready -h localhost -p 5432` or `Get-Service postgresql*`.
  2. Docker Desktop if present: `docker run -d --name opos-pg -e POSTGRES_USER=opportunityos -e POSTGRES_PASSWORD=testpassword123 -e POSTGRES_DB=opportunityos_test -p 5432:5432 postgres:16-alpine`.
  3. User-space portable binaries (no admin rights needed): download the PostgreSQL 16 Windows binaries zip from EnterpriseDB (`https://www.enterprisedb.com/download-postgresql-binaries`), extract under `%LOCALAPPDATA%\opos-pg\` (outside the repository), then `initdb -D <data> -U opportunityos -A trust`, `pg_ctl -D <data> -o "-p 5432" start`, `createdb -U opportunityos opportunityos_test`.
  4. `winget install PostgreSQL.PostgreSQL.16` (may require an elevation prompt; only if 1–3 fail).
  Use the CI credentials (`opportunityos` / `testpassword123` / `opportunityos_test`) so `OPPORTUNITYOS_DB_URL` matches `.github/workflows/test.yml`. Stop the server at the end of the session; do not leave a portable cluster in the repository tree (`.gitignore` covers `out/` and `private/` only).
- If none of these succeed, the Master must still complete every non-PostgreSQL deliverable, push the branch, and rely on the Mandatory workflow on the PR for PostgreSQL evidence. In that case every PG-dependent claim in the report is labelled `CI_VERIFIED_ONLY` and the Master must read the PR's CI conclusion before declaring PASS (via `gh` if authenticated, else by stating that the Overseer must confirm from the run log). Never claim a local PostgreSQL pass that did not happen.
- D11 needs outbound HTTPS to the three hosts; the local machine has it. Obey AGENTS.md rate and stop rules.

---

## 7. Claim ledger and evidence

`reports/evidence/FR-003/CLAIMS.md` has one row per claim:

| ID | Deliverable | Command | Expected | Evidence file | Master | Verifier |
|---|---|---|---|---|---|---|

Mandatory rows (in addition to each deliverable's acceptance commands):

- **A-0 fail-closed probe** — the seven-class probe from the audit (unset env, `sqlite:///` env, explicit `sqlite:///` arg to the two PG adapters, orchestrator with `store=None`, valid PG DSN constructs). Commit it as `storage/test_fail_closed_probe.py` so it runs in CI permanently. Expected: 7/7 raise under misconfiguration; 5/5 construct under a valid DSN.
- **A-1 full suite** — `python -m unittest discover -v 2>&1 | tail -3` on real PostgreSQL. Expected: `Ran N tests`, `OK`, N ≥ 414 + the new tests, 0 skipped.
- **A-2 per-module counts** — derived from the same run, listed in the report. No count may be typed from memory.
- **A-3 migration round-trip** — `alembic upgrade head && alembic downgrade base && alembic upgrade head` exit 0.
- **A-4 guard and integrity** — `check_guard.py` (with `.github/pii-patterns.txt` present) and `check_repository.py` pass.
- **A-5 state sync** — `python scripts/generate_state.py --check` (or diff against a fresh render) shows no drift.
- **A-6 no semantic drift outside scope** — `git diff --stat main...HEAD` lists no file outside the paths named in §2.

---

## 8. Definition of done

PASS requires all of: every deliverable D0–D14 closed (or explicitly `NOT_CLOSED`/`BLOCKED_ENV` with history), A-0…A-6 PASS by Master and verifier, council findings for D5/D10 all fixed or dispositioned, four workflows green on the PR head, report and evidence committed, `docs/STATE.md` regenerated, and no file changed outside §2's paths.

---

## 9. Hard stops (the only reasons to return before PASS)

Per the operating system §7.2: credential exposure; any action that would perform an external mutation (submit/apply/POST other than the TED read-only exception); a frozen-policy contradiction that cannot be resolved from repository evidence; a required tool that is absent and has no fallback (report `BLOCKED_ENV` for that deliverable only and continue the rest). A failing test, a missing package, or a worktree problem is never a hard stop.

---

## 10. Final report format — `reports/REPORT-FR-003.md`

1. Header: brief, date, starting SHA, final SHA, PR URL, CI run IDs.
2. Status: PASS / PASS_WITH_NOT_CLOSED / BLOCKED, one sentence.
3. Deliverable table: ID, status, evidence files, Master verdict, verifier verdict, council verdict (D5/D10), loop count.
4. Test evidence: exact `Ran N tests` line, per-module counts from that run, skipped count (must be 0), migration round-trip result.
5. Claim ledger (copy of CLAIMS.md with both verdict columns filled).
6. Council findings and dispositions.
7. Requirement delta with real IDs, and the regenerated matrix totals.
8. Deviations from this brief, each with a reason.
9. Overseer review packet: PR URL; instruction to download the branch zip and the Mandatory run's log archive.
10. Recommendation for BRIEF-FR-004 (one paragraph; do not start it).

Reports name roles, not vendors.

---

## Appendix A — `.claude/agents/` definitions

Five files. Keep `description` short (they load into every session's context); put detail in the body.

```markdown
<!-- .claude/agents/implementer.md -->
---
name: implementer
description: Implements one brief deliverable with tests. Use for code and doc changes scoped to a single deliverable ID.
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch
model: sonnet
effort: high
maxTurns: 60
isolation: worktree
---
You implement exactly one deliverable from the active brief, with its tests.

Rules:
- Read docs/STATE.md, the active brief, and AGENTS.md first. Frozen briefs are not reopened.
- Change only the files the deliverable names. If the deliverable cannot be done without touching another file, stop and report why instead of expanding scope.
- Write the test before or with the change. Run the narrow test, then `python -m unittest discover -v` from the repo root, and paste the final `Ran N tests` and `OK`/`FAILED` lines verbatim. Never summarise test results in words.
- Run every acceptance command you were given and paste its raw output.
- Never fabricate an observation. If a command cannot run in this environment, say so with the error.
- Return: (1) files changed, (2) raw acceptance outputs, (3) anything you could not verify.
```

```markdown
<!-- .claude/agents/evidence-runner.md -->
---
name: evidence-runner
description: Runs the exact commands in a claim ledger and captures raw outputs to evidence files. Mechanical only; no judgment.
tools: Bash, Read, Grep, Glob, Write
model: haiku
maxTurns: 25
---
You execute commands exactly as written in reports/evidence/<brief>/CLAIMS.md and save each output to the evidence filename given, under reports/evidence/<brief>/. You may write only inside that directory.

Report back a table: claim ID, exit code, first line of output, last line of output. Do not interpret results. Do not modify any command.
```

```markdown
<!-- .claude/agents/verifier.md -->
---
name: verifier
description: Independently re-executes every claim in a claim ledger in a fresh context and returns PASS/FAIL per claim. Use after the Master has accepted deliverables.
tools: Read, Grep, Glob, Bash
model: opus
effort: high
maxTurns: 40
---
You are an independent verifier. You are not told what the implementer or the Master concluded, and you do not read their summaries; you read the code, the tests, and the claim ledger.

For each claim: run the command yourself, compare the observed output with the expected result, and return PASS or FAIL with the observed output. For any FAIL, state the smallest reproduction. Flag any claim whose command does not actually test what the expected-result text asserts.

Also check: no `create_all`/`init_db` in scripts/backup_restore.py; no default SQLite string in storage/test_postgres_integration.py; scripts/__init__.py exists; the fail-closed probe file exists and passes; `git diff --stat main...HEAD` lists no file outside the brief's scope.

Return a single table and nothing else.
```

```markdown
<!-- .claude/agents/council-reviewer.md -->
---
name: council-reviewer
description: Independent high-consequence review of a single diff against its requirement text. Use only for migrations, concurrency, auth, or schema changes named by the active brief.
tools: Read, Grep, Glob, Bash
model: fable
effort: high
maxTurns: 30
---
You review one diff against one requirement. You are given the requirement text and the diff, nothing else; do not read the implementer's or the Master's reasoning.

Look for: correctness under concurrency and restart; migration and restore ordering; silent fallbacks; fail-open paths; tests that pass without exercising the requirement; anything the requirement demands that the diff does not deliver.

Return numbered findings, each with severity (BLOCKER / MAJOR / MINOR), file:line, and the specific change that would resolve it. If there are no findings, say so in one line. No prose beyond the findings.
```

```markdown
<!-- .claude/agents/Explore.md -->
---
name: Explore
description: Fast read-only codebase search.
tools: Read, Grep, Glob
model: haiku
---
Search and summarise. Never edit.
```

## Appendix B — `.claude/settings.json`

```json
{
  "env": {
    "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1"
  },
  "permissions": {
    "deny": [
      "Bash(git push --force*)",
      "Bash(git push -f*)",
      "Read(./.env*)",
      "Read(./private/**)"
    ]
  }
}
```

## Appendix C — Overseer decisions embedded in this brief (override before merge if you disagree)

1. FR-003 is this closure brief; the API/web slice is FR-004.
2. The worker runner is in scope (it closes a finding rather than adding a feature).
3. Provider names are dropped from new documents; history is untouched.
4. Backup stays unencrypted for now; `REQ-SEC-003` stays MISSING.
5. Merge to `main` happens after Overseer review of the PR, not autonomously.
