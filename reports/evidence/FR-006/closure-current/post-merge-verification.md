# FR-006 post-merge verification

Executed 2026-09-13 after PR #79 merged.

## Identity

- PR head: `002e2061c775be6ae53d80554e64b98426b18479`
- Merge SHA and verified `origin/main`: `a2e5043540003242c658d01d73daec14e029d892`
- Repository visibility: public

## Required PR checks

- Mandatory Governance & Test Suite `34762854189`: success
- Mirror `34762854193`: success
- FR-006 Live Evidence `34762854229`: success
- Guard `34762854248`: success
- State `34762854319`: success
- Required PR jobs: 8 successful, 0 failed, 0 skipped

The mandatory run completed the PostgreSQL backend suite with 1102 tests,
0 failures, 0 errors, and 0 skipped. Web build and lint passed, and Playwright
completed 22/22 tests.

## Post-merge checks on main

- Mandatory Governance & Test Suite `34763026202`: success
- Guard `34763026213`: success
- Mirror `34763026230`: success
- State `34763026245`: success
- Heartbeat `34763051720`: success

The post-merge mandatory run completed 1102 backend tests with `OK`, web build
and lint, governance and repository integrity, and 22/22 Playwright tests.

## Public deployment re-verification

- HTTPS root: 200
- Unauthenticated protected opportunities API: 401
- Login: 200
- Authenticated feed: 60 persisted live opportunities returned
- Session cookie: Secure and HttpOnly
- Application process and Cloudflare tunnel process: running
- Prior desktop 1440x900 and mobile 390x844 browser smoke remained valid for
  the unchanged runtime tree; both authenticated, refreshed, displayed the live
  fetched count, and showed no mock-data banner.

The public deployment excludes the private Founder Truth Pack and exposes no
credential values. Durable Render activation remains post-validation operational
hardening because no already-authorized provider account was available.
