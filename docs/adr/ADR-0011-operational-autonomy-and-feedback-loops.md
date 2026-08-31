# ADR-0011: Operational Autonomy, Inbound Signal Processing, Pipeline Synchronization, and Safe Learning

- **Status:** Accepted
- **Date:** 2026-08-30
- **Deciders:** Antigravity Master Agent, OpportunityOS Core Team
- **Consulted:** Product Constitution, Master Plan §20, BRIEF-000 through BRIEF-005

## Context

OpportunityOS possesses end-to-end capabilities to discover opportunities, verify eligibility, tailor artifacts, and execute controlled outbound submissions. Following submission, the system must monitor incoming communication channels, track operational pipeline state, alert the founder strictly for high-leverage human interactions, and learn from outcome data without demanding continuous founder supervision.

Key requirements and constraints:
1. Mailbox ingestion must be strictly read-only: zero mutation (send, reply, delete, archive, move, or mark-read).
2. Dual-track event ontologies (Employment vs Independent/Procurement) must be recognized without semantic collapse.
3. False opportunity correlation must be zero: ambiguous messages must never update a specific opportunity's authoritative state.
4. UNKNOWN != FALSE: absence of evidence is not evidence of absence; never fabricate intent, deadlines, or outcomes.
5. Inbound signals cannot silently clear `UNKNOWN_OUTCOME` or trigger automated retries; they create reconciliation candidates.
6. The learning/analytics loop must be strictly isolated from TruthGraph facts, claim validation, NEVER_CLAIM rules, and outbound action permissions.

## Decision

1. **Read-Only Provider Ingestion Boundary**:
   - `InboundMailTransport` defines a provider-neutral read-only interface (`fetch_messages`, `get_checkpoint`, `save_checkpoint`).
   - Implements `GmailReadOnlyAdapter` and `MockMailTransport` with cryptographic message hashing (`message_content_hash`).
   - Replay-safe cursor management prevents message loss and duplicate processing.

2. **Immutable Signal and Pipeline Event Store**:
   - `InboundMessageEvidence`: Raw immutable record capturing provider ID, sender, recipient, subject, headers, body, timestamp, and content hash.
   - `InboundSignal`: Derived atomic event capturing classified category, confidence, extracted entities, and extracted deadlines.
   - `PipelineEventLog`: Append-only event log. Current pipeline state is derived deterministically from accepted events via `PipelineStateSynchronizer`.

3. **Dual-Track Classification & Action-Required Engine**:
   - Classifies signals into canonical categories:
     - Employment: `APPLICATION_CONFIRMATION`, `REJECTION`, `RECRUITER_OUTREACH`, `ASSESSMENT`, `INTERVIEW_REQUEST`, `OFFER`, `INFORMATION_REQUEST`.
     - Independent/Procurement: `PROPOSAL_CONFIRMATION`, `CLIENT_OR_BUYER_RESPONSE`, `CLARIFICATION_REQUEST`, `SHORTLIST_OR_INVITATION`, `DISCOVERY_CALL_OR_MEETING_REQUEST`, `PROPOSAL_REJECTION`, `AWARD_OR_WIN`, `CONTRACT_PROGRESS`, `PROCUREMENT_AMENDMENT`, `PROCUREMENT_DEADLINE_CHANGE`.
     - Noise: `MARKETING`, `GENERIC_NON_ACTIONABLE_PLATFORM_NOTIFICATION`, `UNCLASSIFIED`.
   - High-priority signals (`Priority.HIGH` / `Priority.URGENT`) generate actionable `FounderNotificationRecord` items with idempotent notification keys (`sha256(workspace:candidate:signal_id:action_type)`).

4. **Multi-Stage Deterministic Correlation Engine**:
   - Prioritizes correlation:
     1. Explicit application/receipt reference ID.
     2. Provider thread ID linked to prior action.
     3. Exact ATS / opportunity source ID match.
     4. Strict multi-field deterministic match (organization + exact role title + temporal window).
     5. Ambiguous / unverified -> `CorrelationStatus.UNLINKED` / `REVIEW_REQUIRED`. Zero false links committed to pipeline state.

5. **Safe Learning Loop & Bounded Experiment Governance**:
   - Tracks conversion analytics across source, organization, role family, scoring bands, and template versions.
   - Strictly enforces read-only boundary over TruthGraph and Outbound Action Authority: optimizer outputs recommendations and versioned ranking weights, but CANNOT mutate assertions, claims, credentials, or submission permissions.

## Consequences

- Founder attention is preserved for interviews, recruiter negotiations, and client meetings.
- Complete operational traceability from inbound email bytes to pipeline state transitions.
- Robust protection against hallucinated deadlines, false opportunity links, and unauthorized mailbox side effects.
