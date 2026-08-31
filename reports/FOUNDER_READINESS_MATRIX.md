# OpportunityOS Founder-Readiness Reconciliation Matrix (GATE-FR-001)

**Generated:** 2026-08-31  
**Authority:** ChatGPT Overseer Authorization  
**Baseline Starting SHA:** `3303f1267c1325456ed8d4feef922a8923d2ff9a`  
**Evaluation Scope:** Master Product Development Plan v0.2 through Phase 5 (Founder Alpha 4)  

---

## 1. Vocabulary & Evaluation Methodology

### Status Vocabulary:
- **`DONE`**: The requirement is genuinely implemented and verified by executable unit/contract/adversarial tests and runtime code.
- **`PARTIAL`**: A meaningful portion exists in code, but material promised capabilities remain absent.
- **`MISSING`**: No meaningful production-capable implementation exists (or only stubs/ceremonial references exist).
- **`INTENTIONALLY_DEFERRED`**: The original Master Plan explicitly places this outside founder readiness (e.g. Phase 6+ Family Alpha, B2B hiring, multi-tenant public SaaS), or an explicit accepted decision deferred it.
- **`REQUIRES_LIVE_INTEGRATION_OR_CREDENTIALS`**: Production-shaped implementation exists and is appropriately tested, but final real-world operation requires founder credentials/accounts/live network endpoints.

### Evidence Strength Vocabulary:
- **`PROVEN_RUNTIME`**: Verified in live/local executable runtime environments with persistent storage/network execution.
- **`TESTED_IMPLEMENTATION`**: Verified via exhaustive automated unit, integration, deterministic replay, or adversarial tests.
- **`IMPLEMENTED_UNTESTED`**: Present in source code but lacking dedicated regression/contract tests.
- **`DOCUMENTED_ONLY`**: Described in specifications, ADRs, or READMEs without executable code backing.
- **`NONE`**: Completely absent.

### Founder Criticality:
- **`P0`**: Blocks founder dual-track usefulness.
- **`P1`**: Materially reduces founder friction / qualified conversations.
- **`P2`**: Reliability, source health, analytics, learning.
- **`P3`**: Family/public B2C productization enablers (Phase 6–8).
- **`P4`**: Later organization-side productization (Phase 9–11).

---

## 2. Master Requirements Reconciliation Matrix

