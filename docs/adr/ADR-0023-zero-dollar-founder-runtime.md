# ADR-0023 — Zero-Dollar Founder Runtime on Supabase, Cloudflare, and GitHub

- **Status:** Accepted
- **Date:** 2026-09-19
- **Supersedes:** the compute-provider, GitHub-scheduler, backup-destination, and cost assumptions in ADR-0022
- **Related:** BRIEF-FR-007, ADR-0022, ADR-0012, ADR-0013

## Context

The Founder has locked a stricter runtime constraint than the earlier FR-007 plan assumed:

> OpportunityOS Founder Alpha must run using resources already owned or already connected, with **zero monetary spend under every circumstance**.

The approved resource set is:

- Founder/operator;
- ChatGPT / Overseer;
- Codex and Antigravity implementation capacity;
- GitHub Pro account and the existing OpportunityOS repository;
- existing Cloudflare account/domain;
- existing Supabase account/project.

Azure, student credits, temporary credits, paid compute, or any additional provider subscription are not part of the approved architecture.

The earlier preferred Azure Container Apps target therefore no longer satisfies Founder intent even when credits would reduce net out-of-pocket cost to zero. Gross provider charge must also remain zero.

## Decision

### 1. Hard zero-dollar invariant

FR-007 production/staging architecture may use only provider features whose selected tier has a **gross provider charge of $0.00** for the declared usage envelope.

Temporary credits, student credits, trial balances, prepaid balances, or reimbursements do not qualify as free.

No component may silently upgrade, overflow into a paid tier, or create a billable add-on.

If a free quota is exhausted, OpportunityOS fails closed, degrades non-critical behavior, or pauses that subsystem. It does not incur spend.

The cost gate must therefore enforce:

- total gross provider charge = $0.00;
- total founder out-of-pocket charge = $0.00;
- no paid-plan dependency;
- no student/trial-credit dependency;
- no unapproved billable resource;
- documented free-tier quota headroom.

### 2. Supabase is the managed application platform

Supabase Free remains the durable application/data plane:

- PostgreSQL remains canonical state;
- Supabase Auth becomes the preferred browser/session authority for the single Founder;
- RLS remains mandatory;
- private Storage holds the Founder Truth Pack and generated artifacts;
- PostgreSQL functions/RPCs expose only deliberate browser operations;
- Supabase Cron / pg_cron may enqueue due work and maintenance;
- Supabase Edge Functions may be used only for thin privileged operations that cannot safely be expressed through authenticated RLS/RPC.

Core tables remain portable PostgreSQL and repository-owned migrations remain schema authority.

Browser clients must never receive database passwords, service-role credentials, private Truth Pack bytes, or unrestricted table access.

### 3. Cloudflare is the public web/edge runtime

The existing Cloudflare account/domain owns:

- DNS and TLS;
- the canonical Founder Alpha hostname;
- static web assets;
- the lightweight Worker/edge layer when required.

The preferred production web posture is static/client-rendered where practical so ordinary static delivery does not consume Worker CPU.

A Cloudflare Worker may perform thin routing/headers/edge duties, but it must not become a Python-domain compute replacement.

Normal feed/search/filter/detail behavior should use authenticated Supabase RPC/view access rather than an always-on FastAPI service.

### 4. There is no always-on paid Python compute

The previous Azure API/worker/scheduler/migrate deployment is removed from the active runtime plan.

FastAPI and the OCI image remain valuable portability/test assets but are no longer production infrastructure requirements for Founder Alpha.

Interactive production correctness must not require an always-on Python process.

### 5. Heavy Python work runs as bounded GitHub Actions jobs

The existing OpportunityOS Python engine remains authoritative for:

- source polling/normalization;
- evaluation/matching;
- projection maintenance where Python is required;
- artifact generation;
- bounded maintenance/backfill;
- logical backup/restore verification.

For Founder Alpha, standard GitHub-hosted Actions runners are the approved zero-dollar Python execution surface.

All correctness state remains in Supabase. A GitHub runner is disposable execution capacity only.

A job must be:

- bounded;
- idempotent;
- retry-safe under existing source/action policy;
- lease/fencing aware;
- resumable from PostgreSQL state;
- safe to lose mid-run.

No secret is stored in workflow source.

### 6. Scheduling is durable before compute dispatch

Source cadence/cooldown/next-due state remains in PostgreSQL.

Supabase Cron / pg_cron is the preferred scheduler for inserting due work because scheduling state remains adjacent to the database and does not depend on a Founder PC.

GitHub Actions may also use scheduled triggers or workflow dispatch to drain persisted work. Under this zero-dollar Founder-Alpha architecture, scheduled Actions are permitted as production execution capacity, but never as the source of truth for schedule state.

If a scheduled runner is delayed, jobs remain durably queued and the feed remains available.

### 7. Poll Now remains asynchronous

Poll Now performs only a durable authenticated request/enqueue operation and returns immediately.

It may:

