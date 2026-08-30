# Phase Gate Report: BRIEF-005 — Outbound Application & Engagement Workflows

**Phase ID:** BRIEF-005  
**Status:** PASS  
**Date:** 2026-08-30  
**Substantive Commit SHA:** 8ec2a434395f80f2126725d07a30a11fd7e5ba90  
**Author:** Antigravity Master Agent (Dual-Loop Autonomous Controller)  
**Independent Auditor:** Independent Terminal Residual Authority Auditor (`94f1776b-e6c2-4799-a55d-80fc838b09bf`)  
**Auditor Provider & Model:** Google Antigravity / Vertex AI (Tier: pro)

---

## 1. Executive Summary

BRIEF-005 establishes OpportunityOS's governed outbound application and engagement subsystem (`outbound/`), transforming the system from an opportunity discovery, qualification, and tailoring engine into an end-to-end execution system that can safely prepare, populate, review, and—only where explicitly authorized—submit employment applications, multilateral procurement dossiers, and freelance proposals.

The subsystem enforces strict side-effect isolation, zero-fabrication answer generation across Green and Yellow tiers, deterministic open-world work authorization semantics (UNKNOWN != FALSE), TOCTOU safety with terminal kill-switch race closure and post-preparation manifest staleness detection, durable cross-instance atomic SQLite idempotency, positive source action permission granularity, real persisted adapter graduation evidence with dynamic runtime invalidation, impossible-to-split registry authority, and non-bypassable candidate/workspace artifact binding:

1. **Central Action Authority (`outbound/authority.py`)**: The single non-bypassable authority governing all form actions. Evaluates 11 prerequisite dimensions fail-closed (kill switch, execution mode, source action policy granularity, authoritative adapter graduation, hard qualification, candidate/workspace artifact validation, red question gates, durable duplicate detection, captcha/mfa barriers, and mandatory field completion).
2. **Global Kill Switch & Terminal Race Closure (`outbound/authority.py`, `outbound/browser_engine.py`)**: Instantaneous emergency halting mechanism evaluated dynamically at action inception, pre-submit gate, and immediately adjacent to the irreversible `driver.submit_page()` call following atomic reservation.
3. **Strict Execution Modes (`outbound/models.py`, `outbound/browser_engine.py`)**:
   - `ExecutionMode.DRY_RUN` (default): Prepares submission manifests without field mutation or network submissions. Requires `PREPARE_ALLOWED` or stronger.
   - `ExecutionMode.ASSISTED`: Populates form fields and attaches tailored artifacts, but strictly refrains from triggering form submissions. Requires `BROWSER_FILL_ALLOWED` or stronger.
   - `ExecutionMode.CONTROLLED_SUBMIT`: Permitted only when the adapter has graduated to `AdapterLifecycleState.SUBMIT_ENABLED`, has explicit founder authorization, and the source policy explicitly allows `SUBMIT_ALLOWED` / `API_ACTION_ALLOWED`.
4. **Canonical 19-Type Ontology & Sensitivity Classifier (`outbound/ontology.py`)**: Normalizes interactive form inputs into 19 canonical types and assigns strict Green, Yellow, and Red sensitivity classes.
5. **Zero Fabrication Answer Engine & Explicit Yellow Policy Authority (`outbound/answer_engine.py`)**:
   - **Green Answers**: Derived strictly from verified `TruthGraph` assertions with atomic assertion IDs. All fallback values and manufactured defaults are completely eradicated. Missing evidence yields `answer=None`, `AnswerClass.RED`, and `disposition="pause"`. `employment.title` is strictly prevented from being used as `identity.name`.
   - **Open-World Work Authorization**: Mismatches (e.g. verified in Egypt, question asks for US authorization) strictly reject "Yes" and "No", yielding `answer=None` / `AnswerClass.RED` (Pause). "No" is generated strictly when explicit verified negative authority (`polarity=Polarity.NEGATIVE`) exists. UNKNOWN != FALSE.
   - **Explicit Yellow Policy Rules (Zero Implicit Defaults)**:
     - `default_sponsorship_required` must be explicitly configured (`bool | None`); if `None` $\rightarrow$ `RED / PAUSE` (never defaults to "No").
     - `default_notice_period_days` must be explicitly configured; if `None` $\rightarrow$ `RED / PAUSE` (never defaults to 30 days).
     - `default_currency` defaults to `None`. Compensation rate answers require explicit rate, explicit currency, AND explicit interval (`/hr` or `/day`); missing currency or rate $\rightarrow$ `RED / PAUSE`.
   - **Red Declarations**: Sensitive, legal, narrative, clearance, or ambiguous questions are never answered autonomously and pause for founder review.
