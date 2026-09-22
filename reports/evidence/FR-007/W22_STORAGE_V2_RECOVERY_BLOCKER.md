# FR-007 Storage V2 recovery evidence

Status: BLOCKED by provider recovery, not by repository implementation.

## Completed

- Storage V2 migration `0021_storage_v2` is implemented after the production baseline `0019_activity_view_access`.
- Cold source artifacts are zlib-compressed, content-addressed, SHA-256 verified, and use the existing private `opportunity-artifacts` Supabase Storage bucket when hosted credentials are present.
- Feed projection is truncated/rebuildable and its obsolete full-text GIN index is not recreated; opportunities retain the single compact authoritative search index.
- PostgreSQL disposable CI proof passed in run `35724303892`.
- Focused repository tests, repository integrity checks, and guard checks pass.
- Commits `93861cf`, `12af886`, `b3f6085`, and checkpoint commit `341301d` were pushed to the authoritative branch.

## Recovery attempts and evidence

- Hosted run `35724540792`: live preflight failed before SQL with `FATAL 57P03`, `the database system is not accepting connections`, `Hot standby mode is disabled`.
- Hosted run `35725285960`: both configured hosted endpoints and bounded retries failed with the same `57P03` provider error.
- Supabase dashboard showed `HostOutOfDiskSpace (critical, /data)` and `Database process is down`.
- Authorized Supabase restart was initiated. The project has remained visibly `PAUSING PROJECT` for more than eight minutes; database controls remain disabled. No restore was attempted while the provider still reported `PAUSING`, as required.
- The scheduled-backup page is unavailable during the paused transition and the organization’s new-project page did not expose a confirmed zero-cost replacement for this project.
- An urgent provider support request was prepared/submitted through the dashboard for project `lrrcpwaapwynzdsxzwhy`, including the hosted run IDs and exact error. The provider has not restored SQL access during this execution window.

## Why execution cannot safely continue

Every authorized hosted SQL path is unavailable, and destructive maintenance cannot be performed without a live writable PostgreSQL session. Continuing by creating a paid resource, guessing a new project’s cost/credentials, or modifying worker rows would violate the assignment and could cause data loss. The single external action required is provider recovery of the existing project (or provider-supplied zero-cost backup/export or confirmed zero-cost replacement) so a fresh SQL connection succeeds.

No final physical footprint, queue acceptance, FULL monitor, Issue #137 resolution, or State-only final commit is claimed. The seven-day soak is not claimed.
