# BRIEF-FR-007 — Cloud-Native Founder Alpha Replatform

**Version:** 1.0  
**Date:** 2026-09-17  
**Status:** ACTIVE ON BRIEF BRANCH; do not merge until all acceptance gates close  
**Governing execution:** `AGENTS.md`, `docs/AUTHORITY_INDEX.md`, `docs/AGENT_EXECUTION_PROTOCOL.md`, `docs/CI_EFFICIENCY_POLICY.md`  
**Related decisions:** `docs/adr/ADR-0022-cloud-native-runtime-and-supabase-data-plane.md` (partially superseded), `docs/adr/ADR-0023-zero-dollar-founder-runtime.md` (current runtime/cost authority)  
**Founder decision:** rebuild the Founder Alpha runtime as a real cloud/web product and remove all production dependence on a founder-owned PC.  
**Phase boundary:** BRIEF-007 / Multi-Tenant Family Alpha remains blocked. This brief is reliability/replatform work required before Founder Alpha can be accepted.

---

## 0. Why this brief exists

The Founder Alpha proved the product model but not the production architecture.
The current public runtime can become unavailable or slow after process/host restarts because interactive feed behavior and polling are still coupled to long-lived local processes, ephemeral process caches, and a founder-owned Windows host. `Poll Now` also has behavior that can enqueue broad source work and compete with feed refreshes.

This brief replaces that runtime posture without discarding the valuable domain engine already built.

The end state is not "the same app on a different machine." The end state is:

- managed durable cloud state;
- indexed, persisted feed projections;
- durable asynchronous jobs;
- separately deployable/failable web, API/domain service, scheduler, and workers;
- no correctness-critical process-local cache;
- no source polling or corpus-wide qualification work on a user request path;
- no production dependency on a founder laptop/desktop;
- tested backup and restore;
- external monitoring;
- portable infrastructure and provider exit capability.

---

## 1. Locked architecture target

### 1.1 Public edge and frontend

- Cloudflare owns DNS, TLS, custom domain, edge protection, and static frontend delivery.
- `opportunityos.m7mdehab.com` remains the canonical Founder Alpha URL.
- The web application is deployed independently of Python workers.
- The feed remains usable if all acquisition/evaluation workers are stopped.

### 1.2 Durable data plane

Supabase becomes the managed production data platform:

- PostgreSQL is the source of truth;
- Auth protects founder access;
- RLS is mandatory on browser-accessible data;
- private Storage holds generated artifacts and private uploaded assets where appropriate;
- Realtime may update job/projection state but is not required for correctness;
- durable queue/job state is persisted in PostgreSQL using Supabase Queues/`pgmq` where available, otherwise an equivalent PostgreSQL-backed lease table with the same semantics;
- scheduling authority lives in durable PostgreSQL state (`source_schedules`) and Supabase Cron/`pg_cron` may enqueue due work; GitHub Actions may execute persisted jobs but is never the source of truth for cadence/cooldown.

PostgreSQL remains authoritative. Do not replace the core datastore with Firestore, D1, Convex, or another non-relational store in this brief.

### 1.3 Compute plane — hard $0 Founder Alpha

The active Founder-Alpha runtime uses **no Azure and no paid compute provider**.

Heavy Python/domain work remains provider-neutral and container-portable, but Founder Alpha executes it as bounded standard GitHub Actions jobs against persisted Supabase queue/schedule state.

Interactive correctness must not require an always-on Python service. Normal feed/search/detail/auth should use Supabase Auth + RLS + indexed views/RPCs where practical, with Cloudflare serving the web/edge layer.

GitHub runners are disposable compute only: all jobs, leases, retries, source cadence, canonical data and artifact metadata remain durable in Supabase. If a runner is delayed or terminated, the existing feed remains available and queued work remains recoverable.

The existing OCI/FastAPI packaging remains a portability asset and future paid-runtime exit path, not an active production dependency.

### 1.4 GitHub

GitHub remains:

- source control;
- PR/CI/independent merge proof;
- the approved zero-dollar Python execution surface for bounded Founder-Alpha poll/evaluate/artifact/maintenance jobs;
- migrations, backup/restore verification and bounded backfills;
- external monitoring/incident evidence.

