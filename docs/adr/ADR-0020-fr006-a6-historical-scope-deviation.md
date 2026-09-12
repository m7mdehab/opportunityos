# ADR-0020 — FR-006 A-6 is an accepted historical deviation, not a retroactive PASS

**Status:** accepted  
**Date:** 2026-09-12  
**Scope:** BRIEF-FR-006 A-6 historical scope-diff disposition only

## Context

FR-006 froze A-6 before implementation: compare the eventual branch diff with the pre-committed closed path set in `reports/evidence/FR-006/a6-expected-scope.md`; if any observed path falls outside it, the expected set must never be widened after observation.

The recorded result was 740 changed paths: 739 were inside that pre-committed set and one was not. Deviation 94 identifies the extra path as a local SQLite artifact, `opportunityos.db`, accidentally committed during the brief. It was not an intended product artifact. The repository now ignores `*.db`, and the local database artifact is not part of the current source tree.

The recovery contract permits three truthful outcomes for A-6: PASS through a pre-existing accepted-deviation mechanism, an explicit accepted historical deviation, or an irreducible historical governance exception. Rewriting the frozen expected set is prohibited.

## Decision

A-6 is permanently recorded as **ACCEPTED_HISTORICAL_DEVIATION**.

It is **not PASS** and the original expected set is not edited. The historical observation remains exactly 740 total / 739 expected / 1 unexpected (`opportunityos.db`). The deviation has no surviving runtime/product artifact, the offending class of local artifact is now ignored by repository policy, and future scope checks remain subject to their own pre-committed sets.

For FR-006 closure accounting, this status satisfies only the requirement to disposition the immutable historical exception honestly. It must never be rendered as `PASS`, `740/740 expected`, or otherwise rewritten to imply the deviation never occurred.

## Consequences

- Historical evidence remains immutable and auditable.
- Generated/reporting state may distinguish `ACCEPTED_HISTORICAL_DEVIATION` from both `PASS` and an unresolved engineering blocker.
- No product, security, source-policy, or truth-lock behavior is weakened.
- The repository remains protected against recurrence by its `*.db` ignore rule and repository guard practices.

## Rejected alternatives

1. **Add `opportunityos.db` to the old expected set.** Rejected as retroactive threshold gaming.
2. **Call A-6 PASS because the file was later removed.** Rejected because deletion does not change the historical diff that A-6 measured.
3. **Leave A-6 indefinitely ambiguous.** Rejected because the recovery brief explicitly requires a permanent disposition of this immutable historical fact.
