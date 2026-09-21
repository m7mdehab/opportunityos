# W22.6 Zero-Dollar Database Capacity Correction Report

## Status

**BLOCKED** — the repository correction and deterministic verification are complete, but this lane has no authenticated hosted Supabase maintenance connection. The controlled live compaction, fresh write-capability proof, queue recovery, FULL monitor, and issue #137 RESOLVE therefore remain unexecuted. No paid infrastructure was introduced and no seven-day soak is claimed.

## Branch and preservation

- Branch: `work/fr007-overseer-storage-budget-correction`
- Starting hosted evidence: W22.5 clean proof run `35654469231`
- W22.5 takeover branch was not modified.
- No merge performed.

## Implemented storage correction

- Added Alembic migration `0016_capacity_archive`.
- Added `opportunity_cold_archive` with zlib payload, compressed-byte SHA-256, original size, content hash, archive version, and timestamp.
- Added repository-managed `plan` and explicit-confirmation `apply` maintenance operations.
- Eligibility is restricted to current-pack `ineligible` opportunities with no founder feedback, triage state, view history, outbound action, or existing archive.
- Hot opportunity identity rows remain; source description/raw payload/provenance are losslessly archived before hot duplication is cleared.
- Synthetic `truth_pack_hash='active'` projections are removed only for opportunities with no founder history.
- Projection `search_text/search_tsv` duplication is cleared; PostgreSQL feed search uses the authoritative opportunity search vector.
- Archive verification checks compressed SHA-256 and decompresses the payload identity.
- Maintenance is idempotent through archive primary-key conflict handling and explicit eligibility.

## Capacity guard

Added `scripts/db_capacity_guard.py` and wired it into scheduler and `evaluate_new` coalescing paths.

- Read-only or recovery mode blocks heavy work before queue/schedule mutation.
- Database size above 425 MiB blocks heavy work.
- 350 MiB emits warning status.
- 400 MiB is the acceptance target.
- Diagnostics contain only numeric capacity and sanitized state; DSNs and data are not emitted.

## Disposable/local proof

Passing:

- `python -m unittest scripts.test_db_capacity_guard scripts.test_db_capacity_maintenance storage.test_feed_query storage.test_feed_projection_service -q` — 16 passed
- `python -m unittest opportunity.test_persistence matching.test_evaluate_persist worker.test_worker worker.test_runner storage.test_feed_projection_service storage.test_feed_query scripts.test_db_capacity_guard scripts.test_db_capacity_maintenance -q` — 64 passed
- `python -m compileall -q storage worker opportunity matching scripts`
- `python scripts/check_repository.py`
- `python scripts/check_guard.py --allow-missing-patterns`
- `git diff --check`
- Alembic offline SQL generation through `0016_capacity_archive` succeeded and produced PostgreSQL DDL without secrets or psql directives.

Disposable PostgreSQL execution is unavailable in this environment (no Docker/local PostgreSQL). The existing CI disposable PostgreSQL surface remains the required independent proof for migration execution.

## Live footprint entering W22.6

Provider-verified entering snapshot:

- Supabase Free Plan
- `pg_is_in_recovery() = false`
- `default_transaction_read_only = on` from provider configuration
- database size: `1,576,176,787` bytes / approximately `1503 MiB`
- `feed_projection`: approximately `865 MB`
- `opportunities`: approximately `330 MB`
- `field_provenances`: approximately `149 MB`
- `match_evaluations`: approximately `135 MB`
- `founder_cv_selections`: approximately `10 MB`

Live before/after maintenance sizes: **NOT EXECUTED in this lane** because the hosted secret/maintenance connection is unavailable. No fabricated after-size or reclaim claim is made.

## Hosted execution state

- Read-only maintenance dry-run: **NOT EXECUTED by this lane**; requires the authenticated hosted connection.
- Controlled repository-managed compaction: **NOT EXECUTED**; must not be launched while provider read-only/quota state is active without the Overseer’s authorized session-scoped maintenance capability.
- Fresh write-capability proof: **NOT EXECUTED**.
- Natural recovery of five expired leases: **NOT EXECUTED**.
- Bounded queue convergence: **NOT EXECUTED**.
- Final protected five-shard proof: **NOT EXECUTED**.
- FULL monitor: **NOT EXECUTED**.
- Issue #137 normal `RESOLVE`: **NOT EXECUTED**.

The W22.5 clean proof remains preserved: max worker connections 10, persistent idle-in-transaction 0, unattributed 0, observer failures 0.

## External blocker

The remaining blocker is authenticated provider execution authority for the Supabase maintenance session and subsequent runtime workflows. The live target is provider-enforced read-only because it exceeds the Free Plan quota; this is not evidence of a read replica. The Overseer must execute the repository-managed plan/apply path using the provider-supported session-scoped write maintenance capability, verify `<=400 MiB` on a fresh normal connection, then run recovery and monitoring.

## Safety confirmations

- No Supabase upgrade or recurring spend introduced.
- No `OPOS_TARGET_DB_URL` change made.
- No worker status/backlog rows manually edited.
- No source truth or founder history silently discarded; archived payloads are compressed and checksum-bound.
- Seven-day soak has not elapsed and is not claimed.