Scheduled Actions are permitted under ADR-0023 because the Founder locked the runtime to already-owned permanent-free resources. Durable schedule truth still lives in PostgreSQL; Actions timing is execution capacity, not canonical state.

### 1.5 Search

Start with PostgreSQL-native search:

- GIN-backed full-text search;
- `pg_trgm` where fuzzy title/company matching materially improves UX;
- `pgvector` only when a measured semantic-search use case justifies it.

Do not add Elasticsearch/Meilisearch/Typesense merely because they are available. A dedicated search service is out of scope unless Postgres fails the measured feed/search SLO.

### 1.6 Notifications

Resend is the default email delivery candidate for digests/alerts, but email is subordinate to runtime reliability. Notification delivery must be server-side and idempotent. A provider abstraction is required so Resend can be replaced without changing OpportunityOS domain logic.

---

## 2. Architectural invariants

These are non-negotiable.

1. Opening the feed never polls sources, evaluates the corpus, warms a process cache, or performs corpus-wide Python filtering.
2. Every feed row is served from persisted database state or a persisted projection.
3. A process restart cannot invalidate correctness.
4. Source polling, normalization, evaluation, artifact generation, notifications, and maintenance are asynchronous jobs with persisted state.
5. Jobs are idempotent and retryable only when the external/source semantics allow retry.
6. A failed source cannot take down unrelated sources or the interactive application.
7. A failed worker cannot take down the feed.
8. `Poll Now` means "request due work"; it never hides the existing feed or synchronously waits for source completion.
9. Every source keeps its explicit policy/rate-limit authority. Cloud migration never widens permission.
10. Canonical source identity and deduplication remain deterministic and stable across retries/redeploys.
11. Truth-lock, provenance, open-world semantics, action authority, and duplicate-submission protections remain unchanged or stronger.
12. Private founder truth is never committed to GitHub or exposed to the browser beyond explicitly authorized fields.
13. No production secret is stored in the repository.
14. Backups are not considered valid until a restore test passes.
15. Provider-specific infrastructure may be replaced without rewriting core domain logic.

---

## 3. Target data model additions

Preserve existing canonical opportunity/provenance/evaluation tables where sound. Add or refactor toward the following durable projections/contracts.

### 3.1 `feed_projection`

One current founder-facing projection per opportunity/profile-version containing at minimum:

- opportunity id and content hash;
- founder/truth-pack version/hash binding;
- canonical title/company/source/url/posting date;
- opportunity type/track/title family/seniority;
- work mode/location/remote scope/employment type;
- qualification decision and reasons;
- fit score/priority score;
- red-line/excluded-industry/visibility state and reason;
- search document / rank fields;
- projection version and evaluated timestamp.

The feed endpoint/query reads this table/view with indexed SQL. It does not construct full `OpportunityFilterContext` objects for the whole corpus.

### 3.2 Durable job model

Every asynchronous unit has persisted state:

- job id/type;
- source/opportunity/artifact key as applicable;
- idempotency key;
- status: queued/running/retry/succeeded/failed/dead;
- attempt count;
- lease owner/expiry;
- scheduled/due time;
- created/started/finished timestamps;
- failure classification/message safe for logs;
- payload reference, not leaked secrets.

The queue implementation may use `pgmq` or an equivalent table-backed lease contract, but the behavioral contract is fixed.

### 3.3 Source schedule state

Persist:

- source id;
- cadence;
- next due time;
- last attempted/succeeded time;
- cooldown/retry-after;
- consecutive failure count;
- latest policy/health classification.

No scheduler restart may cause an unconditional all-source warm-up.

### 3.4 Artifact state

Artifacts bind to:

- opportunity content hash;
- truth-pack/profile hash;
- template/version;
- validator version;
- artifact storage key;
- generation status and validation result.

Binary artifacts live in private object storage, not in ephemeral local disk.

---

## 4. Execution DAG

### Wave 0 — Contract, cloud preflight, and observability baseline

**W0.1 — Freeze current production evidence.** Capture current `main`, schema revision, row/evaluation counts, source-health state, canonical-identity duplicate checks, active founder state counts, and current public smoke behavior. This is the migration comparison baseline.

