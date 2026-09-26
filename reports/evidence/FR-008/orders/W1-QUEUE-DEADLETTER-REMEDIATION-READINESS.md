# W1-QUEUE-DEADLETTER-REMEDIATION Readiness Certificate

- Work order: `W1-QUEUE-DEADLETTER-REMEDIATION`.
- Authoritative code base SHA: `2a40a64` on `work/fr008-incremental-delivery`.
- Dependency status: W1-WAVE-VERIFY-R2 completed once with guard/repository/migration passing and one dead-letter PostgreSQL test failure; the complete raw output is preserved. The previous three test-only fixes passed in both focused and integrated R2 runs.
- External resources: none. Use only the existing local disposable PostgreSQL database specified below.
- Execution surfaces: Python 3.12, PostgreSQL 16, repository test dependencies, Git, and isolated worktrees are available.
- Secret-injection path: none; the local test DSN has no production credential.
- Cost/quota/terms status: no paid services, provider access, or hosted mutations.
- PR/CI path: the listed targeted PostgreSQL test, repository check, and diff check are available locally.
- Unresolved blocker ledger: one PostgreSQL test still relies on zero-second lease expiry; the change is limited to making its simulated crash states explicit and persisted.
- Database `opportunityos_fr008_wave1` is the existing disposable FR-008 target; it is not used by another active runner.
- `READY_TO_DISPATCH: YES`
