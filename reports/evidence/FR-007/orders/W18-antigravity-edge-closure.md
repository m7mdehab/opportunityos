# W18 — Antigravity: Cloudflare / Browser / Reliability / Soak Closure Batch

## Mission

Execute a large, continuous FR-007 edge/deployment/reliability batch on branch `work/fr007-antigravity-edge-closure`.

Work in long autonomous loops: inspect -> implement -> test -> repair -> retest -> continue. Do not stop at the first failing check. Do not return executable technical chores to the Founder. Produce one evidence-backed completion report at the end of the batch.

## Governing authority

Read and obey:

1. `AGENTS.md`
2. `docs/AUTHORITY_INDEX.md`
3. `docs/CHAT_RESUME.md`
4. `docs/STATE.md`
5. `docs/CI_EFFICIENCY_POLICY.md`
6. `briefs/BRIEF-FR-007.md`
7. `docs/adr/ADR-0023-zero-dollar-founder-runtime.md`
8. `docs/adr/ADR-0024-fixed-cv-portfolio-selection.md`
9. current deployment/observability/reliability docs and workflows

ADR-0023 supersedes older Azure/Render/private-Truth-Pack deployment assumptions.

## Locked runtime facts

- Provider set is exactly Supabase Free + Cloudflare + GitHub.
- No gross provider spend, trial/student credits, paid add-ons, Azure, Render, paid VPS/container compute.
- Founder PC must be irrelevant to production correctness.
- Supabase is canonical state/Auth/RLS/private Storage.
- Cloudflare is web/edge only; do not turn it into a heavy Python/domain compute replacement.
- Heavy Python work is bounded GitHub Actions compute against durable Supabase state.
- Repository Truth Pack is canonical and hash-bound.
- Employment CV is one of six immutable approved PDFs; exact bytes only.
- Private data/credentials must never enter Git, browser bundles, logs, screenshots, or evidence.
- Stop on 403/429/CAPTCHA/MFA/policy barriers; no bypasses.

## Existing live baseline already proven by Overseer

Do not spend the batch re-proving setup already closed:

- `fr007-staging` protected GitHub environment exists with DB/storage/Cloudflare/E2E/backup secrets.
- live Supabase is at migration `0009_hosted_founder_auth`.
- 26 public app tables have RLS enabled.
- one confirmed Founder Auth user exists.
- six fixed CVs exist privately and pass authenticated SHA-256 verification.
- repository Truth Pack verification passes.
- Cloudflare Worker `opportunityos-web-staging` exists.
- Cloudflare account/token readiness passes.
- zero-dollar readiness launcher passes end-to-end.
- `OPOS_SOURCE_DB_URL` is deliberately deferred until real source parity.

## Primary ownership

You own deployment, frontend/browser smoke, Cloudflare mechanics, reliability/chaos evidence, observability, cost/quota evidence, and soak automation.

Do not redesign Supabase schema/RPC/auth internals unless a small compatibility repair is required. Codex owns the data-plane/runtime implementation. Keep your work merge-friendly and contract-oriented.

### A. Cloudflare deployment path

Make the Cloudflare workflow production-credible for the zero-dollar architecture:

- explicit checkout of the active implementation branch when used as a reusable/default-branch launcher;
- OpenNext build succeeds reproducibly;
- correct Worker name `opportunityos-web-staging`;
- no stale paid-provider assumptions;
- no accidental deploy to another Worker/account;
- environment variables validated fail-closed;
- Cloudflare token/account validation compatible with the current account-owned token;
- build/deploy uses only Free-plan-compatible features;
- static assets are preferred where possible; Worker CPU remains thin.

Remove the assumption that a separate paid `OPPORTUNITYOS_API_ORIGIN` must exist. Coordinate around the Supabase-native/same-origin contract Codex is implementing. If that contract is not yet landed, prepare the deployment workflow so it can consume it with minimal/no follow-up.

### B. Staging browser/E2E closure

Strengthen and run the real hosted Playwright suite for:

- Desktop Chrome;
- 390px mobile;
- Founder authentication/session;
- feed load;
- pagination;
- search;
- facets/filters/saved views that exist in current UI;
- opportunity detail;
- canonical source link behavior;
- Poll Now immediate/asynchronous behavior;
- fixed-CV preview/download;
- generated artifact access where available;
- logout/session boundary;
- unauthorized access rejection.

