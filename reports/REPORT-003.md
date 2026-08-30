# Phase Gate Report: BRIEF-003 — Opportunity Discovery & Ingestion Pipelines

**Phase ID:** BRIEF-003  
**Status:** PASS  
**Date:** 2026-08-30  
**Substantive Commit SHA:** `542917b6bbbed595811d460082a21479dd86ae98`  
**Author:** Antigravity Master Agent (Dual-Loop Autonomous Controller)  
**Independent Auditor:** Blinded Discovery-Architecture & Structural-Authority Auditor (`ea2b2e3d-773b-4721-bd90-9587e49535ea`)

---

## 1. Executive Summary

BRIEF-003 establishes the autonomous, dual-track opportunity acquisition engine for OpportunityOS. The subsystem (`opportunity/`) ingests authorized opportunities across employment (full-time remote, contract, international) and independent professional consulting / procurement tracks (UNGM, World Bank, EU TED Search API).

All incoming opportunities are normalized into an immutable `Opportunity` schema driven by `MATERIAL_OPPORTUNITY_FIELD_RULES` and `MATERIAL_OPPORTUNITY_FIELD_MANIFEST` without data fabrication (preserving unknown values as `None` / `UNSPECIFIED` / `UNASSERTED_ABSENT`), linked to verified BRIEF-001 geographic classification rules, and processed through a two-layer deduplication engine (exact content-hash matching and conservative cross-source clustering with structured ATS identity). Source health diagnostics consume actual telemetry facts and prevent silent feed failures, parser schema drift, or false cleanliness.

---

## 2. Acceptance Criteria Evaluation

| Acceptance Criterion | Status | Evidence / Verification |
| :--- | :---: | :--- |
| **1. Exact Network Endpoint Authority** | **PASS** | `SourceRegistry.validate_preflight` strictly binds `SOURCE_ID + METHOD + EXACT HOST + EXACT BOARD/SITE TOKEN + ALLOWED PATH`. Enforces exact path segment matching for Greenhouse `/v1/boards/{board_token}/...` and Lever `/v0/postings/{site_token}/...`. Refuses token-prefix collisions (`greenhouse:cloudflare` -> `/v1/boards/cloudflareevil/jobs`, `lever:shyftlabs` -> `/v0/postings/shyftlabs2`), cross-board, cross-site, HTTP downgrade, arbitrary host GET, and query-parameter substring bypasses preflight. Verified in `test_acquisition.py`. |
| **2. Pacing & Rate Limiting** | **PASS** | `RateLimiter` enforces per-source interval pacing with an injectable clock and default conservative limit. Verified in `test_acquisition.py`. |
| **3. Explicit Approved Search Query** | **PASS** | `EUTEDAdapter` configures `method="POST"` with `DEFAULT_TED_SEARCH_BODY` specifying approved query fields (`publication-number`, `notice-title`, `buyer-name`, `buyer-country`, `cpv`, etc.) under ADR-0005. |
| **4. Executable Material Field Manifest & Atomic Compensation Provenance** | **PASS** | `MATERIAL_OPPORTUNITY_FIELD_RULES` in `models.py` drives `validate_opportunity_provenance()`. Populated material fields require valid lineage with single-record SHA-256 checksum and exact raw pointer. Each populated compensation subfield (`compensation.min_amount`, `compensation.max_amount`, `compensation.currency`, `compensation.interval`) requires its own atomic `FieldProvenance` (generic `compensation` cannot substitute). Verified in `test_models.py`. |
| **5. Accurate Pointer Paths & Zero Laundering** | **PASS** | Adapter pointers reflect actual source fields (`companyName`, `text`, `agency`, `borrower`). If EU TED / UNGM / World Bank description is absent, `description = ""` with `unasserted_absent` lineage; never laundered from title. Verified in `test_adversarial.py`. |
| **6. Real Health Telemetry** | **PASS** | `SourceHealthReport` captures exact response latency (`187 ms`) and actual status codes (`OK_206`), decouples transport status from parser status, and distinguishes `EMPTY_RESULTS`, `SCHEMA_DRIFT_SUSPECTED`, and `PERSISTENT_FAILURE` without fake HTTP 500 codes. Verified in `test_adversarial.py`. |
| **7. Real Identity Deduplication** | **PASS** | Eliminated raw substring matching (`source_id in other.source_url`). Similarity without common stable identity preserves both records (`is_ambiguous=True`). Merges occur strictly with canonical outbound ATS URLs or structured ATS IDs. Same-source distinct requisition IDs never merge. Verified in `test_dedupe.py`. |
| **8. Canonical Determinism & Zero Hash Nondeterminism** | **PASS** | Replaced `hash()` and `uuid4()` with SHA-256 digests. Multi-process tests across disparate `PYTHONHASHSEED` values (`0`, `42`, `12345`, `999999`) produce byte-for-byte identical output in `test_deterministic_replay.py`. |
| **9. Four Real Tracks** | **PASS** | Direct deterministic emission of `Track.EMPLOYMENT`, `Track.CONTRACT`, `Track.FREELANCE`, and `Track.PROCUREMENT`. Verified in `test_normalization.py` and `test_adversarial.py`. |
| **10. Architectural Decision Record** | **PASS** | Committed [ADR-0008](../docs/adr/ADR-0008-opportunity-data-model-and-ingestion-pipeline.md) documenting Opportunity Data Model and Ingestion Pipeline Architecture. |
| **11. Independent Blinded Audit** | **PASS** | Independent auditor (`ea2b2e3d-773b-4721-bd90-9587e49535ea`) verified commit `542917b6bbbed595811d460082a21479dd86ae98` against all micro-closure criteria with unanimous PASS. |

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
Your audit target is the exact substantive remediation commit SHA: 542917b6bbbed595811d460082a21479dd86ae98.

