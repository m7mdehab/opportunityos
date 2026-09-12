# Work order R1 — deterministic full-suite and API isolation

## Authority and objective

BRIEF-FR-006 recovery Phase B. Make the canonical real-PostgreSQL test run report
zero skips on supported development/CI platforms, and prove the `api` suite can run
standalone repeatedly without leaving an idle transaction that blocks cleanup.

## Owned behavior seam

Test discovery, test-client/session teardown, and required-suite CI invocation.

## Allowed files

- `api/test_api.py`
- `api/test_lifecycle.py` (new, only if needed)
- `api/test_search_performance.py`
- `scripts/test_alpha.py`
- `.github/workflows/test.yml`
- `reports/evidence/FR-006/closure-current/r1-*` (raw evidence)

`api/deps.py` is allowed only if instrumentation proves a production request-session
leak. Do not change database reset semantics, remove `TRUNCATE`, add sleeps, inflate
timeouts, suppress skip reporting, or delete assertions.

## Required diagnosis and repair

1. Reproduce/bisect the standalone API hang on an isolated PostgreSQL database.
2. Capture the blocking and blocked sessions if it reproduces. Close every
   `TestClient` before session rollback/close and engine disposal; centralize client
   ownership if that is the demonstrated cause.
3. Make the 20k performance assertion execute in the canonical A-1 run instead of
   appearing as a discovered skip.
4. Replace the two Windows skip-decorated POSIX process tests with platform-neutral
   deterministic coverage or platform-conditional test definition that does not
   report a skipped test. Preserve the actual POSIX behavior assertion on POSIX.
5. Record exact commands, test IDs, counts, failures/errors/skips, elapsed time, and
   post-run `pg_stat_activity` evidence.

## Acceptance

- `py -3.12 -m unittest discover -s api -t . -p "test_*.py" -v` completes twice,
  `OK`, without idle-in-transaction test backends afterward.
- With real PostgreSQL and the canonical required environment,
  `py -3.12 -m unittest discover -v` reports `OK`, count > 672, and no skipped
  summary.
- `py -3.12 -m unittest scripts.test_alpha api.test_search_performance -v` is green.
- CI still uses PostgreSQL password authentication and does not weaken a gate.

Commit changes and raw evidence on a dedicated branch/worktree. Report the commit.

