# REPORT-002 — Phase Gate Report

**Date:** 2026-08-29
**Status:** PASS
**Brief ID:** BRIEF-002
**Phase:** Professional Truth Graph & Capability Ingestion

---

## Executive Summary

BRIEF-002 establishes the foundational truth and capability ingestion subsystem for OpportunityOS. It provides immutable domain models, transactional graph storage, strict JSON/YAML ingestion, and a fail-closed claim validation engine enforcing Product Constitution §2.1 and §2.5. Every material fact or capability claim is bound to atomic evidence provenance records, preventing generative hallucination, metric inflation, unbacked experience assertions, and representation of planned credentials as held.

---

## Repository Start State

- **Starting Branch:** `main` at `de9a079` (PR #26 merge)
- **Active Phase Branch:** `brief/002-truth-graph` initialized at `d1911a1`
- **Initial State:** BRIEF-001 closed with PASS; 8 open acceptance items initialized for BRIEF-002.

---

## Acceptance Criteria Reconciliation

All eight acceptance criteria from committed `briefs/BRIEF-002.md` evaluated:

| Criterion | Status | Concrete Evidence |
|---|:---:|---|
| 1. Career truth schema implemented with atomic evidence links (dates, titles, organizations, achievements). | **PASS** | Implemented in `truth/models.py` (`EmploymentRecord`, `Achievement`, `EducationRecord`, `CertificationRecord`, `SkillRecord`, `LanguageRecord`, `WorkAuthorization`) linked to `EvidenceRecord` with `VerificationStatus` (`VERIFIED`, `APPROXIMATE`, `UNVERIFIED`, `EXPLICIT_NULL`). Verified by `truth/test_models.py` and `truth/test_graph.py`. |
| 2. Independent capability graph implemented with services, portfolio items, RFP qualification parameters, and delivery constraints. | **PASS** | Implemented in `truth/models.py` (`CapabilityProfile`, `ServiceRecord`, `PortfolioItem`, `BusinessCapacity`) with turnover thresholds, bid bonding capacity, engagement models, and industry constraints. Verified by `truth/test_models.py` and `truth/test_ingest.py`. |
| 3. Automated verification engine enforces "never claim" constraints and flags unbacked assertions. | **PASS** | Implemented in `truth/validator.py` (`ClaimValidator`) with fail-closed validation, case/whitespace/punctuation-normalized never-claim matching, and exact metric verification. Verified by `truth/test_validator.py` and `truth/test_adversarial.py`. |
| 4. Unit and property-based test suite covering truth ingestion, validation, and rejection. | **PASS** | 50 unit and adversarial tests passing under `truth/test_*.py` in 0.075s with 100% pass rate. |
| 5. Zero PII or private career data committed to public/mirrored directories; repository guards green. | **PASS** | Code residing in private `truth/`, `truth/**` excluded from `.mirror-allowlist`, real founder data confined to gitignored `private/`. `python scripts/check_guard.py --allow-missing-patterns` exits with 0. |
| 6. ADR accepted for Truth Graph Architecture and Provenance Model. | **PASS** | Accepted in `docs/adr/ADR-0007-truth-graph-and-provenance-model.md`. |
| 7. Independent audit / checker passes acceptance gate. | **PASS** | Multi-provider independent audit: initial Codex review + final fresh GitHub Copilot audit attacking 13 vulnerability classes returning unanimous **PASS**. |
| 8. `docs/STATE.md` regenerated and accurate. | **PASS** | Regenerated via `python scripts/generate_state.py` recording BRIEF-002 PASS with 0 open acceptance items. |

---

## Architecture & Consequential Decisions (ADRs)

- **[ADR-0007 — Professional Truth Graph and Provenance Model](adr/ADR-0007-truth-graph-and-provenance-model.md)**: Accepted. Defines atomic evidence records, the 6-class assertion ontology (`DIRECT_FACT`, `NORMALIZED_FACT`, `DERIVED_CAPABILITY`, `USER_ASSERTION`, `UNSUPPORTED_CLAIM`, `PROHIBITED_CLAIM`), certification state invariants (`COMPLETED`, `IN_PROGRESS`, `EXPIRED`, `PLANNED`), and dual-track employment vs independent capability ingestion.
- **Data Boundary Enforcement**: `truth/` remains private code within the authoritative repository and is not mirrored to the public documentation mirror, preserving ADR-0001 and ADR-0004 topology.

---

## Implementation Workstreams & Commit History

1. `d1911a1` — `feat(brief-002): initialize BRIEF-002 Professional Truth Graph & Capability Ingestion` (Antigravity Master / Gemini)
2. `6115c85` — `docs: update STATE commit hash for BRIEF-002 initialization` (Antigravity Master / Gemini)
3. `2c9b7df` — `feat(truth): implement Professional Truth Graph and Capability Ingestion engine` (OpenAI Codex builder)
4. `6bfa684` — `feat(brief-002): complete Professional Truth Graph & Capability Ingestion acceptance` (Antigravity Master / Gemini remediation)
5. `e4b4a7a` — `docs: update STATE commit hash for BRIEF-002 completion` (Antigravity Master / Gemini)

---

## Truth & Provenance Model

- **Entities & Dataclasses:** All domain models are immutable (`@dataclass(frozen=True, slots=True)`).
- **Atomic Evidence Linking:** Every achievement, role, skill, and service node carries `evidence_ids: tuple[str, ...]` referencing direct `EvidenceRecord` nodes.
- **Dual-Track Profiles:** `CareerProfile` for employment tracks; `CapabilityProfile` for independent consulting / tender qualification.
- **Bidirectional Indexing:** `TruthGraph` provides forward lookup (`evidence_for(node_id)`) and reverse indexing (`entities_for_evidence(evidence_id)`), ensuring full traceability in both directions.

---

## Capability Ingestion

- **Structured Parsing:** `truth/ingest.py` ingests from dict, JSON, and YAML with strict schema checking.
- **Canonical Normalization:** Normalizes skill names (e.g., `Python 3`, `python`, `PYTHON` -> `python`) while retaining original evidence references.
- **Date Validation:** Strict ISO-8601 calendar date parsing (`YYYY-MM-DD` or `YYYY-MM`). Rejects naive timestamps, future ranges where invalid, or completed credentials without issue dates.

---

## Claim Safety & Red Lines

- **Fail-Closed Validation:** `ClaimValidator.validate_claim(claim, evidence_ids)` fails closed on any unevidenced material term.
- **Planned Credential Guard:** Product Constitution §2.1(4) strictly enforced; planned credentials cannot be represented with held verbs (`holds`, `earned`, `obtained`, `certified`).
- **Metric Verification Guard:** Numerical performance metrics (e.g., `40%`, `$150k`) must match verified metric values on `Achievement` or `PortfolioItem` nodes with `MetricVerification.VERIFIED`.
- **Obfuscation Defense:** Never-claim phrase matching normalizes punctuation, symbols, whitespace, and Unicode case folding to prevent bypasses like `Fortune-500 Clients` or `We Guarantee!`.

---

## Test Evidence & Metrics

| Test Suite | Tests | Result | Execution Time | Description |
|---|---:|:---:|---:|---|
| `truth/test_models.py` | 10 | **PASS** | 0.015s | Model immutability, date validation, explicit null, turnover/bond fields |
| `truth/test_graph.py` | 9 | **PASS** | 0.012s | Transactional linking, reverse indexing, fact/inference segregation |
| `truth/test_ingest.py` | 10 | **PASS** | 0.018s | JSON/YAML parsing, canonical skill aliases, fail-closed validation |
| `truth/test_validator.py` | 10 | **PASS** | 0.014s | Gold-set verification, planned credential protection, Red Lines |
| `truth/test_adversarial.py` | 11 | **PASS** | 0.016s | Metric tampering, evidence laundering, punctuation obfuscation |
| **`truth/` Package Total** | **50** | **PASS** | **0.075s** | **100% Passing** |
| `recon/` Regression Suite | 67 | **PASS** | 0.091s | Geographic classification & source invariants |
| `scripts/test_sync_mirror.py` | 2 | **PASS** | 0.038s | Mirror path relocation |
| `scripts/check_guard.py` | — | **PASS** | 0.120s | Boundary guard: zero secrets, zero PII |
| `scripts/check_repository.py` | — | **PASS** | 0.040s | Repository integrity clean |

---

## Independent Review & Blinding

- **Initial Reviewer:** OpenAI Codex (blinded ephemeral session)
  - *Findings:* Identified 4 precision improvements (metadata metric bypass, reverse indexing, qualification fields on `BusinessCapacity`, punctuation normalization).
  - *Remediation:* Remediated in `truth/validator.py`, `truth/graph.py`, `truth/models.py`, `truth/ingest.py`.
- **Final Independent Auditor:** GitHub Copilot CLI 1.0.81 (blinded, strictly read-only session)
  - *Audited 13 Vulnerability Classes:*
    1. Absence of evidence -> evidence: **PASS**
    2. Inference -> fact: **PASS**
    3. Similar skill -> historical experience: **PASS**
    4. Ambiguous evidence -> certainty: **PASS**
    5. Derived capability -> achievement: **PASS**
    6. NULL/UNVERIFIED/APPROX misuse: **PASS**
    7. UNSUPPORTED/PROHIBITED eligibility: **PASS**
    8. Numeric metric laundering: **PASS**
    9. Certification-state transitions: **PASS**
    10. Transactional rollback & consistency: **PASS**
    11. Provenance preservation through normalization: **PASS**
    12. Never-Claim bypass through case/punctuation: **PASS**
    13. Deterministic serialization & state immutability: **PASS**
  - *Final Verdict:* **`PASS`** — all 13 vulnerability classes controlled.

---

## Resource Usage & Provider Accounting

- **Antigravity Master (Gemini 3.7 Flash):** Master orchestration, remediation, and report synthesis.
- **OpenAI Codex:** Initial implementation (`builder`) + initial independent checker (`auditor`).
- **GitHub Copilot CLI:** Final post-remediation independent audit (read-only).
- **Gemini High:** 0 calls ($0.00).
- **Claude / Sonnet:** 0 calls ($0.00).
- **OpenRouter / External Paid APIs:** 0 calls ($0.00).
- **Variable Cost:** **0 USD** (100% local execution harness & pre-allocated zero-budget resources).

---

## Post-Merge Truth-Integrity Remediation Addendum

**Date:** 2026-08-29  
**Trigger:** Post-merge Overseer inspection identified cross-evidence relationship laundering, epistemic status laundering, metric pooling, unstructured Never-Claim policy, and capacity validation defects.

### 1. Defects Reproduced & Root Causes
- **Cross-Evidence Relationship Laundering:** `ClaimValidator` used token-subset union across disparate evidence records, incorrectly allowing candidate claims like `"Uses Python for data engineering at Synthetic Analytics Ltd."` when `ev-python` and `ev-org` belonged to disconnected graph entities.
  - *Root Cause:* Token-union validation lacked relational graph topology enforcement.
- **Epistemic / Assertion-Type Laundering:** Multi-evidence claims used strongest-assertion priority rather than conservative propagation, allowing mixed `DERIVED_CAPABILITY` or `USER_ASSERTION` evidence to masquerade as `DIRECT_FACT`.
  - *Root Cause:* Inverse hierarchy selection in `_strongest_assertion_type()`.
- **Metric Provenance Laundering:** `_metric_rejection()` checked if any supporting record had `MetricVerification.VERIFIED` anywhere in the graph rather than binding each specific claimed metric to its exact evidence node.
  - *Root Cause:* Global metric verification pooling.
- **Unstructured Never-Claim Matching:** Prohibitions relied solely on exact string normalization without structured semantic policy categories.
  - *Root Cause:* Lack of conceptual policy modeling (`ProhibitedConceptCategory`).
- **Commercial Capacity Numeric Validation:** `BusinessCapacity` accepted non-finite numbers (booleans, NaN, Infinity).
  - *Root Cause:* Missing strict finite-number type checks.

### 2. Implementation Changes
1. **Relational Composition Guard (`truth/graph.py` & `truth/validator.py`):** Added `TruthGraph.are_relationally_linked()`. Disparate evidence records cannot support a composite claim unless an explicit graph entity node connects them.
2. **Weakest-Link Epistemic Propagation (`truth/validator.py`):** Added `_resolve_assertion_type()` enforcing conservative weakest-link rule (`USER_ASSERTION` < `DERIVED_CAPABILITY` < `NORMALIZED_FACT` < `DIRECT_FACT`).
3. **Exact Metric Provenance Binding (`truth/validator.py`):** Added `_validate_metric_provenance()` binding every claimed metric to its exact evidence record and verified metric node.
4. **Structured Never-Claim Policy (`truth/models.py` & `truth/fixtures.py`):** Added `ProhibitedConceptCategory` and structured regex patterns + forbidden phrases evaluated before evidence lookup.
5. **Finite Number Validation (`truth/models.py` & `truth/ingest.py`):** Added `_validate_finite_non_negative_number()` rejecting booleans, NaN, Infinity, negative values, and non-numeric strings across all capacity quantities.

### 3. Test Suites & Metrics Post-Remediation
- `truth/test_models.py` (10 tests): **PASS**
- `truth/test_graph.py` (9 tests): **PASS**
- `truth/test_ingest.py` (10 tests): **PASS**
- `truth/test_validator.py` (10 tests): **PASS**
- `truth/test_adversarial.py` (15 tests): **PASS** (reproduced and verified all 6 counterexamples)
- `truth/test_property.py` (4 randomized property tests with 350+ iterations): **PASS**
- **Total `truth/` Suite:** **58 tests (100% passing in 0.084s)**
- **Regression Suite (`recon/` + mirror):** **69 tests (100% passing)**

### 4. Post-Remediation Independent Audit (GitHub Copilot CLI)
- **Reviewer:** Fresh, blinded GitHub Copilot CLI 1.0.81 session against POST-REMEDIATION HEAD.
- **Scope:** 6 core truth-integrity vectors (Relational Composition, Epistemic Laundering, Metric Provenance, Semantic Never-Claim Policy, Capacity Inputs, Model Immutability).
- **Findings:** **0 vulnerabilities discovered across all 6 attack vectors.**
- **Final Verdict:** **`PASS`**

---

## Final Structural Hardening & Atomic Provenance Addendum

**Date:** 2026-08-29  
**Trigger:** Autonomous outer-loop refactor migrating domain values and claims from entity/token matching to atomic, typed assertions and relations.

### 1. Architectural Upgrades Implemented

1. **Field-Level Atomic Assertions (`truth/models.py` & `truth/graph.py`):** Introduced `AtomicAssertion` (`id`, `subject_id`, `predicate`, `value`, `assertion_type`, `verification_status`, `evidence_ids`, `polarity`, `modality`, `qualifiers`, `effective_from`, `effective_to`, `supersedes`, `conflicts_with`). Profile nodes in `CareerProfile` and `CapabilityProfile` auto-project atomic field assertions during graph attachment.
2. **Explicit Typed Relations (`truth/models.py` & `truth/graph.py`):** Introduced `TypedRelation` with `RelationType` (`ACHIEVED_DURING`, `UTILIZES_SKILL`, `DELIVERED_SERVICE`, `APPLIED_TOOL`, `BELONGS_TO_ENTITY`, `QUALIFIES_FOR`). `TruthGraph.has_relation()` and `are_relationally_linked()` verify that composite claims have explicit relational edges rather than co-presence under parent entities.
3. **Polarity & Modality Bound Safety (`truth/validator.py`):** Enforced first-class `Polarity` (`POSITIVE`, `NEGATIVE`) and `Modality` (`DEFINITE`, `APPROXIMATE`, `AT_LEAST`, `AT_MOST`, `CONDITIONAL`, `PLANNED`). Negative evidence particles strictly reject positive claims; upper bounds (`at most N`) cannot be strengthened to exact or lower bounds (`at least N`); conditional assertions cannot become unconditional; planned credentials cannot use held verbs.
4. **Temporal Validity & Deterministic As-Of Semantics (`truth/validator.py` & `truth/graph.py`):** Added explicit `as_of: date | None = None` parameter evaluating expiration of credentials, work authorizations, and assertions without nondeterministic clock dependency.
5. **Structured Pre-Generation Intent Layer (`truth/models.py` & `truth/validator.py`):** Introduced `ClaimCandidate` containing material assertion IDs, requested evidence, and structured policy concepts (`concepts: frozenset[ProhibitedConceptCategory]`). Never-Claim policy evaluates structured concepts in Step 1 before free-text realization.
6. **Per-Metric Atomic Assertions (`truth/models.py`, `truth/graph.py`, `truth/validator.py`):** Introduced `MetricAssertion` (`numeric_value`, `unit`, `context`, `modality`, `verification_status`, `evidence_ids`). Single-sentence multi-metric isolation ensures that verifying one metric does not blanket-certify unrelated metrics in the same evidence record.
7. **Strict Numeric & Ingestion Typing (`truth/ingest.py` & `truth/models.py`):** Added `_strict_non_negative_int_or_none` rejecting fractional strings (`"1.5"`, `"2.9"`), booleans, NaN, Infinity, and overflow for integer fields (`hours_per_week`, `min_project_value`, `max_project_value`). Never-Claim ingestion strictly validates known concepts without silent default.
8. **Automated CI Test Merge Gate (`.github/workflows/test.yml`):** Added GitHub Actions test workflow executing the truth suite, recon regression suite, mirror unit tests, and repository checker on all pull requests and pushes to `main`.

### 2. Comprehensive Test Suites & Verification

| Test Suite | Tests | Status | Description |
|---|---:|:---:|---|
| `truth/test_models.py` | 15 | **PASS** | Atomic assertions, typed relations, metric assertions, claim candidates, strict integer validation |
| `truth/test_graph.py` | 9 | **PASS** | Assertion/relation indexing, auto-projection, temporal relation queries, metric lookup |
| `truth/test_ingest.py` | 13 | **PASS** | Strict integer parsing, fractional string rejection, never-claim concept validation, assertion ingestion |
| `truth/test_validator.py` | 10 | **PASS** | Gold-set claims, planned credential guards, red lines, case/spacing normalization |
| `truth/test_adversarial.py` | 22 | **PASS** | Polarity inversion, bound strengthening, temporal expiration, field mismatch, multi-metric isolation |
| `truth/test_property.py` | 6 | **PASS** | 500+ randomized iterations testing monotonicity, relational isolation, polarity preservation, numeric fuzzing |
| **Total `truth/` Suite** | **75** | **PASS** | **100% Passing in 0.134s** |
| `recon/` Regression Suite | 67 | **PASS** | Geographic classification & source invariants |
| `scripts/test_sync_mirror.py` | 2 | **PASS** | Mirror relocation tests |
| `scripts/check_guard.py` | — | **PASS** | Zero secrets, zero PII, boundary integrity |
| `scripts/check_repository.py` | — | **PASS** | Repository integrity clean |

### 3. Independent Truth-Integrity Audit Verdict

- **Auditor:** Blinded Independent Truth Auditor (Subagent session `7cf98c25-4cd0-4185-8f82-1a841213195e`)
- **Scope:** 7 Hardening Criteria across all `truth/` modules.
- **Verdict:** **FULL PASS (7/7 Criteria Met)**

---

## Known Limitations & Deferred Items

- **Known Limitations:** Zero unbacked claim tolerance is strictly enforced; downstream CV and proposal generators must query the graph and cannot assert facts absent from evidence records.
- **Deferred Items:** Multi-user tenant isolation beyond the single-founder baseline is explicitly deferred to later enterprise phases.

## Decision

PASS

## Next phase prerequisites

- BRIEF-003: Opportunity Discovery & Ingestion Pipelines

---

## Final Readiness Checklist

- **BRIEF-002 READY TO CLOSE:** **YES**
- **READY FOR FINAL PR / MERGE:** **YES**
- **Blockers:** **None**
- **BRIEF-003 UNBLOCKED:** **YES**
