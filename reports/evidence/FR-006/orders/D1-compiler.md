# Work order D1 — A real CV compiler

**Brief:** BRIEF-FR-006 §2 Track D. **Wave:** 3. **Depends on:** F1 (identity predicates and the
approved-phrase bank) — do not start until the Master says F1 is integrated.
**Worktree/branch:** `wt/fr006-d1` **Test DB:** `opportunityos_test_d1`
(`py -3.12 scripts/dev_env.py testdb d1`, or `CREATE DATABASE opportunityos_test_d1` and export
`OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_d1`.)

## Why this exists

The founder generated a CV from real data and it had **no name, no contact details, no bullet
points, no education, and no formatting**. The compiler emits atomic claims as bare lines:
`compiler_employment.py` assembles four sections whose content is strings like
`"Background: {title}"`, a comma-joined skills list, `"{title} | {org} ({start} – {end})"`, and
`"{context}: {numeric_value}{unit}"`. That is a claim ledger printed to a page, not a CV.

This is the headline deliverable of the brief. It is also the one most likely to be delivered by
cheating, so read the hard stop below before you read anything else.

## The hard stop, stated first

> **Tailoring = selection and ordering, never rewording. Every rendered sentence maps to a claim
> with evidence ids.** (brief §2 D1, Appendix 2, and §9.)

Concretely:
- You may **choose** which of the founder's bullets appear and in what order. You may **not**
  rewrite, merge, summarise, paraphrase, or "polish" one.
- You may not generate a sentence about the founder that is not either (a) a pack value rendered
  through a claim with evidence ids, or (b) an approved phrase from `approved_phrases` used
  verbatim.
- **`truth/validator.py` and `truth/connective_terms.txt` are frozen.** Adding a word to the
  connective stop-list or relaxing a guard so a nicer sentence validates is the exact failure the
  brief's §9 calls a hard stop. If a claim you believe is true fails validation, the answer is to
  change what you render, not what validates. Report the case; do not touch the validator.
- Claim A-11 mutates the validator's uncovered-term guard and requires **at least two** suites to
  fail. Your new document suite must be one of them. If neutralising the guard leaves your suite
  green, your suite is not exercising the truth-lock and the deliverable is not done.

## Deliverable text (verbatim from the brief)

> **D1 — A real CV compiler (ADR-0017: document model).**
> - Identity block from `identity.*` assertions (name, headline, email, phone, LinkedIn, GitHub,
>   website, location) — the founder's pack already carries them.
> - Sections, each truth-locked: Summary (the approved summary, optionally tailored by selecting
>   the sentence variant whose evidence best matches the role); Experience with the **founder's
>   actual bullet points** (responsibilities and achievements from the pack), ordered and selected
>   by relevance to the posting's requirements, dates rendered "Jan 2026 – Present"; Projects
>   (portfolio with URLs); Education; Certifications; Skills grouped by the pack's categories,
>   ordered by relevance, with proficiency shown honestly for basic/foundations; Languages.
> - Tailoring = **selection and ordering**, never rewording. Every rendered sentence maps to a
>   claim with evidence ids (A-10 rule unchanged). A "what was left out and why" panel lists the
>   bullets not selected.
> - Three committed ATS-safe templates (single column, real heading styles, consistent fonts, no
>   tables for layout, no text boxes): *Classic*, *Compact*, *Modern*. DOCX via `python-docx`
>   with proper styles; **PDF** via a deterministic renderer.
> - Cover letter: same identity block; a narrative skeleton with **the founder's own approved
>   sentences** slotted in; opportunity-provenanced facts (employer, role, location) cited with
>   their provenance; never invents motivation text beyond a committed, founder-editable phrase
>   bank in the pack (new optional section `approved_phrases`, documented in the template).
> - **Acceptance:** on the founder-shaped synthetic pack, the CV DOCX and PDF contain: identity
>   block, >= 2 bullets per non-internship role, education, >= 3 certifications, projects with
>   URLs, grouped skills; text extraction of the PDF passes a committed ATS-parse check (sections
>   detected, dates parsed, no tables); the truth-lock e2e suite and the guard-neutralisation
>   mutation still fail correctly; the Overseer will re-run the mutation.

## Facts established by the Master — do not re-derive

- **The PDF renderer is `reportlab`, and it is already wired.** `matching/binary_export.py`
  already produces DOCX via `python-docx` (0.75in margins, Arial) and PDF via reportlab
  (`SimpleDocTemplate`, 54pt margins, Helvetica). LibreOffice is **not** installed, is **not**
  required, and must not be introduced. Do not add a PDF dependency.
- `matching/ats_quality.py` (`AtsDocumentQualityHarness.verify_claim_parity`) already checks that
  the artifact title, every section heading and item, and every generated claim appear in both
  DOCX and PDF. Extend it; do not replace it.
- The validation entry point is `matching/artifact_validation.py:20-57`
  (`validate_artifact_claims(artifact, validator)`), which routes `policy_source == "NARRATIVE"`
  claims to `validator.validate_narrative` and everything else to `validator.validate_claim`.
  `validate_claim`'s signature is
  `(claim, evidence_ids=None, *, as_of=None, allowed_subject_ids=None)` — there is **no**
  `opportunity_terms` parameter; ADR-0014 removed opportunity-provenanced terms as a claim class
  entirely. Opportunity facts in a cover letter are cited with their provenance, and they are
  **not** founder claims.
