# W0-VERIFY — Integrated privacy-boundary full-suite evidence

## Deliverable

Capture independent, unedited raw acceptance output for the integrated W0-MIRROR privacy-boundary change. This is evidence-only: run the exact commands below, write each command's complete stdout/stderr to its listed file, and report exit codes. Do not edit code, fixtures, or evidence after capture.

## Acceptance commands

1. `python scripts/check_guard.py --allow-missing-patterns`
   - Expected: exit 0; guard passes with the explicit FR-008 deny rules active.
   - Evidence: `reports/evidence/FR-008/orders/W0-VERIFY-guard.txt`
2. `python scripts/check_repository.py`
   - Expected: exit 0 with `Repository integrity checks passed.`
   - Evidence: `reports/evidence/FR-008/orders/W0-VERIFY-repository.txt`
3. Set `OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_fr008-core` and `OPPORTUNITYOS_RUN_SEARCH_PERF=1`; run `alembic upgrade head`, then `python -m unittest discover -v`.
   - Expected: both exit 0; migration reaches head and the backend full suite reports `OK` with zero skipped tests.
   - Evidence: `reports/evidence/FR-008/orders/W0-VERIFY-backend.txt` (include both raw outputs and exit codes).
4. From `web/`, run `npm run build`, `npm run lint`, and `npx playwright test`.
   - Expected: each exits 0; browser smoke suite passes.
   - Evidence: `reports/evidence/FR-008/orders/W0-VERIFY-web.txt` (complete raw output for each command, separated by literal command labels).

## Allowed files

- `reports/evidence/FR-008/orders/W0-VERIFY-*.txt` (raw command output only)
- Test database `opportunityos_test_fr008-core` only
- Ignored build/test-result output created by the commands

## Frozen files

All tracked source, fixtures, briefs, mirror inputs, and project data. Do not access repository `private/`, change any file other than the listed evidence files, or access the FR-007 checkout.

## Environment

- Integrated code: `18e907d` (`FR-008: guard mirror from private artifacts`)
- Runner checkout: `C:\Users\M7mdEhab\projects\oos-wt\fr008-incremental-delivery`, branch `work/fr008-incremental-delivery`.
- Dedicated database: `opportunityos_test_fr008-core`; PostgreSQL 16 is running, Node 24/npm dependencies and Chromium are installed.
- Web port range: not needed by the existing Playwright suite.
