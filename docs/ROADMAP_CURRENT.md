# OpportunityOS Current Roadmap

This is the compact execution map. `docs/MASTER_PLAN.md` remains the long-horizon requirement source.

## Current Phase — FR-007 Cloud-Native Founder Alpha Replatform

Founder Web Alpha exists, but production reliability is not yet accepted because the current product must be proven independent of a Founder-owned PC and local runtime.

FR-007 is therefore the active execution priority. BRIEF-007 / Multi-Tenant Family Alpha remains blocked until FR-007 is accepted and the Founder validates the resulting cloud-hosted Alpha.

## Immediate Goal

Complete the real hosted staging path: connect the managed PostgreSQL/Supabase target, execute migration/parity proof, establish private durable Truth Pack/artifact storage, and deploy the OCI runtime without giving production authority to the new stack until the staging gates pass.

## Already Integrated

The FR-007 integration branch now contains repository/disposable-runtime proof for:

- persisted PostgreSQL `feed_projection` and SQL-native feed/search/filter/pagination reads;
- durable PostgreSQL `worker_jobs` queue with leases, retry/dead-letter behavior and `FOR UPDATE SKIP LOCKED`;
- persisted `source_schedules` for cadence, next-due, cooldown, last-attempt and last-success state;
- due-only generic Poll Now plus permitted explicit-source semantics;
- durable Retry-After/policy cooldown behavior;
- asynchronous Founder settings/facet/unhide projection maintenance;
- OCI-separated `api`, `worker`, `scheduler`, and `migrate` roles;
- Azure Container Apps/Jobs staging deployment manifests and migration-first release harness;
- Cloudflare Workers/OpenNext staging frontend with same-origin `/api/*` proxy and hosted Desktop + 390px smoke contract;
- private Supabase Storage artifact backend with checksum/size verification and deterministic object identity;
- private remote HTTPS Truth Pack runtime contract with hash binding and server-only credentials;
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
- initial public schema/migration history empty;
- project creation cost recorded as $0/month.

Provider credentials and private Founder data remain outside Git.

The next execution is no longer another repository-preparation wave. It is the real hosted data-plane/private-state execution against this staging target.

The Overseer owns connected-provider operations available only through authenticated Supabase/GitHub tooling. Repository executors receive end goals matched to the capabilities they actually possess.

## Remaining Execution Order

### 1. Real hosted data plane

- connect the real hosted PostgreSQL/Supabase staging target;
- execute repository preflight and migrations;
- prove count/invariant/content-hash parity;
- keep current production authority unchanged until staging gates pass.

### 2. Private cloud state execution

- configure a real private Truth Pack object and verify retrieval after API/worker restart;
- configure a real private artifact bucket and verify generation/retrieval after restart;
- prove secrets remain server-side and object bodies remain private.

### 3. Hosted runtime + frontend execution

- deploy API, worker, scheduler and migrate roles from the same immutable OCI image;
- deploy frontend independently behind Cloudflare;
- prove no Founder-PC/local-filesystem dependency;
- run hosted A-4/A-5/A-6/A-7/A-8 evidence and cold-start/feed SLO measurement.

### 4. Shadow migration and source parity

- run cloud polling in shadow/non-authoritative mode;
- compare canonical identities/source occurrences to the authoritative runtime;
- resolve discrepancies before production authority moves.

### 5. Monitoring, backup and portability

- activate external uptime monitoring and application-error capture;
- activate job/queue/source-freshness/worker-stall/backup heartbeats;
- generate a real test alert/incident;
- produce encrypted off-provider backup;
- restore into a fresh staging environment;
- execute provider-neutral export/restore proof.

### 6. Cutover and soak

- public DNS/runtime cutover only after staging evidence authorizes it;
- authenticated desktop and 390px mobile cloud smoke;
- document the real cost/quota envelope;
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
- no paid infrastructure is silently created;
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
