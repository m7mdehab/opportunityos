# ADR-0024 — Founder-Locked CV Portfolio Selection

- **Status:** Accepted
- **Date:** 2026-09-19
- **Updated:** 2026-09-21
- **Related:** BRIEF-FR-004, ADR-0009, ADR-0017, ADR-0023

## Context

OpportunityOS historically generated a tailored CV for each employment opportunity. In practice this introduced avoidable risk in wording, layout, formatting, ATS behavior, and visual regression.

The Founder has now supplied and approved a final 2026 CV system containing **eight targeted role-family CVs plus one Master Comprehensive CV**, each in PDF and DOCX form:

1. Data Engineering & Integration
2. Data Analytics & BI
3. Data Scientist
4. Machine Learning Engineer
5. AI / LLM Engineer
6. Business & Technical Business Analyst
7. AI / Technical Solutions Engineer
8. Full-Stack / Product Engineer
9. Master Comprehensive

The eight targeted PDFs are exactly two pages each. The Master Comprehensive PDF is intentionally three pages. The paired DOCX files are canonical editable masters. The full 2026-09-21 package also carries the Founder-approved role mapping, ATS audit, professional personalization, technology/evidence maps, CV content rules, supporting truth summary, and registry.

## Decision

### 1. Employment CV generation remains disabled

OpportunityOS must not automatically:

- rewrite approved CV bullets;
- rewrite approved summaries;
- regenerate a CV from the Truth Graph at application time;
- change fonts, spacing, pagination, layout or section ordering;
- invent a tenth permanent CV family.

For an employment posting, OpportunityOS selects exactly one of the nine final PDFs and preserves its bytes unchanged.

The DOCX files are stored privately as editable masters for a future controlled, Founder-approved tailoring workflow. Their existence does not re-enable automatic application-time rewriting.

### 2. Matching selects across eight targeted families

CV selection is deterministic from the normalized opportunity:

- title;
- description;
- responsibilities;
- requirements;
- listed skills.

The targeted families are:

- **Data Engineering & Integration:** data engineering, migration, ETL/ELT, source-to-target mapping, integration, pipelines, validation, reconciliation, data-quality and data-platform work.
- **Data Analytics & BI:** SQL analysis, Power BI, Excel, KPI/reporting, dashboards, operational, supply-chain and marketing analytics.
- **Data Scientist:** statistical/probabilistic modeling, forecasting, experimentation, model calibration/evaluation, decision science and geospatial data science.
- **Machine Learning Engineer:** applied ML, deep learning, computer vision, model pipelines, training/evaluation, inference/model serving and production ML engineering.
- **AI / LLM Engineer:** Generative AI, LLMs, RAG, embeddings/retrieval, agents, conversational AI, prompt/tool workflows and AI evaluation.
- **Business & Technical Business Analyst:** requirements, stakeholder coordination, business/process analysis, data mapping/validation, KPI/reporting and technical translation.
- **AI / Technical Solutions Engineer:** technical discovery, solution design, API/data integration, prototyping, implementation planning, client-facing technical consulting and production readiness.
- **Full-Stack / Product Engineer:** Next.js/React/TypeScript, Python/FastAPI, database-backed product engineering, API integration, ecommerce/product systems, testing, CI/CD and deployment.
- **Master Comprehensive:** ambiguous, hybrid or cross-functional opportunities where no targeted family clearly dominates.

The authoritative role aliases and evidence boundaries are the Founder-approved OpportunityOS_CV_Registry.json and ROLE_CV_MAPPING.md from the final pack. Repository selection code mirrors that contract.

### 3. Machine Learning Engineer now has a dedicated final CV

The prior six-CV policy routed ML Engineer roles to AI Engineer, Data Scientist or Data Engineer depending on job emphasis.

That rule is superseded.

Machine Learning Engineer / Applied ML Engineer / Computer Vision Engineer / Geospatial ML Engineer / ML Engineer roles now route to the dedicated **Machine Learning Engineer** CV when that family clearly dominates.

### 4. The Master CV is fallback, not default

A targeted CV is preferred when a role-family signal clearly dominates. The Master Comprehensive CV is selected when the posting is materially hybrid/ambiguous or no targeted family has a clear lead.

### 5. Integrity is hash-bound

Each approved PDF has a committed SHA-256 in founder/cv_portfolio.yaml.

The paired DOCX master hashes and the authoritative source-package metadata are also recorded there.

The runtime must verify retrieved PDF bytes against the expected hash before using or attaching the file. A hash mismatch blocks the application rather than silently using mutated bytes.

The Founder-only pack importer independently checksum-verifies every required PDF, DOCX and supporting document from the 2026-09-21 final package before any production object is replaced, then downloads stored objects and verifies them again byte-for-byte.

### 6. Storage

The production PDFs live in the private Supabase Storage bucket:

founder-cv-portfolio

Object prefixes:

- production PDFs: 2026/
- editable DOCX masters: 2026/editable/
- supporting system documents and authoritative ZIP: 2026/system/

The repository contains catalog metadata, filenames, hashes and selection logic. Founder CV bodies remain outside the repository.

### 7. Professional truth and supporting context remain separate from immutable application PDFs

The structured OpportunityOS Truth Pack remains authoritative for qualification, ranking, requirement-to-evidence mapping, cover letters and application answers.

The 2026-09-21 CV package also contains a Master Professional Personalization document and supporting evidence maps. Those supporting documents are stored privately with the CV system and are the canonical context for future controlled CV/personalization work, subject to the rule that newer explicit Founder instructions override older material.

The package's truth_pack.yaml is a supporting CV-system summary and is **not** silently substituted for the runtime structured Truth Pack schema.

The final PDFs are approved presentations of the Founder truth. OpportunityOS does not patch them automatically.

### 8. Cover letters and application answers may remain generated

Opportunity-specific cover letters and application answers may still be generated, but every Founder-specific claim remains Truth-locked and validated under existing claim rules.

## Consequences

### Positive

- nine stable, role-appropriate application CV choices;
- dedicated ML, solutions-engineering and full-stack/product coverage;
- zero application-time layout drift;
- zero per-posting CV wording mutation;
- predictable ATS behavior;
- byte-level audit of the exact CV submitted;
- canonical DOCX masters retained for later Founder-approved controlled tailoring;
- supporting professional context and evidence maps preserved with the CV system.

### Trade-offs

- an individual posting may contain a keyword absent from the chosen fixed CV;
- updating career history requires deliberately refreshing affected CV variants and hashes;
- nine PDFs plus nine DOCX masters and supporting system documents must be stored and verified;
- stored historical selection metadata may initially reflect a legacy family until a current selector pass refreshes it, while the serving route itself always recomputes the current selection.

These trade-offs are accepted because reliability, truthful evidence and exact presentation are more important than marginal per-posting keyword rewriting.

## Rejected

- generating a new CV for every posting;
- automatically editing the selected PDF;
- silently treating the supporting truth_pack.yaml summary as the runtime Truth Pack;
- retaining the old six-CV / ML-routing rule after the 2026-09-21 final pack;
- using a PDF when its hash does not match the locked portfolio.

## Runtime invariant

**Employment application = opportunity -> deterministic nine-CV selection -> hash verification -> attach the exact approved PDF.**

There is no CV text-generation step in the current employment application path.