**W0.2 — Cloud capability preflight.** Verify required capabilities in the already-owned Supabase, Cloudflare and GitHub surfaces. Azure and any new paid provider are out of scope. The preflight must prove a $0 gross-spend path and record only genuine Founder-only interactive-auth blockers.

**W0.3 — Infrastructure configuration contract.** Add provider-neutral environment/config schema, secret names, migration order, and deployment manifests. No secret values enter Git.

### Wave 1 — Persisted feed and query-path repair

**W1.1 — Build `feed_projection` migration/backfill.** Derive projection rows from canonical opportunity + evaluation + founder visibility state.

**W1.2 — SQL-native feed/query service.** Search, facets, qualification filters, score ranges, hidden visibility, saved views, pagination, and ranking execute against indexed persisted state.

**W1.3 — Remove correctness-critical process caches from the request path.** Caches may remain as optional accelerators only if a cold cache returns the same result and stays within SLO.

**W1.4 — Query-plan tests.** Add regression tests proving default feed, decision filter, score filter, facets, search, and pagination do not hydrate/scan the entire corpus in Python.

### Wave 2 — Durable asynchronous operations

**W2.1 — Queue contract.** Move poll/evaluate/reextract/artifact/maintenance jobs behind persisted queue semantics with leases and idempotency keys.

**W2.2 — Due-only scheduler.** Scheduler inserts work only for due sources not already queued/leased and respects cooldown/rate-limit/source policy.

**W2.3 — Redefine `Poll Now`.** It creates or refreshes due work, returns immediately with a request/job summary, and never immediately performs an expensive feed reload as part of poll execution.

**W2.4 — Failure isolation.** Worker crashes release/expire leases safely; dead-letter state is inspectable; unrelated source jobs continue.

### Wave 3 — Supabase production data plane

**W3.1 — Schema compatibility.** Make migrations deploy cleanly to Supabase PostgreSQL. Keep migration authority in the repository.

**W3.2 — Auth/RLS.** Replace local-only auth posture with Supabase Auth or an equivalent Supabase-backed founder session model. Browser-visible tables/views require explicit RLS policies. Service-role access is server-side only.

**W3.3 — Private storage.** Move generated artifacts/private uploaded files needed in production to private object storage with signed/authorized access.

**W3.4 — Truth Pack.** Move private Founder Truth Pack/profile state out of local-file production dependency into private durable cloud state. Preserve provenance and hash/version binding. Never expose raw private truth through public API responses.

### Wave 4 — Containerized compute and cloud deployment

**W4.1 — Zero-dollar worker execution.** Keep Python worker roles reproducible and provider-neutral, but execute Founder-Alpha background jobs through bounded standard GitHub Actions runners. Jobs drain the durable PostgreSQL queue and never own canonical state.

**W4.2 — Supabase-native browser/API boundary.** Use Supabase Auth plus explicit RLS/views/RPCs for normal feed/search/detail/settings/Poll Now behavior. Add Supabase Edge Functions only for thin privileged operations that cannot be expressed safely through RLS/RPC. FastAPI/OCI remains a portability/test asset, not a required production service.

**W4.3 — Durable zero-dollar dispatch.** Use Supabase Cron/`pg_cron` and/or bounded GitHub scheduled/dispatch workflows to execute due persisted work. The Founder PC is never part of dispatch or execution.

**W4.4 — Independent frontend deploy.** Deploy the web application on the existing Cloudflare account/domain, preferring static/client-rendered delivery and a thin Worker edge.

### Wave 5 — Shadow migration and parity

**W5.1 — Production database migration.** Export the current canonical PostgreSQL database and import to cloud without losing canonical ids, provenance, evaluation history, founder view/action state, artifacts metadata, or source state.

**W5.2 — Parity verifier.** Compare source/opportunity/provenance/evaluation/application/founder-state counts, duplicate invariants, truth-pack evaluation coverage, and sampled content hashes.

**W5.3 — Shadow polling.** Run the cloud ingestion path without making it authoritative until repeated polls prove stable identities and expected source behavior.

### Wave 6 — Cutover, monitoring, backup, and disaster recovery

