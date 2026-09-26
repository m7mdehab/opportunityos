# W1-BASELINE-TEST-REMEDIATION — Resolve integrated verification failures

## Deliverable

Repair only the three repository-owned test failures observed by `W1-WAVE-VERIFY-R1`:

1. Update the PostgreSQL backup/restore table-set assertion to account for `backup_heartbeats`, a migration-owned table that is recreated by Alembic and is intentionally absent from ORM metadata and the row-data dump.
2. Correct the stale-lease precedence test setup so it first creates a genuinely RUNNING stale lease, then creates the pending backlog, and proves the stale lease is reclaimed first.
3. Make the scheduler/worker crash-recovery test seed and assert an explicitly expired persisted lease before recovery, so the test does not depend on timing at a zero-second lease boundary.

Do not change production queue behavior unless investigation proves a product defect; if so, stop before implementation and report the precise finding for a new work order. Preserve the intended behavioral assertions and test isolation.

## Acceptance commands

1. `python -m unittest storage.test_postgres_integration.PostgresProductionIntegrationTest.test_case_m_backup_wipe_restore_postgres_cycle worker.test_postgres_queue_durability.TestPostgresQueueDurability.test_stale_lease_precedence_over_pending_backlog worker.test_postgres_queue_durability.TestPostgresQueueDurability.test_7_scheduler_worker_crash_recovery -v`
   - Set `OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_wave1` in the same PowerShell session.
   - Expected: exit 0; each formerly failing acceptance case passes against this disposable database.
   - Evidence: `reports/evidence/FR-008/orders/W1-BASELINE-TEST-REMEDIATION-focused.txt`
2. `python scripts/check_repository.py`
   - Expected: exit 0 with `Repository integrity checks passed.`
   - Evidence: `reports/evidence/FR-008/orders/W1-BASELINE-TEST-REMEDIATION-repository.txt`
3. `git diff --check`
   - Expected: exit 0 with no whitespace errors.
   - Evidence: `reports/evidence/FR-008/orders/W1-BASELINE-TEST-REMEDIATION-diff-check.txt`

## Allowed files

- `storage/test_postgres_integration.py`
- `worker/test_postgres_queue_durability.py`
- `reports/evidence/FR-008/orders/W1-BASELINE-TEST-REMEDIATION-*.txt` (unedited acceptance output only)

## Frozen files and actions

All production code, other source, tests, fixtures, schemas, migrations, preferences, profile/portfolio assets, work orders, and prior raw evidence. Do not access repository `private/`, any user profile/CV artifacts, shared Supabase staging, or external services. Do not modify or overwrite the failed `W1-WAVE-R1` output. Do not change the 22 documented skips, enable other test gates, or run the full suite in this remediation slice.

## Test database

`opportunityos_fr008_wave1` (`postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_wave1`), the existing disposable FR-008 verification database. No other database may be used.

## Worktree

Use a separate isolated worktree from the authoritative FR-008 branch. Commit locally only; do not push or merge from the implementer worktree.

## Authoritative base

`4bc410f` on `work/fr008-incremental-delivery`.
