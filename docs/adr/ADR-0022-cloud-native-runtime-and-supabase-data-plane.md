# ADR-0022 — Cloud-Native Runtime and Supabase Data Plane

- **Status:** Superseded in part by ADR-0023
- **Date:** 2026-09-17
- **Related:** BRIEF-FR-007, ADR-0008, ADR-0009, ADR-0011, ADR-0012, ADR-0013

## Supersession note

ADR-0023 is the current Founder decision for FR-007 runtime economics and compute: Azure/student-credit/paid compute is no longer approved. Supabase + Cloudflare + GitHub are the only active runtime providers, with a hard $0 gross-spend invariant. The PostgreSQL/projection/queue/portability reasoning below remains historical architecture context where it does not conflict with ADR-0023.

## Context

Founder Web Alpha proved the OpportunityOS domain model and founder-facing workflow, but the production runtime remains too dependent on long-lived local processes, ephemeral process caches, and a founder-owned Windows host. The observed failure mode is not simply insufficient server capacity: the interactive feed can become expensive after process restarts because parts of visibility/filtering behavior are recomputed in process memory, while manual polling can enqueue broad source work and compete with user-facing requests.

OpportunityOS requires a durable cloud runtime that continues acquiring, evaluating, serving, and backing up opportunities while every founder-owned computer is powered off. The system must also preserve the existing truth/provenance, source-policy, identity/idempotency, and external-action safety contracts.

## Decision

### PostgreSQL remains the canonical datastore

OpportunityOS keeps PostgreSQL as its core data system. The product is relational and provenance-heavy: opportunities, source occurrences, evidence, evaluations, founder state, application state, idempotency, artifacts, and scheduling all benefit from transactions, constraints, joins, indexes, and explicit migration control.

Supabase is the preferred managed production data platform for the Founder Alpha replatform because it provides managed PostgreSQL plus Auth, RLS, private Storage, Realtime, and PostgreSQL-native queue/scheduling capabilities under one operational boundary.

The repository remains migration authority. Supabase-specific conveniences may be used, but the canonical schema and business rules must remain portable PostgreSQL where practical.

### Persisted feed projections replace request-time corpus recomputation

Founder-facing feed/search/filter behavior is served from indexed persisted database state, including a durable `feed_projection`-style contract bound to opportunity content and founder/truth-pack version.

Process-local caches may improve latency but may never be correctness-critical. A cold process must return the same logical result without corpus-wide Python hydration or cache warm-up.

### Background work becomes durable and asynchronous

Polling, normalization, re-extraction, evaluation, artifact generation, notifications, and maintenance run as persisted jobs with idempotency keys, leases, retry/dead-letter state, and durable source schedule state.

Supabase Queues/`pgmq` is preferred where available. An ordinary PostgreSQL-backed lease table is an acceptable implementation if it provides equivalent durability and testable semantics.

`Poll Now` becomes an asynchronous due-work request. It must not synchronously poll sources, blank the current feed, or enqueue every read-allowed source without regard to cadence/cooldown/already-pending state.

### Cloudflare is the public edge

Cloudflare remains the owner of the public domain, DNS, TLS, CDN/edge controls, and static web delivery where appropriate. Cloudflare is not the canonical relational datastore.

The frontend deploys independently from acquisition/evaluation workers so worker failure cannot make the existing feed unavailable.

### Compute is container-portable

Python domain workers are packaged as OCI containers with no business-logic dependency on one cloud provider. Initial founder-stage deployment may use Azure Container Apps / Container Apps Jobs under available GitHub Student/Azure for Students benefits because it can run containerized work without a founder PC and without requiring architecture-specific rewrites.

If Azure entitlement/account constraints block deployment, the same images may run on another compatible managed surface such as Railway, Fly.io, Cloud Run, ECS/Fargate, or a conventional cloud VM. Provider substitution must not change OpportunityOS semantics.

FastAPI remains only where Python/domain operations require it. Normal feed reads should use the simplest secure indexed path, including Supabase PostgREST/RPC where appropriate, rather than routing all reads through a heavyweight Python service by default.