6. **Real Persisted Graduation Evidence & Dynamic Runtime Invalidation (`outbound/registry.py`)**:
   - Synthetic string hashes and placeholder JSON claims are eradicated.
   - Production default adapters (`greenhouse`, `lever`, `ashby`, `generic_form`, `procurement_package`, `freelance_proposal`) default strictly to `AdapterLifecycleState.ASSISTED_VERIFIED` with empty evidence hash.
   - `AdapterRegistry.get_graduation_record` performs dynamic runtime disk verification; if graduation evidence is deleted, corrupted, or modified after registry initialization, `SUBMIT_ELIGIBLE` and `SUBMIT_ENABLED` authorities are immediately invalidated and downgraded to `ASSISTED_VERIFIED`.
7. **Impossible-to-Split Registry Authority (`outbound/browser_engine.py`)**:
   - `OutboundBrowserEngine` enforces strict identity equality (`adapter_registry is authority.adapter_registry` and `source_registry is authority.registry`).
   - Passing a different registry instance than the one tied to `ActionAuthority` is strictly rejected with `ValueError`.
8. **Real Prepare $\rightarrow$ Mutate Pre-Submit Staleness & Final Authority Gate (`outbound/browser_engine.py`)**:
   - `PreSubmitManifest` binds all material authorities (`answers_hash`, opportunity content hash, artifact hashes, source policy version, adapter graduation version and evidence hash, tailoring policy version, qualification decision) while excluding non-material runtime metadata like `compiled_at`.
   - Under `CONTROLLED_SUBMIT`, comparing against the genuine prepared snapshot detects and blocks any post-preparation mutation in TruthGraph provenance, source policy version, adapter graduation evidence, or TailoringPolicy.
   - Immediately adjacent to `driver.submit_page()` after reservation, all external action authorities (kill switch, source policy, adapter graduation evidence) are re-validated fail-closed.
9. **Cross-Instance Atomic SQLite Idempotency Ledger (`outbound/idempotency.py`)**:
   - Uses `BEGIN IMMEDIATE` transactions to leverage SQLite's built-in exclusive write locking.
   - Two independent `IdempotencyLedger` instances racing on the same database file result in exactly one successful reservation, with the second receiving `DuplicateSubmissionError`.
   - End-to-end race across two independent browser engines results in exactly ONE external submission call.
   - True runtime UTC timestamps recorded dynamically.
   - `UNKNOWN_OUTCOME` permanently freezes automated retries until explicit founder reconciliation.
10. **Non-Bypassable Bound Artifact Ownership (`outbound/models.py`, `outbound/artifact_selector.py`)**: Mandates `BoundArtifact` with validated non-empty `candidate_id` and `workspace` for assisted upload and controlled submit. Raw unowned artifacts and mismatched candidate/workspace contexts are strictly blocked.

---

## 2. Acceptance Criteria Evaluation

