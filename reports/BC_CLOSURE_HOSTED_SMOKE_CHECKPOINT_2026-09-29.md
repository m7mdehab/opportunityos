# BC Closure Hosted Smoke Checkpoint — 2026-09-29

## Status

The remaining hosted acceptance instrumentation and read-only smoke assertions are committed and pushed on `work/bc-hosted-smoke-closure`, based on verified `main` SHA `8906c455e11c1304f53739c48a3d888a9d47d35a`. PR #191 is open; the changes are not deployed. BC is not closed.

## Change

- The hosted feed route now reports `feed_query`, `hidden_count`, response decoding, row mapping, JSON serialization, and handler-total durations. Existing `edge_auth`, `edge_contract`, `edge_request`, and `edge_upstream_fetch` timings remain at their respective request boundaries.
- The staging smoke fetches the real For You page at `page_size=50`, asserts recommendation role, geography, application access/URL, known-family uniqueness, and absence of explicit negative feedback, and records titles, employer counts, and source counts in the workflow log.
- The smoke visits Saved, Applied, and Later through read-only GETs, verifies each view’s selected query and response, then returns to For You. It does not add or alter Founder actions.
- It records that a separate direct-origin comparison is unavailable in this deployment path because hosted authentication is carried by same-origin HttpOnly cookies and the Cloudflare Worker is the supported serving path.

## Verification performed

- Targeted ESLint for the changed route and staging smoke: passed.
- `npm run lint`: passed.
- `npm run build`: passed, including Next compilation and TypeScript.
- `git diff --check`: passed.
- Production read-only checks: `/login` returned HTTP 200; unauthenticated `/api/opportunities` returned HTTP 401.
- GitHub read-only checks: `main` is still `8906c455e11c1304f53739c48a3d888a9d47d35a`; remote heads contain only `main`; open PR count is zero.

## Not yet verified

The updated authenticated desktop and 390px hosted smoke has not run. The actual hosted top-50 titles, employer/source concentration, tracked-view totals, and new Server-Timing values therefore have not been observed. The production feed was not mutated. GitHub CLI reports no authenticated host, but the branch push succeeded through the configured Git credential manager and PR #191 was created through the existing authenticated Chrome session. Required checks, merge, deployment, and hosted acceptance remain pending.
