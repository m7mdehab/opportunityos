# BRIEF-004 — Opportunity Matching & Truth-Locked Tailoring

**Terminal gate:** Complete, explainable qualification, dual-track matching/ranking, requirement-to-evidence mapping, truth-locked tailoring compilers (for employment and independent consulting), artifact claim-to-evidence validation, versioned policy scoring, and gold set evaluation harness.

## Transactional execution

Maintain an internal unresolved-task ledger and dependency DAG. Do not return while an available agent or tool can execute an unresolved task; repair defects and rerun invalidated evidence automatically.

## Capability preflight

Map every logical role to a capability exposed by the execution harness before
starting. An approved separate model, tool, or session may satisfy an
independence requirement; record the planned handoff and immutable evidence.

```yaml
phase_id: "BRIEF-004"
objective: "Implement the dual-track Opportunity Matching, Qualification, Requirement-to-Evidence Mapping, and Truth-Locked Tailoring layer."
why_now: "With geographic eligibility (BRIEF-001), professional truth modeling (BRIEF-002), and autonomous opportunity ingestion (BRIEF-003) operational, OpportunityOS now requires an intelligent qualification, ranking, and tailoring engine to evaluate fit and generate 100% truth-locked application and proposal artifacts without external mutations."
user_value:
  founder_employment: "Accurately qualifies and ranks employment opportunities against verified career history, generating customized, evidence-safe CVs and application narratives."
  founder_independent_work: "Accurately qualifies and ranks multilateral/international procurement and freelance opportunities, generating structured proposals, capability statements, and compliance checklists backed by verified case studies."
non_negotiables:
  - "Never fabricate or mutate historical facts, skills, titles, employers, dates, credentials, or metrics (Product Constitution §1.1)."
  - "100% material claim coverage: every generated material claim must trace directly to an AtomicAssertion or EvidenceRecord."
  - "Forward-looking commitments must derive from explicit founder policy; unconfigured commitments must be marked UNRESOLVED (RED), never fabricated."
  - "Hard rejections require both an explicit opportunity requirement (with provenance) and verified conflicting founder truth. Missing data or ambiguous language evaluates to UNCERTAIN/REVIEW."
  - "Automatic rejection dropping is disabled by default until >=95% founder precision is demonstrated."
explicitly_out_of_scope:
  - "Automated application or proposal submission to third-party endpoints (reserved for BRIEF-005)."
  - "External interactive communications or live account actions."
allowed_sources_and_tools:
  - "Local TruthGraph (BRIEF-002) and Opportunity models (BRIEF-003)."
  - "Python 3.12 standard library, deterministic scoring, and claim validation."
budget_cap: "0 USD (local execution harness)"
concurrency_cap: "4 parallel worktrees/subagents"
required_acceptance_metrics:
  qualification_precision: "100% adherence to fail-closed hard constraint rules"
  claim_verification_rate: "100% verifiable factual claims across generated artifacts"
  ranking_determinism: "100% identical score evaluation across execution environments"
required_gold_sets:
  - "Dual-track opportunity matching and artifact compilation regression fixtures"
required_deliverables:
  - "briefs/BRIEF-004.md"
  - "matching/ models, qualification, scorer, mapping, compilers, validator, and gold set"
  - "ADR-0009 documenting matching & tailoring architecture"
  - "reports/REPORT-004.md"
  - "docs/STATE.md"
final_report_only: true
```

## Work breakdown & dependency DAG

1. **Phase 1: Data Models & Protocol Contracts (`matching/models.py`)**
   - Qualification decisions (`QUALIFIED`, `INELIGIBLE`, `UNCERTAIN`).
   - Dual-track match evaluations, dimension scores, and explanation structures.
   - Requirement-to-evidence mappings (`SUPPORTED`, `PARTIALLY_SUPPORTED`, `GAP`, `UNKNOWN`, `NOT_APPLICABLE`).
   - Tailored artifact models, sections, generated claims, and forward commitment checklists.
   - Scoring & tailoring policies (`auto_rejection_enabled=False`).

2. **Phase 2: Hard-Constraint Qualification Engine (`matching/qualification.py`)**
   - Employment mandatory constraints (geography, residency restrictions, work authorization, sponsorship, timezone, remote policy, seniority exclusions, required languages).
   - Independent work constraints (entity requirements, turnover/bonding, deadlines, delivery location, mandatory certifications, bid language).
   - Strict rule: Rejection requires explicit requirement with provenance AND verified conflicting founder truth. UNKNOWN != FALSE, ABSENT != INELIGIBLE.

3. **Phase 3: Explainable Dual-Track Scorer & Ranking (`matching/scorer.py`)**
   - Employment scoring dimensions (Core Skill Fit, Seniority/Experience Fit, Responsibility Scope Fit, Domain Fit, Geography/Remote Fit, Compensation Fit, Career Trajectory).
   - Independent scoring dimensions (Service/Capability Fit, Scope Fit, Portfolio Evidence Fit, Budget Fit, Delivery Fit, Evidence Sufficiency, Uncertainty Penalty).
   - Full explainability breakdown and provenance links to TruthGraph records.

4. **Phase 4: Requirement ↔ Evidence Mapping Engine (`matching/mapping.py`)**
   - Maps opportunity responsibilities/requirements to TruthGraph atomic assertions and capability records.
   - Preserves uncertainty; prevents tool similarity or adjacent skill laundering.

5. **Phase 5: Truth-Locked Compilers (`matching/compiler_employment.py`, `matching/compiler_independent.py`)**
   - Employment compiler: tailored CV, cover letter, application narrative. Master CV remains immutable.
   - Independent compiler: freelance proposal, consultant cover response, EOI, capability statement, RFP response scaffold. Forward commitments marked UNRESOLVED (RED) if unstated in policy.

6. **Phase 6: Artifact Claim-to-Evidence Validator (`matching/validator.py`)**
   - 100% claim-to-evidence verification against active TruthGraph assertions.
   - Fails closed on unsupported claims, modified historical values, red-line rule violations, or planned-to-completed credential upgrades.

7. **Phase 7: Gold Set Benchmark Harness (`matching/gold_set.py`)**
   - Dual-track regression fixtures and evaluation harness.

8. **Phase 8: Tests, ADR, Report & Review**
   - Unit, integration, adversarial, and determinism tests.
   - ADR-0009 committed.
   - Blinded independent audit subagent.
   - REPORT-004 and docs/STATE.md.
