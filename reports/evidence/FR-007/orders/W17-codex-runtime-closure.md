# W17 — Codex: Hosted Runtime / Data Plane Closure Batch

## Mission

Execute a large, continuous FR-007 implementation batch on branch `work/fr007-codex-runtime-closure` and drive the zero-dollar Founder Alpha runtime as far toward terminal acceptance as the repository/provider boundaries allow.

Do not stop after the first defect or failed test. Repair, retest, and continue. Do not return ordinary executable work to the Founder. Produce one evidence-backed completion report when the batch reaches its natural terminal point.

## Governing authority

Read and obey, in order:

1. `AGENTS.md`
2. `docs/AUTHORITY_INDEX.md`
3. `docs/CHAT_RESUME.md`
4. `docs/STATE.md`
5. `docs/CI_EFFICIENCY_POLICY.md`
6. `briefs/BRIEF-FR-007.md`
7. `docs/adr/ADR-0023-zero-dollar-founder-runtime.md`
8. `docs/adr/ADR-0024-fixed-cv-portfolio-selection.md`
9. relevant current architecture/deployment/runtime docs and migrations

Current provider/runtime authority is ADR-0023, not older Azure/Render/private-Truth-Pack assumptions.

## Locked runtime facts

- Production/staging provider set: Supabase Free + Cloudflare + GitHub only.
- No Azure, Render, paid VPS/container service, trial/student credit, or billable add-on.
- No Founder PC/local PostgreSQL/local scheduler/local tunnel/local filesystem dependency.
- PostgreSQL/Supabase is canonical state.
- Supabase Auth is the Founder browser/session authority.
- Browser access is RLS/RPC/view/private-Storage-policy bounded.
- Heavy Python work runs as bounded disposable GitHub Actions jobs against durable Supabase state.
- Schedule truth remains in PostgreSQL; GitHub timing is execution capacity only.
- Canonical Truth Pack is repository-managed and hash-bound.
- Employment CVs are exactly the six immutable PDFs in private bucket `founder-cv-portfolio/2026/`; never synthesize or modify a CV.
- Generated artifacts use private `opportunity-artifacts` storage with canonical metadata in PostgreSQL.
- Fixed-CV and generated-artifact access must fail closed on integrity/auth failures.
- Truth-lock, source policy, idempotency, provenance, submission authority, and stop-on-403/429/CAPTCHA/MFA rules remain absolute.

## Existing live baseline already proven by Overseer

Treat these as established provider facts, not work to redo:

- Supabase project is healthy.
- migration head is `0009_hosted_founder_auth`.
- 26 public application tables have RLS enabled.
- exactly one confirmed Founder Auth user exists.
- all six fixed CV objects exist and authenticated SHA-256 verification passed.
- repository-managed canonical Truth Pack verification passed.
- Cloudflare account/token verification passed.
- protected GitHub environment `fr007-staging` contains the required target DB, storage, Cloudflare, Founder E2E, and backup encryption secrets.
- `OPOS_SOURCE_DB_URL` is intentionally absent until a real source-parity operation actually requires it.
- current zero-dollar readiness launcher passes end-to-end.

## Primary ownership

You own the backend/data-plane/runtime half of the remaining FR-007 closure. Avoid editing presentation-only frontend components unless required to preserve a stable contract. Antigravity owns Cloudflare deployment polish, browser/E2E/observability/soak UX-facing closure.

### A. Supabase-native interactive runtime

Remove the production requirement for a separate always-on FastAPI/`OPPORTUNITYOS_API_ORIGIN` service.

Preserve the existing UI/client contract where practical, but make normal Founder interactions work through Supabase-native boundaries:

- Supabase Auth session/JWT;
- RLS-protected views/tables;
- explicit SQL functions/RPCs for deliberate writes and complex reads;
- private Storage access for fixed CVs/generated artifacts;
- thin Cloudflare/Next edge route logic only where needed.

Implement the smallest portable architecture that satisfies ADR-0023. Do not move heavy Python domain logic into Cloudflare.

Required interactive capabilities include at least:

- auth/session identity;
- feed/list/pagination;
- search/filter/facets/saved views needed by current Founder UI;
- opportunity detail;
- hidden reasons / triage state needed by current UI;
- source health;
- asynchronous Poll Now enqueue/status;
- Truth status appropriate to repository-managed Truth Pack;
- private fixed-CV retrieval;
- private generated-artifact retrieval;
- any current Founder control surface required by A-16.

Prefer preserving same-origin `/api/*` semantics if that materially reduces frontend churn, but the upstream must no longer be an always-on paid Python API.

### B. Supabase schema/RPC/RLS/storage closure

Add repository-owned migrations for any functions/views/policies/helper mappings needed by the hosted Founder runtime.

Prove:

- only the authorized Founder can access Founder data;
- anonymous/authenticated-non-Founder access fails closed;
- service-role/database credentials never reach browser bundles;
- private Storage objects remain private;
- browser operations use JWT/RLS/RPC semantics rather than database passwords;
- generated artifact metadata remains canonical in PostgreSQL;
- exact fixed-CV bytes remain hash-bound.

Keep migrations reversible where practical and compatible with current `0009_hosted_founder_auth` live state.

### C. Durable job execution and scheduling

Finish the zero-dollar compute path:

- PostgreSQL queue/schedule state remains canonical;
- due work is enqueued idempotently;
- bounded GitHub Actions runners drain persisted jobs using leases/fencing/retry/dead-letter semantics;
- delayed/terminated runners leave recoverable state;
- source cadence/cooldown/next-due survives restarts;
- no all-source warm-up storm;
- Poll Now returns immediately and never waits for acquisition/evaluation;
- execution cadence respects CI cost policy and the hard $0 envelope.

Use scheduled/dispatch GitHub Actions only as execution capacity. If Supabase Cron is used, it may only enqueue/advance durable state; do not make an ephemeral scheduler authoritative.

### D. Hosted data-plane proof repair

Audit `.github/workflows/fr007-hosted-data-plane-proof.yml` and `scripts/hosted_data_plane_proof.py`.

The target-only PRECHECK path must not require `OPOS_SOURCE_DB_URL` merely to prove the already-live Supabase target. Source credentials become mandatory only for true source-to-target migration/parity modes.

Keep fail-closed behavior and secret redaction.

If an actual source database is discoverable/accessible in the environment, execute the real parity path and close what can be proven. If source state is genuinely inaccessible because it lives only on Founder-owned infrastructure, record the exact minimal external dependency rather than inventing evidence.

### E. Encrypted logical backup / restore implementation

Implement the ADR-0023 backup contract, not the older plaintext-only state:

- logical PostgreSQL backup from GitHub Actions;
- encryption before any GitHub artifact persistence;
- `BACKUP_ENCRYPTION_KEY` consumed only from protected environment;
- authenticated encryption with integrity protection;
- no plaintext Founder backup uploaded as an artifact;
- size cap and bounded retention;
- sanitized manifest/heartbeat;
- decrypt + checksum + fresh restore drill tooling;
- fail closed if encryption/key/quota requirements are not met.

The existing 64-hex-character secret is a 32-byte key; support that contract explicitly and validate it without logging it.

### F. Artifact durability

Complete `opportunity-artifacts` hosted storage integration:

- generated cover letters/application artifacts remain Truth-locked;
- metadata binds opportunity/truth-pack/template/validator/generation version/hash;
- object bytes live privately in Supabase Storage;
- retrieval after process restart succeeds;
- fixed CVs are selected from the six locked files only and never regenerated;
- missing/hash-mismatched fixed CV blocks the application path.

### G. Tests/evidence

Add deterministic unit/integration tests for every new boundary.

Where live provider credentials are unavailable inside your local executor, use repository tests plus workflow-ready live proof scripts; do not fake provider success.

Exercise narrow tests continuously, then the full applicable repository suite before handoff.

Target acceptance evidence primarily for A-1, A-3, A-7, A-8, A-9, A-10, A-11, A-12 and A-15, with supporting evidence for cross-cutting criteria.

## Parallelism inside this batch

Use internal parallel worktrees/subagents where safe. Good parallel partitions include:

- Supabase RPC/RLS/migrations;
- hosted API/edge data adapter;
- job-drain/scheduler workflows;
- backup encryption/restore;
- artifact storage;
- tests/evidence.

Do not parallel-edit shared contracts before stabilizing them.

## Forbidden shortcuts

- no paid provider;
- no Founder-PC runtime dependency;
- no public/private bucket relaxation;
- no service-role key in browser;
- no truth/CV fabrication;
- no weakening tests to make them pass;
- no calling repository/disposable proof “live acceptance”;
- no source action outside committed permission;
- no manual hand-edit of generated `docs/STATE.md`.

## Handoff contract

Before stopping:

1. run narrow tests and all applicable full suites;
2. run repository guard/state/mirror checks locally where possible;
3. update architecture/deployment/runbook docs only for facts that actually changed;
4. write `reports/evidence/FR-007/W17_CODEX_RUNTIME_CLOSURE.md` containing:
   - exact commits/files;
   - tests and results;
   - live proofs actually executed;
   - A0-A17 impact by criterion;
   - remaining genuine blockers;
   - exact provider actions, if any, that only the Overseer can execute;
5. commit all work on `work/fr007-codex-runtime-closure`;
6. return one concise final summary to the Overseer. Do not self-declare FR-007 closed.
