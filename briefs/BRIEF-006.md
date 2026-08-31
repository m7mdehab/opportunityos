# BRIEF-006 — Operational Autonomy, Feedback Loops & Production Pipeline

**Terminal gate:** Complete, deterministic operational autonomy subsystem with read-only inbound message ingestion, immutable signal/event models, dual-track response classification (employment & independent/procurement), zero-wrong-opportunity correlation engine, evidence-backed pipeline event store & derived state synchronization, priority & action-required notification engine with deadline extraction, production polling & checkpoint orchestrator with replayability, dual-track outcome analytics with uncertainty-aware attribution, safe versioned learning & optimization layer with strict truth/submission immutability, synthetic gold & adversarial fixtures, full test suite with 100% high-priority recall and 0 wrong-opportunity correlation, ADR-0011, and independent blinded audit PASS.

## Transactional execution

Maintain an internal unresolved-task ledger and dependency DAG. Do not return while an available agent or tool can execute an unresolved task; repair defects and rerun invalidated evidence automatically.

## Capability preflight

Map every logical role to a capability exposed by the execution harness before starting. An approved separate model, tool, or session may satisfy an independence requirement; record the planned handoff and immutable evidence.

```yaml
phase_id: "BRIEF-006"
objective: "Implement the inbound message ingestion, response classification, opportunity correlation, pipeline state synchronization, priority notification engine, production orchestrator, outcome analytics, and safe learning loop subsystem."
why_now: "With outbound execution operational (BRIEF-005), OpportunityOS requires closed-loop operational autonomy to ingest inbound responses, track pipeline progression, alert the founder only on high-value human interactions, measure conversion performance, and safely optimize strategies without manual founder bookkeeping."
user_value:
  founder_employment: "Automatically tracks application confirmations, rejections, recruiter outreach, assessments, interview invitations, and offers, surfacing urgent action items while processing routine updates silently."
  founder_independent_work: "Automatically tracks proposal confirmations, client clarifications, shortlists, discovery calls, rejections, and contract awards across freelance and procurement tracks."
non_negotiables:
  - "Mailbox operations are strictly READ-ONLY: zero send, reply, delete, archive, move, or mark-read operations."
  - "Zero false correlation on adversarial opportunity sets."
  - "100% recall on high-priority actionable signals (interviews, recruiter messages, assessments, client clarifications, offers, awards)."
  - "Zero duplicate notifications on message replay or repeated polling."
  - "UNKNOWN != FALSE: absence of evidence is not evidence of absence; never fabricate facts, intent, or deadlines."
  - "Learning loop is strictly governed: zero modification of TruthGraph facts, claim validation, NEVER_CLAIM rules, or outbound submission permissions."
  - "BRIEF-005 UNKNOWN_OUTCOME safety remains frozen: inbound signals create reconciliation candidates rather than silently unfreezing retries."
explicitly_out_of_scope:
  - "Multi-tenant / family alpha (reserved for Phase 6)."
  - "Autonomous sending of email replies or calendar booking."
  - "Bypassing CAPTCHA, MFA, or interactive human authentication."
  - "Autonomous acceptance of job offers, price negotiations, or commercial contracts."
budget_cap: "0 USD (local execution harness)"
concurrency_cap: "4 parallel worktrees/subagents"
required_acceptance_metrics:
  high_priority_signal_recall: 1.0
  wrong_opportunity_correlation_rate: 0.0
  duplicate_inbound_event_count: 0
  duplicate_action_notification_count: 0
  mailbox_mutating_operations_count: 0
  unsupported_high_impact_transitions: 0
  truth_rule_mutations_by_learning: 0
  frozen_brief_regressions: 0
required_deliverables:
  - "briefs/BRIEF-006.md"
  - "inbox/ models, ingestion, classification, correlation, pipeline, notifications, orchestrator, analytics, learning, fixtures, test suites"
  - "ADR-0011 documenting operational autonomy, response detection, and safe learning loops"
  - "reports/REPORT-006.md"
  - "docs/STATE.md"
```
