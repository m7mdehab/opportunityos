# W20 — Antigravity Final Hosted Proof / Deployment Contract Batch

## Mission

Execute the final edge/evidence batch on branch `work/fr007-antigravity-hosted-proof-final`.

This branch starts from the Overseer integration branch containing Codex W17/W17-R1 plus imported Antigravity reliability/monitoring work.

Codex W19 owns the actual Supabase schema/API/auth/runtime implementation on a separate parallel branch. You own **tests, deployment workflow, hosted-smoke contract, observability, reliability evidence semantics, and soak mechanics**.

Do not edit database migrations or duplicate Codex runtime logic unless a tiny test-only compatibility shim is unavoidable.

## Governing authority

Read AGENTS.md, BRIEF-FR-007, ADR-0023, ADR-0024, current W18 evidence, and this order.

## Core rule

A local/repository test is never a hosted PASS.

Your job is to make it impossible for the final integrated branch to produce a false green when the Supabase-native runtime is broken.

## Expected final hosted architecture

- Cloudflare Worker/OpenNext frontend;
- same-origin or direct Supabase-native browser/API boundary;
- Supabase Auth;
- RLS/RPC/private Storage;
- no mandatory `OPPORTUNITYOS_API_ORIGIN`;
- public runtime config only: Supabase URL + publishable/anon key;
- protected Founder E2E credentials only in GitHub environment;
- heavy Python jobs via bounded GitHub Actions;
- live DB may initially be empty and must be bootstrapped through protected workflows.

## Required work

### 1. Cloudflare workflow

Make `.github/workflows/fr007-cloudflare-staging-deploy.yml` robust for the final integration:

- supports explicit ref when manually dispatched;
- reusable workflow optional if useful;
- checks out requested ref;
- validates Cloudflare account/token before deploy;
- requires public Supabase URL + publishable/anon key when no legacy API origin;
- build receives browser-safe values;
- deploy receives those values in Worker runtime vars if server routes need them;
- never injects service-role/db/backup/Founder password into Worker vars;
- Worker name remains `opportunityos-web-staging`;
- no R2/KV/D1/paid bindings;
- no DNS/custom-domain mutation in this staging workflow;
- SMOKE mode requires staging URL and Founder email/password secrets.

### 2. E2E contract

Write/repair the hosted smoke so it will fail on shallow/stub implementations.

Desktop Chrome + 390px mobile must prove:
- unauthenticated root redirects/login gate;
- invalid login rejected;
- Founder email/password login succeeds;
- session survives page reload;
- feed endpoint returns exact contract;
- total count can exceed page size;
- page 2 returns different item when corpus has enough rows;
- live search returns target row;
- facets response has the real contract shape, not arrays of bare strings;
- opportunity detail includes nested qualification/scoring arrays safe for DetailDrawer;
- source link is visible;
- Poll Now response contains arrays of {source_id,job_id} and {source_id,reason};
- Poll Now returns quickly/asynchronously and existing feed remains visible;
- fixed CV preview/download returns exact PDF bytes with expected content disposition and PDF magic;
- generated artifact is either correctly returned or a legitimate 404/409/412;
- logout invalidates hosted session;
- subsequent protected request is 401.

If staging has fewer than two feed rows, the smoke must fail with a clear data-bootstrap prerequisite rather than weaken pagination proof.

### 3. Static validators

The Cloudflare validator must fail if:
- cloud runtime requires external API origin;
- no Supabase-native route/client exists;
- public Supabase vars are not wired;
- service-role/db secrets are wired to Worker/browser;
- fixed CV route references obsolete `founder-truth-pack`;
- deployment uses paid Cloudflare primitives.

### 4. Observability

Make live monitoring suitable for the final architecture:
- web liveness;
- authenticated/same-origin API or Supabase-native health;
- DB reachability;
- queue depth/stall;
- scheduler/source freshness;
- backup heartbeat;
- test alert/incident lifecycle;
- no standalone API URL required.

Do not use Founder password for routine monitoring if a non-interactive safe endpoint/DB check can prove health.

### 5. Reliability hosted harness

Preserve repository A4-A8 harnesses but add a protected hosted orchestration mode/script that can collect real evidence after deployment without mutating unsafe external state.

Hosted evidence must identify:
- repository SHA;
- deployment identifier;
- timestamp;
- live target URL;
- database identity fingerprint (non-secret);
- scenario status.

No mock/disposable run may be serialized as hosted PASS.

### 6. Soak

Keep >=168 real hours fail closed.

Require:
- no missing scheduled intervals beyond declared tolerance;
- same deployment identity unless explicit reset;
- repository SHA continuity semantics documented;
- backup heartbeat;
- queue/scheduler/source freshness;
- Founder PC not part of any probe;
- redacted evidence;
- bounded artifact retention;
- no fake elapsed time.

### 7. Cost/quota

Revalidate the post-integration workflow cadence and artifact retention under ADR-0023:
- $0 gross charge;
- standard eligible runners only;
- no paid Cloudflare feature;
- no paid Supabase feature;
- bounded backup/soak artifacts;
- fail closed on quota risk rather than spill into paid resources.

### 8. Branch integration awareness

Do not assume the current Antigravity draft route is authoritative. Codex W19 is replacing/finalizing the hosted API/runtime contract.

Write tests against behavior/contracts, not fragile implementation strings, wherever possible.

## Verification

Run:
- validator unit suites;
- web lint;
- OpenNext build;
- Playwright contract/local smoke where possible;
- monitor/reliability/soak suites;
- cost/quota validation staging + production;
- workflow contract validator;
- repository/guard/state checks.

## Evidence

Create/update:
`reports/evidence/FR-007/W20_ANTIGRAVITY_HOSTED_PROOF_FINAL.md`

Clearly separate:
- repository verified;
- protected-hosted pending;
- actual hosted PASS only if you truly had provider access.

Commit/push. Do not self-declare FR-007 closed.
