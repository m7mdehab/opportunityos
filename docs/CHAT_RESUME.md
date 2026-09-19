# OpportunityOS Chat Resume

Purpose: boot a fresh ChatGPT/agent session without reconstructing OPOS history from chat transcripts.

Last compacted: 2026-09-18, Africa/Cairo.

## Resume Command

A new session may begin with:

`Resume OPOS from canonical state.`

The Owner/Overseer should then read, in order:

1. `AGENTS.md`;
2. `docs/AUTHORITY_INDEX.md`;
3. this file;
4. generated `docs/STATE.md`;
5. `docs/ROADMAP_CURRENT.md`;
6. `docs/ARCHITECTURE_CURRENT.md`;
7. the active FR-007 brief and task-relevant ADR/evidence;
8. live GitHub branch/PR/CI state.

Do not ask Mohammed to reconstruct repository history that can be recovered from the canonical repository layer.

## Project In One Paragraph

OpportunityOS is an autonomous opportunity-acquisition platform for MENA spanning employment and independent professional work. Its core flow is:

`discover -> ingest -> qualify -> score -> persist projection -> truth-locked tailor -> prepare/fill/controlled-submit -> monitor outcomes -> learn safely`.

The system exists to increase useful opportunity throughput while preserving Founder truth, provenance, source policy, action authority and duplicate safety.

## Authority

- Founder/final product authority: Mohammed.
- Owner/Overseer: ChatGPT / GPT-5.6 Sol.
- Executors are bounded implementation capacity, not closure authority.
- Repository/runtime truth outranks executor self-report.

For state claims:

runtime/live behavior > merged authoritative branch > active PR/branch > machine evidence > generated state > reports > chat memory.

For intent:

latest Founder decision > Product Constitution/accepted ADR/PDR > active brief/roadmap > Master Plan > historical reports/chats.

## Locked Overseer Operating Model

`docs/OVERSEER_EXECUTION_LOCK.md` is standing governance.

Default loop:

`Sol pre-solves -> executor implements -> Sol independently verifies -> at most one focused executor remediation -> Sol closes ordinary residuals/integration -> executor moves to next useful independent lane`.

Routine CI/state/PR/test-fixture/integration friction is Overseer work, not grounds for repeated executor ping-pong.

Keep independent Codex and Antigravity capacity productively occupied when non-overlapping work exists.

## Truth Law

Never weaken:

- `UNKNOWN != FALSE`;
- `ABSENT != INELIGIBLE`;
- material Founder claims require evidence authority;
- planned credentials never become held;
- unsupported facts/commitments are omitted, marked uncertain or paused;
- source coverage is not permission;
- 403/429/CAPTCHA/MFA/policy restrictions are stop conditions;
- uncertain external outcome never becomes automatic retry;
- duplicate submission tolerance is zero.

## Current Product Phase

BRIEF-FR-006 is historical/closed with its documented exceptions.

Founder Web Alpha exists, but FR-007 is now the active brief because cloud reliability and Founder-PC independence are not yet accepted.

BRIEF-007 / Multi-Tenant Family Alpha remains blocked until FR-007 is closed and the Founder personally validates the resulting cloud-hosted Alpha.

## Current FR-007 Integration State

Authoritative branch:

`brief/fr-007-cloud-replatform`

Integrated repository-side capabilities include:

- durable PostgreSQL `feed_projection` and SQL-native feed/search/filter/pagination;
- durable PostgreSQL `worker_jobs` queue with leases, recovery, retry/dead-letter and `FOR UPDATE SKIP LOCKED`;
- persisted per-source `source_schedules`, due-only Poll Now, cooldown/Retry-After and async projection maintenance;
- real PostgreSQL 16 W11 durability/concurrency proof: 15 tests, zero skips;
- repository/disposable-PostgreSQL A-4/A-5/A-6 reliability proof;
- OCI runtime roles: `api`, `worker`, `scheduler`, `migrate`;
- Azure Container Apps/Jobs staging deployment manifests and migration-first release harness;
- Cloudflare Workers/OpenNext staging frontend with same-origin `/api/*` proxy and hosted Desktop + 390px Playwright contract;
- private Supabase Storage artifact backend with checksum/size verification and durable metadata;
- private remote HTTPS Truth Pack contract with hash binding, bearer/apikey support and Azure secret wiring;
- migration/backup/restore/parity/provider-exit tooling;
- manual hosted PostgreSQL/Supabase execution harness.

Repository implementation proof is ahead of hosted execution. Production A-gates remain open until real provider/runtime evidence exists.

## Current Parallel Execution

Executor lane status:

