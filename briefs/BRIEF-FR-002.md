# BRIEF-FR-002 — Founder Foundation & Runtime Backbone

**Terminal gate:** Reproducible Python packaging/bootstrap contract (`pyproject.toml`), PostgreSQL as production-shaped primary relational persistence layer with explicit Alembic migrations, legacy SQLite-to-PostgreSQL import path, durable background worker runtime with leases, poison queue, and crash recovery, automated backup/restore verification, structured logging with sensitive-data redaction, fact-locked binary DOCX and PDF export with claim parity and ATS/layout regression protection, generalized alert ingestion engine across regional and global job/opportunity alerts, structured first-party discovery (Ashby adapter, Schema.org extractor, company crawlers), stale-job pre-action re-verification, durable founder feedback backend, prompt-injection / untrusted-content boundary evaluation, 100% pass across all existing and new suites on real PostgreSQL CI, independent reviews PASS, and exact post-merge CI PASS.

## Transactional execution

Maintain an internal unresolved-task ledger and dependency DAG. Do not return while an available agent or tool can execute an unresolved task; repair defects and rerun invalidated evidence automatically.

## Capability preflight

Map every logical role to a capability exposed by the execution harness before starting. An approved separate model, tool, or session may satisfy an independence requirement; record the planned handoff and immutable evidence.

```yaml
phase_id: "BRIEF-FR-002"
objective: "Establish the reproducible packaging, PostgreSQL persistence, Alembic migrations, background worker runtime, backup/restore, log redaction, binary DOCX/PDF export, alert ingestion, structured discovery, stale verification, founder feedback, and untrusted-content security foundation."
why_now: "With domain models and core engines verified in Founder Alpha 0–4 and reconciled in GATE-FR-001, OpportunityOS requires a production-shaped runtime backbone before building the FastAPI backend and Founder Web Alpha."
user_value:
  founder_employment: "Provides reproducible local/staging startup, robust background alert processing, searchable ATS-friendly DOCX/PDF resumes with 100% TruthGraph claim binding, and durable match feedback."
  founder_independent_work: "Provides multi-source procurement alert ingestion, structured proposal export with compliance checklists, and durable pipeline tracking."
non_negotiables:
  - "Zero factual fabrication in binary exports: DOCX and PDF renderers may change presentation only, binding 100% of material claims to verified TruthGraph assertions."
  - "PostgreSQL is the production primary relational persistence target; SQLite is restricted to isolated tests or explicit local development."
  - "Idempotency reservations, submission authority, and UNKNOWN_OUTCOME freezes must survive PostgreSQL migration and concurrency."
  - "Worker execution must never bypass submission authority, PreSubmitManifest, global kill switch, or CAPTCHA/MFA hard stops."
  - "Untrusted job/RFP/email text is DATA, never executable model/tool instructions."
  - "Zero private founder data in mirror-safe reports or repository files."
  - "BRIEF-000 through BRIEF-006 domain invariants remain frozen and 100% green."
explicitly_out_of_scope:
  - "Next.js frontend, dashboard pages, or feed UI (reserved for BRIEF-FR-003)."
  - "FastAPI public REST API endpoints (reserved for BRIEF-FR-003)."
  - "Multi-tenant / Family Alpha productization (BRIEF-007 remains BLOCKED)."
  - "Live founder credentials / real application submissions."
budget_cap: "0 USD (local execution harness)"
concurrency_cap: "4 parallel worktrees/subagents"
required_acceptance_metrics:
  binary_export_claim_parity_rate: 1.0
  ats_layout_regression_failure_count: 0
  postgres_concurrency_race_failures: 0
  legacy_sqlite_migration_data_loss: 0
  untrusted_prompt_injection_breaches: 0
  frozen_brief_regressions: 0
required_deliverables:
  - "briefs/BRIEF-FR-002.md"
  - "pyproject.toml"
  - "storage/ PostgreSQL models, engine, Alembic migrations, repository, and SQLite migrator"
  - "worker/ background queue, runner, leases, dead letters, and crash recovery"
  - "core/logging.py structured logger with sensitive data redaction"
  - "scripts/backup_restore.py automated PostgreSQL backup and restore CLI"
  - "matching/binary_export.py and ats_quality.py DOCX/PDF export with ATS regression suite"
  - "opportunity/alert_ingestion.py, adapters/ashby.py, schema_org.py, reverification.py"
  - "feedback/ models and service for immutable founder feedback events"
  - "security/ untrusted content / prompt-injection evaluation suite"
  - "reports/REPORT-FR-002.md"
  - "docs/STATE.md"
```
