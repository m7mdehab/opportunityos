# FR-007 disposable PostgreSQL portability proof

`scripts/live_portability_proof.py` is the one-command W7 proof runner. It
requires separate environment-injected `OPOS_SOURCE_DB_URL` and
`OPOS_TARGET_DB_URL`, an already migrated/seeded source, an empty target
`public` schema, `pg_dump`, `pg_restore`, Alembic, and a new empty restricted
output directory. The target cannot be the source. Run only after explicitly
selecting a disposable/fresh target:

```sh
python scripts/live_portability_proof.py --output-dir /secure/proof-run --confirm-target-restore
```

It reports `PASS`, `PARTIAL`, `NOT_RUN`, or `FAIL` separately for backup,
manifest, checksum, restore, revision, structural parity, artifact metadata,
artifact body retrieval, and provider-exit bundle. Its JSON stdout contains
only safe counts, filenames, status names, and unsupported concept names. It
never prints DSNs, row content, or artifact bytes. Exit 0 requires all stages
PASS. Exit 3 means PARTIAL; exit 1 means FAIL. A disposable CI job may add
`--allow-partial` to make an explicitly expected partial proof a green job;
the report remains PARTIAL. This does not turn an unsupported check into PASS.

The real PostgreSQL test at `scripts/test_live_portability_postgres.py` is
gated by `OPOS_LIVE_PROOF_TEST=1`. It migrates and seeds a disposable source
database with synthetic data, invokes the command above against a fresh target,
and checks the actual `pg_dump`/manifest/restore/parity/artifact/bundle path.
It also probes corrupted archives, wrong checksums, same source/target,
nonempty target, absent manifest, malformed DSN, secret redaction, unsupported
parity, and artifact missing/metadata-only/checksum states. No production data
or provider credentials are used. The fixture intentionally contains one
artifact with bytes and one metadata-only entry. The canonical schema lacks
`source_states` and other optional concepts, so structural parity and artifact
body proof remain PARTIAL while supported checks must match.

`.github/workflows/fr007-portability-proof.yml` runs only on code changes to
this lane or manual dispatch. A full runner is required for a PostgreSQL
service and native tools. There is no schedule. At four code pushes per month
and a 15-minute job ceiling, the upper-bound estimate is 60 hosted runner
minutes per month; coherent pushes reduce it. The workflow creates two
distinct databases in one disposable PostgreSQL 16 service. It uses an
ephemeral per-run password, never a reusable secret. Full guard runs when
`FOUNDER_NAME_PATTERNS` is available; otherwise the log explicitly shows the
local structural scan with `--allow-missing-patterns`.

This CI proof demonstrates the harness against disposable PostgreSQL. It is
not proof of a production Supabase migration, off-provider encrypted transfer,
RLS/auth behavior, production artifacts, or a cloud restore. Those require
separately authorized real environments and persisted operational evidence.
