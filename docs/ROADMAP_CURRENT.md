# OpportunityOS Current Roadmap

This is the compact execution map. `docs/MASTER_PLAN.md` remains the long-horizon requirement source.

## Current Phase — FR-007 Cloud-Native Founder Alpha Replatform

Founder Web Alpha exists, but production reliability is not yet accepted because the current product must be proven independent of a Founder-owned PC and local runtime.

FR-007 is therefore the active execution priority. BRIEF-007 / Multi-Tenant Family Alpha remains blocked until FR-007 is accepted and the Founder validates the resulting cloud-hosted Alpha.

## Immediate Goal

Complete the real hosted staging path: connect the managed PostgreSQL/Supabase target, execute migration/parity proof, establish private durable Truth Pack/artifact storage, and deploy the OCI runtime without giving production authority to the new stack until the staging gates pass.

## Already Integrated

The FR-007 integration branch now contains:

- persisted PostgreSQL `feed_projection` and SQL-native feed reads;
- durable PostgreSQL `worker_jobs` queue with leases, retry/dead-letter behavior and `FOR UPDATE SKIP LOCKED`;
- persisted `source_schedules` for cadence, next-due, cooldown, last-attempt and last-success state;
- due-only generic Poll Now plus permitted explicit-source semantics;
- durable Retry-After/policy cooldown behavior;
- asynchronous Founder settings/facet/unhide projection maintenance;
- OCI-separated `api`, `worker`, `scheduler`, and `migrate` roles;
- remote HTTPS Truth Pack loading with hash verification and no cloud-mode local-file fallback;
- migration, parity, backup/restore and provider-exit tooling;
- a manual-only hosted PostgreSQL/Supabase proof harness;
- real PostgreSQL 16 W11 durability/concurrency proof: 15 tests, zero skips.

These are implementation proofs. They do not by themselves close hosted-production acceptance criteria.

## Active Parallel Work

Two bounded implementation lanes are active:

1. cloud deployment manifests + staging release harness;
2. a separate non-overlapping FR-007 implementation lane.

The Overseer owns independent review, ordinary remediation, CI, integration and the authoritative checklist.

## Remaining Execution Order

### 1. Hosted data plane

- provision/connect the real hosted PostgreSQL/Supabase staging target;
- run the repository preflight;
- execute staging migration;
- prove count/invariant/content-hash parity;
- keep local production authoritative until the cutover gates pass.

### 2. Private cloud state

- move the production Founder Truth Pack to private durable cloud storage;
- move generated/private artifacts to private durable object storage;
- preserve truth-pack/template/validator version binding;
- verify authorized retrieval after service restart.

### 3. Hosted runtime

- deploy API, worker, scheduler and migrate roles using the same OCI image;
- deploy frontend independently behind Cloudflare;
- prove no Founder-PC/local-filesystem dependency;
- prove workers may fail without taking down feed/search/detail.

### 4. Shadow and reliability proof

- run cloud polling in shadow/non-authoritative mode;
- prove repeated polling is identity/idempotency safe;
- prove one-source failure isolation;
- measure cold-start/feed SLO;
- verify Poll Now behavior in the actual hosted runtime.

### 5. Monitoring, backup and portability

- external uptime monitoring;
- application-error capture;
- job/queue heartbeat;
- source-freshness alerts;
- worker-stall detection;
- backup heartbeat and a real test incident;
- encrypted off-provider backup;
- restore into a fresh staging environment;
- provider-neutral export/restore proof.

### 6. Cutover and soak

- public DNS/runtime cutover only after staging evidence authorizes it;
- authenticated desktop and 390px mobile cloud smoke;
- document real cost/quota assumptions;
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
