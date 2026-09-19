# OpportunityOS Current Roadmap

This is the compact execution map. `docs/MASTER_PLAN.md` remains the long-horizon requirement source.

## Current Phase — FR-007 Cloud-Native Founder Alpha Replatform

Founder Web Alpha exists, but production reliability is not yet accepted because the current product must be proven independent of a Founder-owned PC and local runtime.

FR-007 is therefore the active execution priority. BRIEF-007 / Multi-Tenant Family Alpha remains blocked until FR-007 is accepted and the Founder validates the resulting cloud-hosted Alpha.

## Immediate Goal

Complete the real zero-dollar hosted staging path: finish Supabase parity/RLS, prove the repository-managed canonical Truth Pack, load and hash-verify the six private fixed CVs/artifacts, wire Supabase-native Founder browser boundaries and durable scheduling, then deploy the Cloudflare web/edge path. FastAPI/OCI remains portability/test evidence, not production infrastructure.

## Already Integrated

The FR-007 integration branch now contains repository/disposable-runtime proof for:

- persisted PostgreSQL `feed_projection` and SQL-native feed/search/filter/pagination reads;
- durable PostgreSQL `worker_jobs` queue with leases, retry/dead-letter behavior and `FOR UPDATE SKIP LOCKED`;
- persisted `source_schedules` for cadence, next-due, cooldown, last-attempt and last-success state;
- due-only generic Poll Now plus permitted explicit-source semantics;
- durable Retry-After/policy cooldown behavior;
- asynchronous Founder settings/facet/unhide projection maintenance;
- OCI-separated `api`, `worker`, `scheduler`, and `migrate` roles;
- historical Azure deployment manifests exist but are no longer an active runtime target under ADR-0023;
- Cloudflare Workers/OpenNext staging frontend with same-origin `/api/*` proxy and hosted Desktop + 390px smoke contract;
- private Supabase Storage artifact backend with checksum/size verification and deterministic object identity;
- Founder-approved repository-managed canonical Truth Pack snapshot with pinned hash verification;
- migration, parity, backup/restore and provider-exit tooling;
- a manual-only hosted PostgreSQL/Supabase proof harness;
- real PostgreSQL 16 W11 durability/concurrency proof: 15 tests, zero skips;
- repository/disposable-PostgreSQL reliability proof for A-4/A-5/A-6, including worker absence, source-failure isolation, repeated polling and canonical identity preservation.

These are implementation/repository proofs. They do not by themselves close hosted-production acceptance criteria.

## Current Hosted Staging State

W15 repository preparation is integrated: hosted single-Founder auth/session/RLS and the observability/release/soak control plane are in the authoritative FR-007 integration branch.

A real Supabase staging project now exists and is healthy:

- `opportunityos-staging`;
- project ref `lrrcpwaapwynzdsxzwhy`;
- region `eu-central-1`;
- PostgreSQL 17;
- safe API origin `https://lrrcpwaapwynzdsxzwhy.supabase.co`;
- hosted application schema present at Alembic revision `0009_hosted_founder_auth`, with the expected 26-table public RLS baseline;
- project creation cost recorded as $0/month.

Provider credentials and private artifact bodies remain outside Git. The canonical career Truth Pack is Founder-approved repository-managed product truth. All six fixed CV PDFs are now present in private Supabase Storage and have passed exact remote re-download SHA-256 verification against the committed catalog.

The next execution is no longer another repository-preparation wave. It is the real hosted data-plane/private-state execution against this staging target.

The Overseer owns connected-provider operations available only through authenticated Supabase/GitHub tooling. Repository executors receive end goals matched to the capabilities they actually possess.

## Remaining Execution Order

### 1. Real hosted data plane

- connect the real hosted PostgreSQL/Supabase staging target;
- execute repository preflight and migrations;
- prove count/invariant/content-hash parity;
- keep current production authority unchanged until staging gates pass.

### 2. Career truth and private application-file execution

- prove the repository-managed canonical Truth Pack decodes, loads and verifies its pinned SHA-256 in cloud/background execution;
- [complete] six Founder-approved fixed CV PDFs uploaded to private `founder-cv-portfolio` and every remote object verified against its committed SHA-256;
- configure/verify generated artifact private storage and restart-safe retrieval;
- prove secrets remain server-side and private file bodies remain private.

### 3. Zero-dollar hosted runtime + frontend execution

- wire Supabase Auth + Founder-only RLS/views/RPCs for interactive feed/search/detail/settings/Poll Now;
- wire Supabase Cron/`pg_cron` to persisted source schedule state;
- run bounded Python queue workers through standard GitHub Actions runners, with all state durable in Supabase;
- deploy the frontend on the existing Cloudflare account/domain, preferring static/client-rendered delivery and a thin Worker edge;
- prove no Founder-PC/local-filesystem/paid-compute dependency;
- run hosted A-4/A-5/A-6/A-7/A-8 evidence and cold-start/feed SLO measurement.

### 4. Shadow migration and source parity

- run cloud polling in shadow/non-authoritative mode;
- compare canonical identities/source occurrences to the authoritative runtime;
- resolve discrepancies before production authority moves.

### 5. Monitoring, backup and portability

- activate external uptime monitoring and application-error capture;
- activate job/queue/source-freshness/worker-stall/backup heartbeats;
- generate a real test alert/incident;
- produce an encrypted logical off-provider backup as a size-capped GitHub Actions artifact within the existing zero-dollar allowance;
- restore into a fresh staging environment;
- execute provider-neutral export/restore proof.

### 6. Cutover and soak

- public DNS/runtime cutover only after staging evidence authorizes it;
- authenticated desktop and 390px mobile cloud smoke;
- prove the hard zero-dollar envelope: $0 gross charge, $0 out-of-pocket, no credit/trial dependency, and fail-closed quota behavior;
- run at least 7 consecutive days with Founder-owned production host processes disabled/offline.

### 7. Terminal acceptance

Close A-0 through A-17 only from persisted evidence and independent verification.

FR-007 closure does not automatically start BRIEF-007. Founder product validation remains a separate gate.

## Engineering Priority Rules

- repository/runtime truth outranks executor self-report;
- truth/provenance and external side-effect safety outrank convenience;
- UNKNOWN is not FALSE and ABSENT is not INELIGIBLE;
- source coverage is not permission;
- 403/429/CAPTCHA/MFA/policy restrictions are stop conditions;
- no paid infrastructure, student-credit resource, trial-credit resource or billable overage path is permitted;
- no production secret or private Founder truth enters Git;
- backups are not accepted until restore proof passes;
- provider-specific infrastructure must not rewrite core domain logic;
- use the locked Overseer loop in `docs/OVERSEER_EXECUTION_LOCK.md`: pre-solve -> one executor wave -> independent verification -> at most one focused remediation -> Overseer closes ordinary residuals.

## What Not To Optimize For

- registry/source count without compliant productive yield;
- deployment activity mistaken for acceptance;
- premature multi-tenancy;
- Kubernetes/Kafka/Redis/search infrastructure without measured need;
- repeated executor ping-pong for ordinary last-mile defects;
- provider/model prestige rather than proven product outcomes.
