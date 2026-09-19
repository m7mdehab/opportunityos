# W17-R1 — Overseer remediation: make the Supabase-native runtime actually deployable

## Status

This is an Overseer remediation order against `work/fr007-codex-runtime-closure` after independent review of W17.

Start from current branch head. Two small Overseer repairs are already present:
- `1c311a0` fixes the invalid mutually-exclusive worker CLI invocation.
- `67b0cc6` adds the missing `cryptography` runtime dependency required by encrypted backups.

Do not revert those commits.

## Why remediation is required

W17 materially improved the repository, but the terminal mission was not yet met.

The current repository still has these blocking defects:

1. **No actual Supabase-native Founder web runtime is wired.**
   - `web/app/login/page.tsx` still uses the legacy local-password API flow.
   - `web/lib/api/client.ts` still assumes the legacy FastAPI-shaped `/api/*` backend.
   - `web/app/api/[...path]/route.ts` still requires `OPPORTUNITYOS_API_ORIGIN` on Cloudflare and returns configuration error without it.
   - Therefore Cloudflare staging still cannot function under ADR-0023 without a separate always-on API host.

2. **The W17 Supabase contract is only generated SQL, not repository-owned deployable schema authority.**
   - Runtime view/functions/policies must be represented by a real Alembic migration after `0009_hosted_founder_auth` (normally `0010_...`), not an operator-only ad hoc SQL fragment.
   - The migration must be idempotent/reversible to the project standard and covered by migration tests.

3. **Current `enqueue_poll_now` SQL is semantically insufficient.**
   - It inserts a generic `poll_source` row with empty payload for generic Poll Now.
   - It does not reuse the due-only/read-policy/active-job-dedupe/cooldown semantics in `worker.scheduler.enqueue_due_sources`.
   - It can therefore diverge from A-7/A-8 and from the already-proven Python scheduler semantics.
   - The hosted Poll Now boundary must preserve due-only, policy-safe, idempotent semantics rather than inventing a second incompatible scheduler.

4. **Hosted artifact storage configuration is not mapped to the protected environment already established by the Overseer.**
   - Current code expects new names such as `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_STORAGE_URL`.
   - The actual protected staging environment already contains `STORAGE_SERVICE_KEY`; the Supabase project URL is fixed/known and a publishable key can be obtained by the Overseer.
   - Do not create unnecessary new privileged secret requirements.
   - Browser retrieval must use Founder JWT/RLS/private Storage policy, never service-role material.

5. **The interactive contract is incomplete for the live Founder UI.**
   A deployable zero-dollar path must support the UI surfaces needed for hosted A-16, at minimum:
   - Supabase Auth login/session/logout;
   - feed/list with pagination/search/common filters;
   - opportunity detail;
   - facets required by current UI;
   - source-health state required by the header;
   - repository Truth Pack status;
   - asynchronous Poll Now;
   - fixed CV preview/download;
   - generated artifact retrieval where present;
   - unauthorized access rejection.
   Preserve additional current Founder controls where practical without rewriting domain logic.

## Required outcome

Implement the real zero-dollar interactive runtime so that Cloudflare can serve the Founder Alpha with **no `OPPORTUNITYOS_API_ORIGIN` and no always-on FastAPI service**.

You may preserve same-origin `/api/*` routes if that minimizes UI churn. A valid pattern is a thin Next/Cloudflare adapter that:
- authenticates with Supabase Auth;
- holds only browser-safe publishable configuration;
- forwards the Founder JWT to Supabase PostgREST/RPC/Storage;
- relies on RLS/RPC/storage policies for authorization;
- never contains service-role or DB credentials;
- keeps heavy Python/domain work out of Cloudflare.

Direct browser use of Supabase is also acceptable if it produces the same security and functional result. Choose the smallest robust contract.

## Migration / RLS requirements

Create the next repository-owned migration after 0009.

The migration must:
- establish the single-Founder identity binding in a durable, provider-compatible way;
- add views/RPCs/policies required by the hosted UI;
- deny anon and authenticated non-Founder access;
- expose only deliberate fields/actions;
- add private Storage SELECT policies for the Founder only where needed;
- preserve service-side access for GitHub workers;
- avoid service-role credentials in browser code;
- support rollback consistent with repository standards.

Do not rely on a hand-set database GUC unless you prove that it is durable and compatible with Supabase/PostgREST and is represented in repository migration/config authority. A small founder identity table/helper is acceptable if safer.

## Poll Now requirement

Do not ship the current naive generic insert.

The hosted boundary must preserve the same semantics as the authoritative Python scheduler:
- read-policy safe;
- due-only unless an explicit permitted force/source request is authorized;
- cooldown aware;
- active-job dedupe;
- transactional schedule advancement;
- asynchronous immediate response;
- no source acquisition/evaluation on the request path.

It is acceptable for the browser/RPC to enqueue one bounded scheduler/maintenance job that later invokes the authoritative Python scheduler **only if** the API contract and A-7 evidence clearly prove that this does not enqueue prohibited/not-due source work and does not create duplicate execution. Otherwise implement equivalent SQL semantics against durable schedule state.

## Storage / fixed CV requirement

- Exactly six immutable CVs remain authoritative.
- Never regenerate or patch a CV.
- Browser retrieval must remain Founder-authenticated.
- Exact bytes/hash must be checked at the trusted boundary before use.
- Generated artifacts remain private in `opportunity-artifacts` and metadata-bound in PostgreSQL.
- Reuse the protected staging credential names already established where server-side workers need them; do not add avoidable privileged secrets.

## Backup requirement

Retain W17 AES-256-GCM work and the two Overseer repairs.

Add workflow/test coverage that proves:
- `pip install -e .` installs the encryption dependency;
- backup workflow cannot upload plaintext;
- encrypted restore/decrypt path is compatible with a fresh restore drill;
- the key is never logged or emitted.

## Worker-drain requirement

Retain the Overseer fix using a valid bounded CLI mode.

Add a workflow-contract test that would fail if mutually exclusive worker CLI flags are reintroduced.

## Live-proof readiness

Prepare exact scripts/workflows so the Overseer can then perform:
- migration 0010 application;
- single-Founder identity binding;
- anon/non-Founder/Founder RLS proof;
- private fixed-CV/generated-artifact retrieval proof;
- target-only hosted PRECHECK;
- authenticated feed/Poll Now proof.

Do not require `OPOS_SOURCE_DB_URL` for those target-only proofs.

## Verification

Run:
- all new focused tests;
- existing auth/RLS/runtime/feed/artifact/worker/scheduler tests;
- migration upgrade/downgrade tests;
- web lint/build if web files change;
- repository/guard/state checks;
- full mandatory suite if locally feasible.

Do not weaken any gate.

## Handoff

Update:
`reports/evidence/FR-007/W17_CODEX_RUNTIME_CLOSURE.md`

Add an explicit **R1 remediation** section with:
- defects fixed;
- exact commits/files;
- tests/results;
- hosted operations still not executed;
- A0-A17 impact;
- exact Overseer live actions remaining.

Commit and push the repaired branch. Return one final report. Do not self-declare FR-007 closed.
