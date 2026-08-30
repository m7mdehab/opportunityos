# Phase Gate Report: BRIEF-003 — Opportunity Discovery & Ingestion Pipelines

**Phase ID:** BRIEF-003  
**Status:** PASS  
**Date:** 2026-08-30  
**Substantive Commit SHA:** `0a4e1ec4a3f97d1572c22b1f162ff0317dc15d7e`  
**Author:** Antigravity Master Agent (Dual-Loop Autonomous Controller)  
**Independent Auditor:** Blinded Discovery-Architecture & Structural-Authority Auditor (`73dbf5dd-7cae-4cd5-ae06-1c7dbcc85b62`)

---

## 1. Executive Summary

BRIEF-003 establishes the autonomous, dual-track opportunity acquisition engine for OpportunityOS. The subsystem (`opportunity/`) ingests authorized opportunities across employment (full-time remote, contract, international) and independent professional consulting / procurement tracks (UNGM, World Bank, EU TED Search API).

All incoming opportunities are normalized into an immutable `Opportunity` schema without data fabrication (preserving unknown values as `None` / `UNSPECIFIED` / `UNASSERTED_ABSENT`), linked to the verified BRIEF-001 geographic classification rules, and processed through a two-layer deduplication engine (exact content-hash matching and conservative cross-source clustering). Source health diagnostics prevent silent feed failures, parser schema drift, or false cleanliness.

---

## 2. Acceptance Criteria Evaluation

| Acceptance Criterion | Status | Evidence / Verification |
| :--- | :---: | :--- |
| **1. Central Authorized Acquisition & Transport** | **PASS** | Implemented `SourceRegistry`, `AcquisitionService`, `BaseTransport`, `MockTransport`, and `HttpTransport` in `opportunity/transport.py` and `opportunity/registry.py`. Preflight checks block unregistered/disabled sources before transport. Verified in `test_acquisition.py`. |
| **2. Zero Fabricated Normalized Defaults** | **PASS** | All default strings (e.g. "EU Contracting Authority", "United Nations", "Himalayas Employer", "Remote", default "USD", default yearly) completely eliminated from minimal-record ingestion across all adapters. Verified in `test_adversarial.py`. |
| **3. Atomic Field-Level Provenance & Lineage** | **PASS** | Every material normalized field carries `FieldProvenance` (field name, raw value, normalized value, derivation type, raw pointer, single-record SHA-256 checksum, rule ID) in `opportunity/models.py`. Verified in `test_models.py` and `test_normalization.py`. |
| **4. Canonical Output Determinism** | **PASS** | Removed Python built-in `hash()` and `uuid4()` from canonical IDs, content hashes, dedup keys, and batch IDs. Multi-process testing across disparate `PYTHONHASHSEED` values (`0`, `42`, `12345`, `999999`) proves byte-for-byte identical output in `test_deterministic_replay.py`. |
| **5. Source Health Authority & Diagnostics** | **PASS** | Separated transport and parser statuses in `opportunity/health.py`. HTTP 401/403 -> `POLICY_RESTRICTION`, HTTP 429 -> `RATE_LIMITED`, HTTP 5xx/timeout -> `TRANSIENT_FAILURE`, parse errors -> `PERSISTENT_FAILURE`, schema drift -> `SCHEMA_DRIFT_SUSPECTED`, 0 records -> `EMPTY_RESULTS`. Batch `is_clean` requires >= 1 source and all HEALTHY. |
| **6. Four Real Tracks** | **PASS** | Direct emission of `Track.EMPLOYMENT`, `Track.CONTRACT`, `Track.FREELANCE`, and `Track.PROCUREMENT` without collapsing contract/freelance to EMPLOYMENT. Verified in `test_normalization.py` and `test_adversarial.py`. |
| **7. Conservative Deduplication Invariants** | **PASS** | Same-source distinct requisition IDs never merge (even with identical text); distinct orgs, seniorities, geographic scopes, and tracks never merge. Cross-source opportunities with common outbound ATS URLs merge cleanly into `OpportunityCluster`. Verified in `test_dedupe.py`. |
| **8. Multi-Source Ingestion Pipeline** | **PASS** | Implemented public adapters for Greenhouse, Lever, Himalayas, Remotive, Remote OK, We Work Remotely, UNGM, World Bank, and EU TED in `opportunity/adapters/`. Validated across fixtures in `test_adapters.py`. |
| **9. External Action Safety & Policy Compliance** | **PASS** | All discovery adapters are strictly read-only (`GET`), with the single allowlisted read-only search `POST` query to EU TED under ADR-0005. Zero mutating HTTP verbs (`PUT`, `PATCH`, `DELETE`). Validated in `test_adversarial.py`. |
| **10. Geographic Classifier Integration** | **PASS** | Directly integrated with `recon/classification.py` and `recon/geography.py`. Restricted roles (US Only, Canada, UK, EU) strictly evaluate to `excluded`, preserving precision-first eligibility. Validated in `test_normalization.py` and `test_adversarial.py`. |
| **11. Architectural Decision Record** | **PASS** | Committed [ADR-0008](../docs/adr/ADR-0008-opportunity-data-model-and-ingestion-pipeline.md) documenting Opportunity Data Model and Ingestion Pipeline Architecture. |
| **12. Independent Blinded Audit** | **PASS** | Independent auditor (`73dbf5dd-7cae-4cd5-ae06-1c7dbcc85b62`) verified commit `0a4e1ec4a3f97d1572c22b1f162ff0317dc15d7e` against 12 discovery, acquisition, provenance, determinism, and deduplication criteria with unanimous PASS. |

---

## 3. Subsystem Architecture