Your task is to inspect the opportunity subsystem at C:\Users\norha\projects\system-diagnostics\opportunity (models.py, registry.py, transport.py, acquisition.py, normalization.py, dedupe.py, health.py, pipeline.py, adapters/base.py, adapters/greenhouse.py, adapters/lever.py, adapters/himalayas.py, adapters/remotive.py, adapters/remote_ok.py, adapters/we_work_remotely.py, adapters/ungm.py, adapters/world_bank.py, adapters/eu_ted.py, fixtures/, and test_*.py) and provide a rigorous independent audit report assessing whether the 4 targeted micro-closure criteria are fully and robustly satisfied on commit 542917b6bbbed595811d460082a21479dd86ae98:

1. GREENHOUSE TOKEN-PREFIX COLLISION:
   - Does SourceRegistry preflight authorization enforce exact path segment matching for Greenhouse board tokens?
   - Does source_id="greenhouse:cloudflare" attempting to access url="https://boards-api.greenhouse.io/v1/boards/cloudflareevil/jobs?content=true" strictly fail before transport?

2. LEVER TOKEN-PREFIX COLLISION:
   - Does SourceRegistry preflight authorization enforce exact path segment matching for Lever site tokens?
   - Does source_id="lever:shyftlabs" attempting to access url="https://api.lever.co/v0/postings/shyftlabs2?mode=json" strictly fail before transport?

3. POPULATED COMPENSATION.CURRENCY WITH ONLY PARENT COMPENSATION PROVENANCE:
   - When an Opportunity has populated compensation.currency (e.g. "USD"), does validate_opportunity_provenance() strictly fail if only generic field_name="compensation" provenance is present and field_name="compensation.currency" provenance is missing?

4. POPULATED COMPENSATION.MIN / MAX / INTERVAL WITH ONLY PARENT COMPENSATION PROVENANCE:
   - When an Opportunity has populated compensation min_amount, max_amount, or interval, does validate_opportunity_provenance() strictly fail if only generic field_name="compensation" provenance is present and the specific atomic subfield provenances are missing?

Perform your inspection read-only. Inspect the implementation directly, not merely test names. Report your detailed verdict (PASS/FAIL) with technical evidence and file citations for each of the 4 criteria on commit SHA 542917b6bbbed595811d460082a21479dd86ae98.
```

### 4.2 Auditor Session Metadata & Findings
- **Auditor Subagent Conversation ID:** `ea2b2e3d-773b-4721-bd90-9587e49535ea`
- **Target Commit SHA:** `542917b6bbbed595811d460082a21479dd86ae98`
- **Overall Auditor Verdict:** **PASS (4 / 4 Criteria Satisfied)**

```
1. Greenhouse Token-Prefix Collision: PASS (exact path segment matching enforces segments[2] == board_token)
2. Lever Token-Prefix Collision: PASS (exact path segment matching enforces segments[2] == site_token)
3. Populated compensation.currency Provenance: PASS (MaterialFieldRule requires atomic compensation.currency provenance)
4. Populated compensation.min/max/interval Provenance: PASS (atomic subfield rules require specific individual provenances)
```

### 4.3 Master Disposition of Audit Findings
- **Disposition:** All 4 findings verified and accepted as **PASS**. No remediation or code modifications required.

---

## 5. Phase Gate Determination

**BRIEF-003 COMPLETION STATUS: PASS**  
**BRIEF-003 DEFINITIVELY CLOSED: YES**  
**BRIEF-004 (OPPORTUNITY MATCHING & PROPOSAL TAILORING) UNBLOCKED: YES**

## Decision

PASS

## Next phase prerequisites

- BRIEF-004: Opportunity Matching & Proposal Tailoring
