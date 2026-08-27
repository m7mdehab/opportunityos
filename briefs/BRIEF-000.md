# BRIEF-000 — Repository Foundation & Assistant Interoperability

**Version:** 1.4 — defects found in review of the v1.3 implementation
**Issued to:** Master Development Agent (Claude Code)
**Date:** 27 August 2026
**Supersedes:** v1.3. Replaces `briefs/BRIEF-000.md`.
**Status of phase:** REPORT-000's PASS is **withdrawn**. Revise it in place to
`FAIL / remain in phase` until §1 is fixed, then restore the pass.

Reviewed from the public mirror at `c1fd7c3`. The allowlist widening in v1.3
made this review possible; three of these four defects were invisible before it.

---

## 0. Accepted — do not rebuild

Everything delivered under v1.1 and v1.3 stands except the four items below.
The fail-closed check in `check_guard.py:59` is correct. The identity validation
in `derive_founder_patterns.py:139` is well designed — refusing any pattern set
that matches existing mirrored content structurally prevents the GitHub-handle
mistake rather than relying on an instruction. The temporary-directory handling
is clean. The active-brief fix works. The heartbeat correctly exits zero when
reporting a bad verdict instead of failing the job.

---

## 1. The publish boundary does not scan for secrets — blocking

`check_guard.py:74` gates the entire secret-pattern block behind
`if not args.mirror_only:`. `mirror.yml:29` runs `check_guard.py --mirror-only`
as its "Re-scan exact publish boundary" step.

So the last check before publishing to a public repository does not look for
private keys, GitHub tokens, OpenAI keys, AWS access keys, connection strings,
or `.env` files. It checks names and structural PII only.

This defeats the stated purpose of that step. BRIEF-000 v1.1 §7.3 required the
re-scan specifically because a leak into a private repository is recoverable and
a leak into a public mirror is not. It also invalidates a claim in REPORT-000:
that a bad commit on private `main` still cannot push personal data to the
mirror. That holds for names. It does not hold for credentials.

ADR-0002 makes this reachable rather than theoretical. With CI advisory and
`--no-verify` documented as a known hole, a credential can land in `docs/` on
`main` with `guard.yml` red, and `mirror.yml` will then publish it to a public
repository and into permanent git history.

**Fix:** `--mirror-only` must mean *restrict to mirrored paths*, not *skip secret
checks*. Separate the two concerns — one flag selects the path set, another
selects which check families run — and run both families over the mirrored path
set at the boundary. Add an acceptance test that plants a fake key in a mirrored
path and confirms the sync aborts.

---

## 2. Duplicate workflow runs — the source of the failure emails

`guard.yml` and `state.yml` both declare a bare `on: push:` with no branch
filter, alongside `on: pull_request:`. For a pull request from a branch in the
same repository, both events fire, so each workflow runs twice per push. One
logical failure produces four notifications.

**Fix:** `on: push: branches: [main]` plus `pull_request:` on both workflows.
Confirm in the report that a single failing PR now produces one notification per
workflow.

---

## 3. Heartbeat and Mirror race each other

`mirror.yml:14` sets `concurrency: opportunityos-docs-mirror`.
`heartbeat.yml` has no concurrency block at all. Both trigger on push to `main`
and both push commits to the same public repository.

Two consequences, both observable in the mirror history:

- The heartbeat can read the mirror before `mirror.yml` has synced and report a
  spurious `MIRROR STALE`. Commit `8b8e6fc` reports `MIRROR STALE` at 15:30
  alongside `5a598c5 sync: f8d55cd` at the same minute.
- Both push to the mirror's `main`. The heartbeat retries three times with
  rebase (`heartbeat.yml:73`). `mirror.yml:98` pushes with **no retry at all**,
  so when the mirror loses the race the job fails outright and emails.

**Fix:** trigger the heartbeat on `workflow_run` completion of Mirror rather than
on push, so it always reads a post-sync mirror. Keep the schedule and
`workflow_dispatch`. Put both workflows in the `opportunityos-docs-mirror`
concurrency group regardless, and give `mirror.yml`'s push the same
conflict-safe retry the heartbeat already has.

---

## 4. Generated files reach the mirror unscanned

`sync_mirror.py:77-78` writes `README.md` and rewrites `STATE.md` into the
destination *after* `mirror.yml:29` has run the boundary scan. Those two files
are published without being checked.

The heartbeat gets this right — it generates `CI_STATUS.md`, scans it at
`heartbeat.yml:53`, then publishes. The mirror should match.

**Fix:** move the boundary scan to run against the assembled destination tree
immediately before commit, or scan the generated files individually after
assembly. Low risk today since both are template-generated, but it is an
unscanned publish path and the asymmetry with the heartbeat is the tell.

---

## 5. Note, not a defect

`derive_founder_patterns.py:166` prints the pattern set to stdout. No workflow
calls it, which is correct. Add a comment saying so: if it is ever run inside
Actions, the founder's name variants land in a build log.

---

## 6. Acceptance criteria

- [x] `check_guard.py --mirror-only` runs secret patterns over mirrored paths
- [x] A planted fake API key in a mirrored path aborts the mirror sync and
      nothing is pushed
- [x] A planted fake API key in a non-mirrored path still fails the full guard
- [x] `guard.yml` and `state.yml` fire once per push and once per PR, not twice
- [x] A single failing PR produces one notification per workflow
- [x] Heartbeat runs on `workflow_run` after Mirror, plus schedule and dispatch
- [x] Heartbeat and Mirror share the `opportunityos-docs-mirror` concurrency group
- [x] `mirror.yml`'s push retries on conflict like the heartbeat's does
- [x] Ten consecutive merges produce no spurious `MIRROR STALE` and no failed run
- [x] `README.md` and `STATE.md` are scanned before publication
- [x] `derive_founder_patterns.py` carries the stdout warning comment
- [x] REPORT-000 returns to PASS only after all of the above

---

## 7. Report

Revise `reports/REPORT-000.md` in place. Under "What this changes about the
plan", record that the mirror boundary scan was narrower than the brief that
required it, and that the widened allowlist is what surfaced it — the review
that caught this was only possible because `scripts/` and `.github/workflows/`
became visible in v1.3.

```yaml
phase_id: BRIEF-000
version: 1.4
objective: fix publish-boundary secret scanning, duplicate runs, mirror race,
  and unscanned generated files
founder_prerequisites: none
final_report_only: true
budget_cap: zero external spend
blocking: §1
next_brief: BRIEF-001 — unblocked once REPORT-000 returns to PASS
```
