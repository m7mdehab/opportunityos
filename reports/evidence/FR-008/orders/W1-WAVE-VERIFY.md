# W1-WAVE-VERIFY — Integrated backend checkpoint

## Deliverable

Capture integrated Wave 1 and mirror-guard verification against the FR-008 branch after the reviewed W1.1 profile contract, W1.4 predicate-isolation coverage, and W0.1 Windows Truth Pack loader fix are integrated. This is evidence-only. Do not edit source, tests, fixtures, orders, or prior evidence.

## Acceptance rows

| Command | Expected | Evidence file |
|---|---|---|
| `python scripts/check_guard.py --allow-missing-patterns` | Exit 0; mirror boundary passes with FR-008/private artifacts excluded. | `reports/evidence/FR-008/orders/W1-WAVE-guard.txt` |
| `python scripts/check_repository.py` | Exit 0 with `Repository integrity checks passed.` | `reports/evidence/FR-008/orders/W1-WAVE-repository.txt` |
| In one PowerShell session set `OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_fr008-core` and `OPPORTUNITYOS_RUN_SEARCH_PERF=1`; run the database-target preflight below, then `alembic upgrade head`, then `python -m unittest discover -v`. Capture full output and each exit code. | Target preflight prints exactly `opportunityos_test_fr008-core`; migration reaches head; full backend suite exits 0 with no failures/errors. Its 22 known conditional skips are accepted here: two POSIX-only zombie-process cases on Windows, one FR-007 reliability disposable-Postgres test gated by `FR007_RELIABILITY_POSTGRES`, one Supabase bundle test and 18 portability/migration drills gated by `OPOS_LIVE_PROOF_TEST`. Any new skip is a failure requiring disposition. | `reports/evidence/FR-008/orders/W1-WAVE-backend.txt` |

Database-target preflight command:

```powershell
python -c "import os; from urllib.parse import urlsplit; print(urlsplit(os.environ['OPPORTUNITYOS_DB_URL']).path.lstrip('/'))"
```

## Prior frontend evidence

No frontend source changed in W1.1, W1.4, or W0.1-WIN-PATH. The already-captured `W0-VERIFY-web.txt` is the applicable frontend build/lint/Playwright evidence for this checkpoint; do not rerun Playwright or modify its FR-006 screenshot baselines in this evidence order.

## Allowed files

- `reports/evidence/FR-008/orders/W1-WAVE-guard.txt` (unedited raw output only)
- `reports/evidence/FR-008/orders/W1-WAVE-repository.txt` (unedited raw output only)
- `reports/evidence/FR-008/orders/W1-WAVE-backend.txt` (unedited raw output only)
- Test database `opportunityos_test_fr008-core` only

## Frozen files and actions

All tracked source, tests, fixtures, orders, prior evidence, project data and mirror inputs. Do not access repository `private/`, the FR-007 checkout, or any hosted database. Do not change any tracked screenshot, run optional disposable-database suites, invoke external providers, or change a database other than the named FR-008 test DB.

## Test database

`postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_fr008-core`

## Worktree

`C:\Users\M7mdEhab\projects\oos-wt\fr008-w1-wave-verify`

## Authoritative integrated code baseline

`3db992c` on `work/fr008-incremental-delivery`.
