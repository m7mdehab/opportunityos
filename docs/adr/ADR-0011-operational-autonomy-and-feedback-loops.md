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
3. False opportunity correlation must be zero: ambiguous messages and multi-reference quoted threads must never update a specific opportunity's authoritative state.
4. Inbound evidence, pipeline events, notifications, checkpoints, and reconciliation records must be durably stored in SQLite (`DurableInboxStore`), surviving process restarts and crash interruptions.
5. Signal, event, and notification identities must be deterministically derived from SHA256 hashes of immutable evidence and classification identities rather than random UUIDs.
6. UNKNOWN != FALSE: absence of evidence is not evidence of absence; never fabricate intent, deadlines, outcomes, or zero-event pipeline confirmations.
7. Inbound signals cannot silently clear `UNKNOWN_OUTCOME` or trigger automated retries; they create durable reconciliation candidate records.
8. Conversion analytics must derive application denominators strictly from real outbound submissions, not bare discovered opportunities, and explicitly flag small sample sizes ($N < 5$).
9. The learning/analytics loop must be strictly isolated from TruthGraph facts, claim validation, NEVER_CLAIM rules, and outbound action permissions.

## Decision

1. **Durable Local SQLite Persistence (`inbox/persistence.py`)**:
   - `DurableInboxStore` manages atomic, process-durable tables: `inbound_evidence`, `pipeline_events`, `founder_notifications`, `inbox_checkpoints`, and `reconciliation_records`.
   - Uses `INSERT OR IGNORE` over deterministic cryptographic primary keys to guarantee absolute idempotency across restarts.

2. **Read-Only Provider Ingestion Boundary (`inbox/ingestion.py`)**:
   - `InboundMailTransport` defines a provider-neutral read-only interface (`fetch_messages`).
   - Implements `GmailReadOnlyAdapter` supporting executable read-only message listing, pagination tokens, and MIME header/body extraction.
   - Any mutating operation (`send_message`, `delete_message`, `mark_read`, `archive_message`) strictly raises `PermissionError`.

3. **Deterministic Stable Signal & Notification Identity (`inbox/classifier.py`, `inbox/notifications.py`)**:
   - Signal ID: `sha256(message_content_hash:category:track:version)`.
   - Event ID: `sha256(signal_id:opportunity_id)`.
   - Notification Key: `sha256(workspace:candidate_id:signal_id:category)`.
   - Event chronology flows strictly from message source `received_at`.

4. **Multi-Stage Deterministic Correlation Engine (`inbox/correlation.py`)**:
   - Matches strictly by:
     1. Single explicit reference / receipt ID.
     2. Persisted provider thread ID link.
     3. Exact source opportunity ID.
     4. Unique multi-field match (Org + exact Title).
   - Any multi-reference or multi-opportunity ambiguity strictly fails closed to `CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE` with `is_authoritative=False`.

5. **Append-Only Pipeline Event Store & Zero-Event Safety (`inbox/pipeline.py`)**:
   - Pipeline state is derived by replaying events sorted by source timestamp `occurred_at`.
   - Replaying zero events returns `OpportunityStage.NO_EVENTS` with `last_signal_category=None`.

6. **Outbound Ledger Reconciliation Safety (`inbox/orchestrator.py`)**:
   - When an inbound confirmation matches an outbound action in `ActionStatus.UNKNOWN_OUTCOME`, the status is NOT mutated. A durable `reconciliation_record` is created for founder resolution, preventing automated retries.

7. **Real-Denominator Outcome Analytics & Safe Learning Loop (`inbox/analytics.py`, `inbox/learning.py`)**:
   - Denominator derives strictly from confirmed/submitted outbound actions. Missing outcomes remain explicitly pending.
   - `SafeLearningEngine` generates bounded recommendations only for $N \ge 5$ and raises `PermissionError` on any attempt to mutate truth or permissions.

## Consequences

- Complete process-durable operational loop immune to crashes and restarts.
- Zero duplicate founder alerts, zero false correlations, and zero mailbox side effects.
- Truthful conversion analytics and strictly governed optimization.
