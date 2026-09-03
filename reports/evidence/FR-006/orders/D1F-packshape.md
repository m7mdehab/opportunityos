# Work order D1F — Pack realism and the legacy artifact validator

**Brief:** BRIEF-FR-006 §2 Track D, the residue of D1. **Wave:** 4. **Depends on:** D1, F1 (both integrated).
**Worktree/branch:** `wt/fr006-d1f` **Test DB:** `opportunityos_test_d1f`
**Turn budget:** 60. **Spend at most 8 turns reading.**

**First action:** `git merge --no-edit feat/brief-fr-006-nothing-missed` from your worktree root.

## Why this order exists

Work order D1 rebuilt the CV compiler and it works: 30 artifacts across two synthetic packs,
three templates and three postings, all with valid DOCX and PDF magic bytes and zero validator
rejections. The guard-neutralisation mutation still fails two suites, so the truth-lock holds.

But four of D1's content thresholds could not be met, and in every case the cause was the
**shape of the fixture packs or the schema**, not the compiler. D1 was explicitly forbidden from
adding data to a fixture to reach a threshold, and it correctly refused. This order does the
legitimate half of that work, and it is bounded carefully because the line between the two is the
most important line in this brief.

**What is legitimate here, and why.** The founder-shaped fixture exists to be *shaped like a real
founder pack*. A real pack has several responsibilities per role, portfolio items with URLs, and
skills organised into categories. The current fixture gives most roles exactly **one**
responsibility, no portfolio URLs, and the schema has no skill category at all. That is an
**unrealistic fixture**, and a capability the brief requires ("Experience with the founder's
actual bullet points ... ordered and selected by relevance") cannot be demonstrated at all
against a pack that has only one bullet to select from. Making the fixture realistic is
completing it, exactly as another work order completed a benchmark fixture that lacked the
employment dates the scoring model needs.

**What is not legitimate, and would be an automatic FAIL.** Choosing fixture content so that a
*validation* passes. You are adding plausible pack data with its own evidence records; you are not
reverse-engineering sentences that the compiler happens to emit, and you are not touching
`truth/validator.py` or `truth/connective_terms.txt`. If a bullet you add cannot be rendered
because its evidence does not support it, that is the guard working — leave it and report it.

## Required behaviour

### 1. Fixture realism — `truth/fixtures.py`

Bring `founder_shaped_graph()` up to the shape of a real pack. Both shipped synthetic packs get
the same treatment where it applies.

- **At least two responsibilities or achievements for every non-internship role.** D1 measured
  7 non-internship roles, of which only 2 had ≥2 bullets. Each new bullet is a normal assertion
  with its own evidence record, written as a plausible responsibility for that role — not as a
  sentence chosen to please the compiler.
- **Portfolio URLs.** `PortfolioItem` already has a `url` field; neither pack sets it. Set it for
  both portfolio items, with evidence.
- **Skill categories.** See item 2 — once the field exists, assign every skill in both packs a
  category (e.g. `languages`, `data_platform`, `cloud`, `tooling`), with evidence.
- **Skill proficiencies.** Work order B2 shipped a closed proficiency vocabulary
  (`basic`, `foundations`, `working`, `advanced`, `expert`) and treats absent proficiency as a
  **partial** match. Both packs currently leave proficiency unset on every skill, so no skill can
  ever produce a core-skill strength. Set proficiencies **honestly and with variety** — including
  at least one `basic` skill, because B2's whole defect was "Verified core skill: Javascript" for a
  basic skill, and the fixture must be able to exercise that path.

### 2. `SkillRecord.category` — a new optional field

The brief requires "Skills grouped by the pack's categories". `truth/models.py::SkillRecord` has
`id`, `name`, `evidence_ids`, `proficiency` — and **no category**. Add `category` as an optional
field, register the predicate `skill.category`, project it from the pack the same way
`skill.proficiency` is projected, accept it in the loader, and document it in
`docs/templates/truth_pack.template.yaml`. Keep `truth/test_predicates.py` green.

Then make `matching/document_model.py` group the CV's Skills section by that category, ordered by
relevance, falling back to a single group when no skill carries one. D1 currently groups by
proficiency, which was its documented workaround for the missing field.

### 3. The legacy artifact validator — `matching/validator.py`

D1 reported a regression it was not allowed to fix, and it is real:
`matching/validator.py` contains a **second, legacy** `ArtifactClaimValidator` with a **static
claim-predicate whitelist**. D1's new predicates — `employment.responsibility`,
`achievement.statement`, `education.record`, `certification.record`, `portfolio.record`,
`language.record`, `identity.*`, `profile.approved_summary` — are not in it, so
`matching/test_adversarial.py::TestArtifactValidatorAndAdversarial::test_valid_compiled_cv_passes_validation`
fails.

The production path is `matching/artifact_validation.py` -> `truth/validator.py` under ADR-0014.
Decide, and record the decision in `ADR-0017` as an amendment:
- if the legacy validator still has a caller other than its own tests, extend its whitelist;
- if it does not, **retire it** — delete it and its tests, or reduce it to a thin delegation to
  the production path.

Grep for its callers and let the answer decide. Either way, say which and why. Do **not** widen
the whitelist to include a predicate the production validator would reject.

### 4. Two things to leave alone, and report

- **Dates render in ISO form**, not the brief's `"Jan 2026 – Present"`. D1's reasoning is sound and
  the Master upholds it: the validator's lexical coverage requires a claim's words to appear in its
  evidence, and no pack's evidence text contains month names. Rendering "Jan 2023" against evidence
  reading "2023-01-01" would require relaxing that coverage, which §9 makes a hard stop. An
  ISO date is ATS-readable. **Do not change this and do not touch the validator.** Confirm in your
  return that the ATS parse check accepts ISO dates and report `dates_parsed_count`.
- **`identity.phone` is omitted from every document** because a bare digit run trips the
  validator's unverified-metric check. So the CV carries name, headline, email, LinkedIn, GitHub,
  website and location — but no phone. Investigate only far enough to say whether the phone can be
  rendered **without** any validator change (for example, if the evidence record's text contains
  the number verbatim). If it can, render it. If it cannot, leave it and report it as a known gap.

## Allowed files

`truth/fixtures.py` · `truth/models.py` (the `category` field only) · `truth/ingest.py` (the
`category` field only) · `truth/graph.py` (projecting `skill.category` only) ·
`truth/predicates.py` · `truth/test_*.py` · `docs/templates/truth_pack.template.yaml` ·
`matching/document_model.py` (the Skills grouping only) · `matching/validator.py` and
`matching/test_adversarial.py` (item 3) · `matching/test_compiler.py`,
`matching/test_artifacts_e2e.py` · `docs/adr/ADR-0017-document-model.md` (amendment) ·
`scripts/truth_check.py` (only if the new section field needs counting).

## Frozen — touching any of these is a FAIL

**`truth/validator.py`** · **`truth/connective_terms.txt`** · `matching/scorer.py`,
`matching/seniority.py`, `matching/skills.py`, `matching/title_family.py`,
`matching/qualification.py` · `matching/binary_export.py`, `matching/templates/**` ·
`opportunity/**` · `storage/**` · any migration · `api/**` · `web/**` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| D1F.1 | `py -3.12 -m unittest discover -s truth -p "test_*.py" -v` | `OK`, count stated |
| D1F.2 | `py -3.12 -m unittest discover -s matching -p "test_*.py" -v` | `OK`, count stated; `test_valid_compiled_cv_passes_validation` passes or is gone with its module |
| D1F.3 | the D1.3 content counts, re-run | **every** non-internship role shows **>= 2** bullets, printed per role; projects show URLs; skills show **>= 2** distinct categories; certifications count printed |
| D1F.4 | the ATS parse check | sections listed, `dates_parsed_count` printed and **> 0** if the checker accepts ISO, `tables_detected` = 0 |
| D1F.5 | **the guard-neutralisation mutation, all four steps** | green → neutralised **FAILS** with the test names → `git diff --exit-code` clean → green again. **This row is the reason the order exists and it must still pass.** |
| D1F.6 | `git diff --name-only` against your base | `truth/validator.py` and `truth/connective_terms.txt` **absent** |
| D1F.7 | `py -3.12 scripts/check_guard.py --allow-missing-patterns` | exit 0 — the new fixture and template content contains nothing that looks like real personal data |
| D1F.8 | a `basic`-proficiency skill through the scorer | still produces **no** core-skill strength — the B2 anti-regression must survive the new fixture proficiencies |

Report every threshold you still cannot meet, with the number you got and the reason. That is a
better outcome than a number reached by choosing data to fit it.
