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

## Founder-testable state

Repository slices exist for privacy-safe gold-review contracts and verified capability evidence. No new live application surface has been deployed; Founder-testable progress remains 0% pending a permitted FR-008 preview environment and later gold-review workflow.
