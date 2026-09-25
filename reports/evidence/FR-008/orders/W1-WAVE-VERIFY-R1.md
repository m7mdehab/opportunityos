# W1-WAVE-VERIFY-R1 — Corrected integrated backend evidence

## Deliverable

Repeat the integrated backend verification after the first evidence run exposed a database-lifecycle collision. The repository's full suite includes `TestDropAllExclusion`, which deletes every database with the `opportunityos_test_` prefix except the shared standard databases. Use a fresh isolated database outside that deletion pattern so it survives the prescribed full run. This order changes only the disposable database target; it does not change any product code or prior failure evidence.

## Acceptance commands

1. `python scripts/check_guard.py --allow-missing-patterns`
   - Expected: exit 0; mirror boundary passes.
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R1-guard.txt`
2. `python scripts/check_repository.py`
   - Expected: exit 0 with `Repository integrity checks passed.`
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R1-repository.txt`
3. In a single PowerShell session set `OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_wave1` and `OPPORTUNITYOS_RUN_SEARCH_PERF=1`; run the target preflight below, then `alembic upgrade head`, then `python -m unittest discover -v`. Capture the complete output and each exit code.
   - Expected: target preflight prints exactly `opportunityos_fr008_wave1`; migrations succeed; full backend suite exits 0, with no failures/errors and only the 22 already-disposed platform/feature-gated skips documented in `W1-WAVE-VERIFY.md`.
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R1-backend.txt`

Database target preflight:

```powershell
python -c "import os; from urllib.parse import urlsplit; print(urlsplit(os.environ['OPPORTUNITYOS_DB_URL']).path.lstrip('/'))"
```

## Allowed files

- `reports/evidence/FR-008/orders/W1-WAVE-R1-guard.txt` (unedited raw output only)
- `reports/evidence/FR-008/orders/W1-WAVE-R1-repository.txt` (unedited raw output only)
- `reports/evidence/FR-008/orders/W1-WAVE-R1-backend.txt` (unedited raw output only)
- Disposable PostgreSQL database `opportunityos_fr008_wave1` only

## Frozen files and actions

All source, tests, fixtures, orders, prior evidence, hosted project data, and mirror inputs. Do not access repository `private/`, the FR-007 checkout, or any hosted database. Do not change screenshots, enable optional DB gates, or run any commands outside the acceptance rows. Preserve the first failed raw evidence unchanged.

## Test database

`postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_wave1` (created and verified empty before dispatch; intentionally outside the repository suite's test-database cleanup prefix).

## Worktree

Use a new isolated evidence-runner worktree from the authoritative integrated base; do not reuse the previous runner's stale checkout.

## Authoritative integrated base

`4043be6` on `work/fr008-incremental-delivery`.
