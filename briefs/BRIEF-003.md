# BRIEF-003 — Opportunity Discovery & Ingestion Pipelines

**Terminal gate:** Verified dual-track opportunity ingestion pipelines for employment and independent consulting, deterministic normalization, deduplication, geographic eligibility derivation, and source health tracking across authorized sources.

## Transactional execution

Maintain an internal unresolved-task ledger and dependency DAG. Do not return while an available agent or tool can execute an unresolved task; repair defects and rerun invalidated evidence automatically.

## Capability preflight

Map every logical role to a capability exposed by the execution harness before
starting. An approved separate model, tool, or session may satisfy an
independence requirement; record the planned handoff and immutable evidence.

```yaml
phase_id: "BRIEF-003"
objective: "Implement the dual-track Opportunity Discovery & Ingestion pipeline covering employment, contract, freelance, and procurement tracks."
why_now: "Source reconnaissance (BRIEF-001) established geographic classification rules and truth modeling (BRIEF-002) established atomic provenance. Ingesting, normalizing, and deduplicating live opportunity feeds across both employment and independent consulting channels is the essential next step to feed opportunity matching and proposal tailoring."
user_value:
  founder_employment: "Discovers and filters eligible remote employment and contract opportunities across international company ATS feeds and boards."
  founder_independent_work: "Discovers and filters multilateral, international, and regional procurement opportunities, RFPs, and consulting notices suitable for the founder's capability profile."
non_negotiables:
  - "Coverage is not permission. Every source adapter must follow its documented access, attribution, storage, rate-limit, and automation policy (Product Constitution §3.1, AGENTS.md)."
  - "Never perform external mutations (POST, PUT, PATCH, DELETE) except the committed read-only TED notice query exception under ADR-0005."
  - "Never create an external account or accept terms on the founder's behalf."
  - "All ingested opportunities must retain atomic provenance and source attribution."
explicitly_out_of_scope:
  - "Automated application or proposal submission."
  - "External interactive communications or scraping behind authentication / anti-bot controls."
  - "Generative tailoring / artifact synthesis (reserved for BRIEF-004)."
allowed_sources_and_tools:
  - "Authorized public feeds and APIs registered in docs/SOURCE_REGISTRY.yaml."
  - "Python 3.12 standard library, deterministic ingestion, deduplication, and normalization."
  - "OpenAI Codex, Claude Code, GitHub Copilot according to model routing."
preapproved_external_actions:
  - "READ_ONLY_QUERY to https://api.ted.europa.eu/v3/notices/search (ADR-0005)."
forbidden_external_actions:
  - "All other external POST, PUT, PATCH, and DELETE operations across all hosts."
legal_policy_constraints:
  - "Strict compliance with Product Constitution, robots.txt, and source registry policy."
security_privacy_constraints:
  - "Zero PII in mirrored paths; private credentials or access tokens kept in local environment."
budget_cap: "0 USD (local execution harness and pre-allocated zero-budget resources)"
concurrency_cap: "4 parallel worktrees/subagents"
required_acceptance_metrics:
  pipeline_ingestion_accuracy: "100% deterministic normalization and provenance retention across all active feeds"
  deduplication_precision: "100% deduplication of identical opportunity postings"
required_gold_sets:
  - "Multi-source opportunity feed fixtures across employment and procurement tracks"
required_deliverables:
  - "Unified Opportunity data models and schemas"
  - "Ingestion pipelines for employment and procurement sources"
  - "Deduplication and normalization engine"
  - "Integration tests and source health monitoring"
required_documentation:
  - "ADR documenting Opportunity Data Model and Ingestion Pipeline Architecture"
  - "REPORT-003 phase gate report"
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

- [x] Unified Opportunity data model and schema implemented covering employment, contract, freelance, and procurement tracks.
- [x] Multi-source ingestion pipeline integrating authorized employment feeds (Greenhouse, Lever, Himalayas, Remotive, Remote OK, We Work Remotely) and independent procurement feeds (UNGM, World Bank, EU TED Search API).
- [x] Strict compliance with robots.txt, source registry, rate limits, and external action semantics (zero external mutations; allowlisted read-only TED POST queries).
- [x] Integration with geographic classification engine (`recon/geography.py`) and Professional Truth Graph (`truth/`).
- [x] Content hash deduplication and opportunity deduplication pipeline.
- [x] Unit and integration test suite covering feed parsing, normalization, error handling, and deduplication.
- [x] Independent audit / checker passes acceptance gate.
- [x] `docs/STATE.md` regenerated and accurate.
