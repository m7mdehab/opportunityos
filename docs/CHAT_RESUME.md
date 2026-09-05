# OpportunityOS Chat Resume

Purpose: boot a fresh ChatGPT/agent session without reconstructing OPOS history.

Last compacted: 2026-09-05, Africa/Cairo.

## Resume Command

A new chat may begin with:

`Resume OPOS from canonical state.`

The Owner/Overseer should then read `AGENTS.md`, `docs/AUTHORITY_INDEX.md`, this file, generated `docs/STATE.md`, inspect current GitHub `main` and any active branch/PR, then load only the active brief and task-relevant ADRs/evidence.

Cross-project procedure is defined by `m7mdehab/ai-engineering-control-plane`, using the locked `AI_ENGINEERING_OPERATING_SYSTEM_v2.0.md` baseline plus the current `AI_ENGINEERING_OPERATING_SYSTEM_v2.0.1_ADDENDUM.md`. The repository-only cold-boot acceptance contract is `FRESH_SESSION_ACCEPTANCE.md` in that control-plane repository.

Do not ask Mohammed to re-explain project history that can be recovered from the canonical repository layer. A stale ChatGPT Project snapshot is not authority; re-read the repositories.

## Project In One Paragraph

OpportunityOS is an autonomous opportunity-acquisition platform for MENA that covers employment and independent professional work, including freelance/consulting, contract, and procurement opportunities. Its core flow is `discover -> ingest -> qualify -> score -> truth-locked tailor -> prepare/fill/controlled-submit -> monitor outcomes -> learn safely`. The system is designed to save the founder time and increase access to remote work, freelance/client work, and other economic opportunities without fabricating founder claims or bypassing source/platform rules.

## Authority

- Founder/final product authority: Mohammed.
- Owner/Overseer: ChatGPT. Owns cross-project context continuity, architecture/product judgment, consequence classification, task briefing, Master selection, independent verification, and final PASS/NOT PASS closure.
- Master Agent: dynamically selected by task. Codex is preferred for architecture-sensitive/stateful/concurrency/provenance/submission-authority work when capacity permits; Gemini/Antigravity is strong high-volume/bounded/browser execution capacity; Copilot is secondary/mechanical capacity; Claude Code is also valid Master/reviewer capacity when selected for the task.
- Workers, independent auditors, and councils are evidence-producing/subordinate roles, not closure authority.

A role is not a model.

For state claims: runtime/live behavior where applicable > merged `origin/main` > explicitly active PR/branch > machine evidence > generated state > reports > chat memory.

For intent: latest Founder decision > Product Constitution/accepted ADR/PDR > current brief/roadmap > Master Plan > old reports/handoffs/chats.

For procedure: global control plane > local `AGENTS.md` > OPOS execution/permissions contracts > active brief.

## Truth Law

Never weaken these:

- `UNKNOWN != FALSE`;
- `ABSENT != INELIGIBLE`;
- material founder claims require evidence authority;
- planned credentials never become held;
- unsupported facts/commitments are omitted, marked uncertain, or paused;
- no weaker parallel generator may bypass the Truth Graph;
- source coverage is not permission;
- external side effects fail closed when authority is missing or outcome is uncertain.

See `docs/PRODUCT_CONSTITUTION.md` and accepted ADRs for full law.

## Current Verified Product State

Product-state snapshot on 2026-09-05 before the governance-only context integration:

`7e90eed48f1308d9cbeaa03f111e3dc206c6d26c`

Later governance-only commits may move `main`. Always re-read current `origin/main` and current PRs before treating that snapshot SHA as the repository head.

Generated state reports:

- last shipped: BRIEF-FR-005;
- active: BRIEF-FR-006;
- phase status: in progress;
- BRIEF-007 / Multi-Tenant Family Alpha blocked until Founder Web Alpha is live and validated.

