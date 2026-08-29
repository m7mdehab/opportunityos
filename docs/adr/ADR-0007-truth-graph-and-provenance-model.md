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
5. **Relational Composition Guard:** A composite claim connecting multiple entities (e.g. employer + skill, client + achievement, timeframe + capability) cannot be synthesized merely through token coverage across disconnected evidence atoms. Evidence composition must be grounded in an explicit common entity node (or composite evidence record) in the `TruthGraph`.
6. **Conservative Epistemic Propagation (Weakest-Link Rule):** When a claim relies on multiple evidence records, its epistemic assertion type is strictly bounded by its weakest material dependency (`USER_ASSERTION` < `DERIVED_CAPABILITY` < `NORMALIZED_FACT` < `DIRECT_FACT`). Derived capabilities or self-assertions can never be upgraded to direct facts through evidence mixing.
7. **Exact Metric Provenance Binding:** Numeric performance metrics (percentages, monetary amounts, multipliers) must map to the specific evidence record containing that exact metric value, and that specific record must be bound to a graph entity node with `MetricVerification.VERIFIED`. Unverified or approximate metrics cannot be laundered through global metric pooling.
8. **Structured Never-Claim Policy:** Never-Claim rules represent semantic policy categories (`GUARANTEED_OUTCOME`, `FORTUNE_500_PRESTIGE`, `UNAUTHORIZED_LEGAL_PRACTICE`, etc.) enforced via structural regex and forbidden phrases. Never-Claim policy evaluates first and strictly overrides evidence eligibility: a prohibited concept is rejected even if synthetic or external evidence asserts it.
9. **Strict Finite-Number Commercial Capacity Validation:** All monetary and capacity quantities (`annual_turnover_usd`, `bid_bond_capacity_usd`, `hours_per_week`, `min_project_value`, `max_project_value`) must be finite, non-negative numbers, failing closed on booleans, NaN, positive/negative infinity, and non-numeric strings.
10. **Data Boundary & Private Code:** Truth graph schema and validation code reside in `truth/` within the private authoritative repository (not published to the public documentation mirror), while actual private founder personal data is strictly confined to gitignored `private/`.

## Consequences

Downstream matching engines, CV compilers, and proposal generators can select, reorder, and summarize only verified facts. Hallucinated experience, unbacked metrics, relation laundering, or unheld certifications fail closed at the validation boundary.

## Required tests and rollback

Maintain deterministic unit, adversarial, and property-based test suites covering model immutability, evidence linking, date normalization, relational composition, weakest-link epistemic propagation, exact metric provenance, and 100% rejection of seeded Red Line / Never-Claim violations. Roll back by replacing the validation or extraction logic without discarding underlying evidence nodes.