Do not encode Founder email/password into source. Use protected environment secrets.

Make test selectors resilient and avoid brittle visual timing assumptions.

### C. Reliability / failure-isolation proofs

Use or extend the existing FR-007 reliability harness to prove as much as possible of:

- cold-start authenticated feed SLO;
- feed/search/detail remain usable when acquisition/evaluation workers are absent;
- one source adapter/job failure does not take down unrelated sources/feed/artifacts/scheduler;
- repeated stable-source polling is identity/idempotency safe;
- Poll Now is non-blocking and due-only;
- schedule/cooldown state survives runner/scheduler restarts;
- no all-source restart storm;
- queue/retry/dead-letter failures are observable and recoverable.

Prefer executable automated evidence over prose.

### D. Observability / incident lifecycle

Finish the zero-dollar monitoring path:

- external Cloudflare web liveness;
- Supabase/database reachability;
- queue depth/stall;
- scheduler state;
- source freshness;
- backup heartbeat;
- synthetic test alert;
- GitHub Issue incident creation/dedup/closure behavior where already designed;
- sanitized soak snapshots.

The Founder opening the site must not be required for detection.

### E. Cost/quota / no-charge proof

Close the runtime economics evidence after actual staging deployment:

- Cloudflare configuration uses no billable add-on;
- Supabase usage/config remains Free-tier compatible;
- GitHub execution uses standard eligible runners only;
- no larger runners;
- bounded schedules/retention/artifacts;
- gross provider charge remains $0.00 under the declared envelope;
- fail closed/degrade rather than spill into paid usage.

Update validators/docs if stale assumptions remain.

### F. Soak automation

Prepare the ≥7-day host-off soak so it can start immediately after staging is accepted:

- scheduled monitoring at an economical cadence;
- immutable bounded-retention snapshots;
- acquisition/evaluation heartbeat evidence;
- backup heartbeat;
- failure annotations;
- summary verifier that refuses to claim seven days if intervals are missing;
- Founder PC/local processes explicitly outside the dependency graph.

Do not fabricate elapsed time. The seven-day criterion only closes after seven real consecutive days.

### G. Provider-exit / restore-facing evidence

Without duplicating Codex backup implementation, exercise the existing portability/provider-exit harnesses and strengthen the runtime-facing restore smoke:

- restored staging URL/auth/feed/search/detail/artifact checks;
- evidence format and redaction;
- no private bytes in logs/artifacts except encrypted backup payloads;
- provider-neutral exit path remains documented and executable.

### H. Integration hygiene

PR #93 is currently dirty against `main`, but this work branch intentionally started from the active FR-007 head. Do not spend the whole batch rewriting history.

Keep commits coherent and minimize overlap with Codex-owned data-plane files. Record any contract dependency clearly so the Overseer can integrate both branches and resolve the final main/FR-007 reconciliation once.

## Parallelism inside this batch

Use internal Antigravity parallel tasks/worktrees for:

- Cloudflare workflow/config;
- Playwright/browser smoke;
- reliability harness;
- observability/incident flow;
- quota/cost validation;
- soak evidence tooling.

Do not let parallel workers edit the same workflow/test file simultaneously.

## Forbidden shortcuts

- no paid provider or billable feature;
- no dummy hosted URL accepted as evidence;
- no mock browser test counted as hosted smoke;
- no weakening auth/RLS/private Storage to simplify E2E;
- no hard-coded Founder credentials;
- no fake seven-day soak;
- no bypass of 403/429/CAPTCHA/MFA;
- no self-declaration that FR-007 is closed.

## Handoff contract

Before stopping:

1. run narrow tests continuously and all applicable full suites at the end;
2. perform real Cloudflare/browser/provider proofs when credentials/tooling are accessible; otherwise leave exact workflow-trigger instructions for the Overseer rather than fake evidence;
3. update observability/deployment/runbooks only for verified facts;
4. write `reports/evidence/FR-007/W18_ANTIGRAVITY_EDGE_CLOSURE.md` containing:
   - exact commits/files;
   - tests/results;
   - real hosted evidence;
   - A0-A17 impact;
   - remaining blockers;
   - exact Overseer-only provider actions;
5. commit everything on `work/fr007-antigravity-edge-closure`;
6. return one concise final report to the Overseer. Do not self-approve FR-007.
