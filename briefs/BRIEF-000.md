# BRIEF-000 — Repository Foundation & Assistant Interoperability

**Version:** 1.3 — agent-derived identity; standing delegation rule
**Project:** OpportunityOS
**Issued to:** Master Development Agent (Claude Code)
**Date:** 27 August 2026
**Supersedes:** v1.2, which was never executed. Replaces `briefs/BRIEF-000.md`.
Full v1.1 text remains in git history.
**Status of phase:** remain in phase. Revise REPORT-000 in place.

---

## 0. What is already delivered — do not rebuild

Both repositories, the skeleton, `AGENTS.md`, `CLAUDE.md`, the constitution and
plan copies, templates, `AGENT_PERMISSIONS.yaml`, `SOURCE_REGISTRY.yaml`,
ADR-0001, the deploy key, `state.yml`, `guard.yml`, `mirror.yml`,
`generate_state.py`, `check_mirror.py`, `check_guard.py`,
`check_repository.py`, and the mirror sync chain all passed under v1.1 and are
accepted. Do not re-create, re-verify, or refactor them except where this brief
requires a change.

---

## 1. Founder prerequisites

**None.**

Every item in this brief is executable by the agent with the access it already
has. If any step appears to need the founder, re-read §2.6 before surfacing it.

---

## 2. Work

Apply in order. **2.2 must complete before 2.3.**

### 2.1 Active-brief logic — blocking

`generate_state.py` derives the active brief as the highest-numbered brief with
no matching report. That advanced `STATE.md` to BRIEF-001 while recording
`Last Phase Outcome: FAIL / remain in phase`. Since `AGENTS.md` tells every
agent to read `STATE.md` first, the next session starts the wrong phase — the
exact failure the file exists to prevent.

Correct rule: the active brief is the **lowest-numbered brief that has not
passed**. A brief has passed only when a matching report exists **and** its
Decision section does not contain `FAIL`. The summary line at the top of
`STATE.md` must agree with the detail section. Add a `Phase status` field
reading `in progress`, `passed`, or `failed — remain in phase`.

### 2.2 Founder-name patterns — derived by the agent, stored as a secret

REPORT-000 line 34 records that the name scanner uses locally inferred variants
because no canonical value exists in the repository. The control reports green
while not matching the founder's actual name. Fix it without asking him.

**Derive the canonical identity** from sources already available to you, in
this priority order, taking the first that yields a real value:

1. `gh api user --jq '.name'`
2. `git config --get user.name` and `git config --get user.email`
3. `git log --format='%an|%ae' | sort -u` across the private repository

**Expand variants algorithmically.** For an Arabic name this set is large and
enumerable. Cover at minimum: given-name transliterations
(Mohammed / Mohamed / Muhammad / Mohamad / Muhammed and equivalents for each
name element); surname prefix forms (`El-X`, `El X`, `ElX`, `Al-X`, `AlX`,
bare `X`); full-name orderings; and the email local part. Match
case-insensitively.

**Validate before storing.** The pattern set must produce **zero** matches
against current mirrored content, and must match a deliberately planted variant
in a scratch file. A pattern set that fires on the repository's own
documentation is unusable and must be narrowed until both conditions hold.

**Store it** with `gh secret set FOUNDER_NAME_PATTERNS --repo <private>`, reading
from stdin. Never write the value to a tracked file, and scrub any temporary
file afterwards.

**Guard behaviour.** `check_guard.py` reads the patterns from the environment.
If the variable is unset in CI, **the guard fails**. A missing secret must never
degrade to a skip, or the hollow-green problem returns in a new form. Local runs
without it exit non-zero unless `--allow-missing-patterns` is passed explicitly.

Remove all inferred name variants from `.github/pii-patterns.txt`; that file
keeps only structural patterns — emails, phone shapes, key shapes, file types.

