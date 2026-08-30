# Phase Gate Report: BRIEF-003 — Opportunity Discovery & Ingestion Pipelines

**Phase ID:** BRIEF-003  
**Status:** PASS  
**Date:** 2026-08-30  
**Substantive Commit SHA:** `ff4ee034c4f6cf873da637d54d9632126642723b`  
**Author:** Antigravity Master Agent (Dual-Loop Autonomous Controller)  
**Independent Auditor:** Blinded Discovery-Architecture & Structural-Authority Auditor (`d69bcf5e-5e41-4816-9247-1a2cd8f3b13b`)

---

## 1. Executive Summary

BRIEF-003 establishes the autonomous, dual-track opportunity acquisition engine for OpportunityOS. The subsystem (`opportunity/`) ingests authorized opportunities across employment (full-time remote, contract, international) and independent professional consulting / procurement tracks (UNGM, World Bank, EU TED Search API).

All incoming opportunities are normalized into an immutable `Opportunity` schema driven by `MATERIAL_OPPORTUNITY_FIELD_MANIFEST` without data fabrication (preserving unknown values as `None` / `UNSPECIFIED` / `UNASSERTED_ABSENT`), linked to verified BRIEF-001 geographic classification rules, and processed through a two-layer deduplication engine (exact content-hash matching and conservative cross-source clustering with structured ATS identity). Source health diagnostics consume actual telemetry facts and prevent silent feed failures, parser schema drift, or false cleanliness.

---

## 2. Acceptance Criteria Evaluation

| Acceptance Criterion | Status | Evidence / Verification |
| :--- | :---: | :--- |
| **1. Exact Network Endpoint Authority** | **PASS** | `SourceRegistry.validate_preflight` strictly binds `SOURCE_ID + METHOD + EXACT HOST + ALLOWED PATH`. Refuses arbitrary host GET requests and query-parameter substring bypasses preflight. Verified in `test_acquisition.py`. |
| **2. Pacing & Rate Limiting** | **PASS** | `RateLimiter` enforces per-source interval pacing with an injectable clock and default conservative limit. Verified in `test_acquisition.py`. |
| **3. Explicit Approved Search Query** | **PASS** | `EUTEDAdapter` configures `method="POST"` with `DEFAULT_TED_SEARCH_BODY` specifying approved query fields (`publication-number`, `notice-title`, `buyer-name`, `buyer-country`, `cpv`, etc.) under ADR-0005. |
| **4. Executable Material Field Manifest** | **PASS** | `MATERIAL_OPPORTUNITY_FIELD_MANIFEST` in `models.py` drives `validate_opportunity_provenance()`. Populated material fields require valid lineage with single-record SHA-256 checksum and exact raw pointer. Verified in `test_models.py`. |
| **5. Accurate Pointer Paths & Zero Laundering** | **PASS** | Adapter pointers reflect actual source fields (`companyName`, `text`, `agency`, `borrower`). If EU TED / UNGM / World Bank description is absent, `description = ""` with `unasserted_absent` lineage; never laundered from title. Verified in `test_adversarial.py`. |
| **6. Real Health Telemetry** | **PASS** | `SourceHealthReport` captures exact response latency (`187 ms`), decouples transport status from parser status, and distinguishes `EMPTY_RESULTS`, `SCHEMA_DRIFT_SUSPECTED`, and `PERSISTENT_FAILURE` without fake HTTP 500 codes. Verified in `test_adversarial.py`. |
| **7. Real Identity Deduplication** | **PASS** | Eliminated raw substring matching (`source_id in other.source_url`). Similarity without common stable identity preserves both records (`is_ambiguous=True`). Merges occur strictly with canonical outbound ATS URLs or structured ATS IDs. Same-source distinct requisition IDs never merge. Verified in `test_dedupe.py`. |
| **8. Canonical Determinism & Zero Hash Nondeterminism** | **PASS** | Replaced `hash()` and `uuid4()` with SHA-256 digests. Multi-process tests across disparate `PYTHONHASHSEED` values (`0`, `42`, `12345`, `999999`) produce byte-for-byte identical output in `test_deterministic_replay.py`. |
| **9. Four Real Tracks** | **PASS** | Direct deterministic emission of `Track.EMPLOYMENT`, `Track.CONTRACT`, `Track.FREELANCE`, and `Track.PROCUREMENT`. Verified in `test_normalization.py` and `test_adversarial.py`. |
| **10. Architectural Decision Record** | **PASS** | Committed [ADR-0008](../docs/adr/ADR-0008-opportunity-data-model-and-ingestion-pipeline.md) documenting Opportunity Data Model and Ingestion Pipeline Architecture. |
| **11. Independent Blinded Audit** | **PASS** | Independent auditor (`d69bcf5e-5e41-4816-9247-1a2cd8f3b13b`) verified commit `ff4ee034c4f6cf873da637d54d9632126642723b` against all 12 attack vectors with unanimous PASS. |

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
1. **Layer 1 (Exact Content-Hash):** Matches byte-for-byte canonicalized job payloads within identical requisition IDs.
2. **Layer 2 (Cross-Source Opportunity Clustering):** Pairwise verifies cross-feed matches across ATS feeds and job aggregators. Requires:
   - Identical `track`
   - Matching `organization` (exact or prefix/suffix)
   - Compatible `seniority` (cannot merge `Senior` with `Junior` or `Lead`)
   - Identical `geographic_eligibility.status`
   - Proven common outbound ATS URL or structured `(provider, company, requisition_id)` match
