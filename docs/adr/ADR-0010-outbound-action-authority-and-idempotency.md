# ADR-0010: Outbound Action Authority, Execution Modes, and Idempotency Architecture

- **Status:** Accepted
- **Date:** 2026-08-30
- **Deciders:** Antigravity Master Agent, OpportunityOS Core Team
- **Consulted:** Product Constitution, BRIEF-001, BRIEF-002, BRIEF-003, BRIEF-004, BRIEF-005

## Context

OpportunityOS prepares and executes outbound job applications, multilateral tender responses, and freelance proposals. Outbound actions interact with external systems and create real-world legal and commercial consequences. 

Prior phases established:
- Geographic eligibility authority (BRIEF-001 / ADR-0003, ADR-0006)
- Professional Truth Graph and claim safety (BRIEF-002 / ADR-0007)
- Opportunity discovery, normalization, and deduplication (BRIEF-003 / ADR-0008)
- Qualification, dual-track scoring, and truth-locked tailoring (BRIEF-004 / ADR-0009)

Outbound execution requires an uncompromised side-effect architecture ensuring:
1. No adapter autonomously decides to submit.
2. External mutations require explicit multi-layered authorization.
3. Every populated field is strictly grounded in verified truth or explicit policy.
4. Human verification challenges (CAPTCHA, MFA, bot defenses) are never bypassed.
5. Duplicate submissions and race conditions are strictly prevented via durable idempotency.

## Decision

1. **Explicit Execution Modes**:
   - `DRY_RUN`: Parses forms, plans actions, and populates local mocks only. Records intent without external side effects. Default for all operations.
   - `ASSISTED`: Navigates to application pages, fills fields, uploads approved artifacts, and stops before submission for founder review. Guarantees zero submissions.
   - `CONTROLLED_SUBMIT`: Submits applications only for individually graduated, explicitly enabled adapters against verified opportunities with complete pre-submit manifests.

2. **Central Action Authority & Global Kill Switch**:
   - `ActionAuthority` acts as the single non-bypassable policy engine.
   - An authoritative `GlobalKillSwitch` is checked immediately before any external mutation.
   - Decisions are explicit: `ALLOW_PREPARE`, `ALLOW_FILL`, `ALLOW_SUBMIT`, `PAUSE_FOR_REVIEW`, `BLOCK`.

3. **Source Action Registry**:
   - Granular platform policies: `DISCOVERY_ALLOWED`, `PREPARE_ALLOWED`, `BROWSER_FILL_ALLOWED`, `SUBMIT_ALLOWED`, `API_ACTION_ALLOWED`, `MANUAL_ONLY`, `PROHIBITED`.
   - Unknown platforms default to `PROHIBITED` / `NO SUBMIT`.

4. **Canonical Field Ontology & Green/Yellow/Red Answer Policy**:
   - Detected fields map to 19 canonical types.
   - `GREEN`: Sourced strictly from verified `TruthGraph` assertions.
   - `YELLOW`: Sourced strictly from explicit `TailoringPolicy`. Unconfigured -> PAUSE.
   - `RED`: Legally/contractually sensitive questions (e.g. security clearance, criminal background, binding wage negotiation, guarantees). Never auto-answered autonomously -> PAUSE.

5. **Durable Idempotency Ledger & Confirmation Evidence**:
   - `idempotency_key = sha256(workspace + candidate + canonical_opportunity + action_type)`.
   - Pre-submission intent recorded durably before side effect.
   - Duplicate submissions blocked with zero tolerance.
   - Post-submit state captures cryptographic confirmation evidence. Ambiguous outcomes enter `UNKNOWN_OUTCOME` and freeze automatic retries.

6. **Adapter Graduation Lifecycle**:
   - Adapters progress strictly: `EXPERIMENTAL` -> `DRY_RUN_VERIFIED` -> `ASSISTED_VERIFIED` -> `SUBMIT_ELIGIBLE` -> `SUBMIT_ENABLED` (requires explicit founder flag) -> `SUSPENDED`.

## Consequences

- Outbound side effects are strictly governed, explainable, and reproducible.
- Accidental submissions in assisted mode or on unverified opportunities are impossible.
- Sensitive legal or commercial declarations always require human oversight.
