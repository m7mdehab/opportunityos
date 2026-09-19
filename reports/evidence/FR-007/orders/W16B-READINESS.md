# FR-007 W16B Pre-Dispatch Readiness Certificate

Work order: W16B hosted runtime / edge activation
Authoritative base SHA at certificate creation: `6ce2bbe06c0107332f8651bc53b6eb2797761db7`

## Dependency status

- W15A hosted auth/RLS: LANDED
- W15B observability/release controls: LANDED
- Supabase staging project: ACTIVE_HEALTHY
- Supabase schema migration through `0009_hosted_founder_auth`: EXECUTED LIVE
- Supabase public-table RLS: EXECUTED LIVE
- Supabase browser-role non-row privilege hardening: EXECUTED LIVE
- Supabase private bucket bootstrap: EXECUTED LIVE
- W16A source-data parity: PENDING SOURCE ACCESS
- W16A private Truth Pack object/restart proof: PENDING PRIVATE INPUT
- W16A artifact remote body/restart proof: PENDING RUNTIME

## Safe external resources

- Supabase project: `opportunityos-staging`
- Supabase project ref: `lrrcpwaapwynzdsxzwhy`
- Supabase region: `eu-central-1`
- Safe API origin: `https://lrrcpwaapwynzdsxzwhy.supabase.co`

## Provider execution surfaces

- Supabase management/database DDL: Overseer connected Supabase tool — AUTHENTICATED
- GitHub source/PR/CI: Overseer connected GitHub tool — AUTHENTICATED
- Azure: GitHub `fr007-staging` environment via OIDC — MUST PASS readiness workflow
- Cloudflare: GitHub `fr007-staging` environment via API token — MUST PASS readiness workflow
- Antigravity local Azure/Cloudflare credentials: NOT REQUIRED by design once GitHub provider path is proven

## Secret injection paths

Secret VALUES must never be committed or written to this certificate.

Expected protected GitHub Environment secret names:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `CLOUD_DATABASE_URL`
- `OPPORTUNITYOS_FOUNDER_PASSWORD_HASH`
- `OPPORTUNITYOS_SESSION_SECRET`
- `OPPORTUNITYOS_TRUTH_PACK_URI`
- `OPPORTUNITYOS_TRUTH_PACK_HASH`
- `OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN` or `OPPORTUNITYOS_TRUTH_PACK_API_KEY`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `OPPORTUNITYOS_FOUNDER_PASSWORD`

Expected protected environment variables:

- `AZURE_RESOURCE_GROUP`
- `AZURE_MANAGED_ENVIRONMENT_ID`
- `AZURE_LOCATION`
- `OPOS_AZURE_NAME_PREFIX`
- `OPOS_AZURE_IMAGE` (immutable digest form)

Post-deploy variables such as `OPPORTUNITYOS_API_ORIGIN` and `OPOS_STAGING_WEB_URL` are intentionally not prerequisites for the foundational provider preflight; they are populated from deployment output before browser smoke.

## Cost / terms

- Supabase staging project: $0/month at creation, Founder approved.
- Azure paid-resource creation: NOT AUTHORIZED beyond existing eligible/student resources.
- Cloudflare paid-resource creation: NOT AUTHORIZED.
- No terms acceptance may be performed by an agent.

## PR / CI path

- Provider readiness workflow: `.github/workflows/fr007-provider-readiness.yml`
- It runs automatically on this preparation PR, uses `environment: fr007-staging`, verifies configuration presence, Azure OIDC/resource access, hosted DB read access, Cloudflare token/account access, and immutable image pinning.
- It prints only secret/variable NAMES when missing; it must never echo secret values.

## Known blocker ledger

| Blocker | Owner | Status |
|---|---|---|
| Real source DB/export for A-9 parity | Founder/Overseer setup | PRE_DISPATCH |
| Private Founder Truth Pack bytes for hosted upload | Founder/Overseer setup | PRE_DISPATCH |
| GitHub fr007-staging Azure/Cloudflare/database/truth secret readiness | Readiness workflow | PRE_DISPATCH |
| Azure foundation/resource access | Readiness workflow | PRE_DISPATCH |
| Cloudflare account/token access | Readiness workflow | PRE_DISPATCH |
| Immutable deployable OCI image | Readiness workflow / Overseer | PRE_DISPATCH |
| W16A PR integration and hosted evidence reconciliation | Overseer | PRE_DISPATCH |

## Dispatch decision

`READY_TO_DISPATCH: NO`

This certificate becomes YES only after every PRE_DISPATCH row is resolved.
