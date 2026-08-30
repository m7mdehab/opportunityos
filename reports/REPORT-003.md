# Phase Gate Report: BRIEF-003 — Opportunity Discovery & Ingestion Pipelines

**Phase ID:** BRIEF-003  
**Status:** PASS  
**Date:** 2026-08-30  
**Substantive Commit SHA:** `356a0a93eff4a9a84e54bef3922f64a0bc99378f`  
**Author:** Antigravity Master Agent (Dual-Loop Autonomous Controller)  
**Independent Auditor:** Blinded Discovery Pipeline & Provenance Auditor (`ad029d31-d7cb-493b-bd55-a1e4edb3ece3`)

---

## 1. Executive Summary

BRIEF-003 establishes the continuous, dual-track opportunity acquisition engine for OpportunityOS. The newly implemented `opportunity/` subsystem ingests authorized opportunities across both employment (full-time remote, contract, international) and independent professional consulting / procurement tracks (UNGM, World Bank, EU TED Search API).

All incoming opportunities are normalized into an immutable `Opportunity` schema without data fabrication (preserving unknown values as `None` / `UNSPECIFIED`), linked to the verified BRIEF-001 geographic classification rules, and processed through a two-layer deduplication engine (content-hash matching and conservative cross-source clustering). Source health diagnostics prevent silent feed failures or parser schema drift.

---

## 2. Acceptance Criteria Evaluation

| Acceptance Criterion | Status | Evidence / Verification |
| :--- | :---: | :--- |
| **1. Unified Opportunity Data Model** | **PASS** | Frozen dataclass `Opportunity` with typed enums (`Track`, `SeniorityLevel`, `EmploymentType`, `RemotePolicy`, `CompensationInterval`), `Compensation`, `ProcurementMetadata`, and `SourceProvenance` in `opportunity/models.py`. Validated by `test_models.py`. |
| **2. Multi-Source Ingestion Pipeline** | **PASS** | Implemented public adapters for Greenhouse, Lever, Himalayas, Remotive, Remote OK, We Work Remotely, UNGM, World Bank, and EU TED in `opportunity/adapters/`. Validated across fixtures in `test_adapters.py`. |
| **3. External Action Safety & Policy Compliance** | **PASS** | All discovery adapters are strictly read-only (`GET`), with the single allowlisted read-only search `POST` query to EU TED under ADR-0005. Zero mutating HTTP verbs (`PUT`, `PATCH`, `DELETE`). Validated in `test_adversarial.py`. |
| **4. Geographic Classifier Integration** | **PASS** | Directly integrated with `recon/classification.py` and `recon/geography.py`. Restricted roles (US Only, Canada, UK, EU) strictly evaluate to `excluded`, preserving precision-first eligibility. Validated in `test_normalization.py` and `test_adversarial.py`. |
| **5. Deterministic Normalization & Provenance** | **PASS** | Text cleaning, ISO date normalization, deterministic seniority/employment/compensation parsing in `opportunity/normalization.py`. All opportunities retain SHA-256 raw payload checksums and source URLs in `SourceProvenance`. |
| **6. Two-Layer Deduplication Engine** | **PASS** | Layer 1 (exact content-hash) and Layer 2 (deterministic cross-source clustering) in `opportunity/dedupe.py`. Conservative false-merge rules strictly prevent merging distinct organizations, seniorities, geographic scopes, or tracks. Validated in `test_dedupe.py`. |
| **7. Source Health & Schema Drift Monitoring** | **PASS** | `SourceHealthMonitor` in `opportunity/health.py` tracking `HEALTHY`, `EMPTY_RESULTS`, `SCHEMA_DRIFT_SUSPECTED`, `POLICY_RESTRICTION`, `RATE_LIMITED`, `TRANSIENT_FAILURE`, `PERSISTENT_FAILURE`. Zero results explicitly classified as `EMPTY_RESULTS` (never silently healthy). Validated in `test_health.py`. |
| **8. Unit, Integration, and Adversarial Tests** | **PASS** | 44 tests in `opportunity/` test suite, 99 in `truth/`, 67 in `recon/` passing with 100% success in 0.35s. |
| **9. Architectural Decision Record** | **PASS** | Committed [ADR-0008](../docs/adr/ADR-0008-opportunity-data-model-and-ingestion-pipeline.md) documenting Opportunity Data Model and Ingestion Pipeline Architecture. |
| **10. Independent Blinded Audit** | **PASS** | Independent auditor (`ad029d31-d7cb-493b-bd55-a1e4edb3ece3`) verified commit `356a0a93eff4a9a84e54bef3922f64a0bc99378f` against 8 security, policy, and provenance criteria with unanimous PASS. |
| **11. State & Governance Gates** | **PASS** | Regenerated `docs/STATE.md`, CI test workflow updated with opportunity suite, repository integrity and guard boundary checks passing with zero violations. |

---

## 3. Subsystem Architecture

### 3.1 Opportunity Data Model (`opportunity/models.py`)
```
Opportunity
├── id: str
├── track: Track (EMPLOYMENT | CONTRACT | FREELANCE | PROCUREMENT)
├── source: str (e.g. greenhouse:cloudflare, ungm, eu_ted)
├── source_url / source_id
├── organization: str
├── title: str
├── description: str
├── responsibilities / requirements: tuple[str, ...]
├── skills: tuple[str, ...] (canonical skill aliases)
├── seniority: SeniorityLevel
├── employment_type: EmploymentType
├── location_raw: str
├── remote_policy: RemotePolicy
├── geographic_eligibility: GeographicEligibility (status, reason, individual_eligibility)
├── compensation: Compensation | None (min, max, currency, interval)
├── posted_date / closing_date: ISO 8601 calendar date
├── procurement_metadata: ProcurementMetadata | None (CPV, buyer, notice_type)
├── raw_provenance: SourceProvenance (source_url, feed_url, fetched_at, checksum)
├── content_hash: sha256(org|title|location|description)
└── dedup_key: sha256(org:title:location)
```

### 3.2 Two-Layer Deduplication Engine (`opportunity/dedupe.py`)
1. **Layer 1 (Exact Content-Hash):** Matches byte-for-byte canonicalized job payloads.
2. **Layer 2 (Cross-Source Opportunity Clustering):** Pairwise verifies cross-feed matches across ATS feeds and job aggregators. Requires:
   - Identical `track`
   - Matching `organization` (exact or prefix/suffix)
   - Compatible `seniority` (cannot merge `Senior` with `Junior` or `Lead`)
   - $\ge 70\%$ title token overlap
   - Identical `geographic_eligibility.status` (cannot merge `eligible` with `excluded`)

### 3.3 Source Health & Schema Drift Monitor (`opportunity/health.py`)
- Explicit deterministic health transitions:
  - `records_valid > 0` $\to$ `HEALTHY`
  - `records_fetched == 0` $\to$ `EMPTY_RESULTS`
  - `records_fetched > 0 and records_parsed == 0` $\to$ `SCHEMA_DRIFT_SUSPECTED`
  - `HTTP 401 / 403` $\to$ `POLICY_RESTRICTION`
  - `HTTP 429` $\to$ `RATE_LIMITED`
  - `HTTP 5xx / Timeout` $\to$ `TRANSIENT_FAILURE`
  - `JSON/XML Syntax Parse Error` $\to$ `PERSISTENT_FAILURE`

---

## 4. Source Adapter Coverage

| Source Adapter | Track | Access / Method | Policy Reference | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Greenhouse** | Employment | `GET /v1/boards/{board}/jobs` | `https://www.greenhouse.com/terms-of-use` | `ACTIVE` |
| **Lever** | Employment | `GET /v0/postings/{site}` | `https://www.lever.co/terms` | `ACTIVE` |
| **Himalayas** | Employment | `GET /jobs/api` | `https://himalayas.app/terms` | `ACTIVE` |
| **Remotive** | Employment | `GET /api/remote-jobs` | `https://remotive.com/terms` | `ACTIVE` |
| **Remote OK** | Employment | `GET /api` | `https://remoteok.com/terms` | `ACTIVE` |
| **We Work Remotely** | Employment | `GET /remote-jobs.rss` | `https://weworkremotely.com/terms-and-conditions` | `ACTIVE` |
| **UNGM** | Procurement | `GET /Public/Notice` | `https://www.ungm.org/Public/Terms` | `ACTIVE` |
| **World Bank** | Procurement | `GET /opportunities` | `https://www.worldbank.org/terms-of-use` | `ACTIVE` |
| **EU TED** | Procurement | `POST /v3/notices/search` (ADR-0005) | `https://docs.ted.europa.eu/legal-notice.html` | `ACTIVE` |

---

## 5. Independent Blinded Audit

**Auditor Subagent ID:** `ad029d31-d7cb-493b-bd55-a1e4edb3ece3`  
**Target Commit SHA:** `356a0a93eff4a9a84e54bef3922f64a0bc99378f`  
**Auditor Verdict:** **PASS (8 / 8 Criteria Satisfied)**

### Summary of Audit Findings
1. **Accidental Scraping & External Actions:** PASS — All discovery adapters are strictly read-only; EU TED search POST is the sole allowlisted POST exception under ADR-0005.
2. **No Fabricated Normalized Fields:** PASS — Unknown fields remain `None` / `UNSPECIFIED`; `absent != false` strictly preserved.
3. **Full Provenance Retention:** PASS — Complete `SourceProvenance` with SHA-256 payload checksum attached to every `Opportunity`.
4. **Geography Integration & No False Eligibility:** PASS — Integrated with `recon/geography.py`; restricted locations evaluate to `excluded` without precision loss.
5. **Two-Layer Deduplication & False-Merge Prevention:** PASS — Exact hash and cross-source clustering strictly prevent false merges across organizations, seniorities, geographic restrictions, and tracks.
6. **Deterministic Source Health & Drift Detection:** PASS — Zero-result feeds classified as `EMPTY_RESULTS`; drift and parse errors captured deterministically.
7. **Procurement Data Preservation:** PASS — Structured `ProcurementMetadata` preserves CPV codes, notice types, and buyer organizations.
8. **Boundary Topology & Privacy:** PASS — Zero founder PII or private data in mirrored paths.

---

## 6. Phase Gate Determination

**BRIEF-003 COMPLETION STATUS: PASS**  
**BRIEF-003 DEFINITIVELY CLOSED: YES**  
**BRIEF-004 (OPPORTUNITY MATCHING & PROPOSAL TAILORING) UNBLOCKED: YES**

## Decision

PASS

## Next phase prerequisites

- BRIEF-004: Opportunity Matching & Proposal Tailoring

