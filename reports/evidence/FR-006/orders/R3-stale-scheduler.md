# Work order R3 — durable stale-opportunity reverification cadence

## Authority and objective

BRIEF-FR-006 recovery Phase B. Make the already-wired stale-opportunity reverifier
durable, idempotent, and directly tested across scheduler restarts.

## Owned behavior seam

Scheduler tick -> queue dedup/cadence -> `reverify_stale` handler -> persisted stale
state.

## Allowed files

- `worker/scheduler.py`
- `worker/test_scheduler.py`
- `worker/test_runner.py` only for a demonstrated handler integration gap
- `opportunity/test_reverification.py` only for a demonstrated reverifier gap
- `reports/evidence/FR-006/closure-current/r3-*` (raw evidence)

Do not change visibility/filter semantics, source permission, or evaluation
decisions. Do not use sleeps or a process-memory timestamp as the only cadence
authority.

## Required diagnosis and repair

1. Correct job-status comparisons to the queue's canonical enum/casing.
2. Derive pending/recent execution state durably from worker jobs or the repository's
   existing durable scheduler record so a restart within 24 hours does not enqueue a
   duplicate.
3. Add deterministic clock-driven tests for first tick, `<24h`, `>=24h`, pending and
   retry dedup, and a fresh scheduler instance.
4. Exercise the registered handler and verify idempotent persisted results.

## Acceptance

- `py -3.12 -m unittest worker.test_scheduler worker.test_runner opportunity.test_reverification -v`
- exact queue rows and cadence decisions are captured in raw evidence.

Commit changes and raw evidence on a dedicated branch/worktree. Report the commit.

