# W1-QUEUE-LEASE-RECOVERY-REMEDIATION — Remove immediate expiry timing

## Deliverable

Stabilize `test_lease_expiration_and_recovery` in `worker/test_postgres_queue_durability.py`. Create the first worker's lease with a nonzero duration; persist an explicitly expired timestamp using PostgreSQL time; verify the committed status, owner, retry count, and expiry from a fresh session; then prove a second worker reclaims the same job and increments the retry count. Do not change queue production code.

## Acceptance commands

Set `OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_queue_recovery` for the PostgreSQL-backed command.

1. `python -m unittest worker.test_postgres_queue_durability -v`
   - Expected: exit 0; all 17 PostgreSQL queue durability tests pass, including lease recovery, distinct concurrent stale claims, and guarded stale-worker completion.
   - Evidence: `reports/evidence/FR-008/orders/W1-QUEUE-LEASE-RECOVERY-REMEDIATION-queue-tests.txt`
2. `python scripts/check_repository.py`
   - Expected: exit 0 with `Repository integrity checks passed.`
   - Evidence: `reports/evidence/FR-008/orders/W1-QUEUE-LEASE-RECOVERY-REMEDIATION-repository.txt`
3. `git diff --check`
   - Expected: exit 0 with no whitespace errors.
   - Evidence: `reports/evidence/FR-008/orders/W1-QUEUE-LEASE-RECOVERY-REMEDIATION-diff-check.txt`

## Allowed files

- `worker/test_postgres_queue_durability.py`
- `reports/evidence/FR-008/orders/W1-QUEUE-LEASE-RECOVERY-REMEDIATION-*.txt` (unedited acceptance output only)
- Disposable PostgreSQL database `opportunityos_fr008_queue_recovery` only

## Frozen files and actions

All production worker/queue code, other tests and fixtures, briefs, previous evidence, hosted project data, private Founder data, and mirror inputs. Do not access repository `private/`, local CVs, or any shared/hosted database. Do not run the integrated full suite here; the next wave verification owns the single full-suite run. Preserve R7 raw evidence unchanged.

## Test database

`postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_queue_recovery`, created locally and verified to contain zero public tables. Its name avoids the suite's `opportunityos_test_*` cleanup sweep.

## Worktree

Create a clean isolated implementer worktree from the exact authoritative source base below. Do not push or merge from the implementer worktree.

## Authoritative source base

`1dda8b6` on `work/fr008-incremental-delivery`.