**W6.1 — DNS/public cutover.** `opportunityos.m7mdehab.com` points to the cloud frontend/runtime. Retire the Windows host from production responsibility; retain it only as an optional development environment.

**W6.2 — Monitoring.** External uptime monitor, application error capture, job/queue heartbeat, source-freshness alerts, worker-stall detection, and backup heartbeat are active.

**W6.3 — Backups.** Produce encrypted logical PostgreSQL backups from GitHub Actions and retain only encrypted, size-capped artifacts within the existing GitHub allowance. Supabase paid backup/PITR and paid object-storage add-ons are not permitted. A restore drill is mandatory.

**W6.4 — Restore drill.** Restore a backup into a fresh staging environment and run integrity/smoke checks.

**W6.5 — Provider exit test.** Produce and verify a provider-neutral export of critical database state and private artifact inventory sufficient to rebuild elsewhere.

### Wave 7 — Reliability soak and Founder validation gate

Run the cloud production stack for at least 7 consecutive days with no production process on the Founder PC. Scheduled source acquisition/evaluation must continue, the feed must remain available, and monitoring evidence must cover the period.

After this soak, the Founder performs the actual Founder Web Alpha product validation. BRIEF-007 remains blocked until that explicit acceptance.

---

## 5. Acceptance contract

Every row requires persisted evidence and independent verification before closure.

| ID | Acceptance criterion |
|---|---|
| A-0 | All pre-existing mandatory backend/web/truth/source/action-safety tests remain green; no acceptance criterion is weakened. |
| A-1 | Public Founder Alpha has zero runtime dependency on a founder-owned PC, local PostgreSQL, local scheduler, local tunnel, or local filesystem for correctness. |
| A-2 | After a complete API/web/worker restart with cold process memory, the first authenticated feed request succeeds within the agreed public SLO and returns the same logical result as a warm process. Target p95 public feed API ≤ 1.5 s for normal page/filter requests at current corpus size. |
| A-3 | Query-plan/regression evidence proves the default feed and common filters/search do not perform corpus-wide Python hydration/scans. Indexed SQL/projection access is used. |
| A-4 | Killing every poll/evaluation worker leaves the existing feed/search/detail experience available. |
| A-5 | Breaking one source adapter or forcing one source job failure does not stop unrelated sources, feed access, artifact downloads, or the scheduler. |
| A-6 | Polling the same stable source repeatedly is identity/idempotency safe: zero duplicate canonical opportunities and zero duplicate source occurrences for the same stable source identity. |
| A-7 | `Poll Now` returns asynchronously, queues only due/eligible work (plus an explicitly requested source when applicable), leaves the current feed visible, and never triggers an unconditional all-source enqueue. |
| A-8 | Source cadence/cooldown/next-due state survives scheduler/worker restarts; restart produces no all-source warm-up storm. |
| A-9 | Cloud migration preserves all required canonical opportunity/provenance/evaluation/founder-action state and full current-profile evaluation coverage. Any intentional exclusions require explicit evidence and Founder approval. |
| A-10 | Founder private truth, credentials, service-role secrets, storage signing secrets, database credentials, and auth secrets are absent from Git history/public responses/logs. Browser access is RLS-protected. |
| A-11 | Generated artifacts are stored durably, privately retrievable after service restarts, and remain bound to opportunity/truth-pack/template/validator versions. |
| A-12 | A fresh staging environment is successfully restored from backup and passes schema migration, count/invariant, auth, feed, search, detail, and artifact smoke checks. |
| A-13 | External uptime/error/job heartbeat monitoring is active and produces a test alert/incident signal without relying on the Founder opening the site. |
| A-14 | Production runs for ≥ 7 consecutive days with founder-owned production host processes disabled/offline while scheduled acquisition/evaluation continues successfully. |
| A-15 | A provider-neutral export/restore procedure is tested sufficiently to prove Supabase/compute-provider exit is possible without rewriting domain logic or losing canonical data. |
| A-16 | Desktop and 390px mobile authenticated smoke tests pass after cloud cutover, including feed, pagination, search, facets, detail, source link, Poll Now status, and artifact access. |
| A-17 | The runtime cost envelope proves **$0 gross provider charge and $0 Founder out-of-pocket charge**, with no student/trial-credit dependency, no paid tier/add-on and documented permanent-free quota headroom. Quota exhaustion fails closed rather than creating spend. |

