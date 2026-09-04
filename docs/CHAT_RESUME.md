# OpportunityOS Chat Resume

Purpose: boot a fresh ChatGPT/agent session without reconstructing OPOS history.

Last compacted: 2026-09-05, Africa/Cairo.

## Resume Command

A new chat may begin with:

`Resume OPOS from canonical state.`

The Owner/Overseer should then read `AGENTS.md`, `docs/AUTHORITY_INDEX.md`, this file, generated `docs/STATE.md`, inspect current GitHub `main` and any active branch/PR, then load only the active brief and task-relevant ADRs/evidence.

Do not ask the founder to re-explain project history that can be recovered from the canonical repository layer.

## Project In One Paragraph

OpportunityOS is an autonomous opportunity-acquisition platform for MENA that covers employment and independent professional work, including freelance/consulting, contract, and procurement opportunities. Its core flow is `discover -> ingest -> qualify -> score -> truth-locked tailor -> prepare/fill/controlled-submit -> monitor outcomes -> learn safely`. The system is designed to save the founder time and increase access to remote work, freelance/client work, and other economic opportunities without fabricating founder claims or bypassing source/platform rules.

## Authority

- Founder/final product authority: the founder.
- Owner/Overseer: ChatGPT. Owns context, architecture judgment, task briefing, independent verification, and final PASS/NOT PASS closure.
- Master Agent: dynamically selected by task. Codex is preferred for architecture-sensitive/stateful/concurrency/provenance/submission-authority work when capacity permits; Gemini/Antigravity is strong high-volume/bounded/browser execution capacity; Copilot is secondary/mechanical capacity.
- Independent auditors/councils are evidence-producing roles, not closure authority.

A role is not a model.

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

## Current Verified Repository State

Snapshot `main` on 2026-09-05:

`7e90eed48f1308d9cbeaa03f111e3dc206c6d26c`

Generated state reports:

- last shipped: BRIEF-FR-005;
- active: BRIEF-FR-006;
- phase status: in progress;
- BRIEF-007 / Multi-Tenant Family Alpha blocked until Founder Web Alpha is live and validated.

There are no open PRs at this snapshot.

The generated state says zero open acceptance items, but `reports/REPORT-FR-006.md` concludes `PASS_WITH_NOT_CLOSED`. Treat that as a state/report inconsistency to verify, not something to reconcile by assertion.

## Current Active Brief - BRIEF-FR-006

Title: `Nothing Missed, Nothing Hidden, Nothing Ugly`.

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

Do not make these disappear by relabeling the report or editing targets.

## Owner/Overseer Items From Current Report

Before definitive FR-006 closure:

1. resolve undefined matrix labels by real `req_id`, never invented mappings;
2. independently verify the truth-lock/guard-neutralisation mutation property reserved for Overseer checking;
3. reconcile whether the brief should receive a bounded closure pass or whether separable unmet breadth targets belong in the next explicit brief;
4. make generated `STATE.md` coherent with the actual terminal verdict only through the generator/source facts, never by hand editing.

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

Default startup does NOT require the full `docs/MASTER_PLAN.md`, the 100k+ source registry, all reports, or old Overseer handoff files.

Load deeper context only as required:

- full long-horizon plan: `docs/MASTER_PLAN.md`
- truth/product constitution: `docs/PRODUCT_CONSTITUTION.md`
- exact architecture decisions: `docs/adr/`
- active implementation contract: `briefs/BRIEF-FR-006.md`
- current gate narrative: `reports/REPORT-FR-006.md`
- detailed evidence: `reports/evidence/FR-006/`
- source policy/status: `docs/SOURCE_REGISTRY.yaml`, `docs/SOURCE_EVIDENCE.md`
- execution mechanics: `docs/AGENT_EXECUTION_PROTOCOL.md`

## Engineering Operating Rules

- repository/runtime truth outranks agent reports;
- generated state is never hand-edited;
- one branch per brief, isolated worktrees for writable parallel tasks;
- no agent self-approves high-consequence work;
- councils are targeted exceptions, not default process;
- change strategy after repeated failure instead of looping;
- respect measured host/concurrency limits;
- agents do every solvable task and surface only genuine founder-only blockers;
- once a brief is genuinely closed, freeze it absent concrete regression.

## Next Direction After FR-006

1. improve compliant productive source yield;
2. validate Founder Web Alpha on real daily use;
3. improve extraction only from real evidence, not pattern inflation;
4. strengthen the founder daily workflow and end-to-end opportunity-to-artifact path;
5. continue safe outbound and outcome-monitoring operations;
6. keep BRIEF-007 multi-tenant work blocked until Founder Web Alpha is live and validated.

## Secrets

Never store credential values, private founder data, application history, or raw Truth Graph content in this file or the public docs mirror.

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
