# Work order B2 — Proficiency-aware, requirement-aware skill matching

**Brief:** BRIEF-FR-006 §2 Track B. **Wave:** 2. **Depends on:** A1, B3 (integrated).
**Worktree/branch:** `wt/fr006-b2` **Test DB:** `opportunityos_test_b2`

**First action:** `git merge --no-edit feat/brief-fr-006-nothing-missed` from your worktree root.

## Why this exists

The founder's run showed the reason **"Verified core skill: Javascript"** on cards — while the
founder's own CV records Javascript as *basic*. The scorer matches skills by name only
(`matching/scorer.py:152-202`, string equality on casefolded names at 175-176) and never consults
proficiency. It also cannot tell a posting's **required** skills from its **nice-to-have** ones,
so a nice-to-have match counts as a core-skill strength.

This is the product telling the founder something about themselves that is not true. That is the
first hard rule in `AGENTS.md`.

## Deliverable text (verbatim from the brief)

> **B2 — Proficiency-aware, requirement-aware skills.**
> - Skill match consults the founder's proficiency (`basic`, `foundations` are *partial* matches,
>   shown as such); the posting's required vs nice-to-have skills are separated
>   (Greenhouse/Lever descriptions use headed lists; inference rules in `inference_rules.yaml`);
>   core-skill strength requires a *required* match at >= working proficiency.
> - Reasons are specific: "Required: Python, SQL, Airflow -> you have Python (expert-evidence: 3
>   roles), SQL (3 roles); Airflow not in your pack." Never "Verified core skill: Javascript" for
>   a basic skill.
> - **Acceptance:** fixture tests for required/nice-to-have split and proficiency tiers; the
>   "Senior Customer Engineer" family no longer scores above the founder's data-engineering
>   matches on the fixture corpus.

## Facts established by the Master — do not re-derive

- `truth/models.py::SkillRecord` (lines 251-263) has `id`, `name`, `evidence_ids`, and an
  **optional, unconstrained `proficiency` string**. There is no closed vocabulary in code today.
  You must define one — `basic`, `foundations`, `working`, `advanced`, `expert` — and treat an
  **absent or unrecognised** proficiency as *unknown*, which is a **partial** match, never a
  strength. Unknown must not be optimistic; the whole defect being fixed is optimism.
- `opportunity/inference_rules.yaml` is created by work order A1 and is the committed home for
  text-inference rules. Required-vs-nice-to-have detection goes there as rules, not as Python.
- `matching/title_family.py` (work order B3) provides the family for the ordering acceptance.
- `truth/graph.py` and `truth/predicates.py`: the skill predicate is `SKILL_NAME`. If proficiency
  is not projected today, register and project it the same way B3/F1 did — **read what the graph
  emits, never add a spelling to the graph to suit the scorer**. That was the FR-005 D2 defect and
  the contract test `truth/test_predicates.py` exists to catch it.
- Work order B1 rewrote `seniority_and_experience` and B3 added `title_family_fit` in
  `matching/scorer.py`. Both are integrated before you start. Confine your edits to the skills
  dimension.

## Required behaviour

1. **A proficiency tier model** with the vocabulary above, its ordering, and the rule that
   `basic` and `foundations` are **partial** and unknown is partial. Committed as data with the
   thresholds visible, not scattered constants.
2. **Required vs nice-to-have separation** for the posting: parse headed lists from the
   description (Greenhouse and Lever descriptions use them) via rules in
   `opportunity/inference_rules.yaml`. When the split cannot be determined, every extracted skill
   is treated as **nice-to-have**, not required — the conservative direction, because inflating
   "required" inflates the founder's apparent match.
3. **Core-skill strength requires a *required* match at >= working proficiency.** A `basic` skill
   never produces a strength, under any wording. Add a test that searches every generated reason
   string for the phrase pattern used by the old code and asserts it cannot be produced for a
   `basic` skill.
4. **Specific reason text** in the brief's shape: the posting's required list, what the founder
   has, the evidence strength (how many roles support it), and what is missing by name. Generated
   from the computed match, never a fixed string, and carrying evidence refs.
5. **The ordering acceptance**: on the fixture corpus, the "Senior Customer Engineer" family must
   no longer score above the founder's data-engineering matches. **Print both scores.** If this
   does not hold after your change, report the two numbers and your diagnosis rather than tuning a
   weight until it does — a weight tuned to make one fixture pass is the same defect class as a
   fixture edited to make a claim pass.

## Allowed files

`matching/scorer.py` (the skills dimension only) · `matching/test_scorer.py` ·
`matching/skills.py` (new, if the tier model wants a home) and its test ·
`matching/test_adversarial.py` (only assertions encoding the old name-only behaviour) ·
`truth/predicates.py`, `truth/test_predicates.py` (registry additions only) ·
`truth/graph.py` (**only** to project skill proficiency, if it is not projected today) ·
`opportunity/inference_rules.yaml` and its test (the required/nice-to-have rules only) ·
`truth/fixtures.py` (**only** to give existing skills a proficiency where the pack shape now
requires one — and every such change is named in your return with what it used to be).

## Frozen — touching any of these is a FAIL

`truth/validator.py` · `truth/connective_terms.txt` · `truth/ingest.py` · `truth/models.py`
beyond the proficiency field's own validation · `matching/seniority.py`,
`matching/title_family.py`, `matching/qualification.py` · `opportunity/**` other than
`inference_rules.yaml` · `storage/**` · any migration · `api/**` · `web/**` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| B2.1 | `py -3.12 -m unittest discover -s matching -p "test_*.py" -v` | `OK`, count stated |
| B2.2 | `py -3.12 -m unittest discover -s truth -p "test_*.py" -v` | `OK` |
| B2.3 | the proficiency-tier tests | `basic` and `foundations` produce a **partial** match; unknown produces a partial match; `working` and above can produce a strength — each asserted separately |
| B2.4 | the required/nice-to-have split tests | a headed Greenhouse list and a headed Lever list both split correctly; an unheaded description yields **all nice-to-have** |
| B2.5 | the anti-regression test | no reason string can claim a verified/core skill for a `basic` proficiency, searched across all generated reasons |
| B2.6 | the corpus ordering run | the "Senior Customer Engineer" family score and the best data-engineering match score, both printed, with the former **below** the latter |
| B2.7 | a printed sample of five generated reason strings | each names the required list, what is matched, the evidence strength, and what is missing |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim. Name every fixture you changed and what
it previously asserted.
