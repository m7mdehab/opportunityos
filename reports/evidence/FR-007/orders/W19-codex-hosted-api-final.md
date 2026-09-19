# W19 — Codex Final Hosted API / Data Bootstrap Closure

## Mission

Execute the final architecture-sensitive FR-007 runtime batch on branch `work/fr007-codex-hosted-api-final`.

This branch starts from the Overseer integration branch and already contains W17/W17-R1 plus imported Antigravity reliability/observability work. Your job is to make the actual hosted Founder web runtime function correctly on Supabase + Cloudflare + GitHub with **no always-on FastAPI/API host**.

Do not stop at the first defect. Inspect, implement, test, repair, and continue until the batch reaches a genuine terminal point. Do not self-declare FR-007 closed.

## Governing authority

Read:
1. `AGENTS.md`
2. `docs/AUTHORITY_INDEX.md`
3. `docs/CHAT_RESUME.md`
4. `docs/STATE.md`
5. `docs/CI_EFFICIENCY_POLICY.md`
6. `briefs/BRIEF-FR-007.md`
7. `docs/adr/ADR-0023-zero-dollar-founder-runtime.md`
8. `docs/adr/ADR-0024-fixed-cv-portfolio-selection.md`
9. W17/W17-R1 evidence and current implementation.

## Live provider facts from Overseer

The real Supabase staging project currently has:
- migration head `0009_hosted_founder_auth`;
- exactly one confirmed Founder Auth user;
- 26 public app tables with RLS enabled;
- **0 opportunities, 0 feed_projection rows, 0 source_schedules, 0 worker_jobs, 0 artifact_cache rows**;
- six final fixed CVs privately stored in `founder-cv-portfolio/2026/`, already hash-verified;
- canonical Truth Pack is repository-managed and hash-bound;
- protected GitHub environment `fr007-staging` has target DB, storage service key, Cloudflare, Founder E2E, and backup key secrets;
- public Supabase project URL and publishable key are provider-safe configuration, not privileged secrets.

The live database being empty matters: the hosted path must include a bounded, zero-dollar bootstrap/execution path that can create durable source schedules, enqueue due work, drain jobs, and populate the feed without a Founder PC.

## Independent Overseer findings you MUST resolve

### 1. Existing W17 direct-browser helper is incomplete

Current `web/lib/supabase/browser.ts` is not acceptable as the final hosted path:
- it stores access + refresh tokens in localStorage;
- list `total` is only the current page length, breaking pagination;
- Poll Now maps the RPC TABLE response into the wrong `PollNowResponse` shape;
- detail, truth, source health, dashboard, facets, artifacts, feedback/actions and several other client calls still fall back to the dead legacy `/api/*` route.

Do not count this as a working hosted runtime merely because build/type checks pass.

### 2. Existing cloud API route is still not a complete hosted API contract

The final architecture should preserve the current same-origin client contract where practical, but the edge route must be truly Supabase-backed when `OPPORTUNITYOS_API_ORIGIN` is absent.

Preferred final pattern:
- Next/Cloudflare same-origin `/api/*` adapter;
- Supabase Auth email/password login;
- HTTP-only secure cookies for access/refresh tokens;
- refresh access tokens safely when expired;
- PostgREST/RPC/Storage using the Founder JWT;
- no service-role/database password in browser or Worker config;
- no localStorage auth token requirement;
- local FastAPI fallback only for local development.

A direct-browser design is acceptable only if it provides equivalent security and the entire current hosted contract. Do not split the app between two inconsistent auth models.

### 3. Current UI contract must actually work

Hosted A-16 requires the deployed Founder app to support at least:

- auth login / me / logout;
- feed/list;
- exact total count and pagination;
- free-text search;
- common track/decision/min-score filters;
- opportunity detail with a response shape safe for the existing DetailDrawer;
- facets GET sufficient for current UI and smoke;
- source health;
- repository-managed Truth Pack status;
- dashboard data needed by the header;
- asynchronous Poll Now returning the exact current `PollNowResponse` shape;
- fixed CV preview/download;
- generated artifact retrieval when available;
- unauthorized access rejection.

Do not return placeholder/stub JSON that happens to satisfy one shallow test but breaks the existing UI.

### 4. Fixed CV retrieval must obey ADR-0024 exactly

The current Antigravity draft route incorrectly looked in `founder-truth-pack/cv-final.pdf`. That bucket/path is wrong.

The real invariant is:
`opportunity -> deterministic six-CV selection -> exact private founder-cv-portfolio object -> SHA-256 verify -> return exact bytes`.

Implement this robustly.

Preferred design:
- persist the selected fixed-CV identity/path/hash into durable projection/application metadata at evaluation/projection time, using the existing authoritative Python `matching.cv_selector`;
- expose only the selected object path/hash through the Founder-safe hosted surface;
- Cloudflare/hosted retrieval fetches from private `founder-cv-portfolio` using Founder JWT Storage policy and verifies %PDF + SHA-256 before returning bytes;
- never reimplement a weaker title-only selector in TypeScript;
- never default every opportunity to Master merely to make smoke pass.

Add repository migration(s) after 0010 if required and update ORM/projection tests accordingly.

### 5. Generated artifact retrieval

