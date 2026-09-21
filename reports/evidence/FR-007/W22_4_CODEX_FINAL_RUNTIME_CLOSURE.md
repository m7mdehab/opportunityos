# W22.4 Runtime Closure Evidence

## Status

BLOCKED: deterministic corrections are implemented and green, but protected hosted takeover proof has not reached acceptance. The live five-shard run remains in progress/previously timed out on shard execution and therefore cannot prove zero persistent idle transactions, zero new EMAXCONNSESSION, zero new persistence UniqueViolation, queue convergence, monitor PASS/WARN, or incident #137 resolution.

## Repository

- Branch: work/fr007-codex-runtime-takeover
- Starting takeover SHA: 605fad8841efe7008e467c02634c31617c619c4b
- Final local SHA before evidence commit: 030c20600a11b4ff0efffce674c5b44926b5d14e
- PR: #139, unmerged

## Root causes and corrections

- Foreground idle-in-transaction: worker claim commits while SQLAlchemy expires the claimed ORM row; dispatch field access lazily refreshed it and retained a transaction during network work. Worker-only factories now use expire_on_commit=False. A regression proves a slow handler starts with no foreground transaction.
- Persistence race: lookup-then-insert could race on the same opportunity/provenance identity. PostgreSQL poll-source persistence now acquires a transaction-scoped advisory lock derived from source_id after remote acquisition and before persistence/evaluation. SQLite tests retain their existing behavior.
- Worker pool/session count and five-shard workflow were not reduced or threshold-weakened.

## Changed files

- storage/engine.py
- worker/__main__.py
- scripts/fr007_hosted_bootstrap.py
- worker/handlers.py
- worker/test_runner.py
- docs/STATE.md
- reports/evidence/FR-007/W22_4_CODEX_FINAL_RUNTIME_CLOSURE.md

## Deterministic evidence

- `python -m unittest worker.test_runner opportunity.test_persistence -v`: 26 passed.
- `python -m unittest worker.test_worker worker.test_runner worker.test_postgres_queue_durability scripts.test_w17_runtime_workflows scripts.test_fr007_cloud_monitor scripts.test_fr007_connection_pressure scripts.test_fr007_reliability_proof -v`: 164 passed, 18 skipped because no local PostgreSQL DSN was configured.
- `python -m unittest worker.test_runner.TestWorkerRunner.test_worker_runtime_factory_does_not_open_transaction_before_slow_handler -v`: 1 passed.
- Python compile checks: passed.
- Repository integrity: passed.
- Guard: passed.
- git diff --check: passed.
- State regenerated with STATE_PRESERVE_TIMESTAMP=1; pending evidence commit.

## Hosted proof

- Run 35619944610 (SHA 1b913ba): deterministic and enqueue passed; observer passed; two drain shards exceeded the 35-minute job timeout; summarize failed because the matrix was cancelled.
- Run 35620088135 (SHA 030c206): deterministic and enqueue passed; latest five-shard hosted proof was still running when evidence was captured.
- The hosted proof has not established the required final connection, persistence, queue, monitor, or incident gates.

## Unresolved

- No local PostgreSQL/Supabase DSN is available for direct concurrency proof.
- Protected staging proof has not reached a terminal acceptance result.
- Queue recovery, FULL monitor, and normal RESOLVE closure of issue #137 were not executed to acceptance.
- The seven-day soak has not elapsed.

This report intentionally does not claim runtime closure or FR-007 closure.

