# Work order F1 — Identity predicates and the approved-phrase bank

**Brief:** BRIEF-FR-006 §2 Track F. **Wave:** 2 (no dependencies — dispatched as soon as a slot frees).
**Worktree/branch:** `wt/fr006-f1` **Test DB:** `opportunityos_test_f1`
(`py -3.12 scripts/dev_env.py testdb f1`, or `CREATE DATABASE opportunityos_test_f1` and export
`OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_f1`.)

## Why this exists

The founder generated a CV and it had **no name and no contact details**. The truth pack loader
has no `identity` section at all (`truth/ingest.py:561-565` accepts only `evidence`,
`career_profile`, `capability_profile`, `assertions`, `relations`, `metrics`), so there was
nothing for the compiler to put at the top of the page. Work order D1 rebuilds the CV and
**cannot start until identity exists**. You are on D1's critical path.

## Deliverable text (verbatim from the brief)

> **F1 — Predicate registry gains `identity.*` and `approved_phrases`;** template and
> `truth_check.py` updated; the shipped synthetic template gains an identity block and phrase bank.

And from D1, the part that constrains your schema:

> Identity block from `identity.*` assertions (name, headline, email, phone, LinkedIn, GitHub,
> website, location) — the founder's pack already carries them.
> [...] never invents motivation text beyond a committed, founder-editable phrase bank in the
> pack (new optional section `approved_phrases`, documented in the template).

## Facts established by the Master — do not re-derive

- Loader: `truth/ingest.py:561-565` holds the accepted top-level section list.
- Predicate registry: `truth/predicates.py`. The contract test `truth/test_predicates.py` globs
  every non-test file in `matching/` and requires every predicate the matching engine references
  to be registered, and every registered predicate to be **either** projected by `truth/graph.py`
  from a pack field **or** declared assertion-only with its owning pack section.
- Projection happens in `truth/graph.py` via `_project_entity_manifest()` against
  `CANONICAL_MATERIAL_MANIFEST` (around lines 650-657 and 809-886).
- Template: `docs/templates/truth_pack.template.yaml`, whose current top-level sections are
  `evidence`, `career_profile`, `capability_profile`. Its comment block at lines 32-40 states
  there is no identity section — that comment is now wrong and you fix it.
- `scripts/truth_check.py` prints **section names and entry counts only** — never a name,
  employer, title, skill, or any evidence text. **This property is load-bearing** and your
  change must preserve it exactly: it is the only way the founder can validate a pack without an
  agent reading it.
- Fixture packs: `truth.fixtures.synthetic_graph()` and `truth.fixtures.founder_shaped_graph()`.
- **The founder's own pack at `private/truth_pack.yaml` is never read, listed, or opened.**

## Required behaviour

1. **`identity` — a new optional top-level pack section.** Fields, all optional except `name`:
   `name`, `headline`, `email`, `phone`, `linkedin`, `github`, `website`, `location_city`,
   `location_country`. Each entry carries `evidence_ids` like every other assertion source —
   identity is truth-locked too. Nothing in a generated document may assert an identity value
   that the pack does not carry.
2. **Predicates `identity.name`, `identity.headline`, `identity.email`, `identity.phone`,
   `identity.linkedin`, `identity.github`, `identity.website`, `identity.location_city`,
   `identity.location_country`**, registered in `truth/predicates.py` and **projected by
   `truth/graph.py`** from the new section — not declared assertion-only. Add them to
   `CANONICAL_MATERIAL_MANIFEST` and the projection path in the same way existing entity
   sections are projected. This is the one narrow authorisation you have to touch `graph.py`.
3. **`approved_phrases` — a new optional top-level section**: a list of founder-authored
   sentences, each with an id, the text, optional tags (e.g. `motivation`, `closing`), and
   `evidence_ids`. Predicate `approved_phrase.text`. These are the **only** sentences a cover
   letter may use for motivation. Nothing generates or paraphrases them.
4. **Loader acceptance and validation**: both new sections load, validate, and appear in the
   loader's section list. An unknown field inside them is an error, not a silent ignore.
5. **`scripts/truth_check.py`**: report the two new sections in the counts output, and keep the
   `empty sections:` line working for them. **Add a test asserting the output contains no
   value text from any section** — construct a pack with a distinctive string in every field and
   assert that string never appears in stdout. The FR-005 packet warned the founder to read the
   `empty sections:` line because an unknown top-level heading is silently accepted; if fixing
   that is a one-line change in your section validation, make it and say so. If it is larger,
   leave it and report it.
6. **Template** `docs/templates/truth_pack.template.yaml`: an identity block and a phrase bank,
   with comments explaining each field, plus a correction of the now-false comment at lines
   32-40. Use obviously-synthetic placeholder values.
7. **Fixture packs**: give both `synthetic_graph()` and `founder_shaped_graph()` a full identity
   block and at least four approved phrases, with evidence. D1 asserts against these.

## The trap to avoid

You are adding to the truth system, and the truth system is what stops the product lying about a
real person. Do not weaken anything to make the new sections convenient:
- `truth/validator.py` and `truth/connective_terms.txt` are **frozen**. If you believe a
  validator change is needed, stop and report it as a scope question. Loosening the validator so
  a document looks better is a hard stop under the brief's §9.
- Identity values are assertions with evidence, not free text.

## Allowed files

`truth/ingest.py` · `truth/models.py` · `truth/graph.py` (the identity/approved_phrases
projection only) · `truth/predicates.py` · `truth/fixtures.py` · `truth/test_*.py` ·
`scripts/truth_check.py` and a new `scripts/test_truth_check.py` ·
`docs/templates/truth_pack.template.yaml`.

## Frozen — touching any of these is a FAIL

`truth/validator.py` · `truth/connective_terms.txt` · `matching/**` · `opportunity/**` ·
`storage/**` · `api/**` · `web/**` · any migration · anything under `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| F1.1 | `py -3.12 -m unittest discover -s truth -p "test_*.py" -v` | `OK`, count stated; count is higher than before |
| F1.2 | `py -3.12 -m unittest truth.test_predicates -v` | `OK` — every new predicate registered and projected |
| F1.3 | `py -3.12 scripts/truth_check.py` against a temporary pack you build from the template | exit 0; section names and counts printed; **no value text** |
| F1.4 | the leak test | a pack with a distinctive sentinel in every field produces stdout containing the sentinel **zero** times |
| F1.5 | `py -3.12 -m unittest discover -s matching -p "test_*.py" -v` | `OK` — the fixture changes did not break the existing compiler or validator suites |
| F1.6 | `py -3.12 scripts/check_guard.py --allow-missing-patterns` | exit 0 — the template's placeholder identity values do not look like real personal data or secrets |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim.
