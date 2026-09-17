# FR-007 production migration preflight and cutover contract

This is a rehearsal and acceptance harness for PostgreSQL, including Supabase
PostgreSQL when a direct connection is available. The disposable CI run proves
the code against PostgreSQL. It does not prove Supabase connectivity, hosted
artifact retrieval, production data parity, or traffic cutover.

## Schema truth and parity scope

The canonical migration chain is `storage/migrations/versions/0001` through
`0006_feed_projection`, with `storage/models.py` as the ORM inventory.
`opportunities`, `field_provenances`, `match_evaluations`,
`source_poll_runs`, `founder_opportunity_views`, `founder_triage_states`,
`founder_filter_settings`, `founder_facets`, `founder_saved_views`,
`founder_feedback`, `feed_projection`, and `artifact_cache` are persisted.
Evaluation rows bind `opportunity_id` and `truth_pack_hash`; feed rows bind
`opportunity_id`, `opportunity_content_hash`, and `truth_pack_hash`. The
baseline checks their counts, available identities, decisions, NULL-sensitive
fields, uniqueness, duplicates, and orphan references. The cutover runner
reports feed projection parity independently as well.

There is no canonical `source_states`, `sources`, or `source_occurrences`
table in this migration chain or ORM. `source_poll_runs.source_id` is a poll
history field, not a substitute for a source registry or occurrence identity.
These three concepts remain `UNSUPPORTED` in structural parity. The same
applies to any other baseline concept absent at the actual revision. A
source/target match with unsupported concepts is `PARTIAL`, never `PASS`.

The migrations currently require no external PostgreSQL extension. They use
built-in PostgreSQL features, including full-text search types and indexes.
If this changes, update the explicit required-extension list in
`scripts/production_db_preflight.py` with the migration that requires it.

## Production configuration and commands

Inject secrets through the runtime secret store. The values below are names,
not example connection strings; do not paste DSNs into shell history, CI
variables visible to untrusted jobs, command arguments, or Git evidence.
The source and target must be different databases.

```text
OPOS_SOURCE_DB_URL = injected direct source PostgreSQL DSN
OPOS_TARGET_DB_URL = injected direct target PostgreSQL DSN with sslmode=verify-full (or require)
```

Use the provider's direct database endpoint and its documented certificate
configuration. A transaction or session pooler is blocked for migrations.
The runner cannot independently identify every proxy: `--connection-mode
direct` is an explicit operator declaration, recorded as unverified. Validate
the endpoint in the provider control plane before using it. The SQL preflight
reports the declared direct mode as `PARTIAL` until that independent check.
TLS must be active
and required by the DSN. `--allow-insecure-local` is accepted only for
loopback disposable PostgreSQL and must not be used for production.

First inspect the untouched target:

```bash
python scripts/production_db_preflight.py --connection-mode direct
```

Preflight uses a repeatable-read, read-only transaction. It checks server
version (PostgreSQL 14+), TLS, declared connection mode, extensions,
database/schema CREATE and USAGE privileges, public schema ownership,
Alembic presence, existing public objects, transaction support, search path,
UTC timezone, standard strings, default transaction read-only setting,
statement/lock timeouts, and database size if readable. Non-ownership of
`public` is `PARTIAL` when CREATE privileges still exist; storage size
unavailability is also `PARTIAL`. Existing objects, a pooler declaration,
inadequate privileges, or unsafe connection/session settings block execution.
The check cannot prove available disk quota or future provider throttling.

After application writes to the **source** are paused and **target** writes
are disabled by the actual deployment mechanism, use a fresh empty output
directory and a fresh target database:

```bash
python scripts/production_migration_cutover.py \
  --output-dir /secure/local/fr007-run \
  --connection-mode direct \
  --artifact-backend postgres_payload \
  --acknowledge-source-writes-paused \
  --acknowledge-target-writes-disabled \
  --confirm-target-restore
```

The output directory contains a database archive, backup manifest, sanitized
source/target structural snapshots, artifact manifest, and provider-exit
bundle. Keep it outside Git and protect it as a database backup; the archive
contains private data even though the JSON reports do not. The script never
uploads it or changes DNS/API/frontend routing.

The custom-format archive contains schema, rows, and Alembic state. Therefore
the safe executable order is preflight → source baseline → backup → manifest
and checksum → **empty-target restore** → `alembic upgrade head` → revision
verification → structural/feed parity → artifact checks. The
`target_migration` stage records `NOT_RUN` while the archive is being restored,
then records its outcome after restore. Migrating the empty target before
import would make the current schema-bearing restore fail because it requires
an empty target. No data-only import path is asserted here.

For a Supabase Storage or other external artifact backend, canonical artifact
location data and a reader contract are not yet available. Passing another
`--artifact-backend` value yields `PARTIAL` metadata and `BLOCKED` body proof.
It cannot authorize production cutover. The PostgreSQL payload backend reads
the canonical `artifact_cache.payload`, hashes bytes, and never prints bodies.

## Acceptance, rollback, and retry

Each stage is `PASS`, `PARTIAL`, `NOT_RUN`, `BLOCKED`, or `FAIL`.
`PASS` requires actual execution of that check. A missing schema concept,
metadata-only artifact, or unavailable size metric stays `PARTIAL`.
The runner exits 0 on complete `PASS`, 3 on `PARTIAL`, 2 on `BLOCKED`, and 1
on `FAIL`. `--allow-partial` is only for a disposable CI fixture and changes
the process exit, never the report. A preflight block or failed prerequisite
stops all dependent stages. Review the JSON report and its
`rollback_decision`; the script never performs traffic cutover.

Keep the source authoritative and target writes disabled until the Owner
accepts revision, structural/feed parity, artifact metadata and **body**
retrieval, and the application smoke checks. If verification fails before
cutover, isolate the failed target, keep source traffic on source, verify the
backup manifest/checksum, diagnose, and retry using a **new** empty target.
Never rerun restore over a partially populated target or use `--clean`.

Only after acceptance should the deployment owner switch DNS/API/frontend
traffic. Record the previous routing values and a post-cutover smoke result.
If smoke fails, reverse routing to the still-authoritative source, isolate the
target, confirm source readiness, and preserve the archive and report for
diagnosis. Any writes admitted to the new target after traffic switch require
an explicit reconciliation decision before a later retry; this harness does
not assume automatic reverse replication. Provider-specific DNS, write
disablement, storage transfer, and rollback mechanisms must be supplied by
the actual deployment runbook, not inferred here.
