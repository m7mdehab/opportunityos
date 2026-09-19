# FR-007 hosted Supabase execution

This package is a provider-execution contract. Alembic remains the schema
authority; Codex does not mutate Supabase or claim hosted acceptance.

## 1. Generate and verify the bundle

From the repository root:

```text
python scripts/fr007_supabase_execution_bundle.py generate
python scripts/fr007_supabase_execution_bundle.py verify
```

Artifacts are written under
`reports/evidence/FR-007/provider-execution/`. The nine ordered SQL migration
files are derived offline from revisions `0001_baseline_schema` through
`0009_hosted_founder_auth`. The manifest records every SHA-256 and expected
effect.

## 2. Export and import the source

Create the sanitized logical backup from the authoritative source and restore
it into a fresh target using the existing backup manifest/checksum contract:

```text
OPOS_SOURCE_DB_URL=<injected-at-runtime> python scripts/db_migration_restore.py backup --destination <new-file>
OPOS_TARGET_DB_URL=<injected-at-runtime> python scripts/db_migration_restore.py restore --archive <file> --manifest <file> --confirm-target-restore
```

The target must be empty. The restore path is explicit and never uses
`--clean`/`--create` or an implicit production target.

## 3. Apply or validate the schema

For an empty target, execute the migration files in manifest order. After a
full logical restore, run the repository's idempotent `alembic upgrade head`
against the target to validate the same current head. Record the target
Alembic revision before and after. Stop on the first error; do not continue to storage or parity. The generated SQL has
no credentials, private data, local paths, or psql meta-commands.

Run `verify/schema.sql` as the provider operator and retain sanitized results.

Before browser-role verification, execute `provider-security.sql`. Supabase grants
non-row table privileges such as `TRUNCATE`, `REFERENCES`, and `TRIGGER` on
new public tables by default; RLS does not govern `TRUNCATE`. The provider
security bootstrap therefore protects `public.alembic_version` with deny RLS
and removes those non-row privileges from `anon` and `authenticated`.
Do not expose staging browser access if this bootstrap or its verification fails.

## 4. Verify RLS

Run `verify/rls.sql` as the provider operator. It reports `relrowsecurity`,
policy names/roles/commands/expressions, and browser-role table grants. In
fresh transactions run the provided `SET LOCAL ROLE anon` and
`SET LOCAL ROLE authenticated` probes against the listed protected tables.
Both browser roles must be denied; the owner/service connection must retain
the required backend path. The verification must also show RLS enabled on
`alembic_version` and no `TRUNCATE`, `REFERENCES`, or `TRIGGER`
privileges for `anon` or `authenticated` on public tables. This is the
hosted A-10 proof step.

## 5. Parity

Credentials are runtime-only environment variables:

```text
OPOS_SOURCE_DB_URL=<injected-at-runtime> python scripts/db_migration_restore.py backup --destination <new-file>
OPOS_SOURCE_DB_URL=<injected-at-runtime> OPOS_TARGET_DB_URL=<injected-at-runtime> python scripts/db_migration_restore.py restore --archive <file> --manifest <file> --confirm-target-restore
OPOS_SOURCE_DB_URL=<injected-at-runtime> OPOS_TARGET_DB_URL=<injected-at-runtime> python scripts/db_migration_restore.py parity-live
```

Capture sanitized snapshots with `snapshot --role source` and
`snapshot --role target`, then compare them with `parity`. A mismatch or
unsupported required concept is non-success and blocks cutover.

## 6. Private Storage bootstrap

Execute `storage.sql` only as the provider operator. It creates or repairs the
private buckets `founder-truth-pack` and `opportunity-artifacts` with
`public=false`; it stores no object body. Run `verify/storage.sql` and prove
unauthenticated object reads fail while server-only retrieval succeeds. Use
`storage-rollback.sql` only after confirming both buckets are empty.

Truth Pack objects must use the existing credential-free HTTPS URI plus
server-only bearer/API-key headers and SHA-256 binding. Artifact objects use
the existing `artifacts/<cache_key>` identity and PostgreSQL metadata remains
canonical.

## 7. Evidence and limits

Start with `evidence-template.json`; populate it only from live results. It
must remain `NOT_EXECUTED` until the authenticated operator has run the steps.
Repository/disposable PostgreSQL tests prove the package mechanics. They do
not prove Supabase RLS, hosted Truth Pack retrieval, hosted artifact retrieval,
or A-9/A-10/A-11 closure.
