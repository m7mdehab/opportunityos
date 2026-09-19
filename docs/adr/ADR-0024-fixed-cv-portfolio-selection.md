# ADR-0024 — Founder-Locked CV Portfolio Selection

- **Status:** Accepted
- **Date:** 2026-09-19
- **Related:** BRIEF-FR-004, ADR-0009, ADR-0017, ADR-0023

## Context

OpportunityOS historically generated a tailored CV for each employment opportunity. In practice this introduced avoidable risk in wording, layout, formatting, ATS behavior, and visual regression.

The Founder has now supplied and approved six final 2026 CV PDFs:

1. AI Engineer
2. Business Analyst
3. Data Analyst
4. Data Engineer
5. Data Scientist
6. Master / generalist

The six PDFs have been visually inspected as two-page, text-based, openable documents and are the authoritative employment CV portfolio.

## Decision

### 1. Employment CV generation is disabled

OpportunityOS must not automatically:

- rewrite CV bullets;
- rewrite summaries;
- regenerate a CV from the Truth Graph;
- change fonts, spacing, pagination, layout or section ordering;
- create a seventh role-specific CV.

For an employment posting, OpportunityOS selects exactly one of the six final PDFs and preserves its bytes unchanged.

### 2. Matching selects the CV

CV selection is deterministic from the normalized opportunity:

- title;
- description;
- responsibilities;
- requirements;
- listed skills.

The role families are:

- **Data Engineer:** data engineering, migration, ETL/ELT, integration, pipelines, Databricks/data-platform work.
- **Data Scientist:** statistics, modeling, experimentation, forecasting, ML/deep-learning research/application work.
- **Data Analyst:** BI, Power BI, reporting, dashboards, Excel, KPI/operational analytics.
- **Business Analyst:** requirements, stakeholders, process/specification/UAT/business-delivery work.
- **AI Engineer:** Generative AI, LLM, RAG, agents, conversational AI, AI application engineering.
- **Master:** ambiguous, hybrid or cross-functional roles where no specialist variant clearly dominates.

### 3. Machine Learning Engineer is resolved without a seventh CV

For ML Engineer / Machine Learning Engineer postings:

- use **AI Engineer** when the work centers on LLM/RAG/agents/AI applications;
- use **Data Scientist** when the work centers on modeling/statistics/experimentation;
- use **Data Engineer** when the work centers on ML data pipelines/platforms/MLOps-style infrastructure.

### 4. The Master CV is fallback, not default

A specialist CV is preferred when a role-family signal clearly dominates. The Master CV is selected when the posting is materially hybrid/ambiguous or no specialist variant has a clear lead.

### 5. Integrity is hash-bound

Each approved PDF has a committed SHA-256 in `founder/cv_portfolio.yaml`.

The runtime must verify the retrieved PDF bytes against the expected hash before using or attaching the file. A hash mismatch blocks the application rather than silently using mutated bytes.

### 6. Storage

The production PDFs live in a private Supabase Storage bucket:

`founder-cv-portfolio`

Object prefix:

`2026/`

The repository contains only the catalog, filenames and expected hashes. The PDF bodies are not required in the public repository.

### 7. Truth Pack remains authoritative for claims, not CV assembly

The Truth Pack is still the professional-fact authority for:

- opportunity qualification and ranking;
- requirement-to-evidence mapping;
- cover letters;
- application answers;
- interview preparation;
- future profile changes.

The fixed PDFs are approved presentations of that truth.

If a CV becomes stale because the Founder approves a material career update, that CV variant must be deliberately replaced, re-reviewed and assigned a new hash/version. OpportunityOS never patches it automatically.

### 8. Cover letters and application answers may remain generated

Opportunity-specific cover letters and application answers may still be generated, but every founder-specific claim remains Truth-locked and validated under existing claim rules.

## Consequences

### Positive

- zero layout drift;
- zero per-posting CV wording mutation;
- predictable ATS behavior;
- simpler outbound attachment selection;
- much smaller application-time failure surface;
- easy byte-level audit of the exact CV submitted.

### Trade-offs

- an individual posting may contain a keyword absent from the chosen fixed CV;
- updating career history requires deliberately refreshing affected CV variants;
- six files must be stored and hash-verified.

These trade-offs are accepted because reliability and exact presentation are more important than marginal per-posting keyword rewriting.

## Rejected

- generating a new CV for every posting;
- automatically editing the selected PDF;
- keeping separate role-specific CVs beyond the six approved files without a Founder decision;
- using a different PDF when its hash does not match the locked portfolio.

## Runtime invariant

**Employment application = opportunity -> deterministic CV selection -> hash verification -> attach the exact approved PDF.**

There is no CV text-generation step in the employment application path.
