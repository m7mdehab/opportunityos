# FR-007 Zero-Dollar Cost & Quota Control Plane

This document is the authoritative cost rule for the Founder Alpha under ADR-0023.

The Founder decision is stricter than "no out-of-pocket spend": **OpportunityOS must use only already-owned resources whose declared runtime envelope has a gross provider charge of $0.00.**

Credits do not count as free.

## Locked rules

1. **Gross provider charge = $0.00.**
2. **Founder out-of-pocket charge = $0.00.**
3. Student, trial, promotional, prepaid or reimbursed credits are not architecture.
4. Azure is not an approved FR-007 runtime provider.
5. No paid plan, paid add-on, larger GitHub runner, metered overage or automatic upgrade is allowed.
6. When a free quota is exhausted, that subsystem fails closed, pauses or degrades without spend.
7. Only the current approved provider set may be used: **Supabase, Cloudflare, GitHub**.
8. Any future paid runtime requires a new explicit Founder decision and ADR.

Machine-readable authority:

`reports/evidence/FR-007/cloud-cost-quota.json`

Validation:

`python scripts/validate_cloud_cost_quota.py --production`

## Provider envelope

| Provider | Active use | $0 basis | Fail-closed quota posture |
|---|---|---|---|
| **Supabase Free** | PostgreSQL, Auth, RLS, private Storage, Cron/pg_cron, optional thin Edge Functions | 500 MB DB, 1 GB file storage, 5 GB egress, 500k Edge Function invocations/month, 2 active Free projects | refuse paid add-ons/upgrades; monitor storage/egress/function usage; pause non-critical work before a paid path |
| **Cloudflare Free / existing domain** | DNS/TLS, static frontend assets, thin Worker edge | Workers Free: 100k requests/day, 10 ms HTTP CPU/request, 5 cron triggers/account; static asset requests are free | keep heavy logic off Worker; fail when free request/CPU limits are exhausted; never switch the account to Workers Paid automatically |
| **GitHub existing account** | source/CI, bounded Python worker jobs, external monitoring, encrypted logical backup artifacts | standard GitHub-hosted runners on the current public repository are no-charge; existing Pro artifact/cache allowance applies | standard runners only; no larger runners; artifact size/retention capped; if repository visibility/cost rules change, production execution stops pending a new envelope |

## Runtime economics

There is no always-on paid compute service.

The active runtime shape is:

`Cloudflare web/edge -> Supabase Auth/RPC/PostgreSQL/Storage <- GitHub Actions bounded Python workers`

Supabase Cron or persisted schedule state decides what is due. GitHub Actions provides disposable execution capacity for the existing Python domain engine.

The Founder PC is not a production worker.

## GitHub Actions guardrails

The current repository is public, so GitHub's standard hosted runners are no-charge under GitHub's published Actions billing rules.

This is an explicit zero-dollar assumption.

If the authoritative runtime repository becomes private, the cost validator/readiness gate must be revisited before scheduled production workers continue. Do not silently consume billable minutes.

Allowed:

- standard Ubuntu hosted runners;
- scheduled or workflow-dispatch bounded jobs;
- normal CI;
- encrypted, size-capped artifacts.

Forbidden:

- larger runners;
- paid Actions capacity;
- unchecked artifact growth;
- using Actions filesystem as canonical state.

Canonical state always remains in Supabase.

## Supabase guardrails

Founder-Alpha projections are deliberately far below the Free limits.

The control plane monitors:

- database size;
- file-storage size;
- egress;
- active-project count;
- Edge Function invocations if used;
- inactivity/pause risk.

The system should naturally remain active through cron, worker and monitoring traffic. Synthetic traffic must not be used to conceal a broken runtime.

No paid:

- IPv4 add-on;
- PITR;
- automatic backup add-on;
- custom Supabase domain;
- read replicas;
- compute upgrade.

## Cloudflare guardrails

Prefer static asset delivery so normal page assets do not consume Worker requests/CPU.

The Worker is intentionally thin:

- edge routing;
- security headers;
- optional lightweight request handling.

Heavy polling, matching, document generation, or Python business logic never runs in Workers Free.

The Worker deployment must remain on the Free plan.

## Backup economics

Supabase Free does not provide the paid backup/PITR posture assumed by higher tiers.

FR-007 therefore uses:

1. GitHub Actions standard runner;
2. logical PostgreSQL export;
3. encryption before persistence;
4. encrypted Actions artifact only;
5. max archive size enforced before upload;
6. short bounded retention;
7. fresh restore drill.

No unencrypted Founder data may enter a GitHub artifact.

If the encrypted backup cannot fit within the approved included artifact envelope, backup must fail and FR-007 cannot close until the Founder approves a new architecture. It must not create storage spend.

## Verification invariant

The cost validator must reject:

- any service not in the approved provider set;
- any gross charge greater than zero;
- any student/trial credit dependency;
- any paid resource flag;
- Azure;
- Cloudflare Workers Paid;
- Supabase paid tier/add-on assumptions;
- GitHub larger runners;
- a private-repository Actions assumption that would exceed its included zero-cost allowance;
- contradictory summary totals.

A-17 closes only when runtime evidence proves the deployed configuration matches this envelope.
