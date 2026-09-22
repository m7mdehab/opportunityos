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
- historical Azure deployment manifests exist but are superseded by the zero-dollar runtime decision;
- Cloudflare Workers/OpenNext staging frontend with same-origin `/api/*` proxy and hosted Desktop + 390px Playwright contract;
- private Supabase Storage artifact backend with checksum/size verification and durable metadata;
- Founder-approved repository-managed canonical Truth Pack snapshot with pinned hash verification;
- migration/backup/restore/parity/provider-exit tooling;
- manual hosted PostgreSQL/Supabase execution harness.

Repository implementation proof is ahead of hosted execution. Production A-gates remain open until real provider/runtime evidence exists.

## W19 Codex hosted API branch delta (repository preparation)

`work/fr007-codex-hosted-api-final` adds a same-origin Supabase edge adapter with HTTP-only access/refresh cookies, exact feed totals, Founder-safe detail/source/facet/filter/dashboard surfaces, private CV/artifact retrieval verification, migration `0011_hosted_api_surface`, durable fixed-CV selection metadata, and a bounded manual hosted bootstrap workflow. These are branch/PR facts only; no hosted provider execution or FR-007 closure is claimed.

## Current Hosted Execution State

W15 repository preparation is integrated and green:

- hosted single-Founder scrypt auth, durable PostgreSQL sessions/rate-limit/audit, fail-closed CSRF/origin validation and reversible hosted RLS authority;
- external observability, incident lifecycle, durable soak snapshots, hosted-acceptance manifest, release evidence index and cost/quota control plane.

A real Supabase staging project is now provisioned and healthy:

- project: `opportunityos-staging`;
- safe project ref: `sunjfepvdzfknglrjwhm`;
- region: `eu-central-1`;
- safe API origin: `https://sunjfepvdzfknglrjwhm.supabase.co`;
- PostgreSQL: 17;
- plan/project creation cost: $0/month at provisioning;
- hosted application schema is present at Alembic revision `0009_hosted_founder_auth` with 26 public tables under RLS authority.

Safe hosted-target metadata is persisted at `reports/evidence/FR-007/hosted-staging-target.json`. No database password, service-role key, storage signing secret, Founder credential or session secret is stored in Git. The canonical career Truth Pack is Founder-approved repository-managed product truth. The six Founder-approved fixed CV PDFs are now live in the private `founder-cv-portfolio` bucket and were independently re-downloaded and SHA-256 verified; sanitized proof is in `reports/evidence/FR-007/fixed-cv-portfolio-live-proof.json`.

The failed precondition W16A attempt from the pre-W15 integration head is non-authoritative and must not be reused.

## Current Execution

Next milestone: finish the real hosted Supabase data-plane/private-state path, then activate the zero-dollar Founder runtime using Supabase + Cloudflare + GitHub only. Azure is explicitly excluded.

Task routing must follow actual tool access. Repository agents must not be assigned provider mutations they cannot authenticate. The Overseer owns connected-provider actions available only through authenticated Supabase/GitHub tooling; Codex/Antigravity receive bounded end goals they can actually finish.

## Remaining FR-007 Sequence

### W17-R1 runtime remediation delta

- The runtime-closure branch now carries repository migration `0010_hosted_runtime`
  for durable Founder identity, narrow Supabase views/RPCs, due-only Poll Now,
  and private Storage policies.
- The browser runtime uses publishable Supabase Auth/PostgREST configuration
  when present; legacy API calls remain a compatibility fallback.
- Hosted Supabase migration, identity binding, RLS probes, private object
  retrieval, and source parity remain Overseer-owned operations and are not
  claimed as repository PASS.

1. execute real Supabase schema migration and hosted parity;
2. prove hosted anon/authenticated/backend RLS boundaries;
3. prove the repository-managed canonical Truth Pack loads and hash-verifies in cloud/background jobs;
4. fixed CV upload/retrieval is proven; complete generated-artifact private storage retrieval with exact opportunity/truth/template/version binding;
5. wire Supabase Auth + Founder-only RPC/RLS browser boundary;
6. wire Supabase Cron/pg_cron + bounded GitHub Actions Python workers;
7. deploy the Cloudflare frontend/edge on the existing domain;
8. run hosted A-4/A-5/A-6/A-7/A-8 reliability proof;
9. cold-start/feed SLO proof;
10. shadow polling and identity/source-occurrence parity;
11. external monitoring + real test alert;
12. encrypted logical GitHub backup artifact + restore drill;
13. provider-exit execution proof;
14. public cutover;
15. Desktop + 390px authenticated cloud smoke;
16. prove $0 gross/$0 out-of-pocket quota envelope with no credit dependency;
17. start then complete >=7 consecutive days with Founder production host offline;
18. terminal A-0..A-17 evidence review;
19. Founder validation;
20. only then consider BRIEF-007.

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


### Founder-locked CV portfolio

Employment applications do not synthesize CVs. ADR-0024 locks six final 2026 PDFs (AI Engineer, Business Analyst, Data Analyst, Data Engineer, Data Scientist, Master). Matching selects one immutable PDF, verifies its SHA-256, and attaches those exact bytes. Cover letters/application answers remain Truth-locked generated artifacts. The PDF bodies live in private Supabase Storage; the repository stores only the selection catalog and hashes.