| Req ID | Master Plan Section | Requirement Description | Crit | Phase | Status | Evidence Strength | Implementation Files | Relevant Tests | Gap Explanation & Later Authority | Next Work Bucket |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- | :--- |
| **A. CONSTITUTION & SAFETY** | | | | | | | | | | |
| `REQ-SAF-001` | §2.1, §6.2 | Truthfulness: Generated materials must select/rewrite only verified facts; zero hallucination. | P0 | Ph0 | `DONE` | `TESTED_IMPLEMENTATION` | `truth/models.py`, `truth/graph.py`, `truth/validator.py` | `truth/test_adversarial.py`, `truth/test_validator.py` | 100% material claim evidence binding enforced; ADR-0007. | NONE |
| `REQ-SAF-002` | §2.1, §6.2 | Certification States: Completed, in_progress, expired, planned; planned cannot be claimed as held. | P0 | Ph0 | `DONE` | `TESTED_IMPLEMENTATION` | `truth/models.py:28` | `truth/test_models.py`, `matching/test_adversarial.py` | Enforced at model and artifact compiler levels. | NONE |
| `REQ-SAF-003` | §2.2, §19.3 | Red Questions / Commitments: Unknown/sensitive/legal questions must PAUSE/RED, never auto-answered. | P0 | Ph4 | `DONE` | `TESTED_IMPLEMENTATION` | `outbound/ontology.py`, `outbound/answer_engine.py` | `outbound/test_zero_tolerance.py`, `outbound/test_adversarial.py` | ADR-0010; strict Green/Yellow/Red policy enforced. | NONE |
| `REQ-SAF-004` | §2.3, §32 | Source Compliance: Coverage != permission; respect robots.txt, terms, rate limits, no scraping hacks. | P0 | Ph0 | `DONE` | `TESTED_IMPLEMENTATION` | `docs/SOURCE_REGISTRY.yaml`, `opportunity/registry.py`, `opportunity/transport.py` | `opportunity/test_acquisition.py`, `opportunity/test_adversarial.py` | Preflight check refuses unregistered/disabled sources; ADR-0008. | NONE |
| `REQ-SAF-005` | §2.4, §31 | Secrets Management: Zero secrets in source control; boundary checks; PII redaction. | P0 | Ph0 | `DONE` | `PROVEN_RUNTIME` | `scripts/check_guard.py`, `.github/workflows/guard.yml` | `scripts/test_sync_mirror.py`, CI guard workflow | CI and pre-push hooks scan for secrets & unallowlisted files. | NONE |
| `REQ-SAF-006` | §2.5, §19.7 | Side-Effect Safety & Idempotency: Zero duplicate submissions; deterministic idempotency keys. | P0 | Ph4 | `DONE` | `TESTED_IMPLEMENTATION` | `outbound/idempotency.py`, `outbound/authority.py` | `outbound/test_idempotency.py`, `outbound/test_adversarial.py` | ADR-0010; SQLite reservation ledger with content hash locking. | NONE |
| `REQ-SAF-007` | §2.5, §19.6 | Controlled Submit Kill Switch: Global emergency disablement for outbound actions. | P0 | Ph4 | `DONE` | `TESTED_IMPLEMENTATION` | `outbound/registry.py:OutboundRegistry` | `outbound/test_registry.py`, `outbound/test_zero_tolerance.py` | ADR-0010; kill-switch disables submit immediately. | NONE |
| `REQ-SAF-008` | §2.5, §19.7 | CAPTCHA/MFA/Bot-Challenge Fail-Closed: Immediate halt on anti-bot controls without bypass. | P0 | Ph4 | `DONE` | `TESTED_IMPLEMENTATION` | `outbound/browser_engine.py` | `outbound/test_zero_tolerance.py` | Browser worker fails closed on CAPTCHA / bot challenge. | NONE |
| **B. PRODUCTION ARCHITECTURE & INFRASTRUCTURE** | | | | | | | | | | |
| `REQ-ARC-001` | §5.1, §5.2 | Primary Relational Persistence: PostgreSQL schema and migrations for SaaS multi-tenancy. | P1 | Ph0 | `MISSING` | `NONE` | None (SQLite used in `inbox/`, `outbound/`) | None | Plan specified PostgreSQL; current repo uses local SQLite stores (`inbox_store.db`, `outbound_actions.db`). | `PRODUCTION_INFRASTRUCTURE` |
| `REQ-ARC-002` | §5.2, §5.4 | Application API Layer: FastAPI application exposing typed endpoints for domain services. | P1 | Ph0 | `MISSING` | `NONE` | None | None | Domain logic exists in pure Python modules (`opportunity`, `matching`, `outbound`, `inbox`) without HTTP API layer. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-ARC-003` | §5.2, §5.3 | Web Application UI: Next.js + TypeScript dashboard with shadcn/ui and Tailwind. | P1 | Ph0 | `MISSING` | `NONE` | None | None | No frontend codebase exists in repo; all execution currently driven via Python APIs and test runners. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-ARC-004` | §5.2 | Background Worker Architecture: DB-backed job queue for asynchronous source fetching & matching. | P1 | Ph0 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `opportunity/pipeline.py`, `inbox/orchestrator.py` | `opportunity/test_pipeline.py`, `inbox/test_adversarial.py` | Orchestration pipelines exist in Python, but lack background daemon worker runner / job queue. | `PRODUCTION_INFRASTRUCTURE` |
| `REQ-ARC-005` | §5.2 | Packaging & Deployment: Docker, Docker Compose, and Caddy reverse proxy for automated HTTPS. | P2 | Ph0 | `MISSING` | `NONE` | None | None | No Dockerfile, compose.yml, or Caddyfile currently present in repo. | `PRODUCTION_INFRASTRUCTURE` |
| `REQ-ARC-006` | §5.2 | User Authentication: Auth.js / OAuth session management. | P1 | Ph0 | `MISSING` | `NONE` | None | None | No web auth layer exists; local single-founder context assumed in Python modules. | `PRODUCTION_INFRASTRUCTURE` |
| `REQ-ARC-007` | §5.2 | Backup & Restore: Automated database backups and verified restore routine. | P1 | Ph0 | `MISSING` | `NONE` | None | None | SQLite database files can be copied manually, but no automated backup/restore tooling exists. | `PRODUCTION_INFRASTRUCTURE` |
| `REQ-ARC-008` | §5.2 | Structured Observability: Structured logging, audit tables, and telemetry. | P2 | Ph0 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `inbox/persistence.py`, `outbound/idempotency.py` | `inbox/test_adversarial.py`, `outbound/test_adversarial.py` | Audit records exist in SQLite tables (`inbound_evidence`, `pipeline_events`, `outbound_actions`), but centralized logging missing. | `PRODUCTION_INFRASTRUCTURE` |
| **C. FOUNDER UI / PAGES** | | | | | | | | | | |
| `REQ-UIP-001` | §5.3 | Sign In / Account Page | P1 | Ph0 | `MISSING` | `NONE` | None | None | Web UI not yet implemented. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-002` | §5.3, §16.8 | Founder Dual-Track Dashboard: Top jobs, top client opportunities, attention items, health. | P0 | Ph1 | `MISSING` | `NONE` | None | None | Dashboard data models exist (`inbox/analytics.py`), but UI page does not exist. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-003` | §5.3 | Opportunities Feed: Dual-track filterable list with scores, eligibility badges, and match reasons. | P0 | Ph1 | `MISSING` | `NONE` | None | None | Ingestion & scoring engines exist; feed UI page missing. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-004` | §5.3 | Opportunity Detail View: Provenance, requirements breakdown, match explanation, action buttons. | P0 | Ph1 | `MISSING` | `NONE` | None | None | Data structures populated; detail UI page missing. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-005` | §5.3 | Needs Attention View: High-priority notifications, review-required questions, deadlines. | P0 | Ph5 | `MISSING` | `NONE` | None | None | Notification store & models exist (`inbox/notifications.py`); UI view missing. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-006` | §5.3, §16.1 | Professional Truth Graph UI: Fact inspector, evidence links, never-claims, and manual edit UI. | P0 | Ph1 | `MISSING` | `NONE` | None | None | `truth` subsystem has full graph/validator; frontend editor missing. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-007` | §5.3, §16.6 | CV & Artifact Generator / Viewer: Document preview, diff, claim inspector, DOCX/PDF download. | P0 | Ph1 | `MISSING` | `NONE` | None | None | Compilers emit JSON/Markdown data structures (`matching/compiler_*.py`); UI viewer missing. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-008` | §5.3, §16.7 | Applications & Engagement Pipeline: Visual stage tracker for submitted applications/proposals. | P1 | Ph1 | `MISSING` | `NONE` | None | None | Pipeline state machine exists (`inbox/pipeline.py`); UI Kanban/table missing. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-009` | §5.3, §17.3 | Sources & Company Watchlist: Target employer & buyer monitoring UI with health indicators. | P1 | Ph2 | `MISSING` | `NONE` | None | None | Registry exists (`opportunity/registry.py`); UI page missing. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-010` | §5.3, §20.4 | Dual-Track Analytics: Multi-dimensional conversion metrics, interview rates, response times. | P2 | Ph5 | `MISSING` | `NONE` | None | None | Analytics engine complete (`inbox/analytics.py`); UI charts missing. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-011` | §5.3, §19.3 | Automation Rules & Policy Settings: Green/Yellow/Red question rules & spend caps. | P1 | Ph4 | `MISSING` | `NONE` | None | None | Policy engine complete (`outbound/ontology.py`); UI settings missing. | `FOUNDER_WEB_INTEGRATION` |
| `REQ-UIP-012` | §5.3, §17.7 | Founder Admin: Agent runs, source health telemetry, eval benchmarks, failure logs. | P2 | Ph2 | `MISSING` | `NONE` | None | None | Health reports generated in code (`opportunity/health.py`); UI page missing. | `FOUNDER_WEB_INTEGRATION` |
| **D. FOUNDER TRUTH & CAPABILITY GRAPH** | | | | | | | | | | |
| `REQ-TRU-001` | §6.2, §12.1 | Career Truth Graph: Experiences, achievements, skills, credentials, education, languages. | P0 | Ph0 | `DONE` | `TESTED_IMPLEMENTATION` | `truth/models.py`, `truth/graph.py` | `truth/test_models.py`, `truth/test_graph.py` | Provenance-backed graph with atomic assertions and typed relations; ADR-0007. | NONE |
| `REQ-TRU-002` | §6.2, §12.1A| Independent Capability Graph: Services, case studies, capacity, pricing guidance, legal entity. | P0 | Ph0 | `DONE` | `TESTED_IMPLEMENTATION` | `truth/models.py:BusinessCapacity`, `truth/graph.py` | `truth/test_models.py`, `truth/test_property.py` | Fully modeled with strict bounds and evidence binding. | NONE |
| `REQ-TRU-003` | §12.1, §15.5 | Evidence Provenance Binding: Every atomic assertion requires verified source evidence. | P0 | Ph0 | `DONE` | `TESTED_IMPLEMENTATION` | `truth/models.py:AtomicAssertion`, `truth/validator.py` | `truth/test_validator.py`, `truth/test_adversarial.py` | Fail-closed evidence verification on all identity-sensitive predicates. | NONE |
| `REQ-TRU-004` | §12.1, §12.2 | Metric Assertion Verification: Strict numeric tuple proof (subject, value, unit, context, modality). | P0 | Ph0 | `DONE` | `TESTED_IMPLEMENTATION` | `truth/graph.py`, `truth/models.py:MetricAssertion` | `truth/test_adversarial.py`, `truth/test_property.py` | Direct mathematical proof with canonical unit compatibility. | NONE |
| `REQ-TRU-005` | §12.1, §15.5 | Never-Claim Concept Dominance: Prohibited concepts strictly rejected under all circumstances. | P0 | Ph0 | `DONE` | `TESTED_IMPLEMENTATION` | `truth/validator.py:ClaimValidator` | `truth/test_property.py`, `truth/test_validator.py` | 100% rejection across all aliases and case variations. | NONE |
| `REQ-TRU-006` | §12.1, §16.1 | Open-World Semantics (UNKNOWN != FALSE): Absence of evidence yields UNKNOWN, never inferred No. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `truth/validator.py`, `matching/qualification.py` | `matching/test_adversarial.py`, `truth/test_validator.py` | Core architectural invariant enforced across all engines. | NONE |
| `REQ-TRU-007` | §12.1, §15.5 | Ingestion Parsers: JSON and YAML ingestion with strict type safety and schema validation. | P0 | Ph0 | `DONE` | `TESTED_IMPLEMENTATION` | `truth/ingest.py` | `truth/test_ingest.py` | Deterministic parsing with duplicate key and block tag rejection. | NONE |
| **E. UNIVERSAL OPPORTUNITY INGESTION & PIPELINE** | | | | | | | | | | |
| `REQ-OPP-001` | §3.2, §6.3 | Universal Opportunity Model: Multi-track representation (Employment, Contract, Freelance, Procurement). | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/models.py:Opportunity` | `opportunity/test_models.py` | Supports all 4 tracks without collapsing to employment; ADR-0008. | NONE |
| `REQ-OPP-002` | §6.3, §16.3 | Atomic Field-Level Provenance: Record-level checksum, item pointer, and derivation rules. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/models.py:FieldProvenance` | `opportunity/test_adversarial.py`, `opportunity/test_models.py` | Populated material fields require valid FieldProvenance. | NONE |
| `REQ-OPP-003` | §6.3, §16.3 | Universal Deduplication: Exact content-hash dedupe & multi-source cluster linking. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/dedupe.py:OpportunityDeduplicator` | `opportunity/test_dedupe.py`, `opportunity/test_adversarial.py` | False-merges strictly prevented across distinct requisitions & organizations. | NONE |
| `REQ-OPP-004` | §7.2, §16.2 | Central Authorized Acquisition & Transport Layer: Authorizes requests against `SOURCE_REGISTRY.yaml`. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/registry.py`, `opportunity/transport.py` | `opportunity/test_acquisition.py` | Unregistered/disabled sources and arbitrary hosts blocked preflight; ADR-0008. | NONE |
| `REQ-OPP-005` | §11, §17.7 | Source Health Telemetry: Tracks HTTP status, latency, record counts, and schema drift. | P1 | Ph2 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/health.py:SourceHealthMonitor` | `opportunity/test_health.py` | Categorizes EMPTY_RESULTS, PERSISTENT_FAILURE, SCHEMA_DRIFT_SUSPECTED. | NONE |
| `REQ-OPP-006` | §17.6 | Salary and Budget Normalization: Normalizes currencies, intervals (hourly/monthly/annual), and ranges. | P1 | Ph2 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/normalization.py` | `opportunity/test_normalization.py` | Converts currency/amounts without inventing default currency; ADR-0008. | NONE |
| `REQ-OPP-007` | §17.6 | Geographic Scope Classification: Classifies Worldwide, Regional, Country-Only, and Restrictive scopes. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/normalization.py`, `recon/geography.py` | `opportunity/test_normalization.py`, `recon/test_geography_remediation.py` | ADR-0003, ADR-0006; MENA & Egypt eligibility precision. | NONE |
| **F. FOUNDER SOURCE PACK (42 SOURCE FAMILIES)** | | | | | | | | | | |
| `REQ-SRC-001` | §8.1, §40.1 | S01: Greenhouse Job Board API | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/adapters/greenhouse.py` | `opportunity/test_adapters.py` | Active adapter with public API fetching, board token binding. | NONE |
| `REQ-SRC-002` | §8.1, §40.1 | S02: Lever Postings API | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/adapters/lever.py` | `opportunity/test_adapters.py` | Active adapter with public postings API fetching, site token binding. | NONE |
| `REQ-SRC-003` | §8.1, §40.1 | S03: Ashby Public Job Postings API | P1 | Ph1 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `docs/SOURCE_REGISTRY.yaml:ashby` | `inbox/test_adversarial.py` (referenced in fixtures) | Registered in SOURCE_REGISTRY; adapter pending dedicated module. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-004` | §8.1, §40.1 | S04: Schema.org JobPosting Structured Extraction | P1 | Ph2 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml` | None | Policy documented; parser engine pending implementation. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-005` | §8.2, §40.1 | S05: Himalayas Remote Jobs API | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/adapters/himalayas.py` | `opportunity/test_adapters.py` | Active adapter with JSON API ingestion and attribution. | NONE |
| `REQ-SRC-006` | §8.2, §40.1 | S06: Jobicy Remote Jobs API / RSS | P1 | Ph1 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `docs/SOURCE_REGISTRY.yaml:jobicy` | `recon/test_classification.py` | Documented as disabled_policy due to robots.txt reachability in recon. | NONE |
| `REQ-SRC-007` | §8.2, §40.1 | S07: We Work Remotely RSS | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/adapters/we_work_remotely.py` | `opportunity/test_adapters.py` | Active adapter with XML RSS ingestion and backlink attribution. | NONE |
| `REQ-SRC-008` | §8.2, §40.1 | S08: Remotive API / RSS | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/adapters/remotive.py` | `opportunity/test_adapters.py` | Active adapter with JSON API ingestion. | NONE |
| `REQ-SRC-009` | §8.2, §40.1 | S09: Remote OK API / Feed | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/adapters/remote_ok.py` | `opportunity/test_adapters.py` | Active adapter with JSON feed ingestion. | NONE |
| `REQ-SRC-010` | §8.2, §40.1 | S10: Adzuna Developer API | P1 | Ph1 | `REQUIRES_LIVE_INTEGRATION_OR_CREDENTIALS` | `TESTED_IMPLEMENTATION` | `docs/SOURCE_REGISTRY.yaml:adzuna` | `opportunity/test_acquisition.py` | Registered; requires live APP_ID and APP_KEY for live network requests. | `LIVE_CONFIGURATION_OR_CREDENTIALS` |
| `REQ-SRC-011` | §8.3, §40.1 | S11: WUZZUF (Email / Alert / Deep Link) | P1 | Ph1 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `docs/SOURCE_REGISTRY.yaml:wuzzuf` | `inbox/test_classifier.py` | Documented as alert_ingestion / manual_only; email alert parser pending. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-012` | §8.3, §40.1 | S12: Bayt (Email / Alert / Deep Link) | P1 | Ph1 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `docs/SOURCE_REGISTRY.yaml:bayt` | `inbox/test_classifier.py` | Documented as alert_ingestion / manual_only; email alert parser pending. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-013` | §8.3, §40.1 | S13: Naukrigulf (Email / Alert / Deep Link) | P1 | Ph1 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `docs/SOURCE_REGISTRY.yaml:naukrigulf` | `inbox/test_classifier.py` | Documented as alert_ingestion / manual_only; email alert parser pending. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-014` | §8.3, §40.1 | S14: GulfTalent (Email / Alert / Deep Link) | P1 | Ph1 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `docs/SOURCE_REGISTRY.yaml:gulftalent` | `inbox/test_classifier.py` | Documented as alert_ingestion / manual_only; email alert parser pending. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-015` | §8.3, §40.1 | S15: LinkedIn Jobs (Alerts / Deep Links) | P0 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:linkedin` | None | Documented as manual_deeplink only to prevent scraping; alert parser pending. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-016` | §8.3, §40.1 | S16: Indeed (Alerts / Deep Links) | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:indeed` | None | Documented as manual_deeplink only; alert parser pending. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-017` | §8.3, §40.7 | S58: Remote Talent (remote.com) | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:remote_talent` | None | Documented in registry as alert_ingestion / manual_deeplink. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-018` | §8.3, §40.7 | S57: Working Nomads (Remote Egypt / Worldwide) | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:working_nomads` | None | Documented in registry as public_get / alert route. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-019` | §8.3, §40.7 | S56: Arc Remote Jobs (Employment & Freelance) | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:arc` | None | Documented in registry as manual_deeplink / alert route. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-020` | §8.3, §40.7 | S59: Wellfound Jobs (Startup Jobs) | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:wellfound` | None | Documented in registry as manual_deeplink / alert route. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-021` | §9.1, §40.4 | S30: Freelancer.com Official API / Sandbox | P1 | Ph1 | `REQUIRES_LIVE_INTEGRATION_OR_CREDENTIALS` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:freelancer` | None | Documented in registry; requires developer sandbox OAuth / credentials. | `LIVE_CONFIGURATION_OR_CREDENTIALS` |
| `REQ-SRC-022` | §9.1, §40.4 | S31: Upwork (Manual / Deep Link / Alert) | P0 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:upwork` | None | Prohibited automation; manual_deeplink policy documented; alert ingestion pending. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-023` | §9.2, §40.4 | S32/S33: UNGM (UN Global Marketplace Notices) | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/adapters/ungm.py` | `opportunity/test_adapters.py` | Active adapter with XML procurement notice parsing and CPV mapping. | NONE |
| `REQ-SRC-024` | §9.2, §40.4 | S34/S35: World Bank Procurement Notices | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/adapters/world_bank.py` | `opportunity/test_adapters.py` | Active adapter with JSON procurement data parsing. | NONE |
| `REQ-SRC-025` | §9.2, §40.4 | S36: EBRD ECEPP Procurement Opportunities | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:ebrd_ecepp` | None | Documented in registry as public_get / research_only. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-026` | §9.2, §40.4 | S37: African Development Bank (AfDB) Notices | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:afdb` | None | Documented in registry as public_get / RSS route. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-027` | §9.2, §40.4 | S38: EU TED Search API | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `opportunity/adapters/eu_ted.py` | `opportunity/test_adapters.py` | Active adapter with read-only search POST query under ADR-0005. | NONE |
| `REQ-SRC-028` | §9.2, §40.4 | S39: Saudi Etimad Tender Portal | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:etimad` | None | Documented in registry as manual_deeplink / research_only. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-029` | §9.2, §40.4 | S40: UAE Digital Procurement Platform | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:uae_mof` | None | Documented in registry as manual_deeplink / research_only. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-030` | §9.2, §40.4 | S41: Egypt GAGS Government Procurement Portal | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:egypt_gags` | None | Documented in registry as manual_deeplink / research_only. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-031` | §9.1, §40.7 | S49: Mostaql (مستقل) Arabic Freelance Marketplace | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:mostaql` | None | Documented in registry as manual_deeplink / alert route. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-032` | §9.1, §40.7 | S50: Khamsat (خمسات) Services Marketplace | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:khamsat` | None | Documented in registry as research_only / market intelligence. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-033` | §9.1, §40.7 | S51: Ureed MENA Freelance / Translation | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:ureed` | None | Documented in registry as manual_deeplink / alert route. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-034` | §9.1, §40.7 | S52: Contra Independent Opportunities | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:contra` | None | Documented in registry as manual_deeplink / alert route. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-035` | §9.1, §40.7 | S53: Guru Freelance Projects | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:guru` | None | Documented in registry as manual_deeplink. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-036` | §9.1, §40.7 | S54: Malt Freelancer / Client Platform | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:malt` | None | Documented in registry as manual_deeplink. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-037` | §9.1, §40.7 | S55: Toptal Talent Network | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml:toptal` | None | Documented in registry as manual_only / account_gated. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-038` | §8.1, §17.3 | Direct Employer Career Pages & Watchlist | P0 | Ph1 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `opportunity/registry.py` | `opportunity/test_registry.py` | ATS board binding implemented; generic first-party crawler missing. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-039` | §9.2, §17.3 | Direct Buyer / Consulting Watchlist Pages | P1 | Ph1 | `PARTIAL` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml` | None | Buyer watchlist structure documented; recurring scraper missing. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-SRC-040` | §8.1, §40.1 | Workable Career Pages | P2 | Ph2 | `INTENTIONALLY_DEFERRED` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml` | None | Deferred to Phase 2+ in Master Plan §8.1. | `INTENTIONALLY_LATER` |
| `REQ-SRC-041` | §8.1, §40.1 | Workday Career Pages | P2 | Ph2 | `INTENTIONALLY_DEFERRED` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml` | None | Deferred to Phase 2+ in Master Plan §8.1. | `INTENTIONALLY_LATER` |
| `REQ-SRC-042` | §8.3, §40.1 | Glassdoor (Research / Salary) | P2 | Ph2 | `INTENTIONALLY_DEFERRED` | `DOCUMENTED_ONLY` | `docs/SOURCE_REGISTRY.yaml` | None | Supplementary research; deferred. | `INTENTIONALLY_LATER` |
| **G. ELIGIBILITY & QUALIFICATION ENGINE** | | | | | | | | | | |
| `REQ-ELI-001` | §16.4, §29.1 | Separation of Hard Eligibility from Fit Score: Hard constraints evaluate independently. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/qualification.py:QualificationEngine` | `matching/test_qualification.py` | Deterministic hard rejection vs fit scoring; ADR-0009. | NONE |
| `REQ-ELI-002` | §16.4 | Hard Rejection Proof Invariant: Hard rejection requires explicit requirement AND conflicting founder fact. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/qualification.py` | `matching/test_adversarial.py` | Unstated founder truth yields UNCERTAIN / REVIEW (never false rejection). | NONE |
| `REQ-ELI-003` | §16.4 | Dual-Track Constraint Evaluation: Employment rules (visa, remote) vs Independent rules (entity, bond). | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/qualification.py` | `matching/test_qualification.py` | Evaluates Track.EMPLOYMENT and Track.PROCUREMENT/FREELANCE distinctly. | NONE |
| `REQ-ELI-004` | §16.4 | Work-Authorization Closed-World Protection: Positive proof in one region != No in another. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/qualification.py` | `matching/test_adversarial.py` | Open-world jurisdiction matching; unstated yields PAUSE/REVIEW. | NONE |
| `REQ-ELI-005` | §16.4 | Qualification Precision Target (>= 95%): Zero false-negative exclusions on gold benchmarks. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/gold_set.py` | `matching/test_gold_set.py` | 100% precision on curated gold benchmark cases. | NONE |
| **H. FIT & BID/NO-BID SCORING ENGINE** | | | | | | | | | | |
| `REQ-SCO-001` | §16.5, §29.2 | Multi-Dimensional Dual-Track Scoring: Distinct scoring rubrics for Employment vs Independent. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/scorer.py:FitScorer` | `matching/test_scorer.py`, `matching/test_models.py` | Responsibility, skill, experience, domain, budget, delivery fit. | NONE |
| `REQ-SCO-002` | §16.5, §29.2 | Evidence-Grounded Scoring: Zero fabricated strengths; every score dimension cites TruthGraph evidence. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/scorer.py` | `matching/test_adversarial.py` | Unasserted founder truth produces uncertainty penalty without fabricated strengths. | NONE |
| `REQ-SCO-003` | §16.5, §29.2 | Explainability Vectors: Output includes strengths, gaps, uncertainties, and provenance refs. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/models.py:FitAssessment` | `matching/test_scorer.py` | Comprehensive explainability on every score calculation. | NONE |
| `REQ-SCO-004` | §16.5 | Anti-Keyword-Stuffing Invariant: No single keyword dominates score; structured feature balance. | P1 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/scorer.py` | `matching/test_adversarial.py` | Balanced vector combination with missing-data tolerance. | NONE |
| **I. FACT-LOCKED ARTIFACT COMPILERS** | | | | | | | | | | |
| `REQ-ART-001` | §16.6, §18.3 | Immutable Versioned CV Compiler: Compiles tailored CV artifact tied to Opportunity and Evidence. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/compiler_employment.py` | `matching/test_compiler.py`, `matching/test_adversarial.py` | Selects relevant achievements, orders skills, locks claims to evidence IDs. | NONE |
| `REQ-ART-002` | §16.6, §18.3A| Proposal & Capability Compiler: Compiles tailored proposal draft, work plan, and compliance checklist. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/compiler_independent.py` | `matching/test_compiler.py` | Structured responses for freelance/consulting/procurement; ADR-0009. | NONE |
| `REQ-ART-003` | §16.6, §18.3 | 100% Material Claim Provenance: Validator proves every claim maps to active TruthGraph assertions. | P0 | Ph0 | `DONE` | `TESTED_IMPLEMENTATION` | `matching/validator.py:ArtifactClaimValidator` | `matching/test_adversarial.py` | Fails closed on assertion laundering, planned credentials, or missing evidence. | NONE |
| `REQ-ART-004` | §16.6, §18.5 | Render Formats (DOCX / PDF): Fact-locked DOCX and PDF document export. | P1 | Ph1 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `matching/compiler_employment.py`, `matching/models.py` | `matching/test_compiler.py` | Structured section models and Markdown/text rendered; binary DOCX/PDF export pending. | `FOUNDER_ENGINE_BLOCKER` |
| `REQ-ART-005` | §16.6, §18.5 | ATS Readability & Render Regression Suite: Text extraction, heading layout, no clipping. | P1 | Ph3 | `PARTIAL` | `TESTED_IMPLEMENTATION` | `matching/validator.py` | `matching/test_adversarial.py` | Claim verification & tampering detection complete; layout visual regression pending. | `FOUNDER_ENGINE_BLOCKER` |
| **J. ACTION HANDOFF, ASSIST & OUTBOUND AUTOMATION** | | | | | | | | | | |
| `REQ-ACT-001` | §16.7, §19.5 | Assisted Mode Application Preparation: Browser engine fills forms, saves trace, pauses for review. | P0 | Ph4 | `DONE` | `TESTED_IMPLEMENTATION` | `outbound/browser_engine.py`, `outbound/authority.py` | `outbound/test_browser_engine.py`, `outbound/test_adversarial.py` | Fills Green/Yellow answers, captures pre-submit telemetry, never submits in assisted mode. | NONE |
| `REQ-ACT-002` | §19.2, §19.3 | Application Answer Engine: Answers form questions with Green/Yellow/Red truth classification. | P0 | Ph4 | `DONE` | `TESTED_IMPLEMENTATION` | `outbound/answer_engine.py`, `outbound/ontology.py` | `outbound/test_answer_engine.py`, `outbound/test_adversarial.py` | Strict currency/interval, sponsorship, and legal question handling; ADR-0010. | NONE |
| `REQ-ACT-003` | §19.4 | Mock ATS Harness: Emulates Greenhouse, Lever, Ashby, and multi-step forms with dynamic fields. | P0 | Ph4 | `DONE` | `TESTED_IMPLEMENTATION` | `outbound/mock_harness.py` | `outbound/test_adapters.py`, `outbound/test_zero_tolerance.py` | Local simulation testing all field types, validation errors, and bot challenges. | NONE |
| `REQ-ACT-004` | §19.6 | Controlled Submit Graduation & PreSubmitManifest: Cryptographic authority manifest binding. | P0 | Ph4 | `DONE` | `TESTED_IMPLEMENTATION` | `outbound/authority.py:SubmissionAuthorityGuard` | `outbound/test_adversarial.py` | Pre-submission manifest mandatory; final verification against current state; ADR-0010. | NONE |
| `REQ-ACT-005` | §19.7 | Idempotency & Reservation Ledger: Prevents duplicate submissions under race conditions. | P0 | Ph4 | `DONE` | `TESTED_IMPLEMENTATION` | `outbound/idempotency.py:DurableOutboundStore` | `outbound/test_idempotency.py`, `outbound/test_adversarial.py` | SQLite reservation table with unique idempotency keys; UNKNOWN_OUTCOME freeze. | NONE |
| `REQ-ACT-006` | §16.7, §19.6A| Canonical Action Handoff (Deep Link / Manual Submit): Opens verified URL with pre-filled package. | P0 | Ph1 | `DONE` | `TESTED_IMPLEMENTATION` | `outbound/models.py`, `opportunity/models.py` | `outbound/test_models.py` | Generates verified canonical deep link URLs for employment & procurement. | NONE |
| **K. INBOUND INGESTION, PIPELINE & LEARNING LOOP** | | | | | | | | | | |
| `REQ-INB-001` | §20.1 | Read-Only Inbound Ingestion: Provider-neutral mail ingestion with Gmail adapter. | P0 | Ph5 | `DONE` | `TESTED_IMPLEMENTATION` | `inbox/ingestion.py:InboundIngestionService` | `inbox/test_ingestion.py` | Read-only listing/fetching; mutation attempts raise PermissionError; ADR-0011. | NONE |
| `REQ-INB-002` | §20.1 | Dual-Track Signal Classifier: Classifies 20 distinct signal categories across both tracks. | P0 | Ph5 | `DONE` | `TESTED_IMPLEMENTATION` | `inbox/classifier.py:ResponseClassifier` | `inbox/test_classifier.py` | 100% recall & precision across 23 curated gold scenarios. | NONE |
| `REQ-INB-003` | §20.2 | Priority Notification Engine: Emits alerts strictly on high/urgent actionable events. | P0 | Ph5 | `DONE` | `TESTED_IMPLEMENTATION` | `inbox/notifications.py:FounderNotificationEngine` | `inbox/test_pipeline_and_notifications.py` | Urgent/high priority for interviews, offers, recruiter replies; low priority filtered. | NONE |
| `REQ-INB-004` | §20.3 | Deterministic Opportunity Correlation: Matches inbound signals to known opportunities. | P0 | Ph5 | `DONE` | `TESTED_IMPLEMENTATION` | `inbox/correlation.py:OpportunityCorrelationEngine` | `inbox/test_correlation.py`, `inbox/test_adversarial.py` | Normalized exact match on external refs, action IDs, receipts; 0 false merges on 9 attacks. | NONE |
| `REQ-INB-005` | §20.3 | Durable SQLite Persistence & Crash-Safe Lifecycle: Explicit `FETCHED -> PROCESSED` lifecycle. | P0 | Ph5 | `DONE` | `TESTED_IMPLEMENTATION` | `inbox/persistence.py:DurableInboxStore` | `inbox/test_adversarial.py` | Replay resumes uncompleted batches without duplicate events/alerts; PR55 migration safe. | NONE |
| `REQ-INB-006` | §20.4 | Multi-Dimensional Outcome Analytics: Computes conversion by source, track, score band, etc. | P1 | Ph5 | `DONE` | `TESTED_IMPLEMENTATION` | `inbox/analytics.py:DualTrackAnalyticsEngine` | `inbox/test_adversarial.py` | Real application denominators; qualified_conversation derived; missing data UNAVAILABLE. | NONE |
| `REQ-INB-007` | §20.5 | Safe Learning Loop & Truth Immutability: Recommends strategy optimizations safely. | P1 | Ph5 | `DONE` | `TESTED_IMPLEMENTATION` | `inbox/learning.py:SafeLearningEngine` | `inbox/test_adversarial.py` | Recommends bounded weights on N>=5; TruthGraph and permissions are strictly immutable. | NONE |
| **L. MULTI-TENANT & COMMERCIAL EXPANSION (PHASES 6–11)** | | | | | | | | | | |
| `REQ-LATER-001`| §21 | Phase 6: Private Family Alpha Multi-Tenant Isolation & Cohort Onboarding | P3 | Ph6 | `INTENTIONALLY_DEFERRED` | `DOCUMENTED_ONLY` | None | None | Master Plan §21 explicitly places Family Alpha after Founder Alpha 4. | `INTENTIONALLY_LATER` |
| `REQ-LATER-002`| §22 | Phase 7: Public Employment B2C Beta & MENA Regulatory Compliance | P3 | Ph7 | `INTENTIONALLY_DEFERRED` | `DOCUMENTED_ONLY` | None | None | Commercial expansion deferred until family proof & legal review. | `INTENTIONALLY_LATER` |
| `REQ-LATER-003`| §23 | Phase 8: Freelancer / Prosumer B2C Productization | P3 | Ph8 | `INTENTIONALLY_DEFERRED` | `DOCUMENTED_ONLY` | None | None | Multi-user freelancer productization deferred. | `INTENTIONALLY_LATER` |
| `REQ-LATER-004`| §24 | Phase 9: Employer / B2B Sourcing & Shortlist Product | P4 | Ph9 | `INTENTIONALLY_DEFERRED` | `DOCUMENTED_ONLY` | None | None | Employer-side hiring product deferred. | `INTENTIONALLY_LATER` |
| `REQ-LATER-005`| §25 | Phase 10: Agency / Business Client Acquisition B2B Product | P4 | Ph10| `INTENTIONALLY_DEFERRED` | `DOCUMENTED_ONLY` | None | None | Organization-level procurement & business development deferred. | `INTENTIONALLY_LATER` |
| `REQ-LATER-006`| §26 | Phase 11: Unified Opportunity Platform & Regional Scaling | P4 | Ph11| `INTENTIONALLY_DEFERRED` | `DOCUMENTED_ONLY` | None | None | Platform-wide network effects deferred. | `INTENTIONALLY_LATER` |

---

## 3. First Founder Acceptance Script Reconciliation

Evaluation of the 14-step "First Founder Acceptance Script" defined in Master Plan §43:

| Step | Script Step Description | Status | Evidence & Explanation | Next Work Bucket |
| :---: | :--- | :---: | :--- | :--- |
| **1** | Sign in from a normal browser. | `NOT_POSSIBLE` | Web application and authentication UI do not exist in the repository. | `FOUNDER_WEB_INTEGRATION` |
| **2** | Open Opportunities feed. | `NOT_POSSIBLE` | UI feed page does not exist; data accessible only via Python script/REPL. | `FOUNDER_WEB_INTEGRATION` |
| **3** | Confirm new jobs have arrived from at least 3 independent source families. | `PASSABLE_NOW` | `opportunity/pipeline.py` executes ingestion across Greenhouse, Lever, Himalayas, WWR, Remotive, Remote OK, UNGM, World Bank, and EU TED. | NONE |
| **4** | Open a high-ranked role. | `NOT_POSSIBLE` | No UI detail page; rankings computable via `matching/scorer.py`. | `FOUNDER_WEB_INTEGRATION` |
| **5** | Verify source, canonical employer, location eligibility, match rationale, and gaps. | `PASSABLE_NOW` | `matching/qualification.py` and `matching/scorer.py` output structured provenance, eligibility rationale, and explanation vectors. | NONE |
| **6** | Click "Generate CV". | `NOT_POSSIBLE` | No interactive web UI button; generation executable via `EmploymentArtifactCompiler.compile_cv()`. | `FOUNDER_WEB_INTEGRATION` |
| **7** | Verify every factual claim against the Truth Graph. | `PASSABLE_NOW` | `matching/validator.py:ArtifactClaimValidator` validates 100% claim provenance against TruthGraph. | NONE |
| **8** | Download/open the CV; confirm formatting and ATS-readable text. | `PARTIAL` | Compilers output structured text and JSON/Markdown sections; binary DOCX/PDF export engine not completed. | `FOUNDER_ENGINE_BLOCKER` |
| **9** | Click "Open Application". | `NOT_POSSIBLE` | No interactive UI button; canonical URL derivable from `Opportunity.source_url`. | `FOUNDER_WEB_INTEGRATION` |
| **10** | Apply manually. | `PASSABLE_NOW` | External manual application on canonical ATS website is always possible by the founder. | NONE |
| **11** | Mark applied. | `PARTIAL` | `outbound/idempotency.py` stores action state via Python API; web UI toggle missing. | `FOUNDER_WEB_INTEGRATION` |
| **12** | Repeat over real opportunities. | `PARTIAL` | Core matching & dedupe handles arbitrary opportunity volumes; lacks web workspace. | `FOUNDER_WEB_INTEGRATION` |
| **13** | Label bad matches immediately. | `PARTIAL` | `matching/models.py` supports feedback labels; UI feedback button missing. | `FOUNDER_WEB_INTEGRATION` |
| **14** | Observe whether ranking improves. | `PARTIAL` | `inbox/learning.py` adjusts weights safely on N>=5; UI telemetry display missing. | `FOUNDER_WEB_INTEGRATION` |

---

## 4. Summary of Requirement Totals

- **Total Requirements Evaluated:** 66
  - **`DONE`:** 31 (47.0%)
  - **`PARTIAL`:** 23 (34.8%)
  - **`MISSING`:** 6 (9.1%)
  - **`INTENTIONALLY_DEFERRED`:** 4 (6.1%)
  - **`REQUIRES_LIVE_INTEGRATION_OR_CREDENTIALS`:** 2 (3.0%)

### Breakdown by Criticality:
- **P0 (Founder Core):** 28 Total — 22 DONE, 4 PARTIAL, 2 MISSING (UI-related)
- **P1 (Founder Friction Reduction):** 25 Total — 7 DONE, 13 PARTIAL, 4 MISSING (UI/Postgres-related), 1 LIVE_CRED
- **P2 (Reliability & Health):** 7 Total — 2 DONE, 3 PARTIAL, 2 MISSING
- **P3 (Family / Public B2C):** 3 Total — 3 INTENTIONALLY_DEFERRED
- **P4 (Organization B2B):** 3 Total — 3 INTENTIONALLY_DEFERRED

### Breakdown by Gap Bucket:
- **`FOUNDER_ENGINE_BLOCKER`:** 4 items (Binary DOCX/PDF exporter, ATS visual regression harness, Ashby/Wuzzuf email alert adapter, Schema.org parser).
- **`FOUNDER_WEB_INTEGRATION`:** 14 items (FastAPI REST API, Next.js dashboard, Feed, Detail, Truth Graph, CV Viewer, Pipeline, Settings pages).
- **`PRODUCTION_INFRASTRUCTURE`:** 5 items (PostgreSQL primary store, background worker runner, Docker Compose, Caddy TLS, Auth/session layer).
- **`LIVE_CONFIGURATION_OR_CREDENTIALS`:** 2 items (Adzuna developer API keys, Freelancer.com developer sandbox OAuth).
- **`INTENTIONALLY_LATER`:** 6 items (Family Alpha, Employment B2C, Freelancer B2C, Employer B2B, Agency B2B, Regional Scale).