**Do not include the GitHub handle.** It appears in every repository URL, so
scanning for it would fail the guard against its own documentation. Record in
ADR-0001 consequences that the mirror is inherently attributable to the founder
through the account namespace, and that the PII boundary protects content — CV
text, applications, tracker data — not attribution.

**Only if all three derivation sources yield nothing** is this a hard gate. Say
so explicitly in the report and name which sources were tried.

### 2.3 Widen `.mirror-allowlist`

The review could not verify any guard, because the enforcement layer is not
mirrored. Add:

```text
scripts/**
.github/workflows/**
.github/pii-patterns.txt
.mirror-allowlist
```

After 2.2 these contain no personal data. Add nothing else.

### 2.4 Amended branch policy — replaces v1.1 §6.9

Server-enforced branch protection is **withdrawn as a requirement**. GitHub Free
offers neither protected branches nor rulesets on private repositories, and v1.1
set a zero-spend cap in the same document. The requirement was contradictory,
not the implementation.

**`docs/adr/ADR-0002-unenforced-branch-policy.md`**, status `accepted`, recording:

- **Decision:** private `main` is not server-protected; CI is advisory; PR
  discipline is convention.
- **Why acceptable now:** two writers, the founder and Claude Code. No external
  collaborators, no deployment, no users. No adversary in the threat model, only
  mistakes.
- **What is lost:** a commit failing `state` or `guard` can land on `main`, and
  `STATE.md` can go stale unblocked. Quality drift, not data leakage.
- **What still holds:** `mirror.yml` re-runs the PII scan immediately before
  publishing, so a bad commit on private `main` still cannot push personal data
  to the mirror. That redundancy is now load-bearing.
- **Residual risk owner:** the founder.
- **Revisit triggers:** a non-founder gains write access; anything deploys
  serving a person other than the founder; the account moves to a paid GitHub
  plan for any other reason.
- **Rejected:** GitHub Pro at roughly four dollars monthly (deferred, not
  refused); making the source public (rejected under ADR-0001).

**`scripts/install_hooks.sh`** — idempotent, installs a `pre-push` hook running
the same checks as `state.yml` and `guard.yml` and refusing the push on failure.
Document in `AGENTS.md` and `README.md`. Bypassable only via explicit
`--no-verify`; name that hole in ADR-0002.

### 2.5 CI visibility in the mirror — `heartbeat.yml`

A guard failure aborts the sync, so today a broken `main` and a healthy one look
identical to anyone reading only the mirror. Staleness and failure are
indistinguishable.

New workflow, scheduled every six hours and on push to `main`, which **always
runs to completion and never aborts on a failing check**. It writes exactly one
file to the mirror, `docs/CI_STATUS.md`, containing:

- private `main` short SHA and commit subject
- UTC timestamp
- conclusion of the most recent `state`, `guard`, and `mirror` runs for that SHA
- whether the mirror's last `sync:` SHA equals private `main`
- a one-line verdict: `HEALTHY`, `CHECKS FAILING`, or `MIRROR STALE`

It publishes that file and nothing else, scans it before pushing, and must not
be able to publish repository content by any path. `gh api` for check
conclusions is permitted.

### 2.6 Standing delegation rule — add to `AGENTS.md` and `briefs/TEMPLATE.md`

This is a permanent project rule, not a one-time instruction. Add it verbatim to
`AGENTS.md` as its own section, and to `briefs/TEMPLATE.md` so every future brief
inherits it:

> **Delegation rule.** Anything the agent can do, the agent does. Never return a
> task to the founder that is executable in this environment. Before surfacing
> any request for founder action, check it against the exception list; if it is
> not on that list, do it.
>
> **Exceptions, exhaustive:** interactive authentication requiring the founder's
> own credentials or a browser OAuth flow; any action requiring payment;
> accepting terms of service or entering a binding agreement; professional legal
> or accounting sign-off; and communication with another human being.
>
> Everything else is the agent's: deriving values, generating configuration,
> setting secrets, choosing names, installing tooling, writing tests, and making
> reversible technical decisions. Surfacing an executable task as a founder
> prerequisite is a defect, and should be reported as one.

