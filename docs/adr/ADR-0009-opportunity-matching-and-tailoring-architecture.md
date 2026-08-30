# ADR-0009: Opportunity Matching, Qualification, and Truth-Locked Tailoring Architecture

- **Status:** Accepted
- **Date:** 2026-08-30
- **Deciders:** Antigravity Master Agent, OpportunityOS Core Team
- **Consulted:** Product Constitution, BRIEF-001, BRIEF-002, BRIEF-003, BRIEF-004

## Context

OpportunityOS connects verified founder truth (`truth/`, BRIEF-002) with autonomous, provenance-backed opportunity feeds (`opportunity/`, BRIEF-003) across employment, contract, freelance, and procurement tracks.
To assist the founder in decision-making and opportunity application, the system requires a layer capable of:
1. Deterministically evaluating hard mandatory qualifications without false rejections from missing data;
2. Scoring and ranking opportunities along distinct, explainable dimensions for employment versus independent consulting;
3. Constructing an explicit Requirement ↔ Evidence mapping that traces required competencies to verified evidence;
4. Compiling tailored, opportunity-specific application artifacts (CVs, cover letters, proposals, capability statements) that are 100% truth-locked to verified graph assertions;
5. Validating all generated claims to ensure zero factual fabrication, red-line violations, or credential state upgrades.

## Decision

We establish the `matching/` package as the single authoritative subsystem for qualification, ranking, mapping, tailoring compilation, and artifact claim validation.

### 1. Fail-Closed Qualification Authority
- Hard rejections (`INELIGIBLE` / `NO-BID`) require **both**:
  1. An explicit opportunity requirement backed by raw source provenance;
  2. A verified founder fact or constraint from `TruthGraph` that directly contradicts it.
- Missing data (`UNKNOWN != FALSE`), absent opportunity fields (`ABSENT != INELIGIBLE`), or ambiguous terms evaluate strictly to `UNCERTAIN` (`REVIEW`).
- Automatic drop/rejection is disabled by default (`auto_rejection_enabled=False`) until a founder-labeled gold set demonstrates $\ge 95\%$ precision.

### 2. Dual-Track Explainable Scorer & Ranking
- Separate scoring models for Employment vs Independent/Procurement:
  - **Employment:** Core Skills, Seniority/Experience, Responsibilities, Domain/Industry, Geography/Remote, Compensation, Trajectory.
  - **Independent:** Services/Capabilities, Scope, Portfolio/Case Studies, Budget, Delivery/Location, Evidence Sufficiency, Uncertainty Penalty.
- Every match result emits an immutable `MatchEvaluation` with a detailed explanation, component scores, supporting strengths, gaps, unknowns, and explicit links to TruthGraph assertion IDs and Opportunity field pointers.

### 3. Truth-Locked Tailoring Compilers
- Master CVs are immutable and never modified in place.
- Compilers produce versioned, immutable `TailoredArtifact` instances tied to specific opportunity content hashes, template versions, and source `EvidenceClaim` IDs.
- Historical assertions (employers, dates, titles, skills, tools, credentials, metrics) are restricted to verified `AtomicAssertion` and `MetricAssertion` records.
- Forward-looking commitments (pricing, availability, delivery dates, staffing, guarantees) must derive from explicit founder policy; unconfigured commitments are marked `UNRESOLVED` (RED) and never fabricated.

### 4. 100% Artifact Claim-to-Evidence Validation
- `ArtifactClaimValidator` inspects the generated artifact text directly, validating claims against active assertions, validity dates, red-line rules, certification state, and unmutated employers/dates/titles.
- Fails closed on any unsupported material claim, red-line rule violation, or unproven alias.

## Consequences

- **Positive:** Guarantees zero hallucinated claims, explains every match score transparently, prevents destructive loss of viable opportunities due to missing data, and maintains an auditable bridge between opportunity requirements and verified evidence.
- **Negative:** Requires rigorous maintenance of requirement-to-evidence mappings and strict adherence to claim validation rules.

