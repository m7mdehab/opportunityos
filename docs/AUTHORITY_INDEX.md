# OpportunityOS Authority Index

This is the canonical startup map for a new session. It exists to prevent repeated context reconstruction and to keep current truth separate from historical narrative.

## Three Kinds of Truth

### Intent truth

For what OPOS is supposed to do, use this order:

1. latest explicit Founder decision;
2. `docs/PRODUCT_CONSTITUTION.md` and accepted ADR/PDR decisions;
3. current active brief and `docs/ROADMAP_CURRENT.md`;
4. `docs/MASTER_PLAN.md`;
5. older handoffs, reports, and chats.

A phase may not silently override the Product Constitution. A constitutional change requires an explicit Founder decision and the repository's ADR/PDR process.

### State truth

For what actually exists now, use this order:

1. current runtime/database behavior when the claim concerns live operation;
2. merged `origin/main`;
3. explicitly active branch/PR;
4. deterministic tests, CI, generated artifacts, persisted evidence, and measured runs;
5. generated `docs/STATE.md`;
6. phase report/handoff prose;
7. agent summaries or chat memory.

A report can be wrong. Generated state can be premature. Repository/runtime evidence wins.

### Procedure truth

For how work must be performed, use this order:

1. cross-project AI Engineering Operating System v2.0 plus the current `AI_ENGINEERING_OPERATING_SYSTEM_v2.0.1_ADDENDUM.md` in `m7mdehab/ai-engineering-control-plane`;
2. repository `AGENTS.md`;
3. `docs/AGENT_EXECUTION_PROTOCOL.md` and `docs/AGENT_PERMISSIONS.yaml`;
4. accepted ADRs governing the subsystem;
5. active brief and its acceptance criteria.

## Startup Read Order

For a normal fresh chat or Master session:

1. `AGENTS.md`
2. this `docs/AUTHORITY_INDEX.md`
3. `docs/CHAT_RESUME.md`
4. generated `docs/STATE.md`
5. current `origin/main` and any active PR/branch
6. active brief
7. relevant ADRs and exact subsystem tests/evidence
8. only the task-relevant sections of `docs/MASTER_PLAN.md`

Do not ingest the entire 100k+ source registry, full master plan, old overseer handoff, or all phase reports unless the task genuinely requires them.

Root provider files such as `CLAUDE.md`, `GEMINI.md`, and `.github/copilot-instructions.md` are routing shims to `AGENTS.md`, not independent governance or deep context.

## Canonical Current Documents

- `docs/PRODUCT_CONSTITUTION.md` - non-negotiable truth, human-judgment, source, privacy, and side-effect rules
- `docs/STATE.md` - generated operational state; never hand-edit
- `docs/ARCHITECTURE_CURRENT.md` - compact current architecture
- `docs/ROADMAP_CURRENT.md` - compact phase/priority map
- `docs/CHAT_RESUME.md` - compact new-chat bootloader
- `docs/AGENT_EXECUTION_PROTOCOL.md` - brief execution mechanics
- `docs/AGENT_PERMISSIONS.yaml` - action permissions
- `docs/adr/` - accepted consequential decisions
- `briefs/` - active and historical implementation contracts
- `reports/` - gate reports and evidence

## Deep References

Load only when relevant:

- `docs/MASTER_PLAN.md` - full long-horizon plan and requirement map
- `docs/SOURCE_REGISTRY.yaml` - detailed source policy/status registry
- `docs/SOURCE_EVIDENCE.md` - source evidence
- `docs/INTEROP.md` - provider/tool interoperability
- old `OPOS_OVERSEER_HANDOFF_CURRENT.md` copies outside the repo - historical migration evidence, not current state
- detailed phase evidence under `reports/evidence/`

## Open-World Truth Rules

These are foundational and must survive every phase:

- `UNKNOWN != FALSE`;
- `ABSENT != INELIGIBLE`;
- missing evidence does not become a founder conflict;
- planned credentials do not become held credentials;
- unsupported material claims are omitted, marked uncertain, or paused according to policy;
- every material generated claim remains bound to the Truth Graph/EvidenceClaim authority.

## External-Action Authority

Coverage is not permission.

Discovery, preparation, browser fill, submission, API action, manual-only, and prohibited states remain distinct. `CONTROLLED_SUBMIT` is never the default. Unknown policy fails closed.

CAPTCHA, MFA, anti-bot, account verification, or uncertain side-effect outcome never becomes an invitation to bypass or retry blindly.

## Conflict Handling

When sources disagree:

1. classify the disagreement as intent, state, or procedure;
2. apply the corresponding ladder above;
3. inspect the actual code/evidence before trusting a report label;
4. do not silently reconcile a substantive conflict;
5. record durable resolution in an ADR/PDR where architecture/product law changes;
6. regenerate `docs/STATE.md` only from its generator after underlying facts are corrected.

## Context Budget

`AUTHORITY_INDEX.md`, `CHAT_RESUME.md`, `STATE.md`, and the active brief should usually be enough to begin work.

Compact files point to deep evidence. They do not copy it.

A fresh session must satisfy the control-plane `FRESH_SESSION_ACCEPTANCE.md` using canonical repositories alone. If it needs the full master plan, full source registry, all reports, or old chat history merely to become oriented, the boot layer has failed.