### 2.7 State currency fields

`STATE.md` shows `Source HEAD` and `Mirror sync` as different SHAs — correct by
construction, unreadable in practice. Rename `Source HEAD` to `State generated
at commit` and let the mirror-sync line be the single currency indicator. Keep
both values.

### 2.8 Acceptance-item parser

The parser truncates wrapped markdown list items mid-sentence, so `STATE.md`
misreports open acceptance criteria. Join continuation lines — indented lines
not beginning a new list item — before recording each item.

---

## 3. Scope — out

Unchanged from v1.1 §8, plus: no refactoring of accepted v1.1 work, no widening
of the allowlist beyond §2.3, no paid GitHub plan, no new repositories.

---

## 4. Acceptance criteria

Items verified under v1.1 are checked and must not be re-run.

**Carried forward — accepted**
- [x] Both repositories exist with correct visibility and structure
- [x] `AGENTS.md` under 150 lines, directs the reader to `STATE.md` first
- [x] `CLAUDE.md` line one is `@AGENTS.md`
- [x] Generated state, guards, mirror sync, deletion propagation, drift
      detection, and fresh-clone review context all verified
- [x] ADR-0001 records the real reasoning and rejected alternatives

**Identity and guards**
- [ ] `FOUNDER_NAME_PATTERNS` is set from an agent-derived value with no founder
      involvement, and the report names the source used
- [ ] The pattern set produces zero matches against current mirrored content
- [ ] The guard matches a planted founder-name variant in a mirrored path
- [ ] `check_guard.py` fails in CI when `FOUNDER_NAME_PATTERNS` is unset
- [ ] `.github/pii-patterns.txt` contains no name variants
- [ ] The secret value appears in no tracked file and no temporary file survives

**Branch policy**
- [ ] ADR-0002 exists, `accepted`, with all fields including the three revisit
      triggers and the `--no-verify` hole
- [ ] `install_hooks.sh` is idempotent and documented in both files
- [ ] A commit failing the state check is refused by the pre-push hook

**Heartbeat**
- [ ] `docs/CI_STATUS.md` publishes to the mirror
- [ ] With `main` deliberately red, the heartbeat still runs and reports
      `CHECKS FAILING`
- [ ] With the mirror artificially reverted, it reports `MIRROR STALE`
- [ ] The heartbeat cannot publish any file other than `CI_STATUS.md`

**State and delegation**
- [ ] With REPORT-000 recording FAIL, `STATE.md` reports BRIEF-000 as active
- [ ] Once REPORT-000 passes, `STATE.md` advances to BRIEF-001
- [ ] `Phase status` appears and agrees with the summary line
- [ ] The delegation rule appears verbatim in `AGENTS.md` and `briefs/TEMPLATE.md`
- [ ] The mirror contains `scripts/`, `.github/workflows/`, `pii-patterns.txt`,
      and `.mirror-allowlist`, and still no personal data
- [ ] `STATE.md` open acceptance items are complete sentences

---

## 5. Report

Revise `reports/REPORT-000.md` in place. Keep v1.1 test evidence, append a
remediation section, update the Decision.

In "What this changes about the plan", record two things: that Master Plan §12.9's
branch-protection requirement is unachievable on a zero-budget personal GitHub
plan with a private repository and the plan should carry ADR-0002 instead; and
that the delegation rule in §2.6 now governs every future brief, including
briefs authored upstream.

Include the private `main` SHA and the `CI_STATUS.md` verdict at reporting time.

```yaml
phase_id: BRIEF-000
version: 1.3
objective: remediate REPORT-000 findings; agent-derived identity; delegation rule
founder_prerequisites: none
final_report_only: true
council_required: false
budget_cap: zero external spend
ordering: 2.2 before 2.3; 2.1 is blocking
next_brief: BRIEF-001 (source reconnaissance) — unblocked once REPORT-000 passes
```