| Acceptance Criterion | Status | Evidence / Verification |
| :--- | :---: | :--- |
| **1. Central Action Authority** | **PASS** | `ActionAuthority` is the single non-bypassable gate evaluating all 11 prerequisite dimensions fail-closed. Verified in `test_authority.py` and `test_zero_tolerance.py`. |
| **2. Global Kill Switch & Terminal Race Closure** | **PASS** | `GlobalKillSwitch` evaluated after reservation immediately adjacent to submit call; aborts with 0 submit calls if toggled. Verified in `test_adversarial.py:80-120`. |
| **3. Strict Execution Modes & Positive Granularity** | **PASS** | `DRY_RUN` requires `PREPARE_ALLOWED`; `ASSISTED` requires `BROWSER_FILL_ALLOWED`; `CONTROLLED_SUBMIT` requires `SUBMIT_ALLOWED`; `DISCOVERY_ALLOWED` alone rejects fill/prepare. Verified in `test_authority.py`. |
| **4. Canonical 19-Type Ontology** | **PASS** | `FieldClassifier` categorizes fields into the 19 canonical ontology types and assigns Green/Yellow/Red classes. Verified in `test_ontology.py`. |
| **5. Zero Fabrication Answer Engine & Explicit Policy Authority** | **PASS** | Unconfigured sponsorship, notice period, or compensation currency strictly yields `RED / PAUSE`. Verified in `test_answer_engine.py`. |
| **6. Open-World Work Authorization** | **PASS** | UNKNOWN != FALSE. Absence of evidence for target jurisdiction yields Red/Pause; "No" requires verified negative authority. Verified in `test_answer_engine.py`. |
| **7. Real Persisted Graduation Evidence & Runtime Invalidation** | **PASS** | Default production adapters default to `ASSISTED_VERIFIED`. Deleting, corrupting, or modifying evidence on disk after initialization dynamically invalidates submit eligibility/enablement. Verified in `test_registry.py`. |
| **8. Impossible-to-Split Registry Authority** | **PASS** | `OutboundBrowserEngine` enforces strict identity equality for `AdapterRegistry` and `SourceActionRegistry`. Verified in `test_browser_engine.py`. |
| **9. Real Prepare $\rightarrow$ Mutate Pre-Submit Staleness Gate** | **PASS** | Genuine prepare snapshot compared against fresh re-derivation detects and blocks any post-preparation mutation in TruthGraph, source policy, adapter evidence, or TailoringPolicy. Verified in `test_adversarial.py:280-450`. |
| **10. Cross-Instance SQLite Idempotency Atomicity** | **PASS** | `BEGIN IMMEDIATE` transaction ensures exactly one reservation wins across independent ledger instances; end-to-end browser engine race proves exactly one submit call across contenders. Verified in `test_idempotency.py` and `test_adversarial.py:240-280`. |
| **11. Non-Bypassable Bound Artifact Ownership** | **PASS** | `BoundArtifact` enforces proven non-empty `candidate_id` and `workspace`. Raw unowned artifacts strictly blocked. Verified in `test_artifact_selector.py` and `test_authority.py`. |
| **12. Anti-Bot / CAPTCHA / MFA Handling** | **PASS** | CAPTCHA detection blocks action; MFA detection pauses for human login. Verified in `test_zero_tolerance.py`. |
| **13. Multi-Step Browser Loop** | **PASS** | Full step-by-step navigation, dynamic challenge checks, and ASSISTED submit prohibition. Verified in `test_browser_engine.py` and `test_adversarial.py`. |
| **14. Zero-Tolerance & Adversarial Tests** | **PASS** | All 15 required Zero-Tolerance invariant tests and all 20 Adversarial attack vector tests pass cleanly (347 repository unit tests total). |
| **15. Architectural Decision Record** | **PASS** | Committed [ADR-0010](../docs/adr/ADR-0010-outbound-action-authority-and-idempotency.md) documenting Outbound Action Authority, Execution Modes, and Idempotency Architecture. |
| **16. Independent Blinded Audit** | **PASS** | Independent Auditor (`94f1776b-e6c2-4799-a55d-80fc838b09bf`) audited commit `8ec2a434395f80f2126725d07a30a11fd7e5ba90` with unanimous 4/4 PASS verdict. |

---

## 3. Independent Audit Log

```yaml
audit_session:
  auditor_role: "Independent Terminal Residual Authority Auditor"
  conversation_id: "94f1776b-e6c2-4799-a55d-80fc838b09bf"
  target_commit_sha: "8ec2a434395f80f2126725d07a30a11fd7e5ba90"
  provider_and_model: "Google Antigravity / Vertex AI (pro)"
  criteria_evaluated: 4
  criteria_passed: 4
  criteria_failed: 0
  verdict: "APPROVED / PASS"
```

### Exact Verbatim Audit Prompt:
```
You are an independent, blinded terminal authority auditor for OpportunityOS.
Your audit target is the exact substantive remediation commit SHA: 8ec2a434395f80f2126725d07a30a11fd7e5ba90.

Your task is to inspect the outbound subsystem at C:\Users\norha\projects\system-diagnostics\outbound (models.py, ontology.py, answer_engine.py, artifact_selector.py, registry.py, idempotency.py, authority.py, browser_engine.py, fixtures/, test_*.py) and matching/models.py, and provide a rigorous independent audit report assessing whether the 4 residual authority criteria and attack vectors are fully and genuinely satisfied on commit 8ec2a434395f80f2126725d07a30a11fd7e5ba90:

1. COMPENSATION AUTHORITY — NO IMPLICIT USD / INTERVAL AMBIGUITY:
   - Does TailoringPolicy.default_currency default to None?
   - When hourly rate or daily rate is configured without explicit currency (currency is None), does ApplicationAnswerEngine strictly return RED / PAUSE (answer=None), never defaulting to USD?
   - Is a compensation Yellow answer emitted ONLY when rate, currency, AND interval are all explicitly configured (e.g. "USD 120.0/hr" or "EUR 850.0/day")?
   - Does an empty TailoringPolicy strictly return RED / PAUSE?

2. CONCRETE PERSISTED GRADUATION EVIDENCE & RUNTIME INVALIDATION:
   - Are production default adapters (greenhouse, lever, ashby, generic_form, procurement_package, freelance_proposal) defaulted to ASSISTED_VERIFIED with empty evidence_hash when no underlying test evidence exists?
   - Does AdapterRegistry.get_graduation_record dynamically check the backing evidence file on disk?
   - If graduation evidence is deleted, corrupted, or modified on disk AFTER AdapterRegistry initialization, is SUBMIT_ELIGIBLE / SUBMIT_ENABLED authority immediately and dynamically invalidated (downgraded to ASSISTED_VERIFIED)?

3. PRE-SUBMIT MANIFEST & REAL PREPARE -> MUTATE AUTHORITY PATH:
   - Does PreSubmitManifest bind material authorities (answers_hash, opportunity content hash, artifact hashes, source policy version, adapter graduation version, adapter graduation evidence hash, tailoring policy version, qualification decision) while excluding non-material runtime metadata like compiled_at from the manifest hash?
   - Are there REAL tests proving:
     A. prepare -> no material change -> controlled submit reaches normal authority path successfully;
     B. prepare -> TruthGraph provenance changes -> BLOCK, zero submit;
     C. prepare -> source policy version changes while policy remains submit-capable -> BLOCK, zero submit;
     D. prepare -> adapter graduation evidence changes -> BLOCK, zero submit;
     E. prepare -> relevant TailoringPolicy changes -> BLOCK, zero submit?
   - FINAL SIDE-EFFECT AUTHORITY: Immediately adjacent to driver.submit_page() after reservation, is source policy and adapter graduation evidence re-validated? Does an adversarial mutation hook that alters source policy during/after reservation prove submit_page() is NEVER called?

4. TWO-INDEPENDENT-LEDGER SIDE-EFFECT RACE:
   - Does IdempotencyLedger use BEGIN IMMEDIATE atomic transactions for reserve_submission?
   - When TWO separate, independent IdempotencyLedger(db_path) instances, each driving its own OutboundBrowserEngine, race against the same SQLite database file for the same idempotency key, does exactly ONE contender win reservation while the other is blocked by DuplicateSubmissionError / duplicate authority?
   - Across both engines, is driver.submit_page() called exactly ONCE?
```

