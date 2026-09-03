# ADR-0016 — Founder Seniority From Employment Tenure, Not Title Keywords

- **Status:** Accepted
- **Date:** 2026-09-03
- **Phase:** BRIEF-FR-006 (B1)
- **Supersedes:** none
- **Superseded by:** none

## Context

`matching/scorer.py`'s `seniority_and_experience` dimension decided whether a
founder was "senior" by substring-matching every verified `employment.title`
assertion against a fixed keyword list: `("senior", "sr", "lead", "principal",
"staff", "architect", "chief", "director", "head")`. The founder holds "Team
Lead" titles at two group companies. The substring `"lead"` alone made every
Senior/Lead/Principal/Staff posting look like a verified match, regardless of
how long the founder actually held the role, what it actually involved, or
whether it carried any people-management responsibility. Run against real
data, the alpha claimed "Senior matches founder experience" for postings the
founder's actual tenure and scope did not support. This is a scoring lie about
a real person, which `AGENTS.md`'s first hard rule ("never fabricate a claim
about the founder") forbids outright, not just discourages.

No structural signal in the truth graph distinguished a title that merely
*contains* a senior-sounding word from a founder who actually has the tenure,
role-family depth, or leadership scope a posting's stated level requires.
Fixing the keyword list (e.g., removing `"lead"`) would not fix the underlying
defect: any keyword list is one word away from being wrong in the other
direction, for a real person whose actual titles are what they are.

## Decision

1. **Seniority is computed from truth-graph tenure and text-derived
   leadership evidence, never from title keywords.** `matching/seniority.py`
   reconstructs `EmploymentSpan` records by grouping verified
   `employment.title` / `employment.organization` /
   `employment.market_facing_title` / `employment.start_date` /
   `employment.end_date` / `employment.responsibility` assertions by
   `AtomicAssertion.subject_id` (the same join key `truth/graph.py` uses for
   both profile-projected employment records and flat, directly-asserted
   fixtures), and links `achievement.statement` assertions back to a span only
   through a verified `RelationType.ACHIEVED_DURING` relation — the same
   relation `truth/graph.py::_wire_employment_achievement_relation` already
   establishes. A title with no verified start date computes no tenure; it is
   not treated as "since forever."
