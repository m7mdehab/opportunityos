# W1-WAVE-VERIFY-R4 — Integrated Wave 1 verification after target-tier schema

## Deliverable

Run the prescribed full Wave 1 verification against the exact integrated FR-008 source base below, including W1.3's typed target-role schema and family-taxonomy changes. This is an evidence-only run: make no product, test, or configuration changes. Preserve this run's first full-suite result unchanged. R1–R3 remain historical evidence and must not be altered or retried.

## Acceptance commands

1. `python scripts/check_guard.py --allow-missing-patterns`
   - Expected: exit 0; repository mirror boundary passes.
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R4-guard.txt`
2. `python scripts/check_repository.py`
   - Expected: exit 0 with `Repository integrity checks passed.`
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R4-repository.txt`
3. In one PowerShell session set `OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_wave4` and `OPPORTUNITYOS_RUN_SEARCH_PERF=1`; run the target preflight, `alembic upgrade head`, and then exactly one `python -m unittest discover -v` run. Capture the full output and each exit code.
   - Expected: target preflight prints exactly `opportunityos_fr008_wave4`; migration succeeds; the full backend suite exits 0, with no failures/errors and only the 22 documented platform/feature-gated skips from `W1-WAVE-VERIFY.md`. Record the actual test count.
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R4-backend.txt`
4. `git diff --check`
   - Expected: exit 0 with no whitespace errors.
   - Evidence: `reports/evidence/FR-008/orders/W1-WAVE-R4-diff-check.txt`

Database target preflight:

```powershell
python -c "import os; from urllib.parse import urlsplit; print(urlsplit(os.environ['OPPORTUNITYOS_DB_URL']).path.lstrip('/'))"
```

## Allowed files

- `reports/evidence/FR-008/orders/W1-WAVE-R4-guard.txt` (unedited raw output only)
- `reports/evidence/FR-008/orders/W1-WAVE-R4-repository.txt` (unedited raw output only)
- `reports/evidence/FR-008/orders/W1-WAVE-R4-backend.txt` (unedited raw output only)
- `reports/evidence/FR-008/orders/W1-WAVE-R4-diff-check.txt` (unedited raw output only)
- Disposable PostgreSQL database `opportunityos_fr008_wave4` only

## Frozen files and actions

All source, tests, fixtures, work orders, prior evidence, hosted project data, and mirror inputs. Do not access repository `private/`, any FR-007 checkout, or any hosted database. Do not alter, delete, or retry any previous R1/R2/R3 raw evidence. Do not enable other database/test gates or execute commands beyond the acceptance rows. If any acceptance step fails, preserve the output unchanged and report it; do not retry this work order.

## Test database

`postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_fr008_wave4`, created and verified to have zero public tables before dispatch. Its name avoids the suite's `opportunityos_test_*` cleanup sweep.

## Worktree

Use a new isolated evidence-runner worktree from the authoritative integrated base. Do not reuse any prior runner or implementer worktree. No push or merge from the runner worktree.

## Authoritative integrated base

`7dd17b5` on `work/fr008-incremental-delivery`.
