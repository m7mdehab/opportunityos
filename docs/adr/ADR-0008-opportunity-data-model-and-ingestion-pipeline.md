# ADR-0008 — Opportunity Data Model and Ingestion Pipeline

- **Status:** accepted
- **Date:** 2026-08-30
- **Phase:** BRIEF-003
- **Supersedes:** none
- **Superseded by:** none

## Context

OpportunityOS requires continuous, deterministic opportunity acquisition across employment (full-time remote, contract, international) and independent professional work (procurement, tenders, RFPs, institutional consulting). Without a unified, typed opportunity representation, source normalization, conservative deduplication, and source health tracking, incoming opportunities would either suffer from schema fragmentation, dropped provenance, false merging, or silent failure when external feed schemas drift, violating Product Constitution §2.1, §3.1, and §3.2.

## Decision

Implement an immutable, multi-source Opportunity Discovery and Ingestion Pipeline (`opportunity/` package):

1. **Unified Opportunity Model (`Opportunity`):**
   - Covers dual tracks: `Track.EMPLOYMENT`, `Track.CONTRACT`, `Track.FREELANCE`, `Track.PROCUREMENT`.
   - Explicit typed fields for seniority (`SeniorityLevel`), employment type (`EmploymentType`), remote policy (`RemotePolicy`), compensation ranges (`Compensation`), skills, responsibilities, requirements, and procurement metadata (`ProcurementMetadata` for RFPs/tenders).
   - Preserves source-specific data without destructively forcing procurement structures into employment schemas.
   - Enforces immutability via frozen dataclasses and slots.

2. **Deterministic Normalization & Provenance Retention:**
   - Raw feeds are parsed and normalized without fabricating missing fields (unknown remains None / UNSPECIFIED; absent != false).
   - Every opportunity retains complete `SourceProvenance` (`source_id`, `source_url`, `feed_url`, `fetched_at`, `fetch_latency_ms`, `raw_pointer`, `payload_checksum`).
   - Text cleaning strips HTML tags and normalizes whitespace deterministically.

3. **Geographic Eligibility Integration:**
   - Directly integrates the BRIEF-001 geographic classifier (`recon/classification.py`, `recon/geography.py`).
   - Evaluates geographic eligibility (`eligible`, `excluded`, `unclear`) and individual eligibility (`individual_ok`, `entity_required`, `unclear`) conservatively without weakening precision-first rules.

4. **Two-Layer Deduplication Engine:**
   - **Layer 1 (Exact Content-Hash):** Groups identical opportunities matching sha256 of canonical organization, title, location, and description.
   - **Layer 2 (Deterministic Cross-Source Opportunity Clustering):** Groups matching real-world opportunities across feeds (e.g. ATS direct posting vs remote aggregator listing) based on compatible organization, seniority, title tokens, and geographic scope into `OpportunityCluster`.
   - **Conservative False-Merge Prevention:** Distinct organizations, distinct seniorities (e.g. Junior vs Senior), distinct geographic scopes (e.g. US Only vs Worldwide), or distinct tracks (Employment vs Procurement) are strictly prevented from merging.

5. **Deterministic Source Health & Schema Drift Monitoring (`SourceHealthMonitor`):**
   - Tracks explicit health statuses: `HEALTHY`, `EMPTY_RESULTS`, `SCHEMA_DRIFT_SUSPECTED`, `POLICY_RESTRICTION`, `RATE_LIMITED`, `TRANSIENT_FAILURE`, `PERSISTENT_FAILURE`.
   - Feeds returning zero records are explicitly classified as `EMPTY_RESULTS` and not falsely reported as healthy.

6. **External Action Safety & Compliance:**
   - All discovery adapters are strictly read-only (`GET`), with the sole POST exception being the allowlisted `READ_ONLY_QUERY` to `https://api.ted.europa.eu/v3/notices/search` under ADR-0005.
   - External mutations (PUT, PATCH, DELETE, and all other POSTs) remain strictly prohibited across all hosts.
   - Respects rate limits, robots.txt, and source policies recorded in `docs/SOURCE_REGISTRY.yaml`.

7. **CI/CD Merge Gating:**
   - `.github/workflows/test.yml` executes the opportunity ingestion test suite alongside Truth, Recon, Mirror, and Integrity checks on every pull request and push to `main`.

## Consequences

Downstream opportunity matching, ranking, and proposal generation modules receive strictly typed, deduplicated, and geographically classified Opportunity batches with full provenance traceability and zero fabricated attributes.

## Required tests and rollback

Maintain deterministic unit, integration, and adversarial test suites covering all source adapters, schema normalization, two-layer deduplication, geographic eligibility, source health tracking, and zero-dollar budget compliance. Roll back by updating or disabling individual feed adapters without affecting core opportunity schema contracts.
