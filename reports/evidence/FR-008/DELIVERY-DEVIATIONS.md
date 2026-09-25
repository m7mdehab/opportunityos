# FR-008 delivery deviations and verification ledger

## Work-order base drift

- W1.2 declared `4043be6` but its implementer checkout started at `db22b09`. The latter is a descendant whose intervening changes update only FR-008 work-order/readiness documents; no source change was bypassed. Focused W1.2 tests, repository integrity, and diff checks passed before integration.
- W0.2 declared `25912cd` but its implementer checkout started at `ff39c53`, which includes later FR-008 integration commits and order/readiness updates. The harness was reviewed against its allowed-file scope; its focused tests, repository integrity, and diff checks passed before integration.
- W1-WAVE-VERIFY-R1 declared `4043be6` but its evidence-runner checkout started at `db22b09`, a later docs-only descendant. Guard, repository integrity, preflight, and migration succeeded; the backend suite did not.
- These base mismatches are process deviations. They are preserved here rather than rewriting historical readiness certificates. Future work orders must use the exact declared base or update the order/readiness before dispatch.

## W1-WAVE-VERIFY-R1 result

The run completed 1,566 tests with 22 skips and three failures. The complete unedited output is preserved in `W1-WAVE-R1-backend.txt`; guard and repository outputs are in the accompanying `W1-WAVE-R1-*.txt` files. Failure signatures:

1. Backup/restore expected the ORM tables plus `founder_identity`, while the migration-owned `backup_heartbeats` table was also recreated.
2. The stale-lease precedence test attempted to claim a newly enqueued job after first enqueuing a pending backlog, so the setup did not establish the intended stale lease.
3. The scheduler crash-recovery test relied on a zero-second lease boundary instead of explicitly establishing a persisted expired lease.

`W1-BASELINE-TEST-REMEDIATION` owns the bounded test-only corrections. No FR-008 full-suite checkpoint or push is considered green until the remediation acceptance and subsequent integrated Wave 1 run pass.

## W1-WAVE-VERIFY-R2 result

R2 ran once on a fresh disposable database after the three bounded test corrections. Guard, repository integrity, target preflight, migration, and diff check passed. The suite ran 1,586 tests with 22 skips and one failure: `test_dead_letter_handling` expected `DEAD_LETTER` but got `RUNNING`. The complete transcript is preserved in `W1-WAVE-R2-backend.txt`, with the companion guard/repository/diff outputs. The new failure is consistent with the remaining test's zero-second lease boundary; `W1-QUEUE-DEADLETTER-REMEDIATION` owns that test-only investigation. No Wave 1 full-suite checkpoint or push is green yet.

## Dead-letter test remediation and W1-WAVE-VERIFY-R3 result

`W1-QUEUE-DEADLETTER-REMEDIATION` changed only `worker/test_postgres_queue_durability.py`. The test now records each simulated crashed worker's lease as expired using PostgreSQL's clock, commits it, and verifies the persisted owner, retry count, running status, and expiry from a fresh session before the next recovery claim. Its focused PostgreSQL test passed; repository integrity and diff checks passed. Commit `7c0b18c` integrates the change plus its acceptance output. The first failed focused attempt is retained beside the passing evidence.

R3 ran once from exact code base `7c0b18c` using a fresh disposable database. Guard, repository integrity, target preflight (`opportunityos_fr008_wave3`), migration, and diff check passed. The full suite passed: 1,586 tests, 22 skips, no failures or errors. The unedited transcripts are preserved in `W1-WAVE-R3-{guard,repository,backend,diff-check}.txt`; this is the first green integrated Wave 1 full-suite result. The branch is reviewable and may be pushed, but FR-008 remains partial pending W1.3 and Waves 2–8.

## Founder-testable state

Repository slices exist for privacy-safe gold-review contracts and verified capability evidence. No new live application surface has been deployed; Founder-testable progress remains 0% pending a permitted FR-008 preview environment and later gold-review workflow.

## W1-WAVE-VERIFY-R4 result and evidence-capture wrapper deviation

R4 ran once from the exact source base `7dd17b5` using a fresh disposable database (`opportunityos_fr008_wave4`) and an isolated runner. Guard, repository integrity, target preflight, Alembic migration, the full backend suite, and diff check all passed. The suite passed 1,594 tests with 22 skips and no failures or errors. The unedited outputs are preserved in `W1-WAVE-R4-{guard,repository,backend,diff-check}.txt`; the backend transcript includes the acceptance command exit markers.