- call an authenticated Supabase RPC;
- enqueue due/explicit permitted work;
- optionally trigger a GitHub worker dispatch through a server-side credential path.

It never waits for source acquisition/evaluation and never requires the Founder PC.

### 8. Auth and browser data access use Supabase-native boundaries

The single Founder authenticates through Supabase Auth.

Public signup remains disabled for Founder Alpha.

Browser operations use:

- Supabase authenticated JWT/session;
- explicit RLS;
- dedicated views/RPCs;
- private Storage policies for Founder artifact reads.

Private canonical tables may remain direct-browser deny-all.

A small Founder identity mapping/helper may be added so RPCs and Storage policies can prove that the authenticated user is the one authorized Founder.

The W15 custom durable-session implementation remains repository history/portable fallback but is not required to be the production web-session mechanism under this ADR.

### 9. Truth Pack and artifacts remain private in Supabase Storage

The Founder Truth Pack is stored in the private `founder-truth-pack` bucket.

Heavy jobs retrieve it server-side and validate the committed SHA-256/version contract before using it.

Generated artifact bodies are stored in the private `opportunity-artifacts` bucket with canonical metadata retained in PostgreSQL.

Browser artifact retrieval is Founder-authenticated and least-privilege.

### 10. Backups use encrypted GitHub evidence, not a paid storage provider

Supabase Free does not provide the paid automatic-backup/PITR guarantees assumed by a paid tier.

FR-007 therefore creates logical PostgreSQL backups from GitHub Actions, encrypts them before persistence, and stores only encrypted backup artifacts through the existing GitHub account within its free/included storage envelope.

The encryption key remains a protected secret and never enters Git/artifacts.

Backup workflows must:

- cap archive size;
- use short bounded retention;
- prune/replace old evidence;
- refuse execution that would require paid storage;
- emit a heartbeat;
- prove a fresh restore before A-12 passes.

This is an independent-provider copy because GitHub is separate from Supabase.

### 11. Monitoring remains external and zero-dollar

GitHub Actions performs external monitoring of:

- Cloudflare Founder Alpha URL;
- Supabase/database connectivity;
- queue state;
- scheduler state;
- source freshness;
- backup heartbeat.

Incident lifecycle remains in GitHub Issues.

Soak snapshots remain durable evidence artifacts with bounded retention.

### 12. Portability remains mandatory

The zero-dollar runtime is an economics decision, not a domain rewrite.

Maintain:

- repository-owned Alembic migrations;
- exportable PostgreSQL;
- provider-neutral Python domain code;
- optional OCI packaging;
- private artifact inventory/export;
- tested backup/restore;
- documented provider-exit procedure.

A future paid runtime may replace GitHub Actions compute without rewriting source adapters, matching, Truth Pack, queue semantics, or canonical state.

## Zero-Dollar Provider Envelope

The active Founder-Alpha provider set is exactly:

1. **Supabase Free**
2. **Cloudflare Free / already-owned domain**
3. **GitHub existing account using standard runners under the repository's applicable no-charge allowance**

Azure is explicitly excluded.

No other production provider may be introduced without a new Founder decision and ADR.

## Consequences

### Positive

- no Azure account/subscription/resource group/service principal is required;
- no student-credit economics;
- no idle paid compute;
- no new provider account is required;
- Founder PC remains outside the production dependency graph;
- durable application state stays in managed PostgreSQL;
- heavy existing Python domain code can be reused rather than ported wholesale to JavaScript;
- web availability is decoupled from background worker availability.

### Trade-offs

- GitHub-hosted worker start time is less deterministic than a continuously running worker;
- background throughput is bounded by Actions/job concurrency and provider policies;
- Supabase Free quotas and inactivity behavior must be monitored;
- Cloudflare Workers Free CPU is intentionally unsuitable for heavy application logic;
- Supabase Free lacks automatic production backups/PITR, so encrypted logical backup/restore discipline is mandatory;
- if Founder Alpha outgrows the permanent free allowances, FR-007 does not silently scale into paid infrastructure; a new explicit architecture decision is required.

## Rejected

- **Azure Container Apps under student credit:** rejected because gross provider spend is non-zero and the Founder requires permanent $0 infrastructure.
- **Any paid VPS/container service:** rejected for the same reason.
- **Cloudflare Worker as a Python-domain monolith:** rejected because Worker Free CPU is intentionally constrained and the existing Python domain engine should not be rewritten merely to fit edge CPU limits.
- **Founder PC as production worker:** rejected because FR-007 exists to remove that dependency.
- **Automatic paid Supabase backup/PITR/add-ons:** rejected under the zero-dollar constraint.

## Exit strategy

If a future Founder decision permits paid compute, the persisted queue and provider-neutral Python engine may move to any compatible worker/container platform. The zero-dollar architecture must not create a migration trap.

This ADR changes infrastructure/runtime authority only. It does not weaken truth-lock, provenance, source policy, action authority, idempotency, or single-Founder tenancy.
