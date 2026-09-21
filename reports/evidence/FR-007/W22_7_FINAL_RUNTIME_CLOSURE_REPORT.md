# FR-007 W22.7 Final Runtime Closure Report

## Terminal status

**BLOCKED**

The repository and disposable PostgreSQL closure work is complete and pushed, but the required hosted maintenance/recovery proof could not be executed on this unmerged branch. GitHub does not register `.github/workflows/fr007-final-runtime-closure.yml` until it exists on the repository’s workflow-visible integration/default ref; the Actions page returns “This workflow does not exist” for the branch-only workflow. The user’s no-merge boundary prevents making that workflow dispatchable. No hosted mutation was attempted through an unsafe substitute.

Seven-day soak: **not claimed / not elapsed**.

## Branch and migration graph

- Branch: `work/fr007-overseer-storage-budget-correction-v2`
- Final pre-State implementation head: `5e12a79ea38356576213a8ef6e9bc61adb0ee823`
- Migration graph: `0016_founder_activity` -> `0017_founder_activity_correction` -> `0018_activity_live_fix` -> `0019_activity_view_access` -> `0020_capacity_archive`
- `alembic heads`: exactly one head, `0020_capacity_archive`
- `alembic upgrade head --sql`: passed

## Corrections completed

- Replaced the conflicting capacity migration with linear `0020_capacity_archive`.
- Fixed PostgreSQL view replacement by dropping dependent activity views in dependency order before recreating the corrected shape.
- Prevented migration `0009` from applying policies to the not-yet-created capacity archive relation.
- Added post-create RLS enrollment for `opportunity_cold_archive` in `0020`, including downgrade cleanup.
- Preserved archive invalidation, checksum-verified hydration, placeholder-free re-evaluation, cold feed/search suppression, and Founder-history preservation from the existing W22.7 work.
- Kept subprocess diagnostics sanitized and shell-free.

## Deterministic and PostgreSQL proof

- GitHub Actions run `35669052238` — **SUCCESS**
  - workflow: `FR-007 Disposable PostgreSQL Portability Proof`
  - commit: `5e12a79`
  - PostgreSQL 16 service container
  - fresh migration, archive/capacity tests, portability tests, provider bundle tests, compile, repository integrity, and guard all passed
  - provider artifact digest: `sha256:a7f8529266fa5797730388a931b6c2a0ecf67d3d111e175ab95f800b008e9923`
- Local focused closure suites: **60 tests passed, 0 failures**
- Local archive/capacity/RLS migration suites: **14 tests passed, 0 failures**
- `python scripts/check_repository.py`: passed
- `python scripts/check_guard.py --allow-missing-patterns`: passed
- `python -m compileall -q scripts storage worker opportunity matching`: passed
- `git diff --check`: passed

## Hosted stages

| Stage | Result | Evidence |
|---|---|---|
| Live read-only preflight | NOT EXECUTED | Requires dispatchable W22.7 workflow and `fr007-staging` secret injection |
| Controlled maintenance / migration | NOT EXECUTED | Deliberately not substituted with an unreviewed destructive path |
| Physical reclaim and `pg_database_size <= 400 MiB` | NOT EXECUTED | No hosted connection executed |
| Fresh normal writable connection | NOT EXECUTED | Depends on hosted maintenance |
| Natural five-lease recovery | NOT EXECUTED | Must follow successful maintenance |
| Final five-shard proof | NOT EXECUTED | Must follow recovery |
| FULL monitor / issue #137 RESOLVE | NOT EXECUTED | Must follow final proof |

No hosted database size, queue status, connection metrics, incident state, or provider mutation is represented as PASS in this report.

## Safety and data preservation

- No production or hosted database write was attempted by Codex.
- No worker status, source cadence, Founder history, or source truth was manually altered.
- No paid infrastructure was introduced.
- No credentials, DSNs, or private Founder data are present in this evidence.
- No merge was performed.

## Required external continuation

Once the branch is integrated or the workflow is otherwise registered on an authorized workflow-visible ref, dispatch `.github/workflows/fr007-final-runtime-closure.yml` against `fr007-staging` and complete the live phases in order. The hosted run must record actual before/after database size, fresh-write proof, natural recovery, five-shard metrics, FULL monitor output, and normal issue #137 RESOLVE evidence before W22.7 can become PASS.