---

## 6. SLO and reliability targets

Founder-stage targets for this brief:

- authenticated feed availability target: 99.9% measured externally during the final soak, excluding documented provider-wide incidents only when independently evidenced;
- normal feed/search/filter p95 ≤ 1.5 s at current corpus size after cold service restart;
- `Poll Now` acknowledgement p95 ≤ 1 s because it only persists/dispatches work;
- queue age for due normal-priority polling: normally < 15 minutes during healthy operation;
- scheduled ingestion must continue with Founder PC offline;
- zero duplicate submissions, unsupported founder claims, unauthorized source actions, cross-user leakage, or secret exposure remain zero-tolerance.

These are product acceptance targets, not claims that a provider contractually guarantees the same SLA.

---

## 7. Migration strategy — no big-bang rewrite

Use parallel/shadow migration:

1. preserve current canonical DB and runtime as rollback reference;
2. land feed-projection and queue architecture before cloud cutover;
3. deploy a cloud staging environment;
4. migrate a snapshot and prove parity;
5. run cloud polling in shadow/read-only-authority mode;
6. repair identity/data discrepancies before cutover;
7. freeze local production writes briefly for final delta migration;
8. cut DNS/public runtime to cloud;
9. keep encrypted rollback backup, not a parallel writable production database;
10. complete the 7-day soak before declaring the replatform closed.

Do not rewrite working source adapters, matching logic, truth-lock, artifact semantics, or provenance merely to adopt a new provider. Reuse domain code behind new infrastructure boundaries.

---

## 8. Security/privacy requirements

- Supabase service-role and database admin credentials are server-only.
- Browser uses only public/anon client credentials plus authenticated RLS-scoped sessions.
- Founder Truth Pack/private profile tables deny direct broad browser reads unless a field is intentionally exposed by a dedicated view/RPC.
- Artifact buckets are private; downloads use authenticated/signed access.
- Cloudflare/GitHub/Supabase secrets live in their respective protected secret stores/environment configuration, never committed files.
- Production logs redact credentials, raw private truth, auth tokens, and unnecessary source payload PII.
- Backups containing founder/private state are encrypted before off-provider storage when the destination is not already an equivalently controlled private backup system.
- Production migrations run under a dedicated migration credential/role where practical; normal app access is least privilege.

---

## 9. Explicitly out of scope

- BRIEF-007 multi-tenancy/family accounts;
- changing the Product Constitution;
- broad new source expansion unrelated to validating the new ingestion runtime;
- automatic application submission expansion;
- Kubernetes;
- Kafka;
- adding Redis merely because it is conventional;
- dedicated search infrastructure without measured Postgres failure;
- replacing PostgreSQL;
- redesigning the entire Founder UI before reliability is proven.

---

## 10. Founder-only boundaries

Agents execute everything they can through available tooling. Founder action is limited to genuine boundaries:

- interactive OAuth/login/verification for Supabase, Cloudflare, GitHub, or an explicitly Founder-approved zero-dollar integration when no connected tool can perform it;
- accepting provider terms;
- approving any paid tier/resource or payment-card requirement;
- final product acceptance after the 7-day cloud soak.

Do not return shell commands, configuration derivation, migration scripts, DNS values, or routine deployment steps to the Founder when an available agent/tool can perform them.

---

## 11. Closure

FR-007 closes only when:

1. all A-0..A-17 criteria have evidence;
2. production is cloud-hosted and founder-PC-independent;
3. the 7-day soak has passed;
4. backup restore and provider-exit evidence exist;
5. CI and post-merge checks are green;
6. `docs/ARCHITECTURE_CURRENT.md`, `docs/ROADMAP_CURRENT.md`, `docs/CHAT_RESUME.md`, relevant ADRs, and generated `docs/STATE.md` are reconciled to reality;
7. the Owner/Overseer independently verifies the evidence and issues terminal PASS/NOT PASS.

FR-007 closure does **not** automatically unblock BRIEF-007. Founder Web Alpha must still be personally validated and accepted after the reliable cloud deployment is available.