Use `artifact_cache` metadata:
- object key, SHA-256, size, content type, opportunity/truth/template/kind/generation binding;
- private `opportunity-artifacts` object bytes;
- verify metadata binding and bytes before returning;
- no service role exposed to browser;
- 404/409/412 semantics remain compatible with current UI.

### 6. Founder identity / RLS hardening

Audit `0010_hosted_runtime`.

Ensure final migration authority:
- durable singleton Founder binding;
- Founder-only browser reads;
- anonymous and authenticated non-Founder denied;
- browser roles cannot exploit TRUNCATE/REFERENCES/TRIGGER or other non-RLS privileges;
- Storage policies cover exactly `founder-cv-portfolio` and `opportunity-artifacts`;
- no obsolete private Truth Pack bucket requirement;
- helper/RPC EXECUTE privileges are least-privilege;
- downgrade restores prior deny posture.

Use `auth.uid()` or an equivalent supported Supabase JWT identity primitive that is reliable through PostgREST; do not depend on a fragile operator session GUC.

### 7. Poll Now semantics

The hosted RPC must produce the exact API response shape:
`{ enqueued: [{source_id, job_id}], skipped: [{source_id, reason}] }`.

Preserve authoritative semantics:
- durable source_schedules only;
- due-only;
- cooldown-aware;
- active-job dedupe;
- source-policy safe;
- transactionally advance next_due_at;
- async response;
- no acquisition/evaluation on request path.

If a requested source is absent from durable source_schedules, do not invent it at the browser boundary.

### 8. Empty-live-DB bootstrap and bounded compute

Create a protected workflow / script that can safely initialize the live staging data plane with no Founder PC:
1. bootstrap source_schedules from the committed Source Registry using existing scheduler semantics;
2. enqueue due/read-allowed work;
3. drain a bounded number of jobs per invocation;
4. allow repeated manual/scheduled invocations;
5. never hang waiting for a quota of jobs when the queue becomes empty;
6. keep queue/schedule state durable in Supabase;
7. respect the zero-dollar runner/cost policy;
8. fail/stop on source policy/403/429/CAPTCHA/MFA controls exactly as existing worker code requires.

Do not create a workflow that silently polls every source on every run.

A bounded drain loop should stop when:
- queue is empty, or
- max jobs/time budget is reached.

### 9. Detail / dashboard / facets / source-health data

Prefer narrow SECURITY DEFINER RPCs returning JSON or narrow security-invoker views over granting broad table access.

Detail must not expose raw payloads, private provenance data beyond the Founder UI contract, credentials, or unrelated rows.

It is acceptable to construct the existing response shape from:
- opportunities;
- current match_evaluations;
- field_provenances;
- feed_projection;
- triage/feedback/action state;
provided Founder auth is checked at the function boundary and the output is deliberate.

### 10. Auth session lifecycle

If using same-origin Cloudflare auth:
- login accepts Founder email + password;
- cookies are HTTP-only, Secure on HTTPS, SameSite appropriate;
- do not return raw access/refresh tokens to frontend JavaScript;
- refresh token is not exposed to JS;
- `auth/me` can refresh an expired access token using the refresh token;
- logout clears both cookies and tells Supabase Auth to revoke session where practical;
- no hard-coded Founder email in repository;
- no password in Worker vars/source.

### 11. Public runtime configuration

Hosted Cloudflare should need only browser-safe public config:
- Supabase project URL;
- Supabase publishable/anon key.

Do not create new privileged environment requirements when existing protected names already cover server-side worker jobs:
- `STORAGE_SERVICE_KEY`
- `OPOS_TARGET_DB_URL`
- etc.

## Required migrations

Keep `0010_hosted_runtime` if sound, but add `0011_...` or later revisions where needed.

Update:
- SQLAlchemy model authority;
- Alembic chain;
- provider execution bundle;
- migration tests;
- generated migration evidence.

## Tests

Add deterministic tests that catch:
- page total > page size;
- page 2 different rows;
- Poll Now exact response shape;
- anonymous/non-Founder denial contract;
- access token refresh;
- no auth tokens in localStorage in hosted mode;
- detail shape safe for current DetailDrawer;
- Truth status loaded from repository meta;
- source health shape;
- fixed CV object path/hash selection from authoritative Python selector;
- generated artifact byte/hash validation;
- worker bootstrap stops when queue empty/max reached;
- migration grants and non-RLS privilege revocation;
- no service-role/database URL in web bundle/config.

Run focused suites + worker/scheduler + migration + web lint/build + repository/guard/state.

## Do not claim hosted PASS

This branch still cannot self-prove real Supabase/Cloudflare behavior. Prepare the exact provider-ready code. The Overseer will:
- apply migrations;
- bind Founder UUID;
- run live RLS probes;
- bootstrap live data;
- deploy Cloudflare;
- run E2E;
- run backup/restore/monitoring/soak.

## Handoff

Create/update:
`reports/evidence/FR-007/W19_CODEX_HOSTED_API_FINAL.md`

Include:
- exact commits/files;
- tests;
- migration head expected;
- environment vars/secrets actually required;
- exact protected workflows for live bootstrap;
- exact remaining Overseer actions;
- A0-A17 impact.

Commit/push to the same branch and return one concise report. Do not self-declare FR-007 closed.
