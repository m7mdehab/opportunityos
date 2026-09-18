# FR-007 provider-exit export and verification

This is a deterministic contract for a later real provider-exit drill. It
does not upload data or assert that a restore occurred. Use a restricted local
directory outside Git for all outputs. Database dumps contain private data and
must be encrypted before off-provider transfer. Keys and credentials remain in
separate secret stores; the bundle contains only configuration variable names.

## 1. Export

Inject distinct `OPOS_SOURCE_DB_URL` and `OPOS_TARGET_DB_URL` privately. The
source is read-only for inspection and pg_dump. From the repository root:

```sh
python scripts/db_migration_restore.py inspect
python scripts/db_migration_restore.py backup --destination /secure/exit/source.dump
python scripts/artifact_integrity.py manifest --role source --output /secure/exit/artifacts.json
python scripts/portability_bundle.py create --backup /secure/exit/source.dump --backup-manifest /secure/exit/source.dump.manifest.json --artifact-manifest /secure/exit/artifacts.json --output /secure/exit/bundle.json
```

The custom PostgreSQL dump covers `public`, including canonical metadata and
current `artifact_cache` bytea bodies. The backup manifest records revision,
tool version, UTC time, size, commit and SHA-256. The artifact manifest records
only opaque cache keys, byte counts, body hashes, and retrieval status. The
bundle binds the two manifests and dump with sizes/checksums and records the
required runtime configuration *names*, never values. Private truth or
provider-specific object-store contents outside PostgreSQL need a separately
approved encrypted transfer. A `metadata_only` artifact causes exit 3; do not
interpret that inventory as retrieval PASS.

## 2. Transfer

Encrypt the directory with the approved external encryption procedure and
transfer the encrypted files to independent storage. Preserve all four files
with their names. Do not commit or email raw dumps, manifests, or snapshots.
Transfer and encryption tooling are not implemented here, so W6 off-provider
storage remains unproven until operated and evidenced.

## 3. Integrity verification

After decrypting into a restricted fresh directory:

```sh
python scripts/portability_bundle.py verify --bundle /secure/exit/bundle.json
python scripts/db_migration_restore.py verify-backup --archive /secure/exit/source.dump --manifest /secure/exit/source.dump.manifest.json
```

Both commands fail non-zero on missing, corrupt, mismatched, or substituted
files. The bundle checksum is an integrity check, not a signature or proof of
origin. Authenticate the transferred bundle through the approved channel.

## 4. Fresh target creation

Create a fresh PostgreSQL database or Supabase project through its authorized
provider controls. Inject its separate target DSN privately. The target
`public` schema must have zero base tables. No account creation or cloud
provisioning is performed by these scripts.

## 5. Restore

```sh
python scripts/db_migration_restore.py restore --archive /secure/exit/source.dump --manifest /secure/exit/source.dump.manifest.json --confirm-target-restore
```

Restore is refused without the acknowledgement, a valid archive checksum, or
an empty target `public` schema. It uses one transaction and no `--clean` or
`--create` option. The temporary restore TOC omits only creation of the
already-present default `public` schema.

## 6. Migration and revision validation

```sh
python scripts/db_migration_restore.py inspect
python scripts/db_migration_restore.py migrate
python scripts/db_migration_restore.py verify
```

Compare source and target Alembic revisions explicitly. A migration to a new
revision may legitimately fail same-revision parity; review that change and
capture new source/target evidence at a common revision before declaring
parity.

## 7. Database parity

```sh
python scripts/db_migration_restore.py parity-live
```

Exit 0 means all declared checks are supported and match, exit 1 means
mismatch, exit 2 means inspection/configuration failure, and exit 3 means
unsupported concepts remain. `null` means a schema concept is unsupported,
not zero or PASS. Full row content equality and private fields are intentionally outside
the sanitized parity contract.

## 8. Artifact validation

```sh
python scripts/artifact_integrity.py verify --role target --manifest /secure/exit/artifacts.json
```

The verifier reads actual PostgreSQL `artifact_cache.payload` bytes and
compares their SHA-256 hashes and sizes. It separately reports referenced,
retrievable, missing, mismatched, and metadata-only counts. Exit 0 means all
referenced bodies are retrievable and matched; exit 1 means loss or mismatch;
exit 3 means metadata-only or unsupported backend; exit 2 means an inspection
error. The current schema has no canonical external object-store location
column, so external bucket retrieval is explicitly unsupported. A future
adapter must establish a canonical location/checksum contract before it can
claim object-store parity.

Real source/target PostgreSQL credentials, a fresh target, an encrypted
off-provider transfer, and real artifact-store access are still required for
an actual W5/W6 restore and provider-exit proof.
