# W1-WAVE-VERIFY-R6 Readiness Certificate

- Work order: `W1-WAVE-VERIFY-R6`.
- Authoritative integrated base SHA: `752c2e8` on `work/fr008-incremental-delivery`.
- Dependency status: R4 passed once with 1,594 tests and 22 skips. R5 ran once and is preserved as 1,596 tests, 22 skips, and three failures. The two benchmark fixtures now carry structured geography. The obsolete FR-006 aggregate uncertainty ceiling was replaced with a W2.1 status-only uncertainty regression; the focused 41-test group, committed-corpus regression, repository integrity, and diff check all passed.
- External resources: none. The runner uses only the new local disposable PostgreSQL database below.
- Execution surfaces: Python 3.12, PostgreSQL 16, repository test dependencies, Git, and a new isolated evidence-runner worktree are available.
- Secret-injection path: none; the local test DSN has no password or production credential.
- Cost/quota/terms status: no external paid resource, provider access, or hosted mutation.
- PR/CI path: this work order's local acceptance commands provide the integrated proof.
- Unresolved blocker ledger: none known; preserve any new failure without retrying this order.
- Disposable database `opportunityos_fr008_wave6` was created locally and verified to contain zero public tables. Its name avoids the suite's `opportunityos_test_*` cleanup sweep.
- `READY_TO_DISPATCH: YES`
