# FR-007 W22.8 Terminal Hosted Closure Report

Status: BLOCKED (external hosted provider availability)

## Branch and implementation

- Branch: `work/fr007-overseer-storage-budget-correction-v2`
- Implementation head: `af7dab053bbf329297e9a83cef278c0cc8144150`
- The closure workflow now prefers the configured `CLOUD_DATABASE_URL` endpoint, falling back to `OPOS_TARGET_DB_URL`, without printing or persisting either secret.

## Repository proof

- Cold archive unit coverage: 4 tests passed.
- Capacity guard/maintenance unit coverage: 7 tests passed.
- Repository integrity: passed.
- Guard: passed.
- Python compilation and `git diff --check`: passed.
- Disposable PostgreSQL proof in hosted run `35679994519`: passed (`deterministic-postgres`, 42 seconds).

The cold-state implementation uses checksum-verified in-memory archive payloads for scoring and does not durably re-expand archived opportunities. Existing regression coverage remains green.

## Hosted executions

The registered launcher was dispatched against the feature ref with the authoritative truth-pack hash.

| Run | Ref/SHA | Result |
|---|---|---|
| `35679517022` | `69a82e5` | failed at live preflight; target connection rejected |
| `35679819878` | `69a82e5` | failed at live preflight; repeated target rejection |
| `35679994519` | `af7dab0` | failed at live preflight; repeated rejection using `CLOUD_DATABASE_URL` fallback |

All attempts fail before migration, maintenance, worker recovery, or queue mutation. Sanitized provider error:

`psycopg2.OperationalError: connection to server at aws-0-eu-central-1.pooler.supabase.com port 5432 failed: FATAL: the database system is not accepting connections; DETAIL: Hot standby mode is disabled.`

No live write-capable session was established. Therefore no maintenance, compaction, VACUUM FULL, recovery wave, acceptance proof, monitor, or incident RESOLVE was run.

## External blocker

The registered launcher and feature-ref dispatch path work, the repository correction is pushed, disposable PostgreSQL proof is green, and both configured hosted connection secrets have been exercised without exposing their values. The provider rejects connections before SQL execution. Provider-side restoration of connection availability or a maintenance-session action is required before the mandated live maintenance and five-shard acceptance can proceed.

The seven-day soak is not claimed.
