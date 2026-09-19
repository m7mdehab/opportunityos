# OpportunityOS Founder Alpha deployment

The historical Render Blueprint described by older revisions of this file is retired. ADR-0023 is the current deployment authority.

## Hard runtime boundary

Founder Alpha uses only the already-approved zero-dollar provider set:

- **Supabase Free** — PostgreSQL, Auth/RLS, private Storage, scheduling primitives;
- **Cloudflare** — existing domain, DNS/TLS and web/edge delivery;
- **GitHub** — existing public repository and bounded standard-runner jobs.

Azure, Render, paid VPS/container compute, student/trial credits, and any provider that can create a gross charge are not part of the active deployment.

## Canonical career truth

The Founder-approved career Truth Pack is non-sensitive product truth and ships as the hash-bound repository snapshot:

`founder/truth_pack.yaml.gz.b64`

Cloud/background jobs load it through `truth.pack.load_founder_pack()` and verify its pinned SHA-256. No private Truth Pack bucket or Truth Pack credentials are required.

## Fixed employment CV portfolio

Employment CVs are not generated per posting.

The six final PDFs are catalogued in `founder/cv_portfolio.yaml` and stored in the private Supabase bucket:

`founder-cv-portfolio/2026/`

The application path selects one approved PDF, retrieves it server-side, verifies its SHA-256, and uses those exact bytes. A mismatch or missing object blocks the application; there is no generated-CV fallback.

## Pre-deployment gates

1. `FR-007 Zero-Dollar Provider Readiness` must pass.
2. Supabase schema/RLS and hosted data-plane proof must pass.
3. All six fixed CV objects must exist and match their committed hashes.
4. Cloudflare token/account validation must pass.
5. Backup encryption and zero-dollar quota checks must pass.
6. Hosted authentication/browser smoke must pass before Founder Alpha cutover.

## Deployment flow

- Cloudflare web/edge: `.github/workflows/fr007-cloudflare-staging-deploy.yml`.
- Hosted Supabase proof: `.github/workflows/fr007-hosted-data-plane-proof.yml`.
- Zero-dollar readiness: `.github/workflows/fr007-zero-dollar-readiness.yml`.
- Monitoring/soak: `.github/workflows/fr007-cloud-observability.yml`.
- Portability/restore proof: `.github/workflows/fr007-portability-proof.yml`.

The Founder PC is never a production dependency. GitHub runners are disposable compute only; canonical state remains in Supabase.

## Secrets

Secrets belong in the protected `fr007-staging` GitHub Environment, never in Git. The exact required names are defined by the workflows and validated by the readiness gate.

Do not configure obsolete Azure or Render credentials.
