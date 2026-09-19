# W18-R1 — Overseer remediation: close the false-green Cloudflare deployment path

## Status

This is an Overseer remediation order against `work/fr007-antigravity-edge-closure` after independent review of W18.

## Why remediation is required

W18 added useful deployment/reliability/observability work, but the current Cloudflare path is not deployable under ADR-0023.

The specific contradiction is:

- the workflow now makes `OPPORTUNITYOS_API_ORIGIN` optional;
- but `web/app/api/[...path]/route.ts` still returns a configuration error whenever `OPPORTUNITYOS_CLOUD_EDGE=1` and `OPPORTUNITYOS_API_ORIGIN` is absent;
- `scripts/validate_cloudflare_deployment.py` explicitly validates that legacy fail-closed requirement;
- therefore a deployment without a separate API origin can build and deploy successfully while every protected `/api/*` call fails at runtime.

That is a false-green deployment gate and must be removed.

A second issue: the strengthened staging smoke still exercises the legacy FastAPI-shaped same-origin API. It is valuable as an acceptance contract, but it must run against the Supabase-native runtime Codex is implementing rather than a paid/always-on backend.

## Coordination boundary

Codex owns the Supabase-native data/auth/RPC/storage implementation on `work/fr007-codex-runtime-closure`.

Do not duplicate Codex's schema/RLS implementation.

Your remediation should make the Cloudflare/browser/reliability side **contract-compatible** with a Supabase-native same-origin/direct-Supabase runtime and eliminate all stale mandatory API-origin assumptions.

If the exact Codex route/client shape is not yet available, structure your changes so the final integration requires only a small compatibility merge, not another redesign.

## Required fixes

### 1. Cloudflare deployment must not need a separate API host

The production Cloudflare runtime must work with:
- Supabase Auth;
- Supabase RLS/RPC/views/private Storage;
- no `OPPORTUNITYOS_API_ORIGIN`;
- no local fallback on cloud;
- no paid API/container provider.

Delete or replace the validator assertions that currently require the cloud route to fail when API origin is absent.

A build/deploy without `OPPORTUNITYOS_API_ORIGIN` must be a meaningful deploy, not a runtime guaranteed to return 500.

### 2. Public Supabase configuration

Prepare the workflow/build contract for browser-safe values only:
- Supabase project URL;
- active publishable key / compatible public anon key;
- staging public URL.

Do not treat publishable/anon configuration as a secret authorization boundary.
Do not expose service-role, DB URL, storage service key, backup key, or Founder password in the client bundle.

Prefer environment/vars contracts that the Overseer can populate or inject without creating new privileged secrets.

### 3. Hosted E2E must prove Supabase Auth

Update the Playwright smoke to prove the actual production auth flow:
- email + password Supabase Auth where the page requires it;
- unauthorized user rejected;
- successful Founder session survives navigation/API calls;
- logout invalidates hosted session;
- no legacy local-password-only assumption counted as acceptance.

Continue to cover:
- feed;
- pagination;
- search;
- facets;
- detail;
- source link;
- async Poll Now;
- fixed CV preview/download;
- generated artifact retrieval if present;
- Desktop Chrome + 390px mobile.

### 4. Reliability evidence labels

Do not label A-4 through A-8 as hosted PASS merely because disposable/local harnesses pass.

Update W18 evidence vocabulary:
- repository/disposable proof = IMPLEMENTED/VERIFIED_REPOSITORY;
- hosted PASS only after a protected staging run against deployed Cloudflare + Supabase.

Preserve the harnesses; fix the acceptance labeling.

### 5. Observability

Ensure monitoring remains valid in a no-separate-API architecture.

If there is no standalone API URL:
- do not require `OPOS_MONITOR_API_URL`;
- probe same-origin protected/public health endpoints or Supabase-native health as appropriate;
- retain database/queue/scheduler/source-freshness/backup checks;
- keep issue incident lifecycle and sanitization.

Ensure scheduled workflow checkout/branch behavior will use the landed implementation from main after integration and cannot silently monitor stale code.

### 6. Soak

Keep fail-closed 168-hour verification.

Add explicit evidence that:
- missing intervals fail;
- local Founder host state is irrelevant;
- backup heartbeat is required;
- deployed build/revision identity is recorded;
- changing deployment identity during the soak is either explicitly handled or invalidates the continuity window.

### 7. Cloudflare workflow validation

Add tests that would catch the exact false-green found by the Overseer:
- no required external API origin;
- deployment without API origin still has a functional Supabase-backed request path;
- validator fails if cloud runtime has only a dead/legacy proxy route;
- token/account checks remain least-privilege compatible;
- Worker name remains `opportunityos-web-staging`.

## Verification

Run:
- Cloudflare static validator/tests;
- web lint;
- OpenNext build;
- staging smoke contract tests with mocked transport only for repository contract validation, clearly not hosted acceptance;
- reliability/monitor/soak unit suites;
- cost/quota validators;
- repository/guard/state checks.

Do not claim hosted PASS without a real protected run.

## Handoff

Update:
`reports/evidence/FR-007/W18_ANTIGRAVITY_EDGE_CLOSURE.md`

Add an explicit **R1 remediation** section with:
- false-green defect fixed;
- exact files/commits;
- test results;
- repository-vs-hosted evidence labels;
- exact integration dependency on Codex;
- exact Overseer protected workflows to run after integration.

Commit and push. Do not self-declare FR-007 closed.
