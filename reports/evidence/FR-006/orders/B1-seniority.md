# Work order B1 — Seniority from experience, not keywords

**Brief:** BRIEF-FR-006 §2 Track B. **Wave:** 1. **Depends on:** nothing.
**Worktree/branch:** `wt/fr006-b1` **Test DB:** `opportunityos_test_b1`
(`py -3.12 scripts/dev_env.py testdb b1`, or `CREATE DATABASE opportunityos_test_b1` and export
`OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_b1`.)

## Why this exists

The founder ran the alpha over real data and every senior/staff/principal posting claimed
"Senior matches founder experience". The cause is `matching/scorer.py:218-221`:

```python
is_senior = any(
    any(k in str(a.value).casefold() for k in ("senior", "sr", "lead", "principal", "staff", ...))
    for a in emp_title_assertions
)
```

The founder holds two "Team Lead" titles. The substring `lead` therefore makes every senior
role a match. This is a scoring lie about a real person, which the project's first hard rule
forbids.

## Deliverable text (verbatim from the brief)

> **B1 — Seniority from experience, not keywords.**
> - Founder seniority derived from the truth graph: total professional months since first
>   non-internship role, months in the target role family, and whether any role carried people
>   leadership (from responsibilities, not title tokens). Encoded as a small model with
>   committed thresholds and an ADR (`ADR-0016`). "Team Lead" titles at group companies count
>   as leadership evidence; they do not make a 20-month-tenure founder "senior" for a
>   Staff/Principal engineering role.
> - Scorer output must say what it computed: "Founder: ~2 years professional, 8 months in data
>   engineering; role asks Senior (5+). Gap: 3 years." — with evidence refs.
> - **Acceptance:** on the fixture corpus, Staff/Principal/Lead roles no longer receive a
>   seniority *strength* for the founder-shaped pack; Mid and Junior data roles do. Tests cover
>   the boundaries.

## Facts established by the Master — do not re-derive

- `truth/graph.py` projects, per employment record: `employment.organization`,
  `employment.title`, `employment.market_facing_title`, `employment.start_date`,
  `employment.end_date`, `employment.responsibility` (collection), and nested
  `achievement.statement`. **`truth/graph.py` is frozen for you** — read what it emits; never
  add a predicate spelling to the graph to make the scorer work. That was the FR-005 D2 defect.
- `truth/predicates.py` is the registry. If you need a new predicate constant, add it there and
  keep `truth/test_predicates.py` green — the contract test globs every non-test file in
  `matching/`.
- The founder-shaped fixture pack is `truth.fixtures.founder_shaped_graph()` — nine employment
  roles including concurrent roles and internships, five certifications, thirty-eight skills.
  **Never read `private/`.**
- The scorer dimension is `seniority_and_experience` (`matching/scorer.py:263`).

## Required behaviour

1. **New module `matching/seniority.py`** computing, from the truth graph alone:
   - `total_professional_months` — since the first **non-internship** role, with **overlapping
     concurrent roles counted once** (the founder-shaped pack has concurrent roles; double
     counting them would inflate tenure, which is the same defect in the other direction).
   - `months_in_family(family)` — months in the target role family. Until B3 lands, take the
     family as a parameter with a simple alias list; B3 will supply
     `matching/title_families.yaml` and the wiring is a later, separate change.
   - `has_people_leadership` — derived from **responsibilities and achievements**, never from
     title tokens. Returns the evidence ids that support it.
   - A committed threshold table (a module constant or a small YAML) mapping a required level
     (junior / mid / senior / staff / principal) to a months floor and a leadership requirement.
   The thresholds are **committed data with a rationale in the ADR**, not magic numbers inline.
2. **Rewrite the `seniority_and_experience` dimension** to use it. Delete the `is_senior`
   substring test entirely. Add a test that asserts the old behaviour is gone: a pack whose only
   senior-sounding evidence is a "Team Lead" title must not score a seniority strength against a
   Staff posting.
3. **Explanation text** in the shape the brief gives: months professional, months in family,
   what the role asks, the gap — each backed by `evidence_refs`. The explanation must be
   generated from the computed numbers, never a fixed string.
4. **`docs/adr/ADR-0016-seniority-model.md`** — the model, the thresholds, the rationale, and
   explicitly what it refuses to infer. Follow the format of an existing accepted ADR.
5. Tests covering the boundaries: exactly at a threshold, one month under, one month over;
   internships excluded; concurrent roles counted once; leadership present via responsibility
   text but absent from titles; leadership present in a title but absent from responsibilities
   (must **not** count).

## The trap to avoid

Do not make the tests pass by shaping a fixture to the new model. If a fixture must change,
change it because the old fixture encoded the old wrong behaviour, and **say so explicitly in
your return, naming the fixture and what it used to assert**. Editing fixtures so a claim
validates is an automatic FAIL; replacing a fixture that encoded a defect is required and is
listed in the report.

## Allowed files

`matching/seniority.py` (new) · `matching/test_seniority.py` (new) · `matching/scorer.py` ·
`matching/test_scorer.py` · `matching/test_adversarial.py` (only assertions that encode the old
keyword behaviour) · `truth/predicates.py` and `truth/test_predicates.py` (registry additions
only) · `docs/adr/ADR-0016-seniority-model.md` (new).

## Frozen — touching any of these is a FAIL

`truth/graph.py` · `truth/models.py` · `truth/ingest.py` · `truth/validator.py` ·
`truth/fixtures.py` (B1 does not change the fixture packs; if you believe you must, stop and
report it as a scope question) · `matching/qualification.py` (A1 owns it this wave) ·
`opportunity/**` · `storage/**` · `api/**` · `web/**` · any migration · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| B1.1 | `py -3.12 -m unittest matching.test_seniority -v` | `OK`, >= 10 tests, boundary cases named |
| B1.2 | `py -3.12 -m unittest matching.test_scorer -v` | `OK` |
| B1.3 | `py -3.12 -m unittest matching.test_adversarial -v` | `OK` |
| B1.4 | `py -3.12 -m unittest truth.test_predicates -v` | `OK` |
| B1.5 | `grep -n "is_senior" matching/scorer.py` | no match, or a match that is provably not a substring test on titles — quote the line |
| B1.6 | a script printing, for the founder-shaped pack: the seniority raw_score and explanation against one Staff, one Principal, one Lead, one Mid and one Junior data posting | Staff/Principal/Lead show **no** seniority strength; Mid and Junior do; each explanation names months, family months, required level and gap |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim. Never summarise a test result in words.
