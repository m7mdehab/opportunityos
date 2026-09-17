# FR-007 migration acceptance package

This package supplies a production command and a machine-readable **migration
evidence report**. It does not turn a disposable PostgreSQL CI result into a
Supabase or production PASS. The canonical FR-007 acceptance table is in
`briefs/BRIEF-FR-007.md` §5; generated `docs/STATE.md` is an operational
handoff, not independent evidence that any A-gate is closed.

## Gate map

`Y` means the gate needs that input to be closed. `Executable now` means a
repository check exists; it does not mean the gate has passed. The JSON
report carries all A-0…A-17 entries, their dependencies, and a gate status.

| Gate | Migration-relevant executable check | Executable now | Source DB | Target DB | Artifact store | Cloud deployment | Soak |
|---|---|---|---|---|---|---|---|
| A-0 | Mandatory suites, repository and guard CI; outside this command | Y |  |  |  |  |  |
| A-3 | Target SQL plan inspection; outside this command | Y |  | Y |  |  |  |
| A-6 | Duplicate canonical opportunity check; stable occurrence/repeated polling still unproved | Y, partial | Y | Y |  | Y |  |
| A-8 | No canonical persisted cadence/cooldown state to verify yet | N |  | Y |  | Y |  |
| A-9 | Source/target snapshot, identities, evaluations, founder state, feed projection | Y, partial | Y | Y |  |  |  |
| A-10 | Secret guard in CI; RLS and runtime logging outside this command | Y, partial |  | Y |  | Y |  |
| A-11 | Artifact metadata and PostgreSQL payload retrieval/checksum; hosted storage and restart proof remain | Y, partial |  | Y | Y | Y |  |
| A-12 | Fresh restore, revision and structural checks; auth/feed/search/detail smoke remain | Y, partial |  | Y | Y | Y |  |
| A-15 | Provider-neutral backup, manifest, restore, and exit bundle; actual provider exit remains | Y, partial | Y | Y | Y |  |  |
| A-14 | Seven-day production reliability soak | N |  |  |  | Y | Y |

Other gates are mapped in report JSON and remain `NOT_RUN` by this command.
They require runtime, source-policy, frontend, monitoring, and/or cost evidence
outside migration tooling. `PARTIAL` in the table describes a capability
boundary, not an A-gate PASS.

## Schema conclusion for source concepts

The source registry is committed `docs/SOURCE_REGISTRY.yaml`, read by
`opportunity/registry.py` and `worker/scheduler.py`. It is not a persisted
`sources` table. `opportunities.source_id` and `source_poll_runs.source_id`
record source labels and polling history; they do not prove a unique stable
source-item occurrence or durable cadence/next-due/cooldown state. The ORM
`storage/models.py` and Alembic revisions `0001`–`0006` contain no
`sources`, `source_states`, or `source_occurrences` model/table. The baseline
retains those three concepts as unsupported. No substitute table is invented.
Consequently A-6's source-occurrence clause and A-8 cannot be closed by this
package, even when the database copy matches exactly.

## Direct real-run procedure

The runtime injects `OPOS_SOURCE_DB_URL` and `OPOS_TARGET_DB_URL` as secrets.
They must resolve to **distinct** PostgreSQL databases. Use a direct target
endpoint, TLS with `sslmode=verify-full` (or `require` if certificate-chain
verification is handled by the deployment contract), and an empty fresh
target. The migration role needs public-schema CREATE/USAGE. Never place a
literal DSN in command arguments, logs, Git evidence, or the report directory.
For private `artifact_cache.payload`, choose `postgres_payload`; an external
Supabase Storage backend remains unsupported until canonical artifact location
and provider retrieval credentials are supplied through a separate contract.

Read-only preview, using a separate fresh output directory:

```bash
python scripts/migration_acceptance.py --dry-run \
  --output-dir /secure/local/fr007-preview \
  --connection-mode direct --artifact-backend postgres_payload
```

After source writes are paused and target writes are disabled by the actual
deployment controls, execute once against a **new empty** output directory:

```bash
python scripts/migration_acceptance.py \
  --output-dir /secure/local/fr007-production \
  --connection-mode direct --artifact-backend postgres_payload \
  --acknowledge-source-writes-paused \
  --acknowledge-target-writes-disabled \
  --confirm-target-restore
```

The command runs preflight → sanitized source baseline → custom-format backup
→ manifest/checksum → fresh-target validation → restore → Alembic migration
and revision check → structural/evaluation/feed/triage parity → artifact
metadata/body checks → acceptance report. The archive contains schema and
Alembic state, so migration runs **after** restore; running it before restore
would violate the fresh-target contract.

Expected files in the output directory: `database.dump` (private database
content), its `.manifest.json`, `source-baseline.json`, `target-baseline.json`,
`artifacts.json`, `provider-exit.json`, and `acceptance.json`. Protect the
directory as a production backup. Only the JSON report is suitable for
machine review; it contains counts, hashes, fingerprints, and states, never
descriptions, Truth Pack content, artifact bodies, or DSNs. Do not commit
real-run output. Branch CI/evidence lives at
`reports/evidence/FR-007/codex-migration-acceptance.txt` and uses synthetic
fixtures only.

`acceptance.json` has independent stage states, A-gate states, source/target
fingerprints, commit, revisions, checksum, per-table count status, separate
canonical identity digest status, evaluation decisions,
projection counts, artifact results, unsupported concepts, and an explicit
`ACCEPT`/`REJECT` decision. The command exits 0 for `ACCEPT`, 1 for a failed
stage, 2 for a blocked stage, and 3 for incomplete/partial evidence. Dry run
never restores and cannot accept. The report always says
`traffic_cutover_authorized: false`; Owner must review it and the remaining
FR-007 gates before traffic moves. Presently the canonical missing source
concepts and unverified direct endpoint keep automated acceptance at
`REJECT` even after a matching restore.

Any failed or blocked stage triggers rollback: keep the source authoritative,
isolate the failed target, verify backup/manifest integrity, and retry only in
a new empty target. Do not restore over a partially populated target. If
traffic has already switched and smoke fails, restore previous routing to the
source, isolate target writes, and reconcile any target-only writes explicitly.
No DNS, API, frontend, or provider control-plane switch is performed by this
command.
