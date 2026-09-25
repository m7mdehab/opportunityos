# W1-WAVE-VERIFY Readiness Certificate

- Work order: `W1-WAVE-VERIFY`
- Authoritative code base SHA: `3db992c` on `work/fr008-incremental-delivery`; it includes the integrated W1.1 and W1.4 commits and the reviewed W0.1 Windows path fix.
- Dependency status: source and narrow tests are integrated; the prior W0-VERIFY run was not accepted because its configured database was missing and a Windows-specific path defect was exposed. Both causes have now been corrected. The named database exists and has zero public tables.
- External resources: none. Verification is local against disposable PostgreSQL only.
- Execution surfaces: Python 3.12, PostgreSQL 16, migrations, repository guard and integrity scripts are available on Windows PowerShell. The standard backend suite deliberately skips only documented platform/opt-in PostgreSQL checks; those are routed to their own dedicated workflow, not this order.
- Secret-injection path: none; the local test DSN has no password or production credential.
- Cost/quota/terms status: no external paid resource, mutation, or terms acceptance.
- PR/CI path: local integrated verification runs in a separate worktree; after acceptance the FR-008 branch can be pushed and submitted for review through the connected GitHub surface.
- Unresolved blocker ledger: the live staging project is read-only for this brief while FR-007 closure remains active. This order requires no staging access.
- `READY_TO_DISPATCH: YES`
