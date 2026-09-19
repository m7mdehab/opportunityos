# FR-007 W16 Hosted Execution Readiness Certificate

**Status:** setup in progress  
**Authoritative owner:** Overseer  
**Target:** complete W16A hosted data/private-state acceptance, then authorize W16B runtime deployment  
**Supabase project:** `opportunityos-staging` / `lrrcpwaapwynzdsxzwhy` / `eu-central-1`

## Completed prerequisites

- W15A hosted auth/RLS repository work: LANDED.
- W15B observability/release/soak repository work: LANDED.
- W16A provider-execution bundle: LANDED.
- Supabase staging project: ACTIVE_HEALTHY.
- Hosted schema: migration `0009_hosted_founder_auth` EXECUTED.
- Hosted RLS: anon/authenticated deny probes and owner path EXECUTED.
- Private Supabase buckets: `founder-truth-pack` and `opportunity-artifacts`, `public=false`.
- Supabase security advisor: zero security lints.
- Pre-dispatch governance: LANDED.

## Known blocker ledger

| ID | Requirement | Current state | Owner | Dispatch effect |
|---|---|---|---|---|
| S-01 | Authoritative source PostgreSQL state/export | NOT AVAILABLE to Overseer/provider tools | Founder/setup | Blocks A-9 source->target import/parity |
| S-02 | Actual private Founder Truth Pack bytes | NOT AVAILABLE in repo, ChatGPT files, Library or searched Drive | Founder/setup | Blocks private object upload and hosted Truth Pack restart proof |
| S-03 | GitHub `fr007-staging` protected secrets/vars | Environment exists but required values are absent | Founder + Overseer-prepared values | Blocks Azure/Cloudflare workflows |
| S-04 | Azure account/OIDC target | No configured client/tenant/subscription IDs; no Azure management connector available | Founder interactive setup | Blocks Azure WHAT_IF/deploy |
| S-05 | Azure RG / Container Apps environment | Not configured/proven | Founder interactive Azure bootstrap after S-04 | Blocks Azure deploy |
| S-06 | Deployable private OCI image and pull path | No image-publish workflow/registry target currently configured | Overseer repository prep + Azure/GitHub credential path | Blocks runtime deploy |
| S-07 | Cloudflare API access | Token/account ID absent; no Cloudflare connector available | Founder interactive setup | Blocks Worker deployment |
| S-08 | Cloud DB runtime DSN | Supabase DB password/connection secret not available to GitHub environment | Founder secret injection | Blocks Azure runtime |
| S-09 | Founder staging login secret | Plain staging password absent from GitHub environment | Founder secret injection; hash can be derived in CI | Blocks hosted auth/browser smoke |
| S-10 | Durable session secret | Absent from GitHub environment | Founder/setup script can generate and inject | Blocks API runtime |
| S-11 | Truth Pack private-storage credentials | Supabase server-side credential absent from GitHub environment | Founder secret injection | Blocks API/worker private Truth Pack retrieval |
| S-12 | Staging public/API/web origins | Depend on live Azure/Cloudflare deployments | Overseer after deployments | Not Founder input once providers configured |
| S-13 | Workflow dispatch authority | Current Overseer GitHub connector cannot start workflow_dispatch runs | Founder UI or authenticated CLI, unless push-triggered setup path is deliberately added | Must be resolved before W16B dispatch |

## Provider-readiness probe

Temporary draft PR #123 executes against GitHub Environment `fr007-staging` and reveals only presence/absence plus provider-auth success. Its first run confirmed that every expected W16 Azure/Cloudflare secret and variable is currently absent.

The temporary probe must not be treated as acceptance evidence.

## Capability routing

- Supabase management/SQL mutations: Overseer connected Supabase surface.
- GitHub repository/PR/CI integration: Overseer connected GitHub surface.
- Azure management: no authenticated execution surface currently available.
- Cloudflare management: no authenticated execution surface currently available.
- Master Agent W16B: **DO NOT DISPATCH** until the provider surfaces and protected configuration it needs are ready.

## Dispatch gate

`READY_TO_DISPATCH: NO`

Dispatch may become YES only after:

1. W16A A-9/A-11 private-data prerequisites are supplied and hosted checks completed or explicitly separated from W16B without creating a dependency hole;
2. Azure OIDC and foundational resources are validated;
3. a private immutable OCI image can be pulled by Azure Container Apps;
4. Cloudflare token/account access is validated;
5. required `fr007-staging` secrets/variables are present;
6. a usable deployment invocation path exists;
7. a final readiness probe passes without exposing values.
