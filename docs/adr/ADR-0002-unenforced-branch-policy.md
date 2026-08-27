# ADR-0002 — Unenforced Private Branch Policy

- **Status:** accepted
- **Date:** 2026-08-27
- **Phase:** BRIEF-000
- **Supersedes:** BRIEF-000 v1.1 §6.9
- **Superseded by:** none

## Context

GitHub Free provides neither protected branches nor rulesets for this private personal repository. BRIEF-000 v1.1 simultaneously required server-enforced protection, private visibility, and zero spend, making that policy internally contradictory.

The repository currently has two writers: the founder and Claude Code. There are no external collaborators, deployments, or users. The current threat model contains mistakes, not an adversarial writer.

## Decision

Private `main` is not server-protected. CI is advisory and pull-request discipline is convention. Each clone installs the idempotent `scripts/install_hooks.sh` pre-push check, but any writer can bypass it explicitly with `git push --no-verify`.

## Consequences

A commit failing `state` or `guard` can land on `main`, and `docs/STATE.md` can become stale without a server-side block. This is quality drift, not public data leakage.

The mirror boundary remains protected: `mirror.yml` re-runs the PII scan immediately before publication. A bad commit on private `main` therefore still cannot publish personal data to the public mirror. This redundant boundary scan is now load-bearing.

The founder owns the residual risk.

## Revisit triggers

- A non-founder gains write access.
- Anything deploys that serves a person other than the founder.
- The account moves to a paid GitHub plan for any other reason.

## Alternatives considered

- **GitHub Pro at roughly four dollars monthly:** deferred, not refused; it violates the current zero-spend cap.
- **Make the source public:** rejected under ADR-0001 because it unnecessarily exposes working code.

## Required tests and rollback

Verify the hook refuses a stale-state push and the mirror boundary still blocks PII. When a revisit trigger fires, enable server-enforced pull requests and required `state`, `guard`, and `mirror` checks, then supersede this ADR.
