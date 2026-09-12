# ADR-0019 — Deprecate unresolved FR-006 F4 shorthand aliases

**Status:** accepted  
**Date:** 2026-09-12  
**Scope:** FR-006 evidence/readiness bookkeeping only

## Context

BRIEF-FR-006 F4 refers to readiness rows by the shorthand labels `1B`, `1H`, `2A`, `2B`, `2C`, `3C`, `3E`, and `1G`. Exhaustive repository review recorded during FR-006 found no authoritative definition of those labels in the readiness matrix, Master Plan, reports, or requirement identifiers. The actual readiness matrix is keyed by stable `req_id` values such as `REQ-SAF-001`.

Inventing a mapping from undocumented shorthand to real `req_id` values would falsify governance history. The recovery brief explicitly requires either tracing aliases to authoritative requirement IDs or explicitly deprecating dead aliases when no mapping exists.

## Decision

The eight shorthand labels are **deprecated as dead, non-authoritative aliases**. They SHALL NOT be used to mutate readiness rows and SHALL NOT be inferred onto `req_id` values.

Future readiness updates must name the authoritative `req_id` directly. If historical source material is later produced that defines one of these aliases unambiguously, a successor ADR may restore that alias with the exact source citation; until then the matrix remains unchanged by these labels.

## Consequences

- F4's ambiguous alias bookkeeping no longer blocks safe readiness maintenance.
- No readiness status changes as a result of this ADR.
- Historical FR-006 text containing the aliases remains untouched as evidence.
- Generated State and future briefs must use authoritative requirement IDs, not the deprecated shorthand.

## Rejected alternatives

1. **Guess the mapping from row order or semantic similarity.** Rejected because it would invent governance evidence.
2. **Rewrite the original brief.** Rejected because frozen historical acceptance text must remain auditable.
3. **Leave the aliases indefinitely unresolved.** Rejected because the recovery contract explicitly permits deprecation when no authoritative mapping exists.
