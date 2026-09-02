# ADR-0015 — Predicate Contract Between the Truth Graph and the Matching Engine

- **Status:** Accepted
- **Date:** 2026-09-03
- **Phase:** BRIEF-FR-005 (D2)
- **Supersedes:** none
- **Superseded by:** none

## Context

BRIEF-004 shipped a scorer and qualifier (`matching/scorer.py`,
`matching/qualification.py`) that read `AtomicAssertion.predicate` strings the
truth graph never emits. `truth/graph.py` projects predicates exclusively from
`CANONICAL_MATERIAL_MANIFEST` (`truth/models.py:649-735`), a frozen,
BRIEF-002-owned list of `(model class, field name) -> predicate` pairs. Nothing
in `matching/` had ever been checked against that manifest, and it drifted:
`matching/scorer.py` read `responsibility.item`, `employment.role_description`,
`experience.summary`, and `achievement.description` where the graph actually
emits `employment.responsibility` and `achievement.statement`. Because no
founder-shaped fixture exercised those assertions, the `responsibility_scope`
dimension silently returned a flat 0.50 for every founder, employment or
independent, real or synthetic — the scorer could not see the founder's
career at all on that dimension. Seven more sites carried the same class of
defect (`docs/STATE.md` and this brief's issuing prompt enumerate them).

Not every predicate `matching/` reads is a defect, though. The truth pack
format also accepts a top-level `assertions:` section
(`truth/ingest.py:566-576`, `parse_assertion`) that lets a pack author assert
*any* predicate string directly, with its own evidence, independent of any
profile projection. `career.target_role`, `preference.track`, `career.goal`,
and the founder's residence/location facts have always been supplied this
way — never projected by `truth/graph.py`, and never meant to be. Before this
ADR, nothing distinguished "the graph doesn't emit this because it's a typo"
from "the graph doesn't emit this because it was never supposed to." A fix
that just added spellings to `CANONICAL_MATERIAL_MANIFEST` would have been
wrong twice: it would still leave `matching/` free to invent new predicate
strings unchecked, and it would try to make BRIEF-002's frozen graph semantics
answer a question that belongs to the pack format, not the graph.

## Decision

1. **One committed registry, `truth/predicates.py`.** Every predicate
   `matching/scorer.py` and `matching/qualification.py` may reference is
   declared exactly once, as either:
   - **PROJECTED** — derived programmatically from
     `truth.models.CANONICAL_MATERIAL_MANIFEST`, so this half of the registry
     cannot drift from what `truth/graph.py` actually emits without a source
     change to the (frozen) manifest itself.
   - **ASSERTION_ONLY** — declared by hand, each with the owning pack section
     (`assertions`, per `truth/ingest.py:566-576`) and a description of why no
     profile field projects it. This is not a defect list; it is a contract
     that these predicates carry no profile-projection guarantee and must be
     treated as founder-supplied, not graph-derived.
2. **`matching/` never spells a predicate string itself.** `scorer.py` and
   `qualification.py` import named constants (`predicates.SKILL_NAME`,
   `predicates.RESPONSIBILITY_SCOPE_PREDICATES`, …) instead of writing
   `"skill.name"` inline. A predicate typo becomes an `ImportError` or a
   registry `KeyError`, not a silent flat score.
3. **The responsibility/achievement fix reads what the graph emits.**
   `responsibility_scope` (`matching/scorer.py`) now filters on
   `predicates.RESPONSIBILITY_SCOPE_PREDICATES = (employment.responsibility,
   achievement.statement)` — the two predicates BRIEF-002's graph actually
   projects for a founder's work history — in place of the five orphan
   spellings it read before.
4. **Every other mismatch is fixed by spelling correction, not by widening
   the graph.** `capacity.annual_turnover_usd` is the real projected name for
   both `business.annual_turnover` and `capacity.annual_turnover`;
   `work_authorization.jurisdiction` is the real name for
   `authorization.jurisdiction` and the bare `work_authorization`;
   `language.language` is the real name for `language.name`;
   `portfolio.title` is the real name for `portfolio.item`. Where no manifest
   field exists at all for the concept read (`capacity.team_size`, the
   premium full-time/on-site compensation threshold), the predicate is
   declared ASSERTION_ONLY rather than invented as a fake profile field.
5. **A contract test enforces this going forward, without a hand-maintained
   duplicate list.** `truth/test_predicates.py` parses `matching/scorer.py`
   and `matching/qualification.py` with `ast`, finds every string literal
   compared against an attribute named `predicate` (the pattern `a.predicate
   == "..."` / `a.predicate in (...)` used throughout both files), and
   asserts each one is declared in the registry. Because this walks source
   text rather than a maintained list, it keeps catching drift as the code
   changes.
6. **Scope boundary: this ADR governs `AtomicAssertion.predicate` (the truth
   graph's assertion vocabulary), not `GeneratedClaim.predicate`.**
   `matching/validator.py`, `matching/compiler_employment.py`, and
   `matching/compiler_independent.py` use a `predicate` field on
   `GeneratedClaim` (`matching/models.py:153`) as an internal claim-type tag
   (`"metric"`, `"summary"`, `"employment.record"`, …) that is a distinct,
   D1-owned vocabulary and is not covered by this registry or its contract
   test. `matching/mapping.py` reads `AtomicAssertion.predicate` directly and
   carries the identical orphan-predicate defect this ADR fixes in
   `scorer.py`/`qualification.py`, but `mapping.py` is out of D2's file scope
   and is recorded as a known, unfixed instance of the same defect for a
   future deliverable.

## Consequences

- The `responsibility_scope` dimension is no longer structurally incapable of
  reflecting a founder's actual work history; a founder-shaped graph with real
  `employment.responsibility`/`achievement.statement` assertions now scores
  above the previous flat 0.50, with non-empty `evidence_refs`.
- Any future predicate added to `matching/scorer.py` or
  `matching/qualification.py` must be added to `truth/predicates.py` first, or
  the contract test fails at commit time rather than silently degrading a
  scoring dimension months later.
- `matching/mapping.py` (out of D2 scope) still reads the same five orphan
  predicate names `responsibility_scope` used to read. It is not touched by
  this ADR and remains a defect for the next deliverable to own.
- The premium full-time/on-site compensation rule
  (`preference.fulltime_onsite_premium_monthly`) is declared ASSERTION_ONLY:
  its threshold value lives in the founder's pack, never in code, and it
  participates only in the `compensation_fit` ranking dimension — it cannot
  change a qualification decision, and unstated or currency-mismatched
  compensation is always treated as unknown, never as a penalty.

## Alternatives considered

- **Add the orphan spellings to `CANONICAL_MATERIAL_MANIFEST`.** Rejected:
  BRIEF-002's graph projection semantics are frozen, and doing so would make
  the graph lie about what evidence actually supports those predicates for
  fields that were never modeled (e.g. there is no `BusinessCapacity.team_size`
  field to project from).
- **A hand-maintained list of "known predicates" inside the contract test.**
  Rejected: it would immediately become exactly the kind of silently-stale
  list this ADR exists to eliminate. The registry is instead derived from the
  manifest programmatically, and the test walks source code via `ast`.

## Required tests and rollback

- `truth/test_predicates.py` — registry completeness, PROJECTED/ASSERTION_ONLY
  classification, and the founder-shaped re-score assertion.
- `matching/test_scorer.py`, `matching/test_qualification.py` — updated
  fixtures and premium-rule unit tests (EGP, USD, unknown, non-full-time).
- Rollback: revert `truth/predicates.py`, the `matching/scorer.py` and
  `matching/qualification.py` predicate-lookup call sites, and this ADR in one
  commit; no schema or migration is involved.
