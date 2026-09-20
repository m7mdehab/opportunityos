# W22.2A — OVERSEER EXECUTION DIRECTIVE: STOP BLIND DRAINING AND FIX CONNECTION PRESSURE

## STATUS

W22.2 is **not implemented** yet.

Current runtime branch:
`work/fr007-antigravity-final-closure`

Current branch head:
`76653ceff234eec389cee8d00078a7cbae17a527`

Diff from the previous runtime implementation head `28f535d356a0ca8be3593f6a6d6bea3bba68420b` contains only:
- `reports/evidence/FR-007/W22_2_ANTIGRAVITY_CONNECTION_PRESSURE_CORRECTION_PACKET.md`

No worker/database connection-lifecycle correction has landed.

## LIVE OVERSEER EVIDENCE

While the current five-shard drain continues, the live Supabase session-mode pool is still saturated:

- Supavisor idle connections: **12**
- Supavisor idle-in-transaction connections: **3**
- Supavisor total: **15 / 15**

Current queue state at the same time:
- due runnable: **362**
- oldest due age: **~45,100 seconds**
- expired RUNNING leases: **0**
- RUNNING now: **4**
- migration revision: `0015_hosted_founder_surface`

This means repeated drain dispatches are not satisfying W22.1/W22.2 acceptance. The queue remains severely stale and the five-shard worker path still monopolizes the session-mode pool.

The Codex hosted smoke also returned feed HTTP 500/timeouts while the worker lane was active. Do not misclassify that as missing fixture data until connection pressure is eliminated.

## IMMEDIATE DIRECTIVE

Do **not** dispatch another ordinary drain run after the currently active run finishes until you have implemented and tested the W22.2 connection-lifecycle correction.

The next inner-loop work must be CODE + TESTS, not another manual drain repetition.

Required next sequence:

1. Trace exact per-shard connection ownership.
2. Identify why one five-shard execution consumes all 15 Supavisor session-mode connections.
3. Eliminate long-lived idle / idle-in-transaction connections and redundant per-handler engines/session factories.
4. Bound SQLAlchemy pool behavior deliberately for hosted workers.
5. Preserve five shards, lease heartbeat safety, SKIP LOCKED, retries/dead-letter semantics, and cadence.
6. Add deterministic regression tests.
7. Commit and push the implementation.
8. Then run one measured five-shard proof while concurrently executing hosted bootstrap/feed/database connectivity.
9. Capture peak Supavisor session counts.
10. Only after connection headroom is proven, resume queue catch-up runs as needed.
11. W22.2 still cannot PASS until queue oldest-due age < 900 seconds, expired leases = 0, FULL monitor passes on migration 0015, and incident #137 resolves normally.

## NON-ACCEPTABLE RESPONSES

Do not return:
- another table of drain runs without a code correction,
- “queue is steadily draining” while oldest-due age remains > 900 seconds,
- a lower worker count as the default fix,
- a weakened queue threshold,
- direct row/lease manipulation,
- a claim that W22.2 is complete while branch diff contains only evidence/docs.

## RETURN

After the code correction and live proof, return the existing W22.2 completion contract with:
- implementation SHA(s),
- exact files changed,
- root cause,
- before/after peak connection counts,
- idle-in-transaction before/after,
- concurrent hosted probe result,
- queue metrics,
- monitor run ID,
- incident #137 state,
- READY FOR OVERSEER INTEGRATION YES/NO.