### 3.1 Opportunity Data Model (`opportunity/models.py`)
```
Opportunity
├── id: str (deterministic source:remote_id or source:sha256)
├── track: Track (EMPLOYMENT | CONTRACT | FREELANCE | PROCUREMENT)
├── source: str (e.g. greenhouse:cloudflare, ungm, eu_ted)
├── source_url / source_id
├── organization: str
├── title: str
├── description: str
├── responsibilities / requirements: tuple[str, ...]
├── skills: tuple[str, ...] (canonical skill aliases)
├── seniority: SeniorityLevel (ENTRY | MID | SENIOR | LEAD | PRINCIPAL | EXECUTIVE | UNSPECIFIED)
├── employment_type: EmploymentType (FULL_TIME | PART_TIME | CONTRACT | FREELANCE | INTERNSHIP | TEMPORARY | UNSPECIFIED)
├── location_raw: str
├── remote_policy: RemotePolicy (REMOTE | HYBRID | ON_SITE | UNSPECIFIED)
├── geographic_eligibility: GeographicEligibility (status, reason, individual_eligibility)
├── compensation: Compensation | None (min, max, currency, interval)
├── posted_date / closing_date: ISO 8601 calendar date
├── procurement_metadata: ProcurementMetadata | None (CPV, buyer, notice_type)
├── raw_provenance: SourceProvenance (source_url, feed_url, fetched_at, checksum)
├── record_checksum: str (SHA-256 of single raw item payload)
├── raw_record_pointer: str (e.g. feed:jobs[0].title)
├── field_provenances: tuple[FieldProvenance, ...]
├── canonical_outbound_url: str
├── content_hash: sha256(org|title|location|description)
└── dedup_key: sha256(org:title:location)
```

### 3.2 Two-Layer Deduplication Engine (`opportunity/dedupe.py`)
1. **Layer 1 (Exact Content-Hash):** Matches byte-for-byte canonicalized job payloads.
2. **Layer 2 (Cross-Source Opportunity Clustering):** Pairwise verifies cross-feed matches across ATS feeds and job aggregators. Requires:
   - Identical `track`
   - Matching `organization` (exact or prefix/suffix)
   - Compatible `seniority` (cannot merge `Senior` with `Junior` or `Lead`)
   - $\ge 85\%$ title token overlap
   - Identical `geographic_eligibility.status` (cannot merge `eligible` with `excluded`)
   - Outbound URL identity or mapped stable posting ID
3. **Requisition Headcount Protection:** Distinct same-source requisition IDs are unconditionally prevented from merging.

### 3.3 Source Health & Schema Drift Monitor (`opportunity/health.py`)
- Explicit deterministic health transitions:
  - `records_valid > 0` $\to$ `HEALTHY`
  - `records_fetched == 0` $\to$ `EMPTY_RESULTS`
  - `records_fetched > 0 and records_parsed == 0` $\to$ `SCHEMA_DRIFT_SUSPECTED`
  - `HTTP 401 / 403` $\to$ `POLICY_RESTRICTION`
  - `HTTP 429` $\to$ `RATE_LIMITED`
  - `HTTP 5xx / Timeout` $\to$ `TRANSIENT_FAILURE`
  - `JSON/XML Syntax Parse Error` $\to$ `PERSISTENT_FAILURE` (preserving actual exception without fake HTTP 500)

---

## 4. Independent Blinded Audit Report (Verbatim)

```markdown
# INDEPENDENT STRUCTURAL AUTHORITY & ARCHITECTURE AUDIT REPORT

**Audit Target Commit SHA**: 0a4e1ec4a3f97d1572c22b1f162ff0317dc15d7e
**Subsystem**: Opportunity Acquisition, Ingestion, Normalization, Deduplication, & Diagnostics (opportunity/)
**Auditor**: Independent Discovery-Architecture & Structural-Authority Auditor (Blinded)
**Overall Verdict**: PASS (12 / 12 CRITERIA SATISFIED)

1. Central Authorized Acquisition Layer: PASS (AcquisitionService, SourceRegistry, MockTransport, HttpTransport)
2. Registry Bypass Prevention: PASS (Preflight check refuses unregistered and disabled sources)
3. Strict Network Verb Enforcement: PASS (GET only, sole ADR-0005 allowlisted TED search POST)
4. Zero Fabricated Defaults: PASS (Minimal records leave fields unasserted / empty / None)
5. Atomic Field-Level Provenance: PASS (7-field FieldProvenance schema on material fields)
6. Canonical Output Determinism: PASS (SHA-256 digests; byte-for-byte replay across PYTHONHASHSEED)
7. No Schema Drift Silence: PASS (SCHEMA_DRIFT_SUSPECTED and EMPTY_RESULTS captured)
8. Separation of Parse Errors and HTTP Status: PASS (PARSE_SYNTAX_ERROR preserved without fake HTTP 500)
9. Empty/No-Source Batch Cleanliness Enforcement: PASS (is_clean requires >= 1 source and all HEALTHY)
10. Destructive Duplicate False-Merge Prevention: PASS (Same-source distinct req IDs preserved)
11. Cross-Source Duplicate Detection: PASS (Common outbound ATS URLs cluster cleanly)
12. Four Real Tracks: PASS (EMPLOYMENT, CONTRACT, FREELANCE, PROCUREMENT distinctly emitted)
```

---

## 5. Phase Gate Determination

**BRIEF-003 COMPLETION STATUS: PASS**  
**BRIEF-003 DEFINITIVELY CLOSED: YES**  
**BRIEF-004 (OPPORTUNITY MATCHING & PROPOSAL TAILORING) UNBLOCKED: YES**

## Decision

PASS

## Next phase prerequisites

- BRIEF-004: Opportunity Matching & Proposal Tailoring