3. **Headcount & Ambiguity Invariant:**
   - Same-source distinct requisition IDs never merge.
   - Similar postings across sources without proven identity preserve both opportunities and link in `possible_duplicates` (`is_ambiguous=True`).

---

## 4. Independent Blinded Audit Artifact

### 4.1 Exact Verbatim Audit Prompt Sent to Reviewer
```
You are an independent, blinded discovery-architecture and structural-authority auditor for OpportunityOS.
Your audit target is the exact substantive remediation commit SHA: ff4ee034c4f6cf873da637d54d9632126642723b.

Your task is to inspect the opportunity subsystem at C:\Users\norha\projects\system-diagnostics\opportunity (models.py, registry.py, transport.py, acquisition.py, normalization.py, dedupe.py, health.py, pipeline.py, adapters/base.py, adapters/greenhouse.py, adapters/lever.py, adapters/himalayas.py, adapters/remotive.py, adapters/remote_ok.py, adapters/we_work_remotely.py, adapters/ungm.py, adapters/world_bank.py, adapters/eu_ted.py, fixtures/, and test_*.py) and provide a rigorous independent audit report assessing whether the 12 attack vectors and structural authority criteria are fully and robustly satisfied on commit ff4ee034c4f6cf873da637d54d9632126642723b:

1. REGISTERED-SOURCE ARBITRARY-HOST GET:
   - Does SourceRegistry preflight authorization strictly bind source_id, method, exact allowed host, and allowed path prefix?
   - Is a registered source (e.g. himalayas or greenhouse) strictly prevented from executing GET requests to arbitrary hosts (e.g. evil.example)?

2. TED SUBSTRING URL BYPASS:
   - Does EU TED preflight authorization parse URL components and reject query substring bypasses (e.g. https://evil.example/?x=api.ted.europa.eu/v3/notices/search)?
   - Does it strictly enforce HTTPS POST to api.ted.europa.eu/v3/notices/search?

3. MISSING RATE-LIMIT ENFORCEMENT:
   - Does RateLimiter enforce pacing with an injectable clock and default conservative limit?

4. TED POST WITHOUT ACTUAL SEARCH BODY:
   - Does the EU TED adapter and discovery execution send an explicit, approved read-only search POST query body (e.g. DEFAULT_TED_SEARCH_BODY) rather than bare GET fallback?

5. POPULATED MATERIAL FIELD WITH NO PROVENANCE:
   - Is MATERIAL_OPPORTUNITY_FIELD_MANIFEST executable via validate_opportunity_provenance?
   - Does every populated material field require valid FieldProvenance with record checksum and raw pointer?
   - Does the reflection test verify that any new Opportunity field is classified in the manifest?

6. PROVENANCE POINTER CLAIMING WRONG SOURCE FIELD:
   - Do provenance pointers across all 9 adapters accurately reflect the actual source fields used (e.g. companyName, text, agency, borrower) rather than generic placeholders?

7. TITLE -> DESCRIPTION LAUNDERING:
   - When an EU TED notice (or UNGM / World Bank) has a title but no description, is description strictly kept as "" with unasserted_absent provenance, never silently populated with title text?

8. ACTUAL LATENCY REPLACED BY SYNTHETIC TELEMETRY:
   - Does SourceHealthReport retain the actual fetch latency (e.g. 187 ms) rather than hardcoded 10 ms?

9. PARSED COUNT MASQUERADING AS RAW COUNT:
   - Does ParseResult carry the actual records_raw_count from the source payload, correctly reporting differences when invalid items are skipped?

10. PAYLOAD-LENGTH SCHEMA DRIFT HEURISTIC:
    - Is payload-length heuristic (len > 50) completely removed, and is schema drift flagged deterministically when expected collections are missing or when raw > 0 and parsed == 0?

11. SOURCE-ID SUBSTRING FALSE MERGE:
    - Is raw substring source-ID matching ('source_id in other.source_url') completely removed?
    - Does deduplication strictly prevent false merges where source_id="1" matches ".../jobs/12345"?

12. SIMILARITY-ONLY DESTRUCTIVE MERGE:
    - When two opportunities share same organization, title, and near-identical description across different sources WITHOUT common stable identity proof, does deduplication preserve both opportunities (linking as possible duplicate / is_ambiguous=True without destructive merge)?
    - Do opportunities with proven common outbound ATS URLs merge cleanly?
    - Are distinct same-source requisition IDs strictly prevented from merging?

Perform your inspection read-only. Inspect the implementation directly, not merely test names. Report your detailed verdict (PASS/FAIL) with technical evidence and file citations for each of the 12 attack vectors on commit SHA ff4ee034c4f6cf873da637d54d9632126642723b.
```

