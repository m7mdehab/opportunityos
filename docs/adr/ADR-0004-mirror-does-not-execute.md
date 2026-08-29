# ADR-0004 — Mirror Does Not Execute

- **Status:** accepted
- **Date:** 2026-08-28
- **Phase:** BRIEF-001
- **Supersedes:** none
- **Superseded by:** none

## Decision

Mirrored content must never sit at a hosting-platform executable path. Publish
workflow references under `ci-reference/`; disable Actions in the public mirror
as defence in depth. Review every future allowlist entry for executable paths.
