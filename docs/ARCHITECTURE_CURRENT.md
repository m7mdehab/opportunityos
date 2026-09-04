# OpportunityOS Current Architecture

This document is a compact map of the architecture that exists now. Detailed requirement history remains in `docs/MASTER_PLAN.md`, ADRs, briefs, and reports.

## Product Flow

Current intended system flow:

`discover -> ingest -> qualify -> score -> truth-locked tailor -> prepare/fill/controlled-submit -> monitor outcomes -> learn safely`

OPOS serves both employment and independent professional opportunity tracks, including contract, freelance/consulting, and procurement use cases.

## Authority Layers

### Founder Truth / Provenance

The Truth Graph and `EvidenceClaim` model are the factual authority for material founder claims.

Core invariants:

- generated artifacts may select, reorder, summarize, and rewrite verified facts;
- they may not invent employers, dates, titles, skills, credentials, outcomes, work authorization, compensation, availability, legal declarations, or other material facts/commitments;
- material claims remain traceable to evidence;
- credential states are explicit;
- planned credentials never become held;
- open-world semantics apply: unknown/absent is not false/ineligible.

This authority is reused by later generators and outbound answers. Do not create a weaker parallel truth path.

### Opportunity Discovery and Ingestion

The opportunity layer normalizes multiple opportunity classes and sources under a central source-policy registry.

Established capabilities include:

- employment, contract, freelance/consulting, and procurement opportunity types;
- source registry at runtime;
- source-policy/access-state tracking;
- source health and schema/transport observations;
- atomic provenance;
- geographic eligibility classification;
- conservative cross-source dedupe;
- conservative compensation parsing;
- ATS/source-specific adapters where permitted.

Coverage is never permission. A source can be discoverable and still be manual-only or prohibited for automation.

### Matching and Qualification

Matching is evidence-aware and explainable.

Key rules:

- hard rejection requires an explicit opportunity requirement plus a verified founder conflict or an explicit versioned policy;
- missing evidence does not become a negative fact;
- auto-rejection remains disabled unless its founder-labeled precision requirement is actually met;
- scoring may rank evidence but may not fabricate fit;
- requirement/evidence status must remain inspectable.

Current Founder Web work adds richer extraction, title-family normalization, proficiency-aware skills, seniority derived from tenure/leadership evidence, clustering, facets, search, and user-facing cards.

### Artifact Generation

Employment and independent-work artifacts are truth-locked.

Current document architecture includes structured CV/cover-letter models, multiple ATS templates, DOCX/PDF output, preview, artifact validation, and claim-support inspection.

Artifact authority is bound to the correct founder/workspace/opportunity/truth-pack state. Stale, unsupported, or wrongly owned artifacts must fail closed.

### Outbound Action Authority

Outbound action is governed by explicit execution modes and source/action permissions.

Modes:

- `DRY_RUN` - default, no external mutation;
- `ASSISTED` - may navigate/fill/upload where allowed, must not submit;
- `CONTROLLED_SUBMIT` - only for individually graduated adapters/actions with explicit authority and all pre-submit checks satisfied.

Critical invariants:

- Yellow/policy answers require explicit versioned policy authority;
- Red/legal/sensitive/ambiguous questions pause unless exact founder-approved authority exists;
- global kill switch is checked immediately before side effect;
- CAPTCHA/MFA/bot challenges stop execution;
- durable atomic reservation/idempotency prevents duplicate submission;
- uncertain external outcome becomes `UNKNOWN_OUTCOME`, never automatic retry;
- success requires confirmation evidence, not a button click;
- adapter graduation evidence must be real and persisted, not synthetic text hashed into authority.

### Operational Autonomy / Feedback

The later operational layer owns inbound/recruiter/client signal processing, pipeline synchronization, outcome monitoring, analytics, and safe learning loops without weakening deterministic truth authority.

The system should automate repetitive monitoring/orchestration while preserving founder judgment at interviews, negotiation, ambiguous legal/commercial commitments, and other explicitly human gates.

### Founder Web Alpha

The current FR series builds the founder-facing product/control plane over the earlier engine.

At current `main`, work through BRIEF-FR-005 is shipped and BRIEF-FR-006 is active/not closed.

BRIEF-FR-006 has delivered substantial founder-control and document/search improvements, including:

- richer opportunity extraction;
- seniority/skills/title-family corrections;
- deterministic family clustering;
- facets and full-text search;
- improved cards with work mode/location/remote scope;
- structured CV/document generation and preview;
- saved views and founder-control storage;
- artifact caching;
- expanded source registry and board discovery machinery.

Its current limiting gap is source breadth/real feed yield, not the existence of the core matching/document machinery.

## Storage and State

OPOS uses persistent database-backed state and migrations. Concurrency, idempotency, transaction boundaries, and migration backfills are correctness properties, not implementation details.

Current architecture includes generated `docs/STATE.md` as a repository-state projection. It must be regenerated from the generator and never hand-edited.

## Source Policy and Transport

The source registry distinguishes measured access behavior from permission.

- rate limits and transport failures are recorded rather than reinterpreted;
- 403/429/CAPTCHA/MFA/verification are stop conditions, not bypass targets;
- read-only POST is permitted only where explicitly documented as semantically read-only, such as the TED search exception;
- direct fetch paths must not bypass the central policy/acquisition authority.

## Tenancy

Current product posture remains founder/single-user through the current Founder Web Alpha phase under accepted tenancy decisions.

Multi-tenant Family Alpha / BRIEF-007 remains blocked until the Founder Web Alpha is live and validated. Do not prematurely expand tenancy merely because the schema anticipates later isolation.

## Repository/Governance

- private `opportunityos` is authoritative;
- public `opportunityos-docs` mirrors only allowlisted documentation;
- private founder truth/personal/application/credential data never enters the public mirror;
- one branch per brief and isolated worktrees for writable parallel work;
- deterministic gates, CI, persisted evidence, and independent review govern high-consequence closure;
- the Owner/Overseer independently decides final PASS/NOT PASS.

## Detailed References

Use task-specific sources rather than expanding this file:

- truth/product law: `docs/PRODUCT_CONSTITUTION.md`
- architecture decisions: `docs/adr/`
- full plan: `docs/MASTER_PLAN.md`
- source details: `docs/SOURCE_REGISTRY.yaml`, `docs/SOURCE_EVIDENCE.md`
- execution: `docs/AGENT_EXECUTION_PROTOCOL.md`
- current state: `docs/STATE.md`
- current brief/report/evidence under `briefs/`, `reports/`, and `reports/evidence/`.
