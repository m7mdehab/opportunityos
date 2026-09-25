# W1-QUEUE-TIMING-REMEDIATION — Stabilize queue durability test setup

## Deliverable

Remove two timing-sensitive fixtures in `worker/test_postgres_queue_durability.py` without changing queue production behavior. In `test_concurrent_stale_lease_recovery_skip_locked`, establish persisted expired leases using PostgreSQL time, then retain the concurrent `SKIP LOCKED` proof that each worker claims a distinct job; use a synchronization window robust to ordinary local scheduling delays. In `test_guarded_completion_rejects_stale_worker`, use a nonzero lease, persist and verify its expiry with PostgreSQL time from a fresh session, then prove a second worker takes ownership and the stale worker cannot complete the job.

## Acceptance commands

Set `OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_queue_repair` for the PostgreSQL-backed command.

1. `python -m unittest worker.test_postgres_queue_durability -v`
   - Expected: exit 0; all module tests pass, including distinct concurrent stale-lease claims, persisted lease recovery, and guarded stale-worker completion.
   - Evidence: `reports/evidence/FR-008/orders/W1-QUEUE-TIMING-REMEDIATION-queue-tests.txt`
2. `python scripts/check_repository.py`
   - Expected: exit 0 with `Repository integrity checks passed.`
   - Evidence: `reports/evidence/FR-008/orders/W1-QUEUE-TIMING-REMEDIATION-repository.txt`
3. `git diff --check`
   - Expected: exit 0 with no whitespace errors.
   - Evidence: `reports/evidence/FR-008/orders/W1-QUEUE-TIMING-REMEDIATION-diff-check.txt`

## Allowed files

- `worker/test_postgres_queue_durability.py`
- `reports/evidence/FR-008/orders/W1-QUEUE-TIMING-REMEDIATION-*.txt` (unedited acceptance output only)
- Disposable PostgreSQL database `opportunityos_fr008_queue_repair` only

## Frozen files and actions

All production worker/queue code, other tests and fixtures, briefs, previous evidence, hosted project data, private Founder data, and mirror inputs. Do not access repository `private/`, local CVs, or any shared/hosted database. Do not run the integrated full suite here; the next wave verification owns the single full-suite run. Preserve R6 raw evidence unchanged.

## Test database

`postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_queue_repair`, created locally and verified to contain zero public tables before dispatch. Its name avoids the suite's `opportunityos_test_*` cleanup sweep.

## Worktree

Create a clean isolated implementer worktree from the exact authoritative source base below. Do not push or merge from the implementer worktree.

## Authoritative source base

`752c2e8` on `work/fr008-incremental-delivery`.
