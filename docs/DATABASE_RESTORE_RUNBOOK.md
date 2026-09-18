# FR-007 W5 PostgreSQL migration and restore harness

This harness prepares the W5.1 database transfer and W5.2 parity check. It
operates on PostgreSQL `public` schema, where repository Alembic migrations and
canonical OpportunityOS tables live. It is provider neutral: a Supabase,
self-hosted, or other PostgreSQL endpoint supplies the same connection contract.
This code does not provision a provider, upload backups, or prove a cloud
restore without actual database access.

## Connection and safety contract

Inject `OPOS_SOURCE_DB_URL` and `OPOS_TARGET_DB_URL` in the process environment
from a private secret store. Both must be PostgreSQL URLs with host, user,
password, and database; `?sslmode=require` is supported. No DSN is accepted on
the command line. Both settings are required for target operations, and the
source and target host/port/database identities must differ. Use separate,
least-privilege source reader and target
migration/restore credentials. A target must be an explicitly selected fresh
database: `restore` requires `--confirm-target-restore` and refuses any existing
`public` base table. It never passes `--clean` or `--create` to `pg_restore`.
The target URL is never inferred from the source URL.

Commands never print credentials, URLs, PostgreSQL tool output, private rows,
or driver errors. PostgreSQL client credentials are passed to `pg_dump` and
`pg_restore` in child environment variables, not command arguments or a
password file. Alembic receives only the target URL via its environment.
Never enable shell tracing or save the injected environment in evidence.
Backups and sanitized snapshots should be written outside the repository in a
restricted directory. A custom-format dump still contains private database
data; encrypt it before off-provider storage and remove the unencrypted local
copy under the approved backup procedure. Upload and encryption automation are
future W6 work, not implemented here.

## Execution sequence

Run from the repository root with Python, `psycopg2`, Alembic, `pg_dump`, and
`pg_restore` available. The shown paths are examples, not default destinations.

```sh
python scripts/db_migration_restore.py inspect
python scripts/db_migration_restore.py backup --destination /secure/w5/source.dump
python scripts/db_migration_restore.py verify-backup --archive /secure/w5/source.dump --manifest /secure/w5/source.dump.manifest.json
python scripts/db_migration_restore.py restore --archive /secure/w5/source.dump --manifest /secure/w5/source.dump.manifest.json --confirm-target-restore
python scripts/db_migration_restore.py verify
python scripts/db_migration_restore.py migrate
python scripts/db_migration_restore.py verify
```

`inspect` opens read-only transactions on source and target, checks `SELECT 1`,
counts `public` tables, and reports Alembic revisions. A missing revision is
`null`. `backup` uses `pg_dump --format=custom --schema=public --no-owner
--no-privileges`; it requires a new destination file. `restore` uses
`pg_restore --exit-on-error --single-transaction --no-owner --no-privileges`
against the supplied target database. A temporary restore TOC omits only
`CREATE SCHEMA public`, since a fresh PostgreSQL database already has that
schema; the verified archive is never modified. `migrate` runs the canonical
`python -m alembic -c alembic.ini upgrade head` path against the target only.
If a restore already has the repository head revision, migration is a no-op.
Check source and target revision before parity; any intended revision change
needs explicit review because parity will report it.
`backup` also creates a companion `.manifest.json` with UTC timestamp,
Alembic revision, pg_dump version, application commit, compressed size and
SHA-256. Uncompressed size is `null` because custom-format pg_dump does not
provide it. `restore` verifies the manifest and archive checksum before it
inspects or writes the target.

## Baseline/parity handoff

After `scripts/migration_baseline.py` is integrated, capture its sanitized
snapshot through this harness and compare the two files:

```sh
python scripts/db_migration_restore.py snapshot --role source --output /secure/w5/source.json
python scripts/db_migration_restore.py snapshot --role target --output /secure/w5/target.json
python scripts/db_migration_restore.py parity --baseline /secure/w5/source.json --candidate /secure/w5/target.json
python scripts/db_migration_restore.py parity-live
```

The baseline module is included in this portability branch. `parity-live`
reads both databases in separate read-only transactions and emits a JSON
status plus a human-readable summary. It does not write snapshots to disk.
The file-based `parity` command remains available for retained private
evidence. The harness suppresses snapshot contents and emits only field names
for differences, so private IDs/hashes are not printed in logs.

## Exit status

- `0`: requested operation succeeded (`{"status":"ok",...}` on stdout).
- `1`: baseline comparison found a parity mismatch (`status=mismatch`).
- `2`: missing/invalid configuration, unavailable PostgreSQL tool, nonempty
  restore target, failed command, invalid archive, or database error.
- `3`: structural concepts remain unsupported, or the baseline module is
  unavailable. The JSON status distinguishes `partial` from a missing dependency.

An `inspect` or `verify` success proves only connectivity and observed
revision, not a complete restore. W5 still needs a real fresh-environment
restore, the sanitized baseline comparison, artifact retrieval, application
smoke checks, and provider-specific auth/RLS checks. The unit tests use only
mocks and do not make any production or cloud claim.
