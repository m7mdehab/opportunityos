# REPORT-000 — Repository Foundation & Assistant Interoperability

**Date:** 2026-08-27

## Scope completed

- Created private authoritative repository `m7mdehab/opportunityos` and public derived repository `m7mdehab/opportunityos-docs` with the required visibility and engineering descriptions.
- Added the deliberate repository subset, canonical `AGENTS.md`, Claude import, private-data boundary, unchanged Master Plan, verbatim Product Constitution, templates, permissions, source registry, and accepted ADR-0001.
- Implemented generated state, report/brief and ADR integrity checks, all-path secret scanning, allowlisted-path PII scanning, guarded clean mirror sync, and nightly drift detection and repair.
- Generated an ED25519 deploy key outside the working tree, stored its private half only as `MIRROR_DEPLOY_KEY`, installed the public half as a verified write-enabled deploy key, and blanked the temporary key files after registration.
- Configured PR workflows for `state`, `guard`, and `mirror`; all three checks pass on the current `main` history.
- Intentionally deferred all product frameworks, servers, databases, deployment stacks, source adapters, personal founder data, LLM integrations, and placeholder directories listed out of scope.
- Public review clone: `git clone https://github.com/m7mdehab/opportunityos-docs.git`
- First successful mirror sync source SHA: `7acac24`.

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

## Failures and known limitations

- GitHub returned HTTP 403 when private `main` branch protection was requested: the personal account must upgrade to GitHub Pro or make the repository public. Making the source public is forbidden, paid spend exceeds the zero-budget cap, and no guard was weakened. PR discipline and green checks exist, but GitHub does not enforce them server-side on this plan.
- The founder-name scanner uses locally inferred common name variants because no canonical founder-name value exists in the supplied project documents. Mirrored content is independently clean of those variants, email addresses, and international phone patterns.

## Outcome evidence

- The public mirror is readable without credentials and contains 15 tracked files: generated README plus only the four seeded allowlist classes.
- Claude chat can inspect agent instructions, current state, governance, briefs, reports, registry, and ADRs without access to code or private founder data.
- The current mirror README states plainly that the mirror is read-only, derived, non-authoritative, rejects pull requests, and is disposable after a leak.

## What this changes about the plan

- The two-repository interoperability model is viable and automated on GitHub Free.
- The zero-spend requirement conflicts with enforced branch protection for a private repository on the founder's current personal GitHub plan. The plan must either fund GitHub Pro, move the private repository to an organization plan that supports protection, or explicitly accept unenforced PR discipline until that prerequisite changes.
- Generated state must be committed after source-changing commits and PRs must use merge commits; rebase or squash rewrites the recorded source SHA and correctly makes the state check red.

## Decision

FAIL / remain in phase

The repository, guard, state, and mirror acceptance tests pass, but BRIEF-000 §6.9 requires server-enforced private-branch protection and the zero-budget GitHub plan refuses it.

## Deferred acceptance items

- None. All checkbox acceptance tests passed; the unresolved item is the mandatory branch-policy scope requirement in §6.9.

## Next phase prerequisites

- Enable branch protection support for the private repository without changing its visibility, then require pull requests and the `state`, `guard`, and `mirror` contexts on `main`.
- After protection is verified, regenerate this report decision and `docs/STATE.md`; BRIEF-001 source reconnaissance can then proceed.