2. **Three computed signals, all evidence-backed:**
   - `total_professional_months` — elapsed tenure since the first
     **non-internship** role (title matching `\bintern(?:ship)?\b`,
     case-insensitive — the only structural signal available; the truth
     graph's `EmploymentRecord` model has no dedicated internship flag).
     Concurrent/overlapping roles are merged into a month-index interval union
     before summing, so three roles held at once inside one corporate group
     (the founder-shaped fixture's `group-holdings` /
     `group-logistics` / `group-analytics` roles) count their shared calendar
     time once, not three times. Back-to-back, non-overlapping roles with no
     gap between them are treated as continuous tenure.
   - `months_in_family` — tenure restricted to roles whose title (or
     market-facing title) matches a caller-supplied alias list. This is
     reported for context in the scorer's explanation text, but does not
     drive the pass/fail decision in this deliverable (see "What this model
     refuses to infer" below) — `matching/scorer.py` derives a simple,
     single-alias query from the opportunity's own title (stripping level
     words) until BRIEF-FR-006 B3 lands `matching/title_families.yaml` and
     wires a real family taxonomy in a separate change.
   - `has_people_leadership` — a regex over **responsibility and achievement
     text only** (`led the ... team`, `managed ... team`, `direct reports`,
     `mentored`, `supervised`, `people management`, …), returning the
     supporting evidence ids. `employment.title` and
     `employment.market_facing_title` values are never consulted by this
     check — see below for why.
3. **A committed threshold table**, `matching/seniority.py::SENIORITY_THRESHOLDS`:

   | Level     | Months floor | Requires leadership |
   |-----------|-------------:|:--------------------:|
   | junior    | 0            | no                    |
   | mid       | 24 (2y)      | no                    |
   | senior    | 60 (5y)      | no                    |
   | staff     | 120 (10y)    | yes                   |
   | principal | 180 (15y)    | yes                   |

   Rationale for the bands: 0–2y junior, 2–5y mid, and 5–8y+ senior follow
   common industry usage without asserting a false lower bound (a posting
   asking for "junior" is met by any verified professional history at all).
   Staff and Principal are modeled as individual-contributor levels that
   compound both raw tenure *and* demonstrated leadership scope; 10y/15y
   floors, paired with a hard leadership requirement, deliberately sit above
   what a single strong-but-unverified title claim could otherwise imply —
   the exact failure mode this ADR exists to close. `Opportunity.seniority`
   (`opportunity/models.py::SeniorityLevel`) has no separate `STAFF` member;
   `matching/scorer.py` maps `SeniorityLevel.LEAD` to this table's `"staff"`
   row (industry usage commonly treats "Staff" and "Lead" postings as the
   same band, both below Principal) and `EXECUTIVE` to `"principal"` as the
   nearest defined ceiling.
4. **A posting only earns a seniority *strength* when both conditions for its
   level are met**: `total_professional_months >= months_floor`, and, for
   staff/principal, `has_people_leadership` is true. Falling short of either
   produces a `gaps` entry naming the exact month shortfall (or the missing
   leadership evidence) and **no** strength — never a partial or implied
   match. `matching/scorer.py` deletes the old `is_senior` substring test
   entirely.
5. **Explanation text is generated from the computed numbers, never a fixed
   string.** `matching/seniority.py::explain()` renders "Founder: `<X>`
   professional; `<Y>` in `<family>`; role asks `<level>` (`<floor>`+[,
   leadership]); `<meets the bar | gap: <Z>>`." — the shape the brief
   specifies — from `SeniorityAssessment`'s fields, with `evidence_refs`
   carrying every assertion id (tenure) and, when applicable, every
   leadership-supporting assertion id.

## What this model refuses to infer

- **A title token is never leadership evidence.** A "Team Lead" title with no
  responsibility or achievement text describing team leadership does **not**
  set `has_people_leadership`. The reverse also holds: a plainly titled role
  ("Backend Engineer") whose responsibility text says "Led the data platform
  team of five engineers" **does** count — the evidence has to describe the
  thing, not just label the person.
- **An employment record with a title but no verified start date contributes
  zero months.** It is not treated as "no data, so assume average," and it is
  not silently dropped from `evidence_refs` bookkeeping — it simply never
  becomes an `EmploymentSpan`, so `assess()` returns `None` when no span
  exists at all, which the scorer reports as an explicit unknown, not a score.
- **Internship detection is a title-text heuristic, not a verified fact
  field**, because `truth.models.EmploymentRecord` carries no internship flag.
  This is named here, not hidden: a titled role that happens to contain the
  substring "intern" outside an actual internship context (unlikely, but
  possible) would be misclassified. Fixing this properly requires a truth-graph
  model change, which is out of this deliverable's frozen scope
  (`truth/models.py`, `truth/graph.py`).
- **`months_in_family` does not gate the pass/fail decision in this
  deliverable.** It is computed and reported for the founder's benefit
  (context: "how much of that tenure was in the role family the posting
  actually asks for"), but BRIEF-FR-006 B1's scope is explicitly the tenure
  and leadership model; wiring a real, committed role-family taxonomy
  (`matching/title_families.yaml`) is BRIEF-FR-006 B3's deliverable. Treating
  the current single-alias, level-word-stripped title heuristic as an
  authoritative family gate before B3 lands would be inventing a precision
  the model does not have.
- **No score is fabricated when the truth graph has no employment record at
  all.** `assess()` returns `None`; the scorer's dimension falls back to a
  neutral 0.5 with an explicit `unknowns` entry and no strength, the same
  shape the pre-existing "no verified employment history" branch already
  used.

## Consequences

- A pack whose only senior-sounding evidence is a "Team Lead" title, with no
  responsibility or achievement text describing leadership and insufficient
  tenure, no longer scores a seniority strength against a Staff/Principal
  posting — the defect this ADR exists to close.
- The founder-shaped fixture pack (`truth.fixtures.founder_shaped_graph()`,
  nine roles spanning 2016–2026, three concurrent inside one corporate group)
  computes to 108 verified professional months (9 years, correctly merging
  the concurrent group roles and the overlapping `freelance-cedar` /
  `mid-sahara` period into one continuous span) with verified leadership
  evidence from `group-holdings`'s responsibility text ("Led the shared data
  platform serving all group subsidiaries"). Against this table, that meets
  Mid (24mo), Junior (0mo), and Senior (60mo) postings, and falls short of
  Staff (120mo) and Principal (180mo) on tenure alone despite having
  leadership evidence — which is the acceptance behavior this deliverable's
  order specifies.
- **The founder-shaped fixture is not founder-shaped on tenure.** The brief's
  own context names the real founder as having roughly 20 months of tenure
  ("they do not make a 20-month-tenure founder 'senior' for a Staff/Principal
  engineering role"), but `founder_shaped_graph()` computes to 108 months
  (9 years) — a deliberately richer synthetic pack, frozen for this
  deliverable and depended on by other BRIEF-FR-006 work orders, not a
  stand-in for the real founder's actual tenure. The B1.6 acceptance script's
  Staff/Principal gap is therefore produced by a 120-month floor against a
  9-year pack, not by short tenure. §0's exact combined scenario — a
  short-tenure founder whose only senior-sounding evidence is a "Team Lead"
  title, scored end to end against a Staff/Principal posting — is a committed
  regression test, not just disclosed here:
  `matching/test_seniority.py::TestShortTenureTeamLeadDoesNotMatchStaffPosting::test_20_month_team_lead_title_earns_no_staff_strength`
  builds a local, non-fixture founder with exactly 20 verified professional
  months in a single "Team Lead" role whose responsibility text describes no
  leadership, runs it through `OpportunityScorer` against a Staff posting, and
  asserts both that no seniority strength is produced and that the gap names
  the month shortfall (`"120"` and `"20"` in the gap text).
  `matching/test_seniority.py::TestPeopleLeadershipEvidence::test_leadership_in_title_only_does_not_count`
  remains the narrower unit-level proof that `has_people_leadership` itself
  ignores title tokens, independent of tenure or the scorer.
- `matching/scorer.py`'s `seniority_and_experience` explanation now names
  real computed numbers (months professional, months in family, required
  level, gap) instead of a single fixed sentence
  (`"Seniority requirement evaluated as {level}."`).
- Any opportunity evaluated without `evaluated_at` parsing to a valid ISO date
  falls back to an unspecified "as of" reference for open-ended (no
  `end_date`) roles; every fixture and test in this deliverable supplies
  explicit end dates, so this fallback is not exercised by committed tests.

## Alternatives considered

- **Prune the keyword list instead of removing it.** Rejected: any fixed
  keyword list is a fresh instance of the same defect for whichever real
  title a future founder happens to hold. The fix has to stop reading titles
  for the seniority decision, not curate which titles it reads.
- **Gate strictly on `months_in_family` instead of `total_professional_months`.**
  Rejected for this deliverable: the brief's own worked example
  ("~2 years professional ... role asks Senior (5+). Gap: 3 years.") computes
  the gap from total professional months, and a real, committed family
  taxonomy does not exist yet (that is BRIEF-FR-006 B3). Gating on an
  admittedly provisional single-alias heuristic would trade one false
  precision for another.
- **Treat any title-token match as a legitimate leadership signal**, on the
  theory that a "Group Data Platform Lead" title is itself informative.
  Rejected: this is exactly the substring-matching defect the brief
  identifies by name. The model may only use text that describes what the
  person did.

## Required tests and rollback

- `matching/test_seniority.py` — boundary coverage: exactly at / one month
  under / one month over the mid threshold; internships excluded from total
  months; concurrent/overlapping roles counted once; a title-only-without-
  start-date record produces no span; leadership evidence present in
  responsibility text but absent from title (counts) and present in title but
  absent from responsibility text (does not count); staff/principal
  leadership requirement enforced independently of tenure; `assess()` on an
  empty graph returns `None`; `explain()` names months, family, level, and
  gap.
- `matching/test_scorer.py` — `seniority_and_experience` dimension rewired to
  `matching/seniority.py`; the shared `create_test_graph()` fixture (frozen,
  owned by `matching/test_qualification.py`) is augmented in
  `matching/test_scorer.py`'s own `setUp()` with verified
  `employment.start_date` / `employment.end_date` assertions under the same
  `"founder"` subject its existing title assertion already uses (that fixture
  predates any employment-date model and never carried dates, since the old
  keyword model didn't need them).
- `matching/test_adversarial.py` — unchanged; exercises the dimension
  incidentally (empty-graph and shared-fixture paths) with no
  seniority-specific assertions, so it validates the new model produces no
  strengths on an empty truth graph without needing edits.
- `truth/test_predicates.py` — unchanged; `truth/predicates.py`'s new
  `EMPLOYMENT_ORGANIZATION`, `EMPLOYMENT_MARKET_FACING_TITLE`,
  `EMPLOYMENT_START_DATE`, `EMPLOYMENT_END_DATE` named constants point at
  predicates `CANONICAL_MATERIAL_MANIFEST` already projects, so the registry
  completeness and PROJECTED/ASSERTION_ONLY classification contract tests
  pass unchanged.
- Rollback: revert `matching/seniority.py`, `matching/test_seniority.py`, the
  `seniority_and_experience` block and its imports in `matching/scorer.py`,
  the `_with_employment_tenure` addition in `matching/test_scorer.py`, the
  four new named constants in `truth/predicates.py`, and this ADR in one
  commit; no schema or migration is involved.
