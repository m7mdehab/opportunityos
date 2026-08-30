# BRIEF-005 — Outbound Application & Engagement Workflows

**Terminal gate:** Complete, deterministic outbound preparation, canonical field ontology, Green/Yellow/Red answer policy & provenance, browser execution engine with CAPTCHA/MFA fail-safe controls, central action authority with global kill switch, source action registry, idempotency & duplicate prevention ledger, confirmation detector, mock ATS/forms test harness, adapter graduation lifecycle, independent procurement/freelance action packages, 15 zero-tolerance invariant tests, 20 adversarial attack vector tests, and independent blinded audit PASS.

## Transactional execution

Maintain an internal unresolved-task ledger and dependency DAG. Do not return while an available agent or tool can execute an unresolved task; repair defects and rerun invalidated evidence automatically.

## Capability preflight

Map every logical role to a capability exposed by the execution harness before
starting. An approved separate model, tool, or session may satisfy an
independence requirement; record the planned handoff and immutable evidence.

```yaml
phase_id: "BRIEF-005"
objective: "Implement the outbound application preparation, browser automation, side-effect authority, answer provenance, idempotency, and confirmation subsystem."
why_now: "With opportunity discovery (BRIEF-003) and qualification/tailoring (BRIEF-004) operational, OpportunityOS now requires safe, highly governed outbound execution capabilities to prepare, populate, review, and, only where explicitly authorized, submit applications with minimal founder intervention and strictly controlled external side effects."
user_value:
  founder_employment: "Prepares, accurately populates, and safely executes job applications across Greenhouse, Lever, Ashby, and custom ATS portals with 100% truth provenance and zero accidental submissions."
  founder_independent_work: "Prepares compliant multilateral/international tender response packages, freelance proposals, and EOI submissions with manual deep-link handoffs and strict legal/commercial protection."
non_negotiables:
  - "Default execution mode is DRY_RUN; CONTROLLED_SUBMIT is never the default and requires explicit global enablement and individual adapter graduation."
  - "Central Action Authority is non-bypassable: no adapter may autonomously decide to submit."
  - "Answer classes: GREEN (truth-backed), YELLOW (policy-backed), RED (never auto-answered autonomously; pause for review)."
  - "Artifact upload safety: strict binding to workspace, candidate, opportunity ID, opportunity content hash, and verified artifact hash."
  - "Zero CAPTCHA/MFA bypass attempts: fail-safe and pause on any human-verification or bot-detection challenge."
  - "Strict idempotency and duplicate prevention: durable intent written before side effect; UNKNOWN_OUTCOME prevents automatic retries."
  - "Authoritative global kill switch: checked immediately before external side effects."
explicitly_out_of_scope:
  - "Inbox / recruiter / client response detection and outcome monitoring (reserved for BRIEF-006)."
  - "Bypassing CAPTCHA, MFA, or anti-bot defenses."
  - "Autonomous acceptance of binding legal declarations or commercial guarantees."
allowed_sources_and_tools:
  - "Local TruthGraph (BRIEF-002), Opportunity models (BRIEF-003), Matching & Artifact Compilers (BRIEF-004)."
  - "Python 3.12 standard library, mock ATS harness, browser automation interfaces."
budget_cap: "0 USD (local execution harness)"
concurrency_cap: "4 parallel worktrees/subagents"
required_acceptance_metrics:
  accidental_submits: 0
  duplicate_submits: 0
  unauthorized_red_answers: 0
  captcha_mfa_bypass_attempts: 0
  unvalidated_artifact_uploads: 0
required_gold_sets:
  - "Mock ATS form schemas and end-to-end multi-step application scenarios"
required_deliverables:
  - "briefs/BRIEF-005.md"
  - "outbound/ models, authority, registry, ontology, answer_engine, artifact_selector, browser_engine, idempotency, confirmation, adapters, mock_harness"
  - "ADR-0010 documenting outbound action authority and idempotency"
  - "reports/REPORT-005.md"
  - "docs/STATE.md"
final_report_only: true
```

## Work breakdown & dependency DAG