- `GeneratedClaim` is in `matching/models.py:153-164`.
- Pack sections available to you after F1: `evidence`, `career_profile` (employment, education,
  certifications, skills, languages, work_authorizations, approved_summaries, red_lines,
  never_claims), `capability_profile` (services, portfolio, capacity, ...), plus the new
  `identity` and `approved_phrases`.
- The two synthetic packs are `truth.fixtures.synthetic_graph()` and
  `truth.fixtures.founder_shaped_graph()`. **The founder's own pack is never read.** Claim A-10
  binds synthetic packs only, and the report says so.
- Known engine defects, **not yours to fix**, and not a reason to stop: a metric whose context
  text ends in a full stop, and a number at the very end of a sentence, can each fail to match
  their own evidence (`truth/graph.py` numeric matcher). If a metric claim fails validation for
  that reason, render around it and report the case.

## Required behaviour

1. **`matching/document_model.py`** — a structured document: identity block, ordered sections,
   each section a list of items, each item carrying its `GeneratedClaim` (text, evidence ids,
   predicate). Renderers consume this model; no renderer composes founder-facing prose.
2. **Section builders**, each truth-locked: Summary (select the approved-summary variant whose
   evidence best matches the posting's requirements — selection, not rewriting), Experience
   (role header plus the founder's **actual** responsibility and achievement bullets, selected and
   ordered by relevance to the posting's requirements, **>= 2 bullets per non-internship role**
   where the pack has them), Projects with URLs, Education, Certifications, Skills grouped by the
   pack's own categories and ordered by relevance with `basic`/`foundations` shown honestly,
   Languages.
3. **Date rendering** exactly as the brief asks: `"Jan 2026 – Present"`. A rendered date is a
   claim like any other and carries the evidence ids of the employment record.
4. **"What was left out and why"** — a structured panel listing every bullet not selected with
   the reason (relevance rank, length budget, failed validation). This is part of the API
   response, not only a UI nicety; work order C3/D2 renders it.
5. **Three ATS templates** — *Classic*, *Compact*, *Modern* — committed as data, single column,
   real heading styles, consistent fonts, **no tables used for layout and no text boxes**. Same
   document model, three renderings. A test asserts the DOCX contains no layout table.
6. **Cover letter**: the same identity block, a narrative skeleton whose motivation sentences come
   **verbatim** from `approved_phrases`, and opportunity facts (employer, role, location) cited
   with their provenance. If the pack has no `approved_phrases`, the letter omits the motivation
   paragraph rather than inventing one — assert this with a test.
7. **A committed ATS-parse check** over the extracted PDF text: sections detected, dates parsed,
   no tables. `pdfplumber` is already a dependency.
8. **`docs/adr/ADR-0017-document-model.md`** — the document model, the three templates, the
   selection-and-ordering rule, the renderer choice and why, and explicitly what the compiler
   refuses to do.
9. **The truth-lock suite.** Extend `matching/test_artifacts_e2e.py` (or add a document suite) so
   that neutralising the validator's uncovered-term guard makes it FAIL. Verify this yourself:
   edit the guard by hand, run the suite, confirm the failure, restore the file, confirm it is
   byte-identical, confirm the suite is green again. Paste all four outputs.

## Allowed files

`matching/document_model.py` (new) · `matching/templates/**` (new) · `matching/compiler_employment.py` ·
`matching/compiler_independent.py` · `matching/binary_export.py` · `matching/ats_quality.py` ·
`matching/artifact_validation.py` (routing only — no change that alters what validates) ·
`matching/models.py` · `matching/test_compiler.py`, `matching/test_artifacts_e2e.py`,
`matching/test_binary_export.py`, and new tests beside your new modules ·
`docs/adr/ADR-0017-document-model.md` (new).

## Frozen — touching any of these is a FAIL

**`truth/validator.py`** · **`truth/connective_terms.txt`** · `truth/graph.py` · `truth/ingest.py` ·
`truth/models.py` · `truth/fixtures.py` (F1 has already given both packs an identity block and
phrase bank; if something is missing, stop and report it as a scope question) ·
`matching/scorer.py`, `matching/seniority.py`, `matching/title_family.py`,
`matching/qualification.py` · `opportunity/**` · `storage/**` · any migration ·
`api/**` (work order D2 owns the routes) · `web/**` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| D1.1 | `py -3.12 -m unittest discover -s matching -p "test_*.py" -v` | `OK`, count stated |
| D1.2 | a run generating CV DOCX + PDF for **both** synthetic packs × **three** templates × three fixture postings | every artifact produced; DOCX starts `PK`, PDF starts `%PDF`; **zero** validator rejections |
| D1.3 | the content assertions on the founder-shaped pack | identity block present (name + >= 1 contact); bullets-per-role counts printed with **>= 2 for every non-internship role**; education present; certifications count **>= 3**; projects with URLs; skills grouped — each count printed, not asserted in prose |
| D1.4 | the ATS-parse check over the extracted PDF text | sections detected (listed), dates parsed (count), **no tables** |
| D1.5 | the guard-neutralisation mutation, four steps | (a) suite green before; (b) guard neutralised → suite **FAILS**, with the failing test names; (c) file restored → `git diff --exit-code` clean; (d) suite green again |
| D1.6 | the no-motivation-without-phrases test | a pack without `approved_phrases` produces a letter with no motivation paragraph and no invented sentence |
| D1.7 | `git diff --name-only` against your base | **`truth/validator.py` and `truth/connective_terms.txt` do not appear** |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim. If any content threshold in D1.3 is not
met on the founder-shaped pack, **report the number you got** and why. Do not add data to a
fixture pack to reach a threshold — that is editing evidence to make a claim pass, and it is an
automatic FAIL of this deliverable.
