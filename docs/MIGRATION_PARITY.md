# FR-007 migration parity

`scripts/migration_baseline.py` exports a fixed, structural snapshot of the
canonical PostgreSQL schema. Parity means the before and after snapshots have
the same Alembic revision, table counts, evaluation coverage by truth-pack
hash, integrity counts, and first 32 opportunity ID/content-hash pairs ordered
by ID. A match proves these bounded facts, not full row-by-row data equality.
The source database must be quiescent or a count change can be legitimate but
will fail parity. Investigate every difference before cutover.

## Snapshot

Use Python with `psycopg2` installed. Supply `OPPORTUNITYOS_DB_URL` through a
private environment, never in a command argument, committed file, or evidence.
Point it at a least-privilege PostgreSQL reader. From the repository root:

```sh
python scripts/migration_baseline.py snapshot > baseline.json
```

Run the same command against the migrated database to produce `candidate.json`.
The inspection opens a repeatable-read, read-only transaction and rolls it back.
It queries only allowlisted table/column metadata, counts, truth-pack hashes,
and bounded opportunity identity/hash samples. A missing optional table or
column is represented by `null`. It never runs migrations or writes data.

The snapshot intentionally never exports Founder Truth Pack contents, names or
profile text, descriptions, raw payloads, credentials, database URLs, CVs,
artifact bodies, notes, messages, or source payloads. Opportunity IDs and
content hashes and truth-pack hashes are exported by design; treat snapshots as
private operational evidence. Invalid identity/hash metadata stops inspection
instead of copying unexpected content. Driver errors are redacted.

## W5 comparison

After the W5.1 import and before shadow polling or cutover:

```sh
python scripts/migration_baseline.py compare baseline.json candidate.json
```

Exit `0` and `PARITY PASS` mean the fixed contract matched. Exit `1` means a
deterministic mismatch. Exit `2` means invalid input, configuration, driver,
or database inspection failure. Differences identify fields but never print
stored values. No count, missing-table, sample, invariant, or Alembic-revision
allowance is built in. A deliberate migration-stage difference needs separate
documented review and fresh snapshots once both sides reach the same schema;
this tool does not silently discard it.

Counts include canonical opportunities, field provenance, evaluations, source
polls/state when present, founder views/triage/saved configuration, outbound
actions and reservations, application-related event metadata, artifact cache,
worker jobs, and feed projection. Integrity checks cover duplicate evaluation
and action identities and orphaned opportunity references where columns exist.
`null` means the check cannot be inspected in that schema, distinct from zero.
Current schema has no canonical `sources`, `source_states`, or
`source_occurrences` tables; those counts/checks remain explicit `null` until
such tables and known identity columns are introduced. This snapshot cannot
verify artifact object-store body presence or application payload equality;
W5 needs separate private restore/smoke evidence for those.
