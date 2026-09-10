# CI Efficiency Policy

Effective 2026-09-11. This is durable OpportunityOS operating policy for minimizing private GitHub-hosted Actions spend without weakening repository, truth, mirror, or product validation.

## Objective

Use the least expensive capable execution surface while preserving the same acceptance predicates, source/truth protections, mirror boundary, and autonomous engineering quality.

## Standing rules

1. GitHub Actions remains the independent merge proof. Use local development or Codespaces for iterative lint/test/build/debug loops when the same toolchain is available, then push coherent checkpoints rather than micro-pushes.
2. Never weaken Guard, State, repository integrity, mirror publication boundaries, source-policy checks, backend tests, web build/lint, Playwright, truth-lock, idempotency, or external-action safety to save minutes.
3. Use `ubuntu-slim` for lightweight Git/Python/SSH repository jobs that fit its 15-minute ceiling and need no browser, Docker daemon, PostgreSQL service, privileged operation, or heavyweight build.
4. Keep full Ubuntu runners for the Mandatory backend/web suite and any job that needs PostgreSQL, browser installation, substantial dependency/build work, or capabilities absent from slim.
5. Keep superseded read-only validation cancelable. Do not cancel Mirror/Heartbeat merely to save cost because they write durable public status/mirror state and require ordered completion semantics.
6. Prefer event-driven execution. Existing periodic Mirror/Heartbeat checks remain at their current cadence unless an equivalent mechanism replaces that SLA.
7. Do not add a hosted scheduled workflow without estimating monthly run count and whole-minute billing impact first.
8. Keep the public `opportunityos-docs` mirror disposable and subordinate to the private repository. Public-repository cost economics never justify moving private truth or private runtime state into the public repo.

## Current runner allocation

- `guard.yml`: `ubuntu-slim`, same secret and mirrored-PII scan.
- `state.yml`: `ubuntu-slim`, same deterministic state-generation diff and repository integrity checks.
- `mirror.yml`: `ubuntu-slim`, same mirror-only guard, clean-tree assembly, publish-tree scan, drift detection, SSH publication, and retry semantics.
- `heartbeat.yml`: `ubuntu-slim`, same event/scheduled cadence and single-file CI-status publication semantics.
- `test.yml`: full runner. Do not move the mandatory backend/web test lane to slim because it needs the heavier service/build/browser toolchain.

## Agent execution rule

A fresh agent must read this file before changing workflows, scheduling new automation, or splitting a lightweight job onto a full hosted runner. If a future change moves a slim job back to a full runner, record the missing capability or measured reliability reason. If runner-level independence is not an acceptance requirement, prefer reuse over duplicate hosted setup.
