# ADR-0003 — Geographic Eligibility Model

- **Status:** accepted
- **Date:** 2026-08-28
- **Phase:** BRIEF-001
- **Supersedes:** none
- **Superseded by:** none

## Context

A boolean eligibility result discarded the posting rule that produced it and
made Egypt-specific logic difficult to audit or reuse for MENA expansion.

## Decision

Store evidence-backed `geo_allow`, `geo_deny`, `work_mode`, and unmapped source
phrases on each normalized record. Use the closed Addendum B vocabulary and a
single readable region-membership table. Derive results through the pure
`eligibility_for(record, country="EG")`; Egypt is the default argument, never a
hardcoded extraction rule.

## Consequences

Deny beats allow, country allowlists can exclude Egypt explicitly, and the same
stored corpus supports later queries for other countries. Extending vocabulary
or region membership requires a new ADR.

## Required tests and rollback

Assert extraction and derivation for all mandated cases, including conflicting
allow/deny cases. Roll back by retaining stored evidence and replacing only the
derivation function; never reconstruct rules from a discarded boolean.
