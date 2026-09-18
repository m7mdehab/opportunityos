# FR-007 hosted data-plane proof

This is the repository-owned bridge from disposable PostgreSQL proof to a real
hosted staging PostgreSQL/Supabase data plane. It wraps the existing
`production_db_preflight.py` and `migration_acceptance.py` contracts; it does
not create a second migration engine or claim production completion.

## Secret contract

Inject these names at runtime only:

* `OPOS_SOURCE_DB_URL`
* `OPOS_TARGET_DB_URL`

Values are never printed or written to evidence. The report contains only
short identity fingerprints and sanitized host names. The source and target
must be different databases. Hosted mode rejects loopback targets.

Use a Supabase **direct/session-capable database endpoint** for migration.
Transaction or session pooler endpoints are not accepted for
`MIGRATE_STAGING`; a provider's control plane still has to confirm the
endpoint topology. TLS is required (`sslmode=require`, `verify-ca`, or
`verify-full`). The existing read-only preflight checks PostgreSQL version,
TLS, privileges, schema ownership, Alembic state, target emptiness, session
settings, timeouts, and database size where available.

## Local invocation

```bash
python scripts/hosted_data_plane_proof.py \
  --mode PRECHECK --connection-mode direct \
  --output-dir /secure/fr007-run \
  --evidence /secure/fr007-run/hosted-proof.json
```

After reviewing the preflight and pausing source writes with the deployment
owner, the explicitly authorized staging run is:

```bash
python scripts/hosted_data_plane_proof.py \
  --mode MIGRATE_STAGING --connection-mode direct \
  --confirm-staging-migration \
  --output-dir /secure/fr007-run \
  --evidence /secure/fr007-run/hosted-proof.json
```

`VERIFY_STAGING` reads an existing `acceptance.json` in the output directory;
it does not perform writes. Every dependent stage stops on a blocked or failed
precondition. There is no automatic cutover or DNS/API/frontend change.

## GitHub Actions

Run **FR-007 hosted data-plane proof** through `workflow_dispatch`, selecting
`PRECHECK`, `MIGRATE_STAGING`, or `VERIFY_STAGING`. The job uses the protected
`fr007-staging` environment and the two secret names above. It has no
push/PR trigger, so ordinary CI cannot run a destructive mode. The uploaded
`report.json` is sanitized operational evidence.

## Evidence and acceptance boundary

The report distinguishes `PRECHECK`, `MIGRATE`, `VERIFY`, and
`CUTOVER_READY`, with `PASS`, `PARTIAL`, `NOT_RUN`, `BLOCKED`, or `FAIL` states.
`CUTOVER_READY` is only a partial readiness signal; this packet never performs
traffic cutover. A real source-to-hosted-target run with credentials is needed
for FR-007 A-9 evidence. Unit tests, disposable PostgreSQL, or a PRECHECK do
not close A-9 and do not prove Supabase migration.

If verification fails, keep the source authoritative, isolate the target, and
retry only with a new empty target after checking the backup manifest. Any
post-cutover rollback and traffic routing remain deployment-owner actions.
