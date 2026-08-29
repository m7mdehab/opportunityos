# ADR-0007 — Professional Truth Graph and Provenance Model

- **Status:** accepted
- **Date:** 2026-08-29
- **Phase:** BRIEF-002
- **Supersedes:** none
- **Superseded by:** none

## Context

Opportunity matching, CV tailoring, and proposal generation require verifiable ground truth from founder career data and independent professional capabilities. Without an atomic provenance model, generative or heuristic systems risk hallucinating experience, exaggerating metrics, claiming planned credentials as held, or making commitments beyond business capacity, directly violating Product Constitution §2.1 and §2.5.

## Decision

Implement an atomic, dual-track Professional Truth Graph (`truth/` package):

1. **Atomic Evidence Provenance:** Every material fact or capability claim is linked to one or more `EvidenceRecord` nodes with explicit `VerificationStatus` (`VERIFIED`, `APPROXIMATE`, `UNVERIFIED`, `EXPLICIT_NULL`).
2. **Claim Classification Ontology:** Classify assertions strictly as `DIRECT_FACT`, `NORMALIZED_FACT`, `DERIVED_CAPABILITY`, `USER_ASSERTION`, `UNSUPPORTED_CLAIM`, or `PROHIBITED_CLAIM`.
3. **Certification State Invariants:** Enforce four explicit certification states (`COMPLETED`, `IN_PROGRESS`, `EXPIRED`, `PLANNED`). Planned credentials must never be represented as held (Product Constitution §2.1(4)).
4. **Dual-Track Profiles:**
   - **Employment Career Profile:** Employer history, canonical names, allowed market titles, responsibilities, quantifiable achievements with evidence-backed metric levels, skills, education, languages, work authorizations.
   - **Independent Capability Profile:** Consulting services, portfolio case studies, deliverables, target/excluded industries, engagement types, and business capacity (entity status, availability, turnover/bonding bounds).
5. **Deterministic Claim & Red Line Validation:** Provide `ClaimValidator` to verify candidate CV bullets, statements, and proposal answers against the graph, rejecting unevidenced assertions and enforcing Red Lines / Never-Claim constraints.
6. **Data Boundary & Private Code:** Truth graph schema and validation code reside in `truth/` within the private authoritative repository (not published to the public documentation mirror), while actual private founder personal data is strictly confined to gitignored `private/`.

## Consequences

Downstream matching engines, CV compilers, and proposal generators can select, reorder, and summarize only verified facts. Hallucinated experience, unbacked metrics, or unheld certifications fail closed at the validation boundary.

## Required tests and rollback

Maintain deterministic unit and adversarial test suites covering model immutability, evidence linking, date normalization, metric verification, certification states, and 100% rejection of seeded Red Line violations. Roll back by replacing the validation or extraction logic without discarding underlying evidence nodes.
