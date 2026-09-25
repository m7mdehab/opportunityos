# W1-BASELINE-TEST-REMEDIATION Readiness Certificate

- Work order: `W1-BASELINE-TEST-REMEDIATION`.
- Authoritative code base SHA: `4bc410f` on `work/fr008-incremental-delivery`.
- Dependency status: W0.2 and W1.2 implementation slices are integrated with their focused acceptance evidence. The corrected full-suite attempt exposed three failures in existing restore/worker PostgreSQL test cases; raw output is preserved in `W1-WAVE-R1-backend.txt`.
- External resources: none. Use only the existing local disposable FR-008 database named below.
- Execution surfaces: Python 3.12, PostgreSQL 16, repository test dependencies, Git, and an isolated worktree are available.
- Secret-injection path: none; the local test DSN uses no production credential.
- Cost/quota/terms status: no paid services, provider access, or hosted mutations.
- PR/CI path: targeted PostgreSQL acceptance, repository integrity, and diff checks are local and sufficient for this bounded test-only repair.
- Unresolved blocker ledger: investigate and fix only the identified test expectations/setup; do not modify product behavior without a new approved work order.
- Database `opportunityos_fr008_wave1` is the existing disposable FR-008 integration database, outside the repository's `opportunityos_test_*` cleanup sweep. No other process is using it.
- `READY_TO_DISPATCH: YES`
