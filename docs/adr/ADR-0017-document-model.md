# ADR-0017: The CV/cover-letter document model

- **Status:** Accepted
- **Date:** 2026-09-03
- **Related:** BRIEF-FR-006 §2 Track D, work order D1; ADR-0014 (claim admissibility); ADR-0016 (seniority model)

## Context

Before this order, `matching/compiler_employment.py` assembled a "CV" as four
bare-string sections: `"Background: {title}"`, a comma-joined skills list,
`"{title} | {org} ({start} – {end})"` per employment record, and
`"{context}: {numeric_value}{unit}"` per metric. A founder who generated a
CV from real data got no name, no contact details, no bullet points, no
education, and no formatting — a claim ledger printed to a page, not a CV.

The compiler is also the deliverable most likely to be delivered by
cheating: it would be trivial to make a CV look richer by rewording a
founder's own sentences, inventing motivation text, or relaxing
`truth/validator.py`'s guards until whatever the compiler emits happens to
validate. The brief's hard stop is explicit: tailoring is **selection and
ordering, never rewording**, every rendered sentence maps to a claim with
evidence ids, and `truth/validator.py` / `truth/connective_terms.txt` are
frozen for this order.

## Decision

### The document model

`matching/document_model.py` is the single place that turns `TruthGraph`
assertions into founder-facing prose:

- `DocumentItem` — one renderable line, holding exactly the `GeneratedClaim`
  (`matching/models.py`) that licenses it. `str(item)` is the rendered text.
- `DocumentSection` — a heading plus an ordered `items: tuple[DocumentItem, ...]`,
  plus `omitted: tuple[OmittedItem, ...]` — the bullets/entries considered
  but not selected, with the reason (relevance rank, length budget, or a
  validator conflict). `to_artifact_section()` flattens a section into the
  `ArtifactSection` shape the existing exporters and quality harness already
  consume.
- `IdentityBlock` — the identity section plus resolved field values
  (`name`, `headline`, `email`, `phone`, `linkedin`, `github`, `website`,
  `location`) for any other builder that needs them directly (e.g. the
  cover letter).
- `CompiledDocument` — `title`, `identity`, and the ordered `sections`.
  `flatten()` returns `(ArtifactSection tuple, GeneratedClaim tuple,
  OmittedItem tuple)`.

A set of section-builder functions (`build_identity_block`,
`build_summary_section`, `build_experience_section`, `build_skills_section`,
`build_education_section`, `build_certifications_section`,
`build_projects_section`, `build_languages_section`,
`build_achievements_section`) each take the `TruthGraph` (and, where
relevance-ordering applies, the `Opportunity`) and return a `DocumentSection`.
Every section builder does the same thing: group the graph's own
already-projected `AtomicAssertion`s by subject id and predicate, select and
order a subset, and render each selected item's text **verbatim from
assertion values or, for narrative-adjacent cases, verbatim from cited
evidence content** — never composed prose.

`matching/compiler_employment.py`'s `compile_tailored_cv` and
`compile_cover_letter` call these builders, assemble a `CompiledDocument`
(cover letter builds its own narrative sections directly, per ADR-0014),
and flatten it into the pre-existing `TailoredArtifact` (`matching/models.py`)
shape. This keeps every existing consumer working unchanged:
`matching/binary_export.py`'s DOCX/PDF exporters, `matching/ats_quality.py`'s
`AtsDocumentQualityHarness`, and `matching/artifact_validation.py`'s
`validate_artifact_claims` (the real, frozen `ClaimValidator` dispatch) all
still operate on `TailoredArtifact`/`ArtifactSection`/`GeneratedClaim` — none
of their contracts changed shape. What changed is that every item now has an
explicit, typed claim, rather than an implicit list-order coincidence
between `ArtifactSection.items` and a compiler's separate flat claims list.

### The "what was left out and why" panel

`matching/models.py` adds `OmittedItem` (`section_id`, `text`, `reason`,
`claim_id`) and a new `TailoredArtifact.omitted_items` field (default `()`,
backward compatible). Every section builder that selects a subset of
available content (skills beyond the policy's highlight limit, experience
bullets beyond the per-role budget, unselected approved-summary variants,
unused approved phrases) records the rest here with a reason. This is part
of the artifact's data, not only a UI nicety — work order D2/C3 renders it.

### Three ATS-safe templates

`matching/templates/__init__.py` commits three `Template` records —
*Classic*, *Compact*, *Modern* — as **data**: a font name for DOCX
(`docx_font`), two reportlab Base-14 font names for PDF (`pdf_font`,
`pdf_font_bold` — no font file is embedded or installed), and size/margin
numbers. `matching/binary_export.py`'s `export_to_docx`/`export_to_pdf` take
an optional `template: str | Template` argument and render the *same*
`TailoredArtifact` three times, varying only font and spacing. All three are
single column; DOCX section headings use Word's built-in "Heading 2" style
(a real heading style, not a bold paragraph impersonating one); no template
uses a table for layout (`binary_export.py` never calls
`Document.add_table()`) or a text box (no `reportlab.platypus.Table` /
frame-based layout is imported).

### Renderer choice

`python-docx` for DOCX, `reportlab` (already wired, `SimpleDocTemplate`) for
PDF. LibreOffice is not installed and is not introduced — no new dependency
was added for this order.

### What the compiler refuses to do

- It never rewrites, merges, summarises, or "polishes" a founder's
  responsibility/achievement bullet, approved-summary variant, or approved
  phrase. Every rendered sentence is either (a) a pack value read straight
  off an `AtomicAssertion` (or a small number of same-subject,
  relationally-linked assertions combined the same way the pre-existing
  employment-header claim already did — e.g. title + org + dates), or (b) an
  `ApprovedPhrase` used verbatim, or (c) evidence content quoted verbatim
  (used only for a planned certification's "planning to pursue" framing —
  see below).
