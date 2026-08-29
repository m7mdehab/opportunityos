# ADR-0006 — Geographic Region Completion and Taxonomy Invariants

- **Status:** accepted
- **Date:** 2026-08-29
- **Phase:** BRIEF-001
- **Supersedes:** none
- **Superseded by:** none

## Context

ADR-0003 established the geographic eligibility model and region-based membership, but initial definitions for EU, EEA, Europe, Africa, and the Americas were incomplete sample sets. Additionally, regional hierarchy invariants (such as `LATAM ⊆ AMERICAS` and `AFRICA ∪ EUROPE ⊆ EMEA`) were not strictly enforced.

## Decision

Complete closed region membership definitions in `recon/regions.py` to cover:
1. **EU**: All 27 member states.
2. **EEA**: EU-27 + Norway (NO), Iceland (IS), Liechtenstein (LI).
3. **EUROPE**: EEA + UK (GB), Switzerland (CH), European microstates (AD, MC, SM, VA), and Western Balkan / Eastern European nations (AL, BA, ME, MK, RS, UA, BY, MD, XK).
4. **AFRICA**: All 54 UN-recognized African nations.
5. **NORTH_AFRICA**: Egypt (EG), Sudan (SD), Libya (LY), Algeria (DZ), Morocco (MA), Tunisia (TN).
6. **MENA**: Core Middle East and North Africa states.
7. **LATAM**: Latin American nations.
8. **AMERICAS**: North, Central, and South America + Caribbean (`LATAM ⊆ AMERICAS`).
9. **EMEA**: Full union of Europe, MENA, and Africa (`_EUROPE | _MENA | _AFRICA`).
10. **APAC**: Key Asia-Pacific nations.

## Consequences

Derivations for regional postings resolve accurately across all member countries while maintaining mathematical set hierarchy invariants. Regional classification rules remain pure, deterministic, and evidence-backed.

## Required tests and rollback

Maintain deterministic unit tests verifying exact membership, boundary exclusions, and hierarchy invariants (`EU ⊆ EEA ⊆ EUROPE ⊆ EMEA`, `LATAM ⊆ AMERICAS`, `AFRICA ⊆ EMEA`).

