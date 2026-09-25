# W1-WAVE-VERIFY-R2 Readiness Certificate

- Work order: `W1-WAVE-VERIFY-R2`.
- Authoritative integrated base SHA: `67679de` on `work/fr008-incremental-delivery`.
- Dependency status: W0.2 gold-review harness and W1.2 capability evidence are integrated with focused acceptance evidence. The three R1 failures were traced to an incomplete migration-owned table expectation, an incorrectly ordered stale-lease test setup, and a timing-dependent zero-second crash-recovery setup. Test-only corrections are integrated and their three targeted PostgreSQL cases pass; no production worker/storage behavior changed.
- External resources: none. The runner uses only the new local disposable PostgreSQL database below.
- Execution surfaces: Python 3.12, PostgreSQL 16, repository test dependencies, Git, and an isolated evidence-runner worktree are available.
- Secret-injection path: none; the local test DSN has no password or production credential.
- Cost/quota/terms status: no external paid resource, provider access, or hosted mutation.
- PR/CI path: this work order's local acceptance commands provide the full integrated proof.
- Unresolved blocker ledger: none; preserve any new failures without retrying this order.
- Disposable database `opportunityos_fr008_wave2` was created locally and verified to contain zero public tables. Its name avoids the suite's `opportunityos_test_*` cleanup sweep.
- `READY_TO_DISPATCH: YES`