- It never invents cover-letter motivation text. If the pack carries no
  `approved_phrases`, `compile_cover_letter` omits the motivation paragraph
  entirely rather than writing one (work order D1.6; enforced by
  `matching/test_artifacts_e2e.py`-style coverage — see "what was not
  reached" below for exact test status).
- It never touches `truth/validator.py` or `truth/connective_terms.txt`. Both
  are byte-identical to the pre-order tree (verified: D1.5 and D1.7 below).
- It never adds data to a fixture pack to make a claim pass or a threshold
  read better. Every gap between the brief's exact wording and what the two
  shipped synthetic packs actually support is documented below and in the
  work order return, not patched over by editing `truth/fixtures.py`.

## Real conflicts between the brief's exact wording and the frozen validator

`truth/validator.py` guard 9 (material lexical coverage) rejects a claim
containing any word not covered by its cited evidence, `CONNECTIVE_TERMS`,
or `_NON_MATERIAL_WORDS` — and none of the three are editable in this order.
Three genuine conflicts were found empirically (by compiling both shipped
packs and reading the validator's own rejection reasons), not hypothesised:

1. **Date format.** The brief asks for dates rendered `"Jan 2026 – Present"`.
   Every date's evidence in both shipped packs is stored as an ISO string
   (e.g. `"2023-01-01 to 2026-08-31"`) with no English month name in it, so
   rendering `"Jan"`/`"Aug"` etc. fails guard 9 on **every** employment,
   education, and certification date in both packs. `_render_date_value`
   renders the brief's preferred month-name form only when that month word
   is textually present in the record's own cited evidence, and falls back
   to the ISO form (guaranteed covered) otherwise — on both packs today,
   every date falls back to ISO. `_render_present` applies the same rule to
   the word "Present" for an open-ended role; no role in either pack is
   actually open-ended, so this path is unexercised by fixture data.
2. **A phone number can look like an unverified metric.** A claim whose
   entire text is a short, digit-led value (e.g. `<phone from identity.phone>`
   — an Egypt-format number beginning with the country code digits "20" —
   not spelled out literally here because a phone-number-shaped string trips
   the secret-scan guard even in illustrative prose; see the guard note on
   template email addresses for the same reason) reads to
   `ClaimValidator._validate_metric_provenance` as a bare numeric claim
   (`"20 count"`, taken from those leading digits) with no verified metric
   backing it, and is rejected — a
   validator false positive on short digit-led values, not a content
   problem. `build_identity_block` detects this pattern (a defensive,
   never-imported mirror of the metric regex's leading clause) and omits
   the field from the rendered identity block rather than misrepresent or
   reformat the founder's actual value; the field is still resolved on
   `IdentityBlock` for any non-claim internal use. On the founder-shaped
   pack this drops `phone` from the identity section (name, headline,
   email, LinkedIn, GitHub, website, and location still render — well above
   the ">= 1 contact" floor).
3. **A planned certification whose own name contains a "held" word cannot
   be rendered at all.** `ClaimValidator._planned_credential_reasons`
   rejects any claim naming a planned certification unless the claim
   contains a "planning" word and no "held" word. The founder-shaped pack's
   planned certification is named "Certified Group Analytics Architect" —
   the word "Certified" is itself a held-word trigger, so no framing of a
   claim naming it can pass. `build_certifications_section` detects this
   (same defensive-mirror pattern) and omits that one certification with a
   reason, rather than misrepresent it as held. For a planned certification
   whose name does *not* trigger this, the section instead quotes the
   record's own evidence sentence verbatim (e.g. "Planning to pursue the
   {name} certification from {issuer}.") — evidence text, not composed
   prose — which is why the synthetic pack's planned certification ("Example
   Cloud Architect") renders successfully.

None of these three are solved by editing the validator; each is solved by
choosing, deterministically and generically, what to render. All three are
also reported in the work order return with the exact numbers/values
involved, per the order's explicit instruction not to bury a content
threshold miss in code comments alone.

## Skills grouping and proficiency

The brief asks for skills "grouped by the pack's own categories ... with
proficiency shown honestly for basic/foundations." `truth.models.SkillRecord`
(frozen) has no `category` field at all, and neither shipped pack sets
`SkillRecord.proficiency` (always `None`). `build_skills_section` groups by
`skill.proficiency` when the pack states one (rendered as `"{name}
({proficiency})"`, a same-subject combined claim, same pattern as the
existing employment header) and falls back to a single "Technical Skills"
group otherwise — the only grouping key the current schema and fixture data
actually support. This is a genuine schema/fixture gap, not a design choice
to dodge grouping; a category field would need to be added to
`SkillRecord` in a follow-up order.

## Consequences

- Every DOCX/PDF the compiler produces now has a real identity block,
  founder-authored bullet points, education, certifications, projects, and
  languages — the founder's original complaint is fixed.
- The "what was left out and why" panel is real, structured data
  (`TailoredArtifact.omitted_items`), not a UI-only afterthought.
- Three ATS-safe templates exist as committed data and share one renderer
  code path; adding a fourth template later is a data change, not a code
  change.
- The three validator conflicts above are permanent, structural properties
  of the current fixtures + frozen validator, not bugs in this compiler;
  they will resurface identically for any real founder pack whose evidence
  is phrased the same way (ISO dates, a phone number, a certification named
  with a held-word) until a follow-up order changes the validator, the
  fixture data, or both.