The generated state says zero open acceptance items, but `reports/REPORT-FR-006.md` concludes `PASS_WITH_NOT_CLOSED`. Treat that as a state/report inconsistency to verify, not something to reconcile by assertion or hand-editing generated state.

## Current Active Brief - BRIEF-FR-006

Title: `Nothing Missed, Nothing Hidden, Nothing Ugly`.

This is the interrupted product brief to resume after repository/context boot is proven. Do not restart it from scratch.

The brief responded to real founder-use failures including generic uncertainty, missing work-mode/location clarity, duplicate cards, weak seniority semantics, and poor generated CV output.

Substantial work already on `main` includes:

- richer opportunity extraction;
- tenure/leadership-based seniority rather than title substring heuristics;
- proficiency-aware skills;
- broader title-family normalization;
- deterministic opportunity-family clustering;
- facets and full-text search;
- cards exposing work mode/location/remote scope;
- structured CV/document model;
- three ATS templates;
- DOCX/PDF generation;
- in-browser preview and unsupported-sentence visibility;
- artifact cache;
- founder-control/saved-view storage;
- expanded board discovery/source registry machinery;
- source-policy path repairs;
- truth-lock guard-neutralisation evidence.

## What Did Not Close

Current FR-006 report explicitly records material gaps:

- 36 boards versus a 300 target;
- zero new read-allowed sources producing rows in the product;
- work-mode extraction 52.2 percent versus 90 percent target;
- country-or-remote-scope 72.2 percent versus 85 percent target;
- title-family mapping 86.9 percent versus 95 percent target;
- source breadth is the dominant founder-facing limitation;
- two Playwright checks do not exercise the service-worker property they claim to test;
- live poll did not run in the recorded host-exhaustion attempt;
- several acceptance claims remain `NOT_CLOSED` or partial;
- `stale_postings` has a writer that is not yet invoked.

Do not make these disappear by relabeling the report, weakening targets, or treating a partial result as terminal PASS.

## Owner/Overseer Items From Current Report

Before definitive FR-006 closure:

1. resolve undefined matrix labels by real `req_id`, never invented mappings;
2. independently verify the truth-lock/guard-neutralisation mutation property reserved for Overseer checking;
3. determine from the brief's actual terminal contract whether remaining work receives a bounded closure pass or genuinely separable unmet breadth targets move into an explicit next brief;
4. make generated `STATE.md` coherent with the actual terminal verdict only through generator/source facts, never by hand editing.

A pre-existing Mandatory CI defect also exists around founder-readiness coverage, where unittest method identifiers are being surfaced as if they were founder opportunities. It predates the governance integration. Do not corrupt readiness data or weaken semantic coverage checks merely to green that gate. Treat it as an explicit engineering defect when BRIEF-FR-006 closure work resumes.

## Founder Value Priority

OPOS should optimize for real founder leverage:

- higher-quality remote/employment opportunity discovery;
- freelance/consulting/client/procurement opportunities;
- fewer duplicate/irrelevant cards;
- explainable fit;
- truthful tailored artifacts;
- less repetitive form/application work;
- safe operational follow-up;
- meaningful time saved.

Source-count growth that does not produce useful compliant opportunities is not success.

## External Action Safety

Preserve:

- `DRY_RUN` default;
- `ASSISTED` may fill/navigate/upload where permitted but not submit;
- `CONTROLLED_SUBMIT` only for explicitly graduated/authorized paths;
- Red/legal/sensitive/ambiguous answers pause unless exact founder-approved policy exists;
- kill switch immediately before side effect;
- CAPTCHA/MFA/bot challenge stop;
- no bypass services;
- durable atomic idempotency reservation;
- `UNKNOWN_OUTCOME` means no automatic retry;
- confirmation evidence required for success;
- duplicate submission tolerance is zero.

## Context Loading Rules

Default startup does NOT require the full `docs/MASTER_PLAN.md`, the 100k+ source registry, all reports, old Overseer handoff files, or old chat transcripts.

