# FR-007 Zero-Dollar Runtime — Pre-dispatch Readiness

Updated: 2026-09-19
Authority: ADR-0023
Approved production providers: Supabase, Cloudflare, GitHub
Hard economics: $0 gross provider charge; $0 Founder out-of-pocket; no student/trial credits; no paid overage.

## Already complete

- Supabase staging project `opportunityos-staging` / `lrrcpwaapwynzdsxzwhy`: ACTIVE_HEALTHY.
- OpportunityOS schema 0001 -> 0009 applied to real hosted PostgreSQL.
- Provider security hardening applied.
- 26/26 public base tables RLS-enabled.
- 52 browser-deny policies.
- Dangerous browser grants removed.
- Live RLS probe: owner 10 rows; anon 0; authenticated 0.
- Private buckets exist:
  - `founder-truth-pack` (public=false)
  - `opportunity-artifacts` (public=false)
- Supabase security advisor: 0 findings.
- GitHub repository is currently public, enabling the approved standard-runner no-charge execution path.
- Azure is explicitly excluded. No Azure resource, account, credential, workflow, or subscription is required.

## Founder-only setup required before the next runtime Master dispatch

These values must be configured in GitHub Environment `fr007-staging`. Never place values in Git or chat.

### Supabase database/runtime

- `OPOS_TARGET_DB_URL`
- `CLOUD_DATABASE_URL`

Use the Supabase staging project's PostgreSQL connection suitable for the GitHub/runtime network path.

### Private Truth Pack

- Upload the actual current Truth Pack into private bucket `founder-truth-pack`.
- Record the credential-free private object URI as `OPPORTUNITYOS_TRUTH_PACK_URI`.
- Record its SHA-256 as `OPPORTUNITYOS_TRUTH_PACK_HASH`.
- Configure server-only Storage credentials:
  - `OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN`
  - `OPPORTUNITYOS_TRUTH_PACK_API_KEY`

### Cloudflare

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

The token must be least-privilege for the existing Cloudflare account/domain and must not enable or require a paid Workers plan.

### Backup encryption

- `BACKUP_ENCRYPTION_KEY`

Logical backups will be encrypted before being persisted as size-capped GitHub artifacts.

### Founder Supabase Auth — required before hosted auth/browser smoke

- create the single Founder user in Supabase Auth;
- public signup must remain disabled;
- GitHub protected test credentials:
  - `E2E_FOUNDER_EMAIL`
  - `E2E_FOUNDER_PASSWORD`

These are for hosted acceptance smoke only and are never committed.

## Source migration/parity

A-9 still requires comparison with the authoritative pre-cloud Founder Alpha PostgreSQL data.

If the authoritative source DB is local-only on the Founder PC:
- do not expose it publicly;
- use the one-shot local export/encrypted transfer/parity path that will be prepared before migration authority moves.

If it is already remotely reachable:
- configure `OPOS_SOURCE_DB_URL` as a protected environment secret.

Source parity is not a prerequisite for repository implementation of the zero-dollar runtime, but it is mandatory before A-9/cutover closure.

## Automatically derived/deferred values

Do not ask the Founder to configure these before deployment creates them:

- final Cloudflare staging/public web URL;
- monitor web URL;
- any post-deployment route identifiers.

## Pre-dispatch rule

Run:

`.github/workflows/fr007-zero-dollar-readiness.yml`

before sending the next provider-dependent Master prompt.

The workflow must prove:
- hard $0 envelope;
- current public/no-charge GitHub standard-runner path;
- target Supabase DB connectivity + migration/RLS baseline;
- private Truth Pack retrieval + hash;
- Cloudflare token/account access.

`READY_TO_DISPATCH: YES` is allowed only after all task-critical checks are green.

Current state:

`READY_TO_DISPATCH: NO`

Reason: protected Founder/provider secrets and the private Truth Pack object are not yet configured. This is a setup boundary, not executor work.