- Antigravity: W15B.1 remediation complete on `work/fr007-antigravity-observability-release-wave15`. Workflow <-> CLI contract aligned (`--output-report`, `--output-incident`, `--backup-heartbeat-path`), alert action schema unified (`CREATE`, `UPDATE`, `RESOLVE`, `NONE`), fail-closed issue processor (`scripts/process_incident_alert.py`), durable soak evidence via Actions artifacts (90-day retention) and fetcher (`scripts/fetch_soak_artifacts.py`), fail-closed soak verifier enforcing `proof_scope == "FULL_HOSTED"`, audited hosted acceptance manifest (A-0, A-3 PASS repository-only; A-1, A-2, A-4..A-13, A-15, A-17 REPOSITORY_VERIFIED; A-14, A-16 NOT_EXECUTED), recomputed cost envelope (30-min Actions cadence = 1,440 billed min/mo, ACA student credit separated from permanent free tier), workflow contract validator, and expanded test suite (67/67 PASS) verified;
- Codex: hosted-grade single-Founder auth/session hardening plus PostgreSQL/Supabase RLS policy authority.

The Overseer owns PR/CI/integration, ordinary residual repair and the authoritative checklist.

## Remaining FR-007 Sequence

1. hosted-grade auth/session/RLS boundary;
2. connect real Supabase/PostgreSQL staging;
3. real staging migration + parity;
4. configure/test private Truth Pack retrieval;
5. configure/test private artifact storage retrieval;
6. deploy Azure API/worker/scheduler/migrate;
7. deploy Cloudflare frontend;
8. run hosted A-4/A-5/A-6/A-7/A-8 reliability proof;
9. cold-start/feed SLO proof;
10. shadow polling and identity/source-occurrence parity;
11. external monitoring + test alert;
12. encrypted off-provider backup;
13. fresh-environment restore drill;
14. provider-exit execution proof;
15. public cutover;
16. Desktop + 390px authenticated cloud smoke;
17. real cost/quota envelope;
18. >=7 consecutive days with Founder production host offline;
19. terminal A-0..A-17 evidence review;
20. Founder validation;
21. only then consider BRIEF-007.

## Founder-Only Boundaries

Agents execute every safely solvable technical task available through tools.

Founder intervention is reserved for genuine boundaries such as:

- interactive provider login/OAuth/verification;
- inaccessible credentials that cannot be injected through connected tooling;
- payment or paid-resource approval;
- acceptance of binding provider terms;
- irreversible external actions;
- legal/compliance judgment;
- subjective final product acceptance.

Do not hand routine technical commands, reversible configuration or ordinary engineering judgment back to the Founder.

## Cloud Acceptance Boundary

Do not confuse:

- code merged;
- CI green;
- disposable PostgreSQL proof;
- staging deployment;
- production cutover;
- terminal FR-007 acceptance.

They are separate evidence levels.

Real hosted evidence is still required for the cloud acceptance criteria.

## Security / Privacy

Never store in Git or public docs:

- credential values;
- DB connection strings;
- service-role/storage signing secrets;
- private Founder Truth Pack contents;
- raw personal/application history;
- auth tokens/passwords.

Evidence should contain names, hashes, safe fingerprints and operational conclusions, not secrets.

## Context Loading Rules

Load only what the task requires:

- product law: `docs/PRODUCT_CONSTITUTION.md`
- current architecture: `docs/ARCHITECTURE_CURRENT.md`
- current roadmap: `docs/ROADMAP_CURRENT.md`
- cloud ADR: `docs/adr/ADR-0022-cloud-native-runtime-and-supabase-data-plane.md`
- long horizon: `docs/MASTER_PLAN.md`
- source policy/status: `docs/SOURCE_REGISTRY.yaml`, `docs/SOURCE_EVIDENCE.md`
- execution mechanics: `docs/AGENT_EXECUTION_PROTOCOL.md`
- Overseer loop: `docs/OVERSEER_EXECUTION_LOCK.md`
- action permissions: `docs/AGENT_PERMISSIONS.yaml`
- exact gate evidence: relevant `reports/evidence/FR-007/`

Provider chat histories are never the sole state authority.

## Compaction Rule

Before moving to another chat:

1. persist durable architecture/product decisions in repository docs/ADRs;
2. reconcile `ARCHITECTURE_CURRENT.md` when architecture changes;
3. reconcile `ROADMAP_CURRENT.md` when execution priority changes;
4. regenerate/reconcile `docs/STATE.md`;
5. update this file with only the compact current delta/next action;
6. do not duplicate history already preserved in reports/ADRs/briefs.