Root `CLAUDE.md`, `GEMINI.md`, and `.github/copilot-instructions.md` are small routing shims to `AGENTS.md`; they are not parallel policy sources.

Load deeper context only as required:

- full long-horizon plan: `docs/MASTER_PLAN.md`
- truth/product constitution: `docs/PRODUCT_CONSTITUTION.md`
- current architecture: `docs/ARCHITECTURE_CURRENT.md`
- current roadmap: `docs/ROADMAP_CURRENT.md`
- exact architecture decisions: `docs/adr/`
- active implementation contract: `briefs/BRIEF-FR-006.md`
- current gate narrative: `reports/REPORT-FR-006.md`
- detailed evidence: `reports/evidence/FR-006/`
- source policy/status only when source work requires it: `docs/SOURCE_REGISTRY.yaml`, `docs/SOURCE_EVIDENCE.md`
- execution mechanics: `docs/AGENT_EXECUTION_PROTOCOL.md`
- action permissions: `docs/AGENT_PERMISSIONS.yaml`

## Engineering Operating Rules

- repository/runtime truth outranks agent reports;
- generated state is never hand-edited;
- one branch per brief, isolated worktrees for writable parallel tasks;
- no agent self-approves high-consequence work;
- councils are targeted exceptions, not default process;
- change strategy after repeated failure instead of looping;
- respect measured host/concurrency limits;
- agents do every solvable task and surface only genuine founder-only blockers;
- once a brief is genuinely closed, freeze it absent concrete regression;
- use exact vocabulary: built, landed, verified, closed;
- never call a failing gate green;
- the control-plane pre-existing/unrelated-failure exception may be used only with exact evidence and only for a bounded recovery/governance path that does not mask high-consequence risk.

## Exact Resume Order

After this repository/context setup is proven, resume product execution as follows:

1. verify current `main`, open PRs, and current BRIEF-FR-006/report/evidence rather than trusting this snapshot blindly;
2. recover the interrupted FR-006 terminal contract and current unresolved ledger;
3. investigate and repair the pre-existing founder-readiness test/collector defect semantically if still present;
4. resolve the Owner-reserved FR-006 verification items above;
5. close FR-006 honestly against its contract, with exact CI/evidence and generated state reconciliation;
6. only then move to the next explicit brief/product phase.

Do not skip directly to BRIEF-007. It remains blocked until Founder Web Alpha is live and validated.

## Next Direction After FR-006

1. improve compliant productive source yield;
2. validate Founder Web Alpha on real daily use;
3. improve extraction only from real evidence, not pattern inflation;
4. strengthen the founder daily workflow and end-to-end opportunity-to-artifact path;
5. continue safe outbound and outcome-monitoring operations;
6. keep BRIEF-007 multi-tenant work blocked until Founder Web Alpha is live and validated.

## Founder-Only Boundaries

Agents execute everything available tools can safely do. Mohammed should only be required for genuine external boundaries such as interactive authentication/OAuth, inaccessible accounts/credentials that cannot be securely injected, payment, accepting binding terms, professional legal/accounting sign-off, human communication the system cannot perform, or product/business judgment explicitly reserved to him.

Do not hand back technical commands, configuration derivation, tests, reversible implementation choices, or repository changes merely because a human could do them.

## Secrets

Never store credential values, private founder data, application history, raw Truth Graph content, passwords, tokens, connection strings, or other sensitive operational data in this file or the public docs mirror.

Read credentials supplied for verification are used only through secure/approved access and are never echoed into canonical docs.

## Compaction Rule

Before moving to another chat:

1. record durable product/architecture decisions in ADR/PDR form;
2. update `ARCHITECTURE_CURRENT.md` only if architecture changed;
3. update `ROADMAP_CURRENT.md` only if priorities changed;
4. regenerate `docs/STATE.md` from repository facts;
5. replace this file with the compact current delta/next action;
6. do not copy history already preserved in reports/ADRs/briefs.

This file is a bootloader, not an archive.
