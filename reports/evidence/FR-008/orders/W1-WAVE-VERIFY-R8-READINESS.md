# W1-WAVE-VERIFY-R8 Readiness Certificate

- Work order: `W1-WAVE-VERIFY-R8`.
- Authoritative integrated base SHA: `0a0de55` on `work/fr008-incremental-delivery`.
- Dependency status: R7 ran once: 1,596 tests, 22 skips, one failure in `test_lease_expiration_and_recovery`. The remaining queue recovery fixture was changed to a nonzero lease plus PostgreSQL-clock expiry and fresh-session verification. The full 17-test queue module, repository integrity, and diff check passed after this correction.
- External resources: none. The runner uses only the new local disposable PostgreSQL database below.
- Execution surfaces: Python 3.12, PostgreSQL 16, repository test dependencies, Git, and a new isolated evidence-runner worktree are available.
- Secret-injection path: none; the local test DSN has no password or production credential.
- Cost/quota/terms status: no external paid resource, provider access, or hosted mutation.
- PR/CI path: this work order's local acceptance commands provide integrated proof.
- Unresolved blocker ledger: none known; preserve any new failure without retrying this order.
- Disposable database `opportunityos_fr008_wave8` was created locally and verified to contain zero public tables. Its name avoids the suite's `opportunityos_test_*` cleanup sweep.
- `READY_TO_DISPATCH: YES`
