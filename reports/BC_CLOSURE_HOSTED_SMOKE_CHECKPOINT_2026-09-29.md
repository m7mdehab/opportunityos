# BC Closure Hosted Smoke Checkpoint — 2026-09-29

## Status

The execution work is merged and deployed, and the authenticated hosted
acceptance smoke passed on populated For You. The evidence below is ready for
the Owner/Overseer's independent closure decision. This report does not itself
declare BC closed. The measurable All Time dashboard latency is retained as a
specific follow-up finding rather than being conflated with the feed SLO.

## Git, PR, and deployment

- Repository: `m7mdehab/opportunityos`.
- Authoritative `main`: `ad80b82316e180648061864e05f89aa93acea2cc`.
- PR #192 merged: https://github.com/m7mdehab/opportunityos/pull/192.
- PR commits: `4c0cbe0008a755bf96b570740a2bbb9d89c474b4` and
  `696d5166b131ddb0bf45d8d84cc150d0108f3ee3`.
- Production workflow run `36507082631` succeeded: migration,
  bounded candidate refresh, Cloudflare deployment, and hosted authenticated
  Playwright smoke all passed. Run:
  https://github.com/m7mdehab/opportunityos/actions/runs/36507082631.
- Live migration `0034_opportunity_created_at` is present. Its concurrent
  `opportunities(created_at)` index is 720,896 bytes, and the measured date
  range plan uses it.
- Final repository check: clean checkout, local/remote heads contain only
  `main`, and PR #192 is merged. GitHub CLI was not authenticated in this
  environment; Git remote access and the signed-in GitHub UI provided the
  merge/branch evidence.

## Live product and candidate integrity

Authenticated hosted desktop and 390px Playwright completed the populated
For You flow, filter interactions, date selector, selection toolbar, and
read-only Saved/Applied/Later checks. The live projection currently contains
26 For You rows; the diversity-composed API currently returns 10 cards in its
top-50 request (`total=10`, `returned=10`). The actual served titles and
organizations were:

1. Senior Backend Engineer - Databases - Analytics | US | Remote — Grafanalabs
2. Data Platform Operations Engineer – Performance — Imc
3. Software Engineer, Macro Quant Analytics Technology — Point72
4. Machine Learning Engineer — Imc
5. Master Data Management - Analyst — Icapitalnetwork
6. Data Quality Engineer — Imc
7. Site Reliability Engineer - Data Engineering — Imc
8. Staff Engineer, AI Operations & Governance, Workplace AI (R5428) — Shieldai
9. Generative AI Application Engineer, Learning & Development (R5856) — Shieldai
10. Python Engineer - AI — Imc

The list is data/AI/platform/analytics infrastructure focused. It spans five
employers and five sources; the largest employer/source contributes 5 of the
10 served cards. The quant-analytics software title is a contextual adjacent
role, not a generic software-engineering classification.

Read-only live invariants over current projected For You:

- Explicitly incompatible geography: 0/26.
- Inaccessible, premium/manual/unknown route or missing application URL: 0/26.
- Explicitly ineligible qualification state: 0/26.
- `bad_match` / `irrelevant_role` historical IDs in For You: 0 of 158 distinct
  IDs (0% leakage; threshold is under 5%).
- `eligibility_wrong` is also excluded by the hosted smoke assertions.
- The two historical `good_match` opportunities remain in Review because one
  has an unknown application route and the other has unresolved role,
  geography, and route classification. Positive feedback does not bypass
  those hard eligibility/access gates.

The current local browser has no Founder session. The hosted authenticated
Playwright session is the Founder-flow evidence. `/login` is publicly
reachable; unauthenticated feed access correctly returns 401. The smoke
verified Saved (106), Applied (15), and Later (1) through read-only GETs and
returned to For You. It did not write Founder state. A reversible Not-for-me
mutation was skipped because no isolated Founder fixture was available.

## Feed and dashboard performance

The existing hosted target remains 1,500 ms p95. The 20-sample authenticated
feed smoke passed on both viewports:

| Viewport | First authenticated feed total | First probe total | Warm feed total p95 | Warm TTFB p95 |
| --- | ---: | ---: | ---: | ---: |
| Desktop Chrome | 725.57 ms | 2,153.10 ms | 798.70 ms | 797.60 ms |
| Mobile, 390px | 491.64 ms | 1,225.70 ms | 775.10 ms | 774.50 ms |

The slowest first desktop probe was above 1.5 seconds, while the measured
20-sample p95 and first authenticated UI request met the target. Feed server
timings showed query, hidden-count, and edge-request values in the hundreds of
milliseconds; hydration and serialization were reported as 0 ms for this
projection response. For example, desktop first-page timing was approximately
`feed_query=237ms`, `hidden_count=513ms`, `feed_handler_total=513ms`, and
`edge_request=698ms`. Mobile first-page server timing was approximately
`feed_query=293ms`, `hidden_count=293ms`, and `edge_request=464ms`.

The supported Founder session is same-origin, HttpOnly-cookie authenticated
through the Cloudflare Worker. A separate authenticated direct-origin request
is not available in this deployment path, so the cold desktop tail cannot be
cleanly separated into Worker, connection, and upstream-network components.
The smoke logged that limitation explicitly.

Dashboard metric requests returned correct period shapes, but the measured
`dashboard_rpc` timings were: Today 253 ms, Yesterday 763 ms, and All Time
5,743 ms. A read-only production `EXPLAIN ANALYZE` of the All Time hidden-count
subquery took 4,137.492 ms, scanning 12,647 `feed_projection` rows, parsing
3,777 visibility values, and performing 3,777 opportunity lookups. This is a
measured All Time dashboard latency issue; it does not change the passing
populated-feed p95. It is the remaining performance follow-up to prioritize if
the Founder requires the period selector to share the feed SLO.

The deployed date index changed the Yesterday metric plan from the previously
observed 3,769.685 ms to a date-range plan with an index scan over 565
opportunities and 127.860 ms execution. The hosted Yesterday metric call was
763 ms including the Worker/PostgREST request path. No new index was added for
All Time: live evidence identifies the broad hidden-count scan as its cost, and
any further change should first preserve the metric semantics and be tested
against the same live-equivalent query.

## Live database, queue, and history

Read-only production snapshot after deployment:

- Database: `385,666,195 bytes` (`367.80 MiB`).
- Compared with prior `384,945,299 bytes`: `+720,896 bytes` across the observed
  interval. The new date index itself is 720,896 bytes; the interval delta is
  not attributed exclusively to that index because normal queue writes also
  continued.
- Capacity: `+18,664,595 bytes` above the 350 MiB warning band;
  `33,764,205 bytes` below the 400 MiB heavy-work pause;
  `59,978,605 bytes` below the 425 MiB hard stop; and
  `114,333,805 bytes` below the approximate 500,000,000-byte provider quota.
- Lifecycle: HOT 11,586; PROTECTED 1,061; COLD 18,647.
- Feed projection: For You 26; Review 12,387; Excluded 234.
- Queue: COMPLETED `evaluate_new` 153; PENDING `evaluate_new` 1;
  COMPLETED `poll_source` 1,545; PENDING `poll_source` 124;
  DEAD_LETTER `poll_source` 77; RETRY 0; RUNNING 0.
- No new broad source activation or corpus-wide projection rewrite was started.
  The previously observed 227 pending polls fell to 124 while normal queued
  work continued; completed polls increased from 1,442 to 1,545. This closure
  did not manually modify queue rows or history.
- Founder feedback remains present (including 140 `irrelevant_role`, 24
  `bad_match`, 2 `good_match`, and 5 `eligibility_wrong` events in the prior
  live breakdown); submitted applications remain 15. The hosted smoke used
  read-only checks only. Queue history and dead letters were not edited.

## Verification conclusion for Owner/Overseer

The recommendation suppression is corrected and deployed: For You is
non-empty, the served titles were inspected, strong-negative leakage is zero,
and all 26 projected recommendations pass current route/geography gates. The
date-index repair removed the timeout and the authenticated desktop/mobile
feed SLO passes at p95. The remaining evidence-based caveats are the 5.743 s
All Time dashboard RPC and the lack of an isolated fixture for a reversible
Not-for-me write test. No Founder data was changed to manufacture acceptance.

The report is an execution evidence package for independent Owner/Overseer
review. Final vocabulary and brief closure remain with that authority.
