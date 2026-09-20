# W23 Codex Founder Surface Corrections

- **Status:** PASS (repository and disposable PostgreSQL proof complete; no production claim)
- **Start SHA:** `ef3d298c764462ff4908ac7ca2e8cce14f8bb0f6`
- **Branch:** `work/fr007-codex-founder-surface-corrections`
- **Implementation SHA:** `416813e8a6af4a2d0f9f4906a76007b97afc9bc4`
- **Hosted production:** not executed in this lane; no live Supabase claim

## Acceptance matrix

| Gate | Result | Evidence |
|---|---|---|
| D1 centered responsive detail modal | PASS | `web/components/feed/detail-drawer.tsx`; Dialog with bounded `92dvh/92vw`, outside/Escape close via base primitive |
| D2 persisted hosted evaluation detail | PASS | `web/app/api/[...path]/route.ts`; hard constraints, dimensions, strengths/gaps/unknowns parsed; raw JSON omitted |
| D3 canonical feed projection | PASS | `storage/migrations/versions/0015_hosted_founder_surface.py`; deterministic `row_number` dedup, scored-first ordering, stale/source metadata |
| D4 dashboard aggregate | PASS | `founder_dashboard_daily` SECURITY DEFINER RPC and hosted route mapping |
| D5 source overview/filter | PASS | `founder_source_overview`, source family/source id filters, Reddit marked manual-only |
| D6 Poll Now UX | PASS | due-only RPC response surfaced as queued/skipped status with cadence/cooldown tooltip |
| D7 Greenhouse tombstone | PASS | exact normalized marker, Greenhouse URL scope, conservative near-miss tests |
| D8 capacity ownership | PASS | no worker queue/scheduler capacity files changed |

## Verification

- `python -m unittest scripts.test_w23_founder_surface -v`: **5 passed**.
- Focused backend command (`storage.test_hosted_runtime_migration scripts.test_fr007_supabase_execution_bundle opportunity.test_reverification worker.test_worker api.test_api`): **32 passed, 19 skipped**; skips are the existing real-PostgreSQL API fixtures because no local `OPPORTUNITYOS_DB_URL` was provided.
- Baseline/restore/portability unit suites: **27 passed** after repairing the pre-existing literal-escaped-newline comment that had commented out `IDENT` in `scripts/migration_baseline.py`.
- `npm ci`: **success**, 863 packages audited, 0 vulnerabilities.
- `npm run lint`: **success**.
- `npm run build`: **success**.
- `npm run test:e2e`: **24 passed**, including 360px and 1280px screenshot/mobile coverage.
- `python -m py_compile` for changed Python modules: **success**.
- `python scripts/check_repository.py`: **passed**.
- `python scripts/check_guard.py --allow-missing-patterns`: **passed**.
- `git diff --check`: **passed**.

## Disposable PostgreSQL proof

Workflow `FR-007 Disposable PostgreSQL Portability Proof`, run `35506297906`, concluded **SUCCESS** at commit `65dfd3b...`. It exercised the migration/parity/restore suites against disposable PostgreSQL. The provider bundle test includes the W23 feed fixture: two truth-pack projections for one opportunity resolve to exactly one `founder_feed` row, with the scored projection selected and `source_family=reddit`. The follow-up bundle test is included in the next workflow run after the evidence commit.

## Files changed

- `.github/workflows/fr007-portability-proof.yml`
- `opportunity/reverification.py`
- `opportunity/test_reverification.py`
- `reports/evidence/FR-007/provider-execution/execution-manifest.json`
- `reports/evidence/FR-007/provider-execution/migration-manifest.json`
- `reports/evidence/FR-007/provider-execution/migrations/15_0015_hosted_founder_surface.sql`
- `scripts/migration_baseline.py`
- `scripts/test_fr007_supabase_execution_bundle.py`
- `scripts/test_fr007_supabase_execution_postgres.py`
- `scripts/test_w23_founder_surface.py`
- `storage/migrations/versions/0015_hosted_founder_surface.py`
- `storage/test_hosted_runtime_migration.py`
- `web/app/api/[...path]/route.ts`
- `web/app/page.tsx`
- `web/components/feed/detail-drawer.tsx`
- `web/components/feed/filter-bar.tsx`
- `web/components/feed/header-strip.tsx`
- `web/lib/api/client.ts`
- `web/lib/contract/types.ts`

## Unresolved / out of lane

- Live Supabase execution, real Founder authentication, artifact-store retrieval, and production deployment remain Overseer-owned and were not claimed.
- No schema migration was applied to a live database by Codex.

**READY FOR OVERSEER INTEGRATION:** YES (after remote workflow for the final pushed SHA is green).
