# W0-VERIFY Readiness Certificate

- Work order: `W0-VERIFY`
- Authoritative code baseline: `18e907d` (W0-MIRROR is integrated on the isolated FR-008 branch).
- Dependencies: W0-MIRROR source commit and three narrow acceptance outputs are available; integration checkout is clean except for the two user-provided FR-008 source documents, which remain untracked and are explicitly excluded from mirror assembly.
- External resources: local disposable PostgreSQL database `opportunityos_test_fr008-core`; web build and Playwright run locally only.
- Execution surfaces: Python 3.12, PostgreSQL 16, Node 24, installed web dependencies and Chromium are ready.
- Secret-injection path: none; web tests must not call external providers.
- Cost/quota/terms: no paid resource or provider mutation.
- PR/CI path: local mandatory CI commands are executable; GitHub Actions requires a later authenticated Owner/Overseer handoff.
- Unresolved blocker ledger: none for local full-suite proof.
- `READY_TO_DISPATCH: YES`