### Complete Auditor Findings & Verdict:
> "Below is my detailed verdict and technical evidence against the four residual authority criteria:
> 
> Verdict: PASS on all 4 criteria.
> 
> 1. COMPENSATION AUTHORITY — NO IMPLICIT USD / INTERVAL AMBIGUITY: PASS
>    - `TailoringPolicy.default_currency` is explicitly initialized to `None` in `matching/models.py:302`.
>    - `outbound/answer_engine.py` skips generating a compensation answer if `default_currency` is falsy, decisively returning `AnswerClass.RED` with `answer=None` and `disposition="pause"`. It never falls back to USD implicitly.
>    - When currency is explicitly provided with hourly or daily rate, it constructs an explicit interval string (`/hr` or `/day`) and emits `AnswerClass.YELLOW`.
>    - An empty `TailoringPolicy()` correctly drops into the RED/PAUSE path.
> 
> 2. CONCRETE PERSISTED GRADUATION EVIDENCE & RUNTIME INVALIDATION: PASS
>    - Production default adapters strictly default to `AdapterLifecycleState.ASSISTED_VERIFIED` with `evidence_hash=""`.
>    - `AdapterRegistry.get_graduation_record` triggers a runtime file presence and integrity check (`_compute_evidence_hash`) anytime an adapter claims to be `SUBMIT_ELIGIBLE` or `SUBMIT_ENABLED`.
>    - If evidence is deleted, corrupted, or modified after initialization, `get_graduation_record` dynamically downgrades the record to `ASSISTED_VERIFIED`, nullifying prior submit authority.
> 
> 3. PRE-SUBMIT MANIFEST & REAL PREPARE -> MUTATE AUTHORITY PATH: PASS
>    - `PreSubmitManifest` strictly binds material authorities into `manifest_hash` while excluding `compiled_at`.
>    - Real tests in `outbound/test_adversarial.py` verify all 5 prepare $\rightarrow$ mutate paths (A through E).
>    - Final post-reservation authority re-validation directly adjacent to `driver.submit_page()` is verified; adversarial post-reservation mutation hook proves `submit_page()` is NEVER called (`harness.submits_count == 0`).
> 
> 4. TWO-INDEPENDENT-LEDGER SIDE-EFFECT RACE: PASS
>    - `IdempotencyLedger.reserve_submission` employs `BEGIN IMMEDIATE` transactions, safely preventing read-modify-write races.
>    - Racing two independent ledgers against the same SQLite file proves exactly one reservation succeeds and the other receives `DuplicateSubmissionError`.
>    - Racing two full `OutboundBrowserEngine` instances connected to distinct mock drivers proves `harness.submits_count == 1` and `ActionStatus.CONFIRMED` fires only once across contenders."

### Master Disposition
All 4 residual authority criteria are robustly satisfied. BRIEF-005 is definitively closed.

---

## Decision

PASS

## Next phase prerequisites

- BRIEF-006: Operational Autonomy, Feedback Loops & Production Pipeline

## Blocked

- None
