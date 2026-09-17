# FR-007 cloud runtime configuration contract (W0.3)

This is a deployment preflight contract, not an assertion that the current application consumes these names. Values belong in provider secret/config stores, never Git, build logs, URLs, or browser bundles. Run `python scripts/validate_cloud_config.py --role ROLE` separately for `web`, `api`, `worker`, `scheduler`, and `backup` before starting each role. The validator checks presence and obvious template/URL mistakes; it cannot establish reachability, least privilege, RLS, encryption, backup validity, or application wiring. A passing preflight is not a production acceptance gate by itself.

`R` means required for that role's startup; `O` means optional until the named capability is deployed. “Startup” values are checked before serving work; “runtime” values are used for operations after boot. The `web` values are compiled into browser-delivered assets and are **public**, including the publishable/anon key. All other names are server-only even when non-secret. Never put a service-role key, database URL, storage signing secret, or private truth in a `NEXT_PUBLIC_*` variable. Configure authenticated RLS-scoped browser reads; an anon key is not authorization.

| Area | Variable | Requirement / consumer(s) | Secret? | Use | Fail-closed behavior |
|---|---|---|---|---|---|
| Database/data plane | `CLOUD_DATABASE_URL` | R: api, worker, scheduler, backup | Yes | Startup and runtime | Refuse that role's startup; no fallback to local DB or an unverified instance. Use role-specific least-privilege connection strings at deployment despite the shared variable name. |
| Auth | `AUTH_JWKS_URL` | R: api | No | Startup and runtime | Do not accept bearer tokens if key discovery/configuration fails. Require HTTPS. |
| Auth | `AUTH_ISSUER` | R: api | No | Startup and runtime | Reject tokens without exact issuer match. |
| Auth | `AUTH_AUDIENCE` | R: api | No | Startup and runtime | Reject tokens without exact audience match. |
| Auth | `AUTH_SERVICE_KEY` | R: api | Yes | Startup and runtime | Disable privileged auth administration; never substitute the public anon key. |
| Storage | `STORAGE_SERVICE_KEY` | R: api, worker | Yes | Startup and runtime | Disable private artifact reads/writes/signing; never issue public bucket access. May be same provider credential as auth service key, but inject separately for role scoping. |
| Storage | `STORAGE_PRIVATE_BUCKET` | R: api, worker | No | Startup and runtime | Disable artifact operations; never default to a public bucket/local disk. |
| Worker/queue | `QUEUE_NAMESPACE` | R: worker, scheduler | No | Startup and runtime | Refuse enqueue/consume on absent namespace; never use an implicit global queue. Queue backend is PostgreSQL (`pgmq` or equivalent lease table). |
| Scheduler | `SCHEDULER_DISPATCH_TOKEN` | O: scheduler, api/dispatcher when external dispatch is chosen | Yes | Runtime | Reject unsigned/unverified external dispatch; an in-database scheduler need not set this. No GitHub Actions correctness dependency. |
| Frontend/public | `NEXT_PUBLIC_DATA_API_URL` | R: web | No, browser-safe | Build/startup and runtime | Do not build/serve a client pointing at an absent or non-HTTPS data endpoint. |
| Frontend/public | `NEXT_PUBLIC_DATA_ANON_KEY` | R: web | No, browser-safe publishable key | Build/startup and runtime | Do not build/serve data client without it; RLS and user session still enforce access. |
| Frontend/public | `NEXT_PUBLIC_APP_URL` | O: web | No, browser-safe | Build/startup | Disable absolute-link features until canonical HTTPS origin configured; do not infer an arbitrary host. |
| Monitoring | `MONITORING_ERROR_ENDPOINT` | O: api, worker, scheduler, web | May contain credential; server-only by default | Runtime | Disable reporting and mark observability gate pending; do not put credential-bearing endpoint in a browser bundle. |
| Monitoring | `MONITORING_HEARTBEAT_URL` | O: worker, scheduler, backup | Yes (URL can be a bearer capability) | Runtime | Report heartbeat unavailable; never claim monitoring acceptance. |
| Notifications | `NOTIFICATION_API_KEY` | O: worker | Yes | Runtime | Disable delivery and retain durable pending job; never silently treat as delivered. |
| Notifications | `NOTIFICATION_FROM_ADDRESS` | O: worker | No | Runtime | Disable delivery until verified sender configuration exists. |
| Backup/DR | `BACKUP_DESTINATION_URL` | R: backup | May contain credentials; server-only | Startup and runtime | Refuse off-provider export if absent/invalid; use a private independent target. |
| Backup/DR | `BACKUP_ACCESS_KEY` | R: backup | Yes | Startup and runtime | Refuse export; never fall back to public/unauthenticated write. |
| Backup/DR | `BACKUP_ENCRYPTION_KEY` | R: backup | Yes | Startup and runtime | Refuse export without encryption; no plaintext private-state backup. |

The `backup` role is the encrypted off-provider export job, not a claim about provider-native backup configuration. Monitoring and notifications remain optional to this W0 preflight because no provider/resource is provisioned here; their respective FR-007 acceptance gates require configured, tested delivery later. Production deployment gates must also test connectivity, permissions, auth/RLS, signed private retrieval, queue leases, dispatch authentication, monitoring alerts, and actual restore. Do not expose secret values in diagnostics.

## Migration and cutover order

1. Provision staging secret stores and least-privilege database roles; inject each role's variables independently. Run preflight with synthetic inputs first, then secured deployment inputs. No values in repository or CI output.
2. Apply repository migrations and RLS/private bucket policy in staging; verify auth key discovery, exact issuer/audience, storage access, queue leases, scheduler due-only behavior, and a restore from an encrypted off-provider export.
3. Deploy web independently from API/worker/scheduler; validate browser bundle contains only `NEXT_PUBLIC_*` public values, authenticated RLS reads, and a cold feed with workers stopped. Do not confuse frontend build-time variables with runtime server secrets.
4. Migrate a snapshot and prove parity; shadow poll without authoritative writes. Freeze old production writes, apply final delta, verify identities/counts and a rollback backup, then switch public traffic. Do not keep two writable production databases.
5. Verify monitoring and notification signals, restore drill, and host-off soak separately before FR-007 closure. A config preflight alone cannot authorize cutover.

## Rotation and compatibility

Rotate each secret in its owning provider store with overlap only where the provider supports dual credentials. Roll database/backup/storage/auth keys through affected roles, redeploy/restart consumers, verify access and revocation, and invalidate stale sessions/signed URLs as appropriate. Rotate public anon keys through a new web build after RLS verification. Never paste old/new values into evidence. A compromise calls for immediate revocation and incident review, not merely a redeploy. Keep backup encryption keys recoverable under controlled key custody for the retention period; test decrypt/restore before retiring an old key.

Provider aliases (e.g. Supabase project URL/publishable key/service-role key, Supabase Storage bucket, Cloudflare static build variables, R2 credentials, Azure secret references) are deployment mappings to the neutral names above, not additional required application variables. `CLOUD_DATABASE_URL` must point to PostgreSQL; `QUEUE_NAMESPACE` maps to `pgmq` or a PostgreSQL lease table. This W0 contract **does not wire existing code**: current local alpha and real E2E paths still use `OPPORTUNITYOS_DB_URL`, local founder password/session secret, and `NEXT_PUBLIC_USE_MOCK_API` in mock tests. No production fallback to these is authorized. Overseer must review the exact alias/compatibility bridge and whether auth and storage service credentials can be split on the chosen provider before later waves change consumers; local-only obsolete variables are intentionally omitted from `.env.cloud.example`.
