# ADR-0001 — Private Source with Public Documentation Mirror

- **Status:** accepted
- **Date:** 2026-08-27
- **Phase:** BRIEF-000
- **Supersedes:** none
- **Superseded by:** none

## Context

Working code has no reason to be public, so the authoritative repository should be private. One reviewing assistant, Claude in the chat interface, has no GitHub credentials or connector and cannot read a private repository. Independent report review therefore needs a separately readable documentation trail.

The mirror is an accessibility workaround for that tooling limitation, not a security measure. The content guard is necessary hygiene for the mirrored subset, but it is not the reason for the topology.

## Decision

Keep `opportunityos` private and authoritative. Publish only `.mirror-allowlist` matches to the public, derived, read-only, disposable `opportunityos-docs` repository after the boundary guard passes.

## Consequences

Claude chat can review governance, briefs, state, evidence, and reports without seeing working code. CI and private-repository checker agents remain responsible for validating code claims. A leaked mirror is deleted and recreated from the private source.

The public mirror is inherently attributable to the founder through the GitHub account namespace. The PII boundary protects mirrored content—CV text, applications, tracker data, personal contact details, and similar records—not repository ownership attribution. The founder-name content patterns therefore exclude the GitHub handle, which necessarily appears in repository URLs.

## Alternatives considered

- **Fully public:** rejected because it unnecessarily exposes working code.
- **Fully private:** rejected because it removes independent report review by Claude chat.
- **Read-only token pasted into chat:** rejected because it is worse for security and manual effort.

## Required tests and rollback

Guard the exact publish set, sync from a clean checkout, delete stale mirror paths, and detect drift nightly. Roll back by deleting the public mirror and recreating it from the private repository.
