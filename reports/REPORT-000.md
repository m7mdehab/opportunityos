# REPORT-000 — Repository Foundation & Assistant Interoperability

**Date:** 2026-08-27
**Version:** 1.3

## Scope completed

- Created private authoritative repository `m7mdehab/opportunityos` and public derived repository `m7mdehab/opportunityos-docs` with the required visibility and engineering descriptions.
- Added the deliberate repository subset, canonical `AGENTS.md`, Claude import, private-data boundary, unchanged Master Plan, verbatim Product Constitution, templates, permissions, source registry, and accepted ADR-0001.
- Implemented generated state, report/brief and ADR integrity checks, all-path secret scanning, allowlisted-path PII scanning, guarded clean mirror sync, and nightly drift detection and repair.
- Generated an ED25519 deploy key outside the working tree, stored its private half only as `MIRROR_DEPLOY_KEY`, installed the public half as a verified write-enabled deploy key, and blanked the temporary key files after registration.
- Configured PR workflows for `state`, `guard`, and `mirror`; all three checks pass on the current `main` history.
- Intentionally deferred all product frameworks, servers, databases, deployment stacks, source adapters, personal founder data, LLM integrations, and placeholder directories listed out of scope.
- Public review clone: `git clone https://github.com/m7mdehab/opportunityos-docs.git`
- First successful mirror sync source SHA: `7acac24`.
- Remediated the v1.1 phase findings under BRIEF-000 v1.3 without rebuilding accepted foundation work.

## Test evidence

- `python scripts/generate_state.py`, `python scripts/check_repository.py`, and `python scripts/check_guard.py` pass locally with Python 3.12 and no third-party dependencies.
- A hand-edited `docs/STATE.md` failed the `state` check in pull request 1; the probe was closed without merge.
- An unmatched `REPORT-999.md` failed with `RULE REPORT_BRIEF_PAIRING` and an exact remedy; the fixture was reverted.
- A fake API key failed with `RULE SECRET_OPENAI_KEY`; the fixture was reverted.
- An email under `docs/` failed both guard and mirror boundary checks in pull request 2, and the public mirror HEAD remained unchanged.
- The same email-shaped fixture under non-mirrored `scripts/` passed, proving PII scope is allowlist-specific; the fixture was reverted.
- Pull request 3 published `docs/mirror-removal-probe.md`; pull request 5 deleted it, and the subsequent mirror lookup returned HTTP 404.
- Mirror commits use `sync: <source-short-sha>`; the current sync was produced by one successful Mirror workflow run after merge.
- A local mirror was committed as `sync: 0000000`; `check_mirror.py` exited 2, clean reassembly produced `sync: 1c08120`, and the follow-up check exited 0.
- A fresh public clone contained the required review context, reported a current mirror SHA, and `git grep -i` for known founder-name variants returned no match.
- Maker/checker repair loop: a rebase-merge SHA rewrite caused one post-merge state failure; the state was regenerated and merge-commit PR handling was verified with all three checks green.
- Serial work covered instructions, skeleton, and allowlist first; scripts and governance artifacts followed; mirror workflow and remote configuration were last.

## v1.3 remediation

- Corrected active-phase selection to choose the lowest-numbered brief not passed. While this report recorded FAIL, generated state showed BRIEF-000 active with `failed — remain in phase`; after this PASS decision it advances to BRIEF-001 with `in progress`.
- Added `Phase status`, renamed the private currency field to `State generated at commit`, and joined wrapped acceptance-item continuation lines into complete sentences.
- Derived the canonical identity from `gh api user --jq '.name'`, expanded full-name transliterations, surname-prefix forms, orderings, and eligible email-local forms algorithmically, validated zero current mirror matches plus a planted scratch match, and streamed the JSON pattern set directly into the `FOUNDER_NAME_PATTERNS` repository secret.
- Removed inferred name values from tracked patterns. CI now fails closed when `FOUNDER_NAME_PATTERNS` is absent; local structural scans require the explicit `--allow-missing-patterns` flag.
- Widened `.mirror-allowlist` only to `scripts/**`, `.github/workflows/**`, `.github/pii-patterns.txt`, and `.mirror-allowlist`; the expanded public boundary passes the full guard.
- Accepted ADR-0002, documenting advisory CI, conventional PR discipline, residual-risk ownership, the `--no-verify` hole, and all three revisit triggers.
- Added and documented idempotent `scripts/install_hooks.sh`; a committed stale-state probe was refused by the pre-push hook and no remote branch was created.
- Added six-hour and push-triggered `heartbeat.yml`. Its public commits stage exactly `docs/CI_STATUS.md`; the first publication reported HEALTHY.
- Pushed one deliberate stale-state commit through the documented `--no-verify` hole. `state` failed, heartbeat still completed successfully, and public status reported `CHECKS FAILING`. A normal hook-verified repair restored green checks.
- Reverted the public mirror ref to a previously boundary-scanned `sync: f67f004` commit. Heartbeat reported `MIRROR STALE`; normal mirror and heartbeat workflow dispatches restored `HEALTHY` at private SHA `f8d55cd`.
- Reporting-time private `main` SHA: `f8d55cd`. Reporting-time `docs/CI_STATUS.md` verdict: `HEALTHY`.

## Failures and known limitations

- None.

## Residual risks

- Private branch enforcement is intentionally advisory under accepted ADR-0002; the founder owns the documented residual quality-drift risk.
- Local hooks remain explicitly bypassable with `--no-verify`. The mirror boundary scan is load-bearing and remains mandatory immediately before every public sync.

## Outcome evidence

- The public mirror is readable without credentials and now exposes the enforcement scripts, workflow definitions, structural PII patterns, allowlist, generated CI heartbeat, governance, briefs, state, and reports.
- Claude chat can inspect agent instructions, current state, governance, briefs, reports, registry, and ADRs without access to code or private founder data.
- The current mirror README states plainly that the mirror is read-only, derived, non-authoritative, rejects pull requests, and is disposable after a leak.
- The final heartbeat reports `HEALTHY`, all three private checks successful, and mirror currency current.

## What this changes about the plan

- The two-repository interoperability model is viable and automated on GitHub Free.
- Master Plan §12.9's branch-protection requirement is unachievable on a zero-budget personal GitHub plan with a private repository. The plan should carry accepted ADR-0002's advisory policy and revisit triggers instead of treating paid enforcement as a current gate.
- The standing delegation rule from BRIEF-000 v1.3 §2.6 now governs every future brief, including briefs authored upstream: executable work stays with the agent unless it falls within the exhaustive exception list.
- Generated state must be committed after source-changing commits and PRs must use merge commits; rebase or squash rewrites the recorded source SHA and correctly makes the state check red.

## Decision

PASS

All BRIEF-000 v1.3 acceptance criteria pass. BRIEF-001 source reconnaissance is unblocked.

## Deferred acceptance items

- None.

## Next phase prerequisites

- Begin BRIEF-001 source reconnaissance using the active brief, accepted ADRs, generated state, advisory pre-push hook, and public heartbeat.
