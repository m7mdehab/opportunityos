# BC Dashboard Metrics Performance Checkpoint

Date: 2026-09-29

## State

BC remains open. The populated hosted-feed smoke on main deployment run
`36504673678` failed while switching dashboard metrics to Yesterday. The
failure was PostgreSQL SQLSTATE `57014` (statement timeout), repeated on desktop
and 390px mobile. Login succeeded and the failure occurred after the bounded
candidate refresh produced 20 `for_you` projection rows.

## Measured cause

The hosted hidden-count metric filters `founder_feed.opportunity_created_at`
for its date window, then parses `visibility_reason` and checks staleness. The
live `EXPLAIN ANALYZE` took 3,769.685 ms. PostgreSQL sequentially scanned all
12,647 `feed_projection` rows, parsed JSON for 3,777 matches, and performed
3,777 opportunity primary-key lookups before applying the date restriction.
`opportunities.created_at` had no index. A date-first alternative without that
index still took 3,200.351 ms by scanning the 116 MB opportunities heap.

## Bounded correction

The single active repair branch adds Alembic revision
`0034_opportunity_created_at`: a concurrent B-tree index on
`opportunities(created_at)`, with a concurrent downgrade. It does not change
metric definitions, feed query semantics, job inventory, history, or capacity
policy. The checked-in provider execution bundle is regenerated for the new
head. PostgreSQL coverage asserts both index presence and planner usability for
the dashboard's date-range predicate.

Focused migration-contract and provider-bundle tests passed locally. Live
query-plan confirmation, required PostgreSQL CI, production deployment, and the
repeated hosted desktop/mobile smoke are pending this migration's merge. The
last live database measurement before the correction was `384,945,299` bytes
(~367 MiB), inside the warning band and below the 400 MiB heavy-work pause.
No source expansion or broad refresh was started.

## Remaining BC acceptance

- Deploy revision `0034_opportunity_created_at` and verify the live date-metric
  plan/runtime.
- Pass authenticated desktop and 390px smoke on populated For You with p95 at
  or below 1.5 seconds.
- Inspect the actual hosted top results and organization/source diversity,
  historical-negative leakage, geography, and application access.
- Confirm Saved, Applied, and Later state reads and the reversible action path
  only if an accepted isolated fixture exists; do not mutate Founder history.
- Recheck queue, database size, preserved histories, branch, and PR state.