### 4.2 Auditor Session Metadata & Findings
- **Auditor Subagent Conversation ID:** `d69bcf5e-5e41-4816-9247-1a2cd8f3b13b`
- **Target Commit SHA:** `ff4ee034c4f6cf873da637d54d9632126642723b`
- **Overall Auditor Verdict:** **PASS (12 / 12 Invariants Satisfied)**

```
1. Registered-Source Arbitrary-Host GET: PASS (validate_preflight binds source_id + method + exact host + allowed path)
2. TED Substring URL Bypass: PASS (parsed URL components enforce exact scheme, host, path; reject substring bypasses)
3. Missing Rate-Limit Enforcement: PASS (RateLimiter with injectable clock and conservative pacing default)
4. TED POST Without Actual Search Body: PASS (DEFAULT_TED_SEARCH_BODY explicitly sent with Content-Type: application/json)
5. Populated Material Field With No Provenance: PASS (MATERIAL_OPPORTUNITY_FIELD_MANIFEST executable via validate_opportunity_provenance)
6. Provenance Pointer Claiming Wrong Source Field: PASS (pointers accurately reflect exact raw schema properties)
7. Title -> Description Laundering: PASS (absent descriptions remain "" with unasserted_absent provenance)
8. Actual Latency Replaced By Synthetic Telemetry: PASS (exact fetch latency preserved in SourceHealthReport)
9. Parsed Count Masquerading As Raw Count: PASS (ParseResult carries raw_count decoupled from parsed count)
10. Payload-Length Schema Drift Heuristic: PASS (zero len heuristics; deterministic key & count drift detection)
11. Source-ID Substring False Merge: PASS (raw substring matching removed; exact URLs & structured ATS tuples used)
12. Similarity-Only Destructive Merge: PASS (similarity without identity proof preserves both records as possible duplicates)
```

### 4.3 Master Disposition of Audit Findings
- **Disposition:** All 12 criteria verified and accepted as **PASS**. No remediation or code modifications required.

---

## 5. Phase Gate Determination

**BRIEF-003 COMPLETION STATUS: PASS**  
**BRIEF-003 DEFINITIVELY CLOSED: YES**  
**BRIEF-004 (OPPORTUNITY MATCHING & PROPOSAL TAILORING) UNBLOCKED: YES**

## Decision

PASS

## Next phase prerequisites

- BRIEF-004: Opportunity Matching & Proposal Tailoring