### GitHub Actions is CI/CD, not the production scheduler

GitHub remains the source/PR/CI system and may build images, run migrations, execute bounded backfills, and deploy. Scheduled GitHub Actions is not a correctness-critical ingestion scheduler because schedule timing is not a production availability contract.

### Search stays in PostgreSQL initially

Use PostgreSQL full-text search with GIN indexes and `pg_trgm` where useful. Add `pgvector` only for a measured semantic-search requirement. A dedicated search service is introduced only if measured Postgres query performance fails the product SLO after correct indexing/projection design.

### Private truth and artifacts move to durable cloud state

Production no longer depends on `private/truth_pack.yaml` or local filesystem artifacts. Founder truth/profile data is stored in private durable state with explicit version/hash/provenance binding and least-privilege access. Generated files live in private object storage and remain bound to opportunity/truth-pack/template/validator versions.

No raw founder truth, service credentials, database credentials, or storage secrets enter GitHub.

### Backup and observability are independent concerns

A production backup is trusted only after a restore test. Use provider-native backup features available on the selected tier plus an encrypted logical off-provider copy in Cloudflare R2 or an equivalent independent store.

External availability monitoring, application error capture, queue/job heartbeats, source freshness, and backup heartbeat must detect incidents without the founder opening the application.

## Consequences

### Positive

- Founder-owned computers leave the production dependency graph.
- Web/feed availability is isolated from worker/source failures.
- Cold restarts no longer require corpus cache warm-up.
- Source and job state survive process restarts.
- Polling becomes cadence-aware, idempotent, and observable.
- Managed Auth/RLS/Storage reduce bespoke production plumbing.
- Existing Python opportunity/matching/truth/artifact domain code can be retained behind new infrastructure boundaries.
- PostgreSQL portability keeps a credible exit path from Supabase or the initial compute provider.

### Costs and trade-offs

- The replatform requires schema/projection, queue, auth, storage, deployment, migration, monitoring, and DR work before Founder Alpha can be considered reliable.
- Supabase free-tier behavior is not treated as a contractual production SLA; a future paid tier may be justified by product reliability/backup requirements.
- Azure Student benefits are temporary economics, not architecture. The worker image must remain portable.
- Direct browser access to Supabase increases the importance of correct RLS and explicit public/private views.
- Running a parallel shadow migration temporarily increases operational complexity but reduces data-loss/cutover risk.

## Rejected as primary architecture

- **Founder PC + Cloudflare Tunnel:** useful for development, rejected as production dependency because residential power/network/process state becomes a single point of failure.
- **Move the existing monolith unchanged to a VPS:** improves host uptime but retains request-path recomputation, process coupling, and failure-domain problems.
- **Firestore/Firebase as the core store:** weaker fit for OpportunityOS's relational/provenance-heavy model and migration/query needs.
- **Cloudflare D1 as the core store:** useful edge database but not preferred over PostgreSQL for the current relational workload and existing domain model.
- **Convex as the core platform:** attractive reactive model, but unnecessary provider coupling for a product whose domain model already aligns well with PostgreSQL.
- **GitHub Actions as the primary scheduler/worker fleet:** retained for CI/CD and bounded maintenance only, not production orchestration.
- **Kubernetes/Kafka/Redis by default:** rejected as premature operational complexity without a measured requirement.
- **Dedicated search cluster now:** rejected until indexed PostgreSQL search fails measured product SLOs.

## Exit strategy

The system must maintain:

1. repository-owned migrations;
2. provider-neutral OCI worker images;
3. exportable PostgreSQL data;
4. private artifact inventory/export;
5. documented secret/config schema without provider-specific values in code;
6. a tested restore/export path sufficient to move Supabase data and worker compute to another compatible provider.

This ADR changes infrastructure/runtime authority only. It does not weaken the Product Constitution, truth-lock, source-policy, action-authority, provenance, idempotency, or single-Founder tenancy rules.