1. **Phase 1: Outbound Data Models & Canonical Ontology (`outbound/models.py`, `outbound/ontology.py`)**
   - Execution modes, action authority decisions, source action policies, adapter lifecycle states.
   - 19 canonical field ontology types, answer classes (GREEN, YELLOW, RED), submission states.
   - ApplicationAnswer, DetectedFormField, PreSubmitManifest, ConfirmationEvidence, OutboundActionRecord.
   - FieldClassifier for deterministic form field inspection and classification.

2. **Phase 2: Action Authority, Source Policy Registry & Kill Switch (`outbound/authority.py`, `outbound/registry.py`)**
   - Authoritative GlobalKillSwitch checked immediately before side effects.
   - Central ActionAuthority evaluating 11 prerequisite safety dimensions.
   - SourceActionRegistry mapping platforms to allowed action classes (default PROHIBITED).

3. **Phase 3: Answer Engine & Artifact Selector (`outbound/answer_engine.py`, `outbound/artifact_selector.py`)**
   - ApplicationAnswerEngine deriving GREEN (truth-backed), YELLOW (policy-backed), and RED (review-required) answers with complete atomic provenance.
   - ApplicationArtifactSelector enforcing opportunity ID/hash binding, artifact validation, and digest matching.

4. **Phase 4: Browser Automation Engine & Mock ATS Harness (`outbound/browser_engine.py`, `outbound/mock_harness.py`)**
   - BrowserDriver abstraction with mock and headless implementations.
   - Multi-step page navigation, field population, artifact upload, error detection.
   - Anti-bot and challenge detection (CAPTCHA/MFA -> STOP).
   - Mock ATS harness simulating Greenhouse, Lever, Ashby, multi-step, dynamic questions, upload errors, challenges, and confirmation receipts.

5. **Phase 5: Idempotency Ledger, Confirmation Detector & Adapters (`outbound/idempotency.py`, `outbound/confirmation.py`, `outbound/adapters/`)**
   - IdempotencyLedger with durable intent writing, state machine, duplicate prevention, and UNKNOWN_OUTCOME freeze.
   - ConfirmationDetector for receipt capture and cryptographic evidence.
   - Outbound adapters for Greenhouse, Lever, Ashby, Generic Forms, Procurement Packages, and Freelance Proposals.

6. **Phase 6: Comprehensive Test Suites, Zero-Tolerance & Adversarial Coverage (`outbound/test_*.py`)**
   - Unit tests for all modules.
   - Integration & mock-browser E2E tests for DRY_RUN, ASSISTED, and CONTROLLED_SUBMIT.
   - 15 zero-tolerance invariant tests.
   - 20 adversarial attack vector tests.

7. **Phase 7: Governance, ADR, Independent Audit & Report (`docs/adr/`, `reports/`)**
   - Commit ADR-0010.
   - Independent blinded audit against the substantive commit SHA.
   - Final phase gate report REPORT-005.md.

## Acceptance Criteria

- [x] Execution modes (DRY_RUN, ASSISTED, CONTROLLED_SUBMIT) implemented with DRY_RUN default.
- [x] Central ActionAuthority enforces kill switch, source policy, adapter graduation, qualification, artifact validation, and red question gates.
- [x] SourceActionRegistry distinguishes action permissions and defaults to PROHIBITED for unknown platforms.
- [x] 19-type canonical field ontology and Green/Yellow/Red answer policy implemented with full atomic provenance.
- [x] ApplicationArtifactSelector enforces opportunity ID/hash binding and claim validation.
- [x] Browser execution engine navigates forms, fills fields, uploads artifacts, and stops on CAPTCHA/MFA.
- [x] ASSISTED mode provides 100% guarantee of zero submissions.
- [x] Adapter graduation model enforces lifecycle transitions from EXPERIMENTAL to SUBMIT_ENABLED.
- [x] Pre-submit manifest and IdempotencyLedger guarantee duplicate prevention and safe UNKNOWN_OUTCOME handling.
- [x] ConfirmationDetector captures cryptographic receipt evidence.
- [x] Independent procurement/freelance packages generated without autonomous binding legal/commercial commitments.
- [x] Mock ATS harness reproduces all target platforms, challenges, and edge cases.
- [x] 15 zero-tolerance invariant tests pass with 0 defects.
- [x] 20 adversarial attack vector tests pass.
- [x] ADR-0010 committed.
- [x] Blinded independent audit PASS.
- [x] REPORT-005.md completed and docs/STATE.md updated.
