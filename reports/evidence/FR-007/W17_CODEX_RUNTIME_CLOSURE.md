# FR-007 W17 Codex runtime closure batch

## Execution

- Branch: `work/fr007-codex-runtime-closure`
- Starting integration commit: `663ea97`
- Batch commits: `95a9f8d` (Supabase runtime contract), `e4cf825`
  (authenticated encrypted backup)
- R1 remediation is carried in the current branch on top of the preserved
  W17/Overseer fixes; the final commit SHA is recorded by the completion
  packet after this evidence update.
- No production or hosted mutation was executed by Codex.

## Implemented

- Target-only hosted data-plane PRECHECK no longer requires
  `OPOS_SOURCE_DB_URL`; source credentials remain mandatory for migration and
  parity modes. Source/target identity checks and redaction remain fail closed.
- Added deterministic Supabase runtime SQL for a persisted feed view, async
  Poll Now enqueue, and job status. Browser access is deny-by-default unless
  `auth.uid()` matches the provider-owned `app.founder_auth_uid` setting.
  Anonymous/public execution is revoked; no service key or database URL is
  emitted.
- Added AES-256-GCM backup encryption with strict 64-hex key validation,
  checksum/authentication verification, temporary plaintext cleanup, and a
  manual protected GitHub workflow that uploads only encrypted bytes and a
  sanitized manifest.
- Added a bounded scheduled/manual GitHub worker drain using the durable
  PostgreSQL queue and `OPPORTUNITYOS_DB_URL` from the protected environment.
- Artifact retrieval and idempotent writes now verify opportunity, Truth Pack,
  template, kind, generation version, and cache-key bindings before serving or
  reusing a row.

## Verification

- Focused runtime/backup/artifact/hosted-proof/migration suites: **78 tests,
  0 failures**.
- `python -m py_compile` for all changed Python modules: passed.
- `python scripts/check_repository.py`: passed.
- `python scripts/check_guard.py --allow-missing-patterns`: passed.
- `STATE_PRESERVE_TIMESTAMP=1 python scripts/generate_state.py`: passed;
  generated `docs/STATE.md` is committed and must remain fresh.
- Disposable/live PostgreSQL and Supabase provider execution were not
  available in this executor; no test was converted to PASS to hide that.

## Acceptance impact

- A-1/A-3/A-7/A-8/A-12/A-15: repository contracts and deterministic tests
  strengthened; hosted acceptance remains unearned.
- A-9 migration/parity: existing provider-neutral tooling remains available;
  source parity is `NOT_EXECUTED` until `OPOS_SOURCE_DB_URL` is supplied.
- A-10 RLS: runtime SQL and deny-by-default contract are repository-ready;
  real anon/authenticated/backend role execution remains provider-owned.
- A-11 private storage/artifacts: metadata binding and private backend
  checks are covered by unit tests; remote restart retrieval remains
  provider-owned.
- A-0/A-2/A-4/A-5/A-6/A-13/A-14/A-16/A-17: unchanged by this batch.

## Genuine remaining blockers

The Overseer must execute the protected hosted workflow against the existing
Supabase staging project, bind the real Founder UUID in `founder_identity`
through a secure database session, run migration 0010, perform real role/RLS and
private-storage retrieval tests, and provide source credentials for parity.
Those operations are intentionally absent here; this report does not claim
FR-007 closure, production cutover, or live artifact/Truth Pack proof.

## R1 remediation

The R1 review defects were repaired in this batch:

- `storage/migrations/versions/0010_hosted_runtime.py` is now the repository
  migration authority after `0009_hosted_founder_auth`. It binds a durable
  singleton Founder identity to the Supabase JWT subject, exposes narrow
  security-invoker views, adds private Storage read policies, and restores
  deny policies on downgrade.
- `enqueue_poll_now` is due-only, cooldown-aware, row-locked,
  active-job-deduplicated, policy-bound and transactionally advances durable
  schedule state. It never creates a generic empty-payload job.
- `scripts/fr007_supabase_execution_bundle.py` and committed provider
  artifacts now discover and render the dynamic Alembic head
  `0010_hosted_runtime` instead of hard-coding `0009`.
- `scripts/db_migration_restore.py` now supports authenticated encrypted
  restore through a temporary plaintext file that is always removed.
- Web browser runtime wiring uses Supabase Auth, PostgREST feed reads, and the
  Poll Now RPC when publishable browser configuration is present; the legacy
  proxy is no longer required at the cloud edge for that path.
- Workflow contract tests cover the crypto dependency, encrypted-only upload,
  key non-disclosure, and the single bounded worker CLI mode.

R1 verification:

- Runtime/migration/provider/backup/hosted-proof/workflow suites: **56 tests,
  0 failures**.
- Python compile, repository integrity, guard, state generation and diff
  checks: passed.
- Web lint/build: passed locally after installing the lockfile dependencies
  with `npm ci --ignore-scripts` (`npm run lint`, `npm run build`).

The 0010 migration and provider bundle were also checked for role-optional
execution: disposable/plain PostgreSQL can run the chain without Supabase
browser roles, while a Supabase target applies the authenticated Founder
policies when those roles exist.

Hosted operations still not executed by Codex: applying migration 0010 to the
real Supabase project, inserting the real Founder UUID, anon/non-Founder/
Founder RLS probes, private CV/artifact retrieval after restart, and source
parity. Those remain exact Overseer actions and are not represented as PASS.
