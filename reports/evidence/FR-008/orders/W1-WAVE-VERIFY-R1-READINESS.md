# W1-WAVE-VERIFY-R1 Readiness Certificate

- Work order: `W1-WAVE-VERIFY-R1`
- Authoritative base SHA: `af4ef84` on `work/fr008-incremental-delivery`.
- Dependency status: mirror guard, W1.1 profile contract, W1.4 predicate isolation, W0.1 Windows loader fix, and W0.3 portfolio reconciliation are integrated. First W1 wave run completed with guard/repository/migration passing but the backend suite errored because its own `testdb --drop-all` probe removed the selected `opportunityos_test_fr008-core` database. The raw failed output remains intact in the prior runner worktree.
- External resources: none; only a new local disposable PostgreSQL database is required.
- Execution surfaces: prewarmed Python 3.12, PostgreSQL 16, repository test dependencies, and isolated evidence-runner worktree are available.
- Secret-injection path: none.
- Cost/quota/terms status: no paid services or provider access.
- PR/CI path: local acceptance rows provide the complete proof.
- Unresolved blocker ledger: none. The replacement database name avoids the repository suite's documented `opportunityos_test_*` cleanup sweep; preflight must verify it exists and contains no tables before migration.
- `READY_TO_DISPATCH: YES` only after the named disposable database is created and its public schema is verified empty.