One PowerShell `Add-Content` command used to append a human-readable label to the evidence wrapper failed because of quoting. The acceptance commands continued, each exit marker was captured, and the raw output files were copied byte-identically from the isolated runner with hashes verified. This is a wrapper-only evidence-capture deviation; no acceptance command was rerun, no output was rewritten, and the run remains green. Future evidence wrappers should use a quoting-safe literal here-string or write the label before command execution.

## W1-WAVE-VERIFY-R5 result and compatibility-test remediation

R5 ran once from exact source base `9b0458f` against a fresh local disposable database (`opportunityos_fr008_wave5`). Mirror guard, repository integrity, database target preflight, Alembic migration, and diff check passed. The full suite ran 1,596 tests with 22 skips and three failures. The complete unedited outputs are preserved in `W1-WAVE-R5-{guard,repository,backend,diff-check}.txt`; the first run must not be repeated.

The two matching failures (`test_high_fit_employment_opportunity` and `test_gold_set_benchmark_execution`) used status-only geography labels as if they were evidence. Their fixtures need structured worldwide scope for expected remote passes and structured onsite plus verified negative authorization for the hard-negative example. The third failure was the historical FR-006 A-12 cap requiring total corpus uncertainty below 25%. Under the newer FR-008 W2.1 contract, unresolved geography must remain review-required even when an old classifier label says `eligible`; the R5 aggregate was 459/540 uncertain (85%). FR-008's explicit evidence contract supersedes that old aggregate ceiling. The bounded `W2.1-R5-TEST-RECONCILIATION` updates only synthetic benchmark fixtures and changes the frozen-corpus regression to keep reporting the aggregate while asserting that status-only rows remain uncertain and never hard-fail. It does not lower any FR-008 acceptance threshold or alter qualification production logic. The acceptance `git diff --check` passed in the isolated runner; the captured backend transcript itself contains emitted whitespace, which remains unchanged as raw evidence.

## W1-WAVE-VERIFY-R6 result and queue-test timing remediation

R6 ran once from exact source base `752c2e8` against a fresh local disposable database (`opportunityos_fr008_wave6`). Mirror guard, repository integrity, database target preflight, Alembic migration, and diff check passed. The full suite ran 1,596 tests with 22 skips and two failures. The complete unedited outputs are preserved in `W1-WAVE-R6-{guard,repository,backend,diff-check}.txt`; the first run must not be repeated.

The failures were `test_concurrent_stale_lease_recovery_skip_locked` (the 10-second two-worker synchronization barrier broke) and `test_guarded_completion_rejects_stale_worker` (the second worker could not claim immediately after a zero-second lease). Both are test setup timing assumptions in `worker/test_postgres_queue_durability.py`; production queue code is frozen. `W1-QUEUE-TIMING-REMEDIATION` will persist explicitly expired leases using PostgreSQL time before recovery assertions and extend the synchronization window while retaining the distinct-claim/guarded-completion assertions.

`W1-QUEUE-TIMING-REMEDIATION` changed only the queue durability test fixture: leases are now created with nonzero durations and explicitly expired using PostgreSQL time, verified from fresh sessions, and the concurrent barrier has a 30-second window. The full queue test module passed (17 tests), repository integrity and diff check passed. Integrated R7 is the next one-shot full-suite proof; R6 evidence remains red and unchanged.

## W1-WAVE-VERIFY-R7 result and remaining lease-boundary remediation

R7 ran once from exact source base `1dda8b6` against a fresh local disposable database (`opportunityos_fr008_wave7`). Mirror guard, repository integrity, database target preflight, Alembic migration, and diff check passed. The full suite ran 1,596 tests with 22 skips and one failure. The complete unedited outputs are preserved in `W1-WAVE-R7-{guard,repository,backend,diff-check}.txt`; the first run must not be repeated.

The failure was `test_lease_expiration_and_recovery`, which attempted to reclaim a job immediately after creating a zero-second lease. This is a remaining boundary in the same PostgreSQL queue durability test file, not a production queue failure. `W1-QUEUE-LEASE-RECOVERY-REMEDIATION` will use a nonzero lease, persist an explicit past expiry via PostgreSQL time, and verify the expired row before the second worker claims it.
