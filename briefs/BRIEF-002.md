# BRIEF-002 — Professional Truth Graph & Capability Ingestion

**Terminal gate:** Verified deterministic schema, ingestion pipeline, evidence-claim graph, atomic truth validation, and zero unbacked claims across founder career data and independent professional capabilities.

## Transactional execution

Maintain an internal unresolved-task ledger and dependency DAG. Do not return while an available agent or tool can execute an unresolved task; repair defects and rerun invalidated evidence automatically.

## Capability preflight

Map every logical role to a capability exposed by the execution harness before starting. An approved separate model, tool, or session may satisfy an independence requirement; record the planned handoff and immutable evidence.

```yaml
phase_id: "BRIEF-002"
objective: "Implement the dual-track Professional Truth Graph and Capability Ingestion engine for employment and independent professional contracting."
why_now: "Source reconnaissance (BRIEF-001) established the geographic eligibility model and proved that general Western boards alone have a 0.32% Egypt-eligible rate. Ingesting structured founder career facts and independent professional capabilities is the essential prerequisite for opportunity matching, tailoring, and proposal generation."
user_value:
  founder_employment: "Enables accurate, evidence-backed matching and CV tailoring without fabricating experience or exceeding verified claims."
  founder_independent_work: "Structures consulting services, project portfolio, RFP qualifications, and business capacity to evaluate multilateral and commercial procurement tenders."
non_negotiables:
  - "Never fabricate a claim about the founder (Product Constitution §1, AGENTS.md)."
  - "Every capability and career claim must link to verified evidence or explicit null (Master Plan §12.1, §12.1A)."
  - "Red Lines and 'never claim' phrases must be strictly enforced with automated rejection."
  - "Private founder personal data must remain within the private/ boundary and never leak to the public documentation mirror (ADR-0001, ADR-0004)."
explicitly_out_of_scope:
  - "Automated application or proposal submission to external platforms."
  - "Live external API mutations or interactive human communications."
  - "Multi-user tenant isolation beyond the founder single-tenant baseline."
allowed_sources_and_tools:
  - "Local structured JSON/YAML/Markdown schemas in private/ and truth/."
  - "Python 3.12 standard library and deterministic graph/schema validation."
  - "OpenAI Codex, Claude Code, GitHub Copilot according to model routing."
preapproved_external_actions: []
forbidden_external_actions:
  - "All external POST/PUT/PATCH/DELETE mutations across all hosts."
legal_policy_constraints:
  - "Strict compliance with Product Constitution and AGENTS.md external action semantics."
security_privacy_constraints:
  - "Zero PII in mirrored paths; private career details kept in private/ or local storage."
budget_cap: "0 USD (local execution harness and pre-allocated zero-budget resources)"
concurrency_cap: "4 parallel worktrees/subagents"
required_acceptance_metrics:
  truth_graph_validation: "100% deterministic schema adherence and zero unbacked claims"
  red_line_rejection_rate: "100% rejection on seeded exaggerations / red-line terms"
required_gold_sets:
  - "Synthetic career and capability fixtures with verified vs unbacked claims"
required_deliverables:
  - "truth/ domain models, schemas, and evidence-linking graph"
  - "Ingestion parser for career milestones, skills, deliverables, and service offerings"
  - "Verification test suite and guard integration"
required_documentation:
  - "ADR documenting Truth Graph schema and atomic claim provenance"
  - "REPORT-002 phase gate report"
final_report_only: true
```

## Master Agent Obligations

- Derive the technical and product task graph independently.
- Identify parallel-safe, serial, and gated work.
- Instantiate needed council roles and specialist maker/checker agents.
- Keep ordinary implementation decisions internal.
- Execute repair loops after failed reviews or tests.
- Stop consequential branches safely at hard gates while continuing independent work.
- Return one evidence-backed Phase Gate Report.

## Acceptance Criteria

- [x] Career truth schema implemented with atomic evidence links (dates, titles, organizations, achievements).
- [x] Independent capability graph implemented with services, portfolio items, RFP qualification parameters, and delivery constraints.
- [x] Automated verification engine enforces "never claim" constraints and flags unbacked assertions.
- [x] Unit and property-based test suite covering truth ingestion, validation, and rejection.
- [x] Zero PII or private career data committed to public/mirrored directories; repository guards green.
- [x] ADR accepted for Truth Graph Architecture and Provenance Model.
- [x] Independent audit / checker passes acceptance gate.
- [x] `docs/STATE.md` regenerated and accurate.
