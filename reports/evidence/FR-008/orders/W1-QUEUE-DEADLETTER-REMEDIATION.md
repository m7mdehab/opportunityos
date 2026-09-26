# W1-QUEUE-DEADLETTER-REMEDIATION — Stabilize persisted dead-letter test setup

## Deliverable

Investigate the single failure from `W1-WAVE-VERIFY-R2`: `TestPostgresQueueDurability.test_dead_letter_handling` left its job `RUNNING` instead of reaching `DEAD_LETTER`. Make a test-only correction so each simulated worker crash is represented by an explicitly persisted, already-expired lease before the next recovery claim. Assert persisted status, owner, and retry count at each handoff so the test proves the dead-letter threshold rather than depending on a zero-second lease timing boundary.

Do not change production queue behavior. If investigation finds evidence of a production defect instead of a test-setup issue, stop before implementation and return the finding for a new Master work order.

## Acceptance commands

1. Set `OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_wave1`, then run:
   `python -m unittest worker.test_postgres_queue_durability.TestPostgresQueueDurability.test_dead_letter_handling -v`
   - Expected: exit 0; the persisted job advances through the retry threshold and reaches `DEAD_LETTER`.
   - Evidence: `reports/evidence/FR-008/orders/W1-QUEUE-DEADLETTER-REMEDIATION-focused.txt`
2. `python scripts/check_repository.py`
   - Expected: exit 0 with `Repository integrity checks passed.`
   - Evidence: `reports/evidence/FR-008/orders/W1-QUEUE-DEADLETTER-REMEDIATION-repository.txt`
3. `git diff --check`
   - Expected: exit 0 with no whitespace errors.
   - Evidence: `reports/evidence/FR-008/orders/W1-QUEUE-DEADLETTER-REMEDIATION-diff-check.txt`

## Allowed files

- `worker/test_postgres_queue_durability.py`
- `reports/evidence/FR-008/orders/W1-QUEUE-DEADLETTER-REMEDIATION-*.txt` (unedited acceptance output only)

## Frozen files and actions

All production code, other source/tests/fixtures, migrations, prior work orders, and raw evidence. Do not access repository `private/`, profile/CV artifacts, hosted services, shared Supabase staging, or databases other than the named local disposable target. Do not run the full suite in this remediation slice, do not rerun the failed R2 order, and do not push or merge from the implementer worktree.

## Test database

`opportunityos_fr008_wave1` (`postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_wave1`), the existing local disposable FR-008 test database. No other process is using it.

## Worktree

Use a clean isolated implementer worktree from the authoritative code base below. Commit locally only.

## Authoritative code base

`2a40a64` on `work/fr008-incremental-delivery`.
