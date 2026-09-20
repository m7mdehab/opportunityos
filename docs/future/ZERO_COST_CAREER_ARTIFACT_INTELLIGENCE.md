# Future Capability — Zero-Cost Career Artifact Intelligence

Status: SHELVED / LOCKED FOR LATER IMPLEMENTATION
Owner: Overseer
Financial constraint: HARD $0 recurring spend

## Frozen product intent

OpportunityOS will later add an LLM-assisted career artifact subsystem for:
- job-specific cover letters,
- final-touch CV tailoring across the six Founder-approved CV variants,
- evidence-aware wording refinement,
- ATS-aware keyword alignment,
- deterministic DOCX/PDF generation without layout drift.

The six editable DOCX CVs will be treated as canonical layout masters.

## Hard $0 rule

The subsystem must not require:
- paid LLM APIs,
- paid inference endpoints,
- paid model-hosting subscriptions,
- new paid infrastructure.

Default execution is local open-weight inference on Founder-owned hardware.
Any paid provider must remain optional, disabled by default, and require explicit Founder approval before use.

## Frozen architecture

The LLM is a writer/editor, not the source of truth and not the document renderer.

Pipeline:

job posting
-> structured job brief
-> select best Founder CV variant
-> retrieve verified Founder evidence
-> constrained LLM content proposal
-> truth/evidence validation
-> deterministic structured patch
-> DOCX master renderer
-> PDF renderer
-> ATS/layout/page-count validation
-> persisted artifact metadata
-> live preview/download

The LLM must never:
- invent Founder claims,
- invent metrics,
- inflate titles,
- claim unverified tools/skills,
- directly redesign or freely mutate the DOCX/PDF layout,
- silently change page count or formatting.

## Canonical CV variants

- Master / General
- AI Engineer
- Data Analyst
- Data Scientist
- Data Engineer
- Business Analyst

Editable canonical DOCX versions are required before implementation.
Existing PDFs remain immutable visual/reference artifacts.

## Model strategy

The application layer must be provider/model agnostic.

A local provider interface such as CareerWriter.generate(...) will abstract the model.

Candidate open-weight models will be benchmarked on a Founder-specific evaluation set before one becomes the default. No model is permanently hard-coded into product architecture.

Initial quality strategy:
- strong Career Writing Skill / system specification,
- structured output,
- retrieval of verified Founder evidence,
- truth validation after generation,
- no fine-tuning unless evaluation later demonstrates a repeatable deficiency.

## Cover-letter requirements

Target:
- approximately 250–350 words by default,
- role/company specific,
- concise, natural and evidence-led,
- no generic boilerplate opening,
- no CV repetition,
- no fabricated company knowledge,
- no unsupported Founder-specific statements.

## CV tailoring permissions

Allowed:
- rewrite professional summary from verified evidence,
- reorder/select truthful skills,
- selectively rewrite/reorder verified experience bullets,
- selectively rewrite/reorder project bullets,
- role-specific keyword alignment where truthful.

Locked:
- contact/header identity,
- fonts,
- margins,
- styles,
- page structure,
- section architecture unless explicitly approved,
- education/certification facts except safe ordering/presentation,
- any claim unsupported by the truth/evidence layer.

## Rendering rule

The LLM returns structured content patches, not modified Word files.

Example:
- selected_cv
- summary replacement
- ordered skill IDs
- bullet replacements by stable bullet ID
- omitted bullet IDs

OpportunityOS applies those patches to the canonical DOCX structure deterministically.

## Generation policy

Artifacts are generated on demand for jobs the Founder is seriously considering, then cached.
Do not mass-generate artifacts for the entire opportunity corpus.

## Evaluation before production use

Benchmark across approximately 15–20 real target jobs spanning the main career tracks.

Evaluate:
- factual accuracy,
- hallucination rate,
- ATS alignment,
- keyword integration,
- naturalness,
- specificity,
- unnecessary rewriting,
- CV page/layout preservation,
- cover-letter usefulness,
- Founder edit burden.

Implementation remains shelved until explicitly reactivated by the Founder.
