# W1-WAVE-VERIFY-R5 — Integrated Wave 1 verification after W2.1

## Deliverable

Run the prescribed full Wave 1 verification against the exact integrated FR-008 source base below, including W2.1's structured geography evidence rules. This is an evidence-only run: make no product, test, or configuration changes. Preserve this run's first full-suite result unchanged. R1–R4 remain historical evidence and must not be altered or retried.

## Acceptance commands

1. `python scripts/check_guard.py --allow-missing-patterns`
   - Expected: exit 0; repository mirror boundary passes.
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R5-guard.txt`
2. `python scripts/check_repository.py`
   - Expected: exit 0 with `Repository integrity checks passed.`
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R5-repository.txt`
3. In one PowerShell session set `OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_wave5` and `OPPORTUNITYOS_RUN_SEARCH_PERF=1`; run the target preflight, `alembic upgrade head`, and then exactly one `python -m unittest discover -v` run. Capture the full output and each exit code.
   - Expected: target preflight prints exactly `opportunityos_fr008_wave5`; migration succeeds; the full backend suite exits 0, with no failures/errors and only the 22 documented platform/feature-gated skips from `W1-WAVE-VERIFY.md`. Record the actual test count.
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R5-backend.txt`
4. `git diff --check`
   - Expected: exit 0 with no whitespace errors.
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R5-diff-check.txt`

Database target preflight:

```powershell
python -c "import os; from urllib.parse import urlsplit; print(urlsplit(os.environ['OPPORTUNITYOS_DB_URL']).path.lstrip('/'))"
```

## Allowed files

- `reports/evidence/FR-008/orders/W1-WAVE-R5-guard.txt` (unedited raw output only)
- `reports/evidence/FR-008/orders/W1-WAVE-R5-repository.txt` (unedited raw output only)
- `reports/evidence/FR-008/orders/W1-WAVE-R5-backend.txt` (unedited raw output only)
- `reports/evidence/FR-008/orders/W1-WAVE-R5-diff-check.txt` (unedited raw output only)
- Disposable PostgreSQL database `opportunityos_fr008_wave5` only

## Frozen files and actions

All source, tests, fixtures, work orders, prior evidence, hosted project data, and mirror inputs. Do not access repository `private/`, any FR-007 checkout, or any hosted database. Do not alter, delete, or retry any previous R1/R2/R3/R4 raw evidence. Do not enable other database/test gates or execute commands beyond the acceptance rows. If any acceptance step fails, preserve the output unchanged and report it; do not retry this work order.

## Test database

`postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_wave5`, created locally and verified to contain zero public tables before dispatch. Its name avoids the suite's `opportunityos_test_*` cleanup sweep.

## Worktree

Use a new isolated evidence-runner worktree from the authoritative integrated base. Do not reuse any prior runner or implementer worktree. No push or merge from the runner worktree.

## Authoritative integrated base

`9b0458f` on `work/fr008-incremental-delivery`.
