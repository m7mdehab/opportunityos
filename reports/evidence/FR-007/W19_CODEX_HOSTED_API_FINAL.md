# FR-007 W19 Codex Hosted API / Data Bootstrap Final Batch

## Branch and scope

- Branch: `work/fr007-codex-hosted-api-final`
- Base: `2e20e446b413ce3605428a15926f98c353d30761`
- Migration head on this branch: `0011_hosted_api_surface`
- No hosted Supabase, Cloudflare, source, artifact-store, or production mutation was executed by Codex.
- This report records repository preparation only; it does not close FR-007.

## Implemented

- Replaced the W17 direct browser Supabase helper with a same-origin client. Browser JavaScript no longer reads or writes `localStorage` auth tokens.
- Added a Cloudflare/Next same-origin Supabase adapter in `web/app/api/[...path]/route.ts`: email/password login, HTTP-only Secure SameSite cookies, refresh-on-expiry, logout, CSRF checks, exact `Prefer: count=exact` feed pagination, Founder-safe detail/source-health/filter/facet/saved-view/dashboard/truth surfaces, asynchronous Poll Now, and private CV/generated-artifact retrieval with size/hash checks.
- Added Alembic `0011_hosted_api_surface`: durable `founder_cv_selections`, Founder-safe detail/CV/filter/facet/saved-view views, source-poll health policy coverage, exact JSON Poll Now response (`enqueued`/`skipped`), and least-privilege grants/RLS with downgrade cleanup.
- Evaluation persistence now records fixed-CV variant/path/SHA-256 selected by authoritative `matching.cv_selector`.
- Updated provider execution artifacts and dynamic head checks through `0011_hosted_api_surface`.
- Added bounded, repeatable `scripts/fr007_hosted_bootstrap.py` and protected manual workflow `.github/workflows/fr007-hosted-bootstrap.yml` for schedule bootstrap, due enqueue, and queue-empty/max-budget drain.
- Added deterministic W19 contract tests.

## Tests and checks

- `python -m unittest scripts.test_w19_hosted_api storage.test_rls_policy storage.test_hosted_runtime_migration scripts.test_fr007_supabase_execution_bundle scripts.test_supabase_runtime_contract -q`: **23 tests, 0 failures**.
- `python -m unittest scripts.test_fr007_supabase_execution_postgres -q`: disposable PostgreSQL job **1 skipped by explicit environment gate** (no live disposable PostgreSQL service in this executor).\n- `python -m unittest api.test_api.FilterSeedSyncTest matching.test_evaluate_persist -q`: **11 tests, 0 failures**.
- `python -m py_compile storage/models.py storage/rls_policy.py storage/migrations/versions/0009_hosted_founder_auth.py storage/migrations/versions/0011_hosted_api_surface.py matching/evaluate_persist.py scripts/fr007_hosted_bootstrap.py scripts/test_w19_hosted_api.py`: passed.
- `python scripts/fr007_supabase_execution_bundle.py generate` then `verify`: passed; generated manifest and migration SQL are hash-verified through `0011_hosted_api_surface`.
- `npm ci` (web dependencies): passed.
- `npm run build`: passed.
- `npm run lint`: passed with `--max-warnings=0`.
- No production credentials, DSNs, Founder Truth Pack contents, descriptions, raw payloads, or artifact bodies were emitted.

## Protected live execution contract

The manual bootstrap workflow uses environment secret `OPOS_TARGET_DB_URL` and optional variable `OPPORTUNITYOS_TRUTH_PACK_PATH`. It is `workflow_dispatch` only, has an explicit mode (`bootstrap`, `enqueue`, `drain`, `all`), bounded `max_jobs`, and `dry_run`; it has no push or scheduled trigger. Live execution still requires the Overseer to provide the protected Supabase target, bind the Founder UUID, run Alembic, execute RLS probes, populate durable schedules, and perform real Cloudflare/private-storage smoke tests.

## Acceptance impact

- Repository readiness strengthened for A-9 migration/parity, A-10 hosted API/RLS surface, A-11 private CV/artifact retrieval, A-16 Founder web contract, and bounded zero-dollar bootstrap.
- Hosted A-9/A-10/A-11/A-16 evidence remains `NOT_EXECUTED` until the Overseer runs the real Supabase/Cloudflare path. Unsupported or unavailable hosted operations are not represented as PASS.
- FR-007 remains open for independent Owner/Overseer verification and closure.
