# FR-007 W16 Hosted Setup — Pre-dispatch Readiness

Updated: 2026-09-19

## Supabase data plane

- Supabase project provisioned: **PASS**
- Project `opportunityos-staging` / `lrrcpwaapwynzdsxzwhy`: **ACTIVE_HEALTHY**
- Schema 0001 -> 0009 applied: **PASS**
- Provider security hardening applied: **PASS**
- 26/26 public base tables RLS-enabled: **PASS**
- 52 browser-deny policies: **PASS**
- anon/authenticated probe against seeded Founder settings: **0 rows / 0 rows**
- owner probe: **10 rows**
- private buckets `founder-truth-pack` and `opportunity-artifacts`: **PASS, public=false**
- Supabase security advisor: **0 findings**

### Still required before hosted data-plane acceptance can close

1. **Authoritative source database access**
   - Need the current Founder Alpha PostgreSQL source connection available to the hosted-proof workflow as `OPOS_SOURCE_DB_URL`.
   - Needed for real data export/import/parity. Do not paste the DSN into chat or Git.

2. **Supabase runtime database connection**
   - Need the staging direct PostgreSQL connection string available as GitHub Environment secrets `OPOS_TARGET_DB_URL` and `CLOUD_DATABASE_URL`.
   - The connected Supabase management tool can execute SQL but does not expose the database password/DSN.

3. **Private Founder Truth Pack bytes**
   - Need the actual current Truth Pack uploaded to the private `founder-truth-pack` bucket through an authenticated storage surface.
   - Need its SHA-256 and credential-free object URI; object bytes/private claims must never enter Git/chat evidence.
   - Current connected Supabase tooling does not expose Storage object upload.

4. **Private artifact live proof**
   - Requires a running API/worker and server-side storage credential path; bucket is ready but object generation/retrieval-after-restart is not yet executable.

## Azure / Cloudflare provider readiness

A dedicated no-mutation GitHub Actions preflight was executed against the protected `fr007-staging` environment.

All provider variables/secrets are currently absent there.

Missing before Azure/Cloudflare execution:
- `AZURE_RESOURCE_GROUP`
- `AZURE_MANAGED_ENVIRONMENT_ID`
- `AZURE_LOCATION`
- `OPOS_AZURE_NAME_PREFIX`
- `OPOS_AZURE_IMAGE`
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `CLOUD_DATABASE_URL`
- `OPPORTUNITYOS_FOUNDER_PASSWORD_HASH`
- `OPPORTUNITYOS_SESSION_SECRET`
- `OPPORTUNITYOS_TRUTH_PACK_URI`
- `OPPORTUNITYOS_TRUTH_PACK_HASH`
- one of `OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN` or `OPPORTUNITYOS_TRUTH_PACK_API_KEY`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

Deferred until deployments create endpoints:
- `OPPORTUNITYOS_API_ORIGIN`
- `OPOS_STAGING_WEB_URL`

Required before hosted browser smoke:
- `OPPORTUNITYOS_FOUNDER_PASSWORD`

## Dispatch status

`READY_TO_DISPATCH_W16B: NO`

Reason: known provider/account/secret prerequisites remain unresolved. Do not send Antigravity W16B until this certificate is revised to YES.
