# FR-007 W23 — Clean Rebuild, Storage V2, Egress-Safe Runtime Closure

## Mission

This is a **single end-to-end execution sprint**.

You are GPT-6 Luna acting as the implementation/execution owner. The Overseer has already made the architectural decisions and completed the provider bootstrap. Do not spend the sprint re-deciding the problem. Execute the brief, diagnose ordinary failures yourself, repair them, strengthen coverage, and continue until the terminal PASS contract is satisfied.

Do **not** return a plan.
Do **not** stop at “repository work complete”.
Do **not** stop at “ready for live migration”.
Do **not** ask the Founder to perform routine GitHub/Supabase UI actions you can perform with browser/CLI access.
Do **not** merge.
Do **not** claim the seven-day soak.
Do **not** introduce paid infrastructure.

For every ordinary failure:

`inspect -> diagnose -> fix -> strengthen coverage -> rerun -> continue`

Return only:

- **PASS** when this entire sprint is complete; or
- **BLOCKED** only when a genuinely external authorization/data dependency remains after exhausting the explicit fallbacks in this brief.

---

# 1. Authoritative repository state

Repository:

`m7mdehab/opportunityos`

Work exclusively on:

`work/fr007-clean-rebuild-storage-v2`

This branch was created from the latest Storage V2 recovery branch state:

`6686b231b148d1e4119ffbb855a7c0f6d4ea27a1`

Before editing:

1. fetch origin;
2. verify this branch;
3. verify ancestry includes W22.5 runtime/session corrections and W22 Storage V2 work;
4. read all of:
   - `reports/evidence/FR-007/W22_5_CODEX_RUNTIME_ACCEPTANCE_CORRECTION.md`
   - `reports/evidence/FR-007/W22_6_ZERO_DOLLAR_DB_CAPACITY_CORRECTION.md`
   - `reports/evidence/FR-007/W22_6A_OVERSEER_ACCEPTANCE_CORRECTION.md`
   - `reports/evidence/FR-007/W22_7_FINAL_RUNTIME_CLOSURE_EXECUTION.md`
   - `reports/evidence/FR-007/W22_8_TERMINAL_HOSTED_CLOSURE_UNBLOCK.md`
   - `reports/evidence/FR-007/W22_STORAGE_V2_EXECUTION_CHECKPOINT.md`
   - `reports/evidence/FR-007/W22_STORAGE_V2_RECOVERY_BLOCKER.md`
   - this W23 brief.

Do not restart the historical investigation.

---

# 2. The old database is intentionally gone

The Founder deliberately deleted the failed Supabase OpportunityOS project.

Do not attempt to recover or reconnect to the old project.

Old project ref, for historical evidence only:

`lrrcpwaapwynzdsxzwhy`

Any use of that ref in runtime code, active workflows, deployment configuration, URLs, secrets, defaults, or acceptance probes is stale and must be removed/replaced. Historical evidence files may retain it.

There is no production data migration from the old database in this sprint.

The Founder explicitly stated that the old database had not yet accumulated meaningful real product usage. Treat the old queue, feed projections, evaluations, source poll history, test opportunities, sessions, and other derived staging state as disposable.

Canonical source truth is recreated from the registered external sources.

Unique Founder data should be reconstructed only from authoritative external/private sources where needed; do not invent old database state.

---

# 3. New Supabase project — already created

The Overseer has already created the replacement project at confirmed **$0/month**.

Organization:

`OpportunityOS`

organization id:

`oxytmzezepplpnawavnh`

plan:

`free`

New project:

`opportunityos-staging`

project ref:

`sunjfepvdzfknglrjwhm`

region:

`eu-central-1`

API URL:

`https://sunjfepvdzfknglrjwhm.supabase.co`

direct PostgreSQL host:

`db.sunjfepvdzfknglrjwhm.supabase.co`

The Overseer verified the fresh DB:

- `pg_is_in_recovery() = false`
- `default_transaction_read_only = off`
- database size at bootstrap: **10 MB**
- no OpportunityOS public-schema migrations yet.

Do not create another Supabase project.

Do not upgrade this organization.

---

# 4. Storage bootstrap — already completed

The Overseer already created two private buckets.

## opportunity-artifacts

Purpose:

- Storage V2 compressed cold opportunity source truth;
- other private generated artifacts where already supported.

Configuration:

- private;
- 10 MiB per-object limit;
- allowed MIME types include:
  - `application/octet-stream`
  - `application/zlib`
  - `application/json`
  - `text/plain`

## founder-cv-portfolio

Purpose:

- final canonical CV PDFs/DOCX and supporting private portfolio files.

Configuration:

- private;
- 10 MiB per-object limit;
- allowed MIME types include:
  - `application/pdf`
  - DOCX MIME
  - `application/octet-stream`
  - `text/plain`
  - `application/json`

Do not make either bucket public.

Hosted runtime may use the Supabase service-role key; browser clients must not receive it.

---

# 5. Why the old architecture failed

This was not “too much job data”.

The old database contained only roughly **26,000 opportunities**, yet reached approximately **1,503 MiB**.

Last reliable physical footprint:

| relation | approximate physical size |
| --- | ---: |
| `feed_projection` | **865 MB** |
| `opportunities` | **330 MB** |
| `field_provenances` | **149 MB** |
| `match_evaluations` | **135 MB** |

Those four relations represented approximately **98%** of the database.

The same source content was repeatedly represented as:

- raw source payload;
- full opportunity description;
- normalized provenance rows;
- opportunity `search_tsv`;
- verbose evaluation JSON;
- feed projection;
- feed `search_text`;
- feed `search_tsv`;
- GIN indexes over duplicate search data;
- duplicate projection populations for synthetic `truth_pack_hash='active'` and the real truth pack.

The old `feed_projection` had roughly **50k rows** for roughly **26k opportunities**.

Measured duplicate feed search payload alone was approximately:

- `search_text`: 199 MB
- `search_tsv`: 359 MB

This design is prohibited in the clean rebuild.

---

# 6. Egress was a second independent defect

The previous organization billing cycle showed approximately:

- Free egress allowance: **5 GB**
- already consumed in current cycle: **3.87 GB**
- remaining headroom at that observation: roughly **1.13 GB**

Deleting the old project does not imply organization-level billing counters reset.

Therefore W23 has TWO resource goals:

1. PostgreSQL storage efficiency.
2. Supabase egress efficiency.

The previous proof/recovery loop repeatedly downloaded large relational payloads from Supabase to hosted workers and observers. That is not acceptable.

For the remainder of the current billing cycle, treat Supabase egress as scarce.

### W23 bootstrap egress budget

Preferred incremental Supabase egress during the entire clean rebuild:

`<= 250 MB`

Hard sprint safety ceiling unless the Founder explicitly approves otherwise:

`<= 500 MB additional`

Do not perform corpus-wide `SELECT *` exports or repeatedly download descriptions/evaluation JSON from Supabase.

External-source -> GitHub runner traffic is not Supabase database egress. Use that fact.

Normalize/evaluate source payloads in memory before writing to Supabase whenever possible.

---

# 7. New architecture — frozen

The architecture is:

`external sources -> worker memory -> compact hot PostgreSQL + compressed private object storage`

PostgreSQL is the **operational index/state database**, not the warehouse for every full source document and every derived representation.

Supabase Storage is the cold immutable source-truth tier.

The target model is:

## HOT

Keep enough relational state for:

- current qualified/uncertain opportunities;
- current visible feed;
- current matching/ranking;
- Founder interaction/history;
- outbound/application state;
- queue/runtime state;
- compact search/filtering.

## COLD

Hard-ineligible, unchanged opportunities with no Founder interaction/history.

Retain:

- identity;
- source identity;
- content hash;
- compact normalized metadata;
- compact current decision;
- archive object key;
- archive SHA-256;
- archive state/version.

Store full source truth/provenance in compressed private object storage.

## PROTECTED/HISTORICAL

Never cold-delete information needed to inspect:

- applied;
- dismissed;
- snoozed;
- Founder feedback;
- Founder activity events;
- outbound/application activity;
- other genuine Founder history.

---

# 8. Resource budgets — mandatory acceptance invariants

## PostgreSQL

Fresh baseline was approximately 10 MB.

After complete source bootstrap and runtime acceptance:

Preferred:

`<= 150 MiB`

Hard engineering acceptance:

`<= 200 MiB`

Warning threshold:

`>= 250 MiB`

Strong warning:

`>= 300 MiB`

Block nonessential heavy work:

`>= 350 MiB`

Absolute runtime safety stop:

`>= 400 MiB`

The Supabase Free database limit remains 500 MB. Do not operate near it.

## Supabase Storage

Preferred cold/object footprint:

`<= 300 MiB`

W23 safety ceiling:

`<= 500 MiB`

## Egress

Steady-state target after this billing cycle:

`<= 2 GB/month`

Internal warning:

`>= 2.5 GB/month`

Operational ceiling:

`3 GB/month`

Do not design a system that requires the full 5 GB allowance every month.

---

# 9. First mandatory action — rotate all hosted configuration to the new project

Before running migrations or sources, update the `fr007-staging` GitHub environment.

Use browser/dashboard access where necessary.

Do not expose secret values in Git, logs, reports, chat, screenshots, or artifacts.

Replace stale old-project secrets with credentials from the NEW project.

At minimum inspect/update:

- `OPOS_TARGET_DB_URL`
- `CLOUD_DATABASE_URL`
- `SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `STORAGE_SERVICE_KEY` and/or `SUPABASE_SERVICE_ROLE_KEY`
- publishable/anon key secrets used by the web app, if any;
- any project-ref or API URL variables;
- `STORAGE_PRIVATE_BUCKET=opportunity-artifacts` where configured.

Recommended connection posture:

### OPOS_TARGET_DB_URL

Use a direct PostgreSQL connection suitable for:

- Alembic;
- DDL;
- controlled maintenance;
- session-sensitive proof.

### CLOUD_DATABASE_URL

Use the provider's appropriate runtime pooler connection.

Preserve W22.5 connection limits and semantics.

Do not configure an unbounded application pool.

### Service role

Retrieve the new project's service-role/secret key from Supabase dashboard/API settings and update the protected GitHub environment secret.

Never use the publishable key as a service-role substitute.

---

# 10. Remove stale old-project literals

Search the entire active branch for:

`lrrcpwaapwynzdsxzwhy`

Classify each occurrence.

Historical evidence may retain it.

Active code/workflows/configuration must not.

Replace active hardcoded Supabase URLs/project refs with:

- environment configuration; or
- the new project ref where a literal is genuinely necessary.

Known historical problem:

`.github/workflows/fr007-final-runtime-closure.yml`

previously hardcoded the old Supabase URL in monitor/storage defaults.

Correct this before hosted execution.

Add a regression check that fails active runtime/workflow configuration if the deleted project ref reappears outside explicitly historical evidence.

---

# 11. Reconcile the canonical 9-CV portfolio BEFORE source evaluation

Do not resurrect the stale six-CV manifest currently visible on the Storage V2 branch.

The canonical final portfolio is the **nine-CV 2026-09-21 system**.

Canonical specialist families:

1. Data Engineering & Integration
2. Data Analytics & BI
3. Data Scientist
4. ML Engineer
5. AI/LLM Engineer
6. Business/Technical Analyst
7. AI/Technical Solutions
8. Full-Stack/Product
9. Master Comprehensive fallback

The staged canonical repository lane is:

`work/cv-canonical-final-2026-09-21`

Draft PR was #141.

Integrate/cherry-pick the canonical repository metadata/selector/truth snapshot into THIS clean-rebuild branch before source matching.

Do not merge unrelated branch history wholesale.

Do not activate stale six-CV metadata.

Expected canonical package hash from prior accepted evidence:

`f5475977e331c5efb70e21a6b2b702904c80ebdc8aa2f22a1dccee24a8e807a4`

Expected canonical registry hash:

`201ee75c2675f707b2a24af728f85ed62ceeb25df6667b5ec549a6a50eff4b71`

Expected personalization hash:

`6e1005ec9fc6f0562b870769f431df1cab7ff850ae8f507e4a7521d6e21afcdd`

Expected ATS audit hash:

`92da65cf861282fa57d132583d269f1287b643b9020e9192baa2323cacd051e5`

The prior old project storage was deleted, so the nine canonical binaries must be uploaded again to the NEW `founder-cv-portfolio` bucket.

Search for the final ZIP/package in all already-authorized local/user project locations before declaring it unavailable.

Verify each uploaded object against the canonical manifest SHA-256.

Do not write CV binaries into the public Git repository.

If the final package genuinely cannot be found after exhausting authorized files/workspaces, continue all non-CV infrastructure work and identify the exact missing file as a terminal external artifact blocker rather than inventing replacements.

---

# 12. Migration strategy

The repository currently contains migrations through:

`0021_storage_v2`

The old live baseline was 0019, but THIS database is fresh.

Apply the repository's tested migration chain cleanly from baseline to head.

Do not manually recreate production tables ad hoc through dashboard SQL.

Use Alembic through the authenticated direct database connection whenever possible so repository migration history and live schema remain identical.

After migration require:

- exactly one Alembic head;
- live revision equals repository head;
- PostgreSQL schema diff/integrity check clean;
- no stale old-project objects;
- no migration skips.

If the architecture changes in W23 require schema cleanup, add the NEXT migration after `0021_storage_v2`.

Do not rewrite old migrations.

---

# 13. Storage V2 is not complete until ingestion writes the right tier directly

This is crucial.

Do NOT repeat the old pattern:

1. write full raw payload + full description + all provenance + search vectors to PostgreSQL;
2. score it;
3. later run a huge maintenance job to move it cold.

That creates transient storage amplification and unnecessary WAL/egress.

For the fresh rebuild, normal ingestion must tier data correctly at write time.

Desired path:

1. fetch source opportunity into worker memory;
2. normalize it in memory;
3. calculate identity/content hash;
4. evaluate it in memory against the current Truth Pack;
5. determine HOT/COLD/PROTECTED state;
6. persist only the correct hot relational representation;
7. upload compressed cold source truth once where required;
8. build the current lean feed representation only when required.

For a brand-new hard-ineligible/no-Founder-state opportunity, avoid first persisting a heavyweight hot copy merely to compact it later.

Repository maintenance remains useful for future transitions, but direct tiering is the normal steady-state contract.

---

# 14. Cold object contract

Cold objects are content-addressed.

Use the existing Storage V2 pattern:

`cold-opportunities/<content_hash>.json.zlib`

Each object must include enough authoritative information to:

- prove identity;
- inspect source truth;
- recover full description;
- recover raw source payload where relevant;
- recover provenance;
- re-evaluate accurately when necessary.

Store in PostgreSQL:

- object key;
- content hash;
- compressed-object SHA-256;
- compressed size;
- original size where useful;
- archive version;
- archive state/backend.

Before using a cold object:

1. download;
2. verify SHA-256;
3. decompress;
4. verify opportunity identity/content hash;
5. fail closed if any check fails.

No placeholder such as `[archived]` may ever be used as actual match input.

---

# 15. Content change contract

For same source identity + same content hash:

- do not rewrite the archive;
- do not re-evaluate unless another valid invalidation applies;
- keep operations cheap.

For same source identity + changed content hash:

- old decision/archive version becomes stale;
- evaluate the NEW source truth;
- update current archive pointer/version;
- transition to HOT/COLD based on the new result;
- do not leave stale archive metadata preventing future compaction.

Repeated source updates must not produce unbounded metadata/orphan growth.

---

# 16. Truth-pack change contract

A truth-pack change may invalidate old match decisions.

Do not permanently rehydrate the whole cold corpus into PostgreSQL.

Use verified cold source truth in memory when full source material is actually required.

After scoring:

- persist compact current match state;
- leave still-ineligible opportunities cold;
- make newly actionable opportunities hot;
- keep Founder-protected rows protected.

Measure object-storage download bytes during any corpus re-evaluation because they are Supabase egress.

Do not run full-corpus re-evaluation casually during this billing cycle.

---

# 17. Feed projection — one current lean read model

The old 865 MB feed relation must never recur.

There must be NO synthetic per-opportunity `truth_pack_hash='active'` corpus.

There must be one current read model.

Recommended contract:

- one current projection per interactive opportunity;
- current truth-pack hash may remain as metadata if needed;
- no full description;
- no raw payload;
- no provenance;
- no duplicate full-text search body;
- no verbose multi-KB evaluation detail;
- no historical truth-pack feed copies.

Cold hard-ineligible/no-Founder-state opportunities are not part of the active interactive feed.

Founder-protected rows remain inspectable according to product requirements.

If schema changes are needed to make `feed_projection` truly current-only, do them now while the database is empty.

---

# 18. Search — exactly one compact authoritative search representation

The old design maintained multiple copies of full description search vectors.

Prohibited steady state:

- full-description `opportunities.search_tsv`;
- plus `feed_projection.search_text`;
- plus `feed_projection.search_tsv`;
- plus separate GIN indexes over the same corpus.

Use one compact searchable representation built from fields actually useful in the UI, such as:

- title;
- organization;
- title family;
- normalized skills/technologies;
- location;
- selected responsibility/role keywords only when proven useful.

The original long description belongs in object storage for cold rows.

Measure both relation and index size after ingestion.

Do not keep a large GIN index without evidence that the product query needs it.

---

# 19. Match-evaluation storage

For COLD terminal hard-ineligible jobs, PostgreSQL should retain compact current state, not several KB of explanation JSON.

Compact state should be sufficient to know:

- current truth-pack/version;
- content hash/version;
- decision;
- score;
- hard-failure/reason code;
- evaluated timestamp/policy version.

Verbose strengths/gaps/unknowns/dimension explanation may be:

- retained for HOT/current interactive opportunities;
- retained for Founder-protected records;
- archived with source truth where appropriate.

Do not preserve verbose evaluation history indefinitely for every rejected job.

Add retention for stale truth-pack evaluation detail.

---

# 20. Provenance

Row-per-field provenance is expensive when multiplied across the rejected corpus.

For COLD rows:

- provenance belongs in the verified cold object;
- do not keep hundreds of thousands of relational provenance rows.

For HOT/PROTECTED rows:

- retain relational provenance where the product needs it.

No provenance data is silently destroyed; it is moved to the appropriate tier.

---

# 21. Source bootstrap strategy

The source registry is authoritative.

Do not import old opportunity tables.

Re-poll the registered read-allowed sources from scratch.

Before full bootstrap:

1. run one small representative source through the complete new ingestion path;
2. inspect PostgreSQL and Storage footprint;
3. inspect Supabase egress-sensitive behavior;
4. prove no heavyweight duplicate projection/search state;
5. then scale to the remaining sources.

Because this is a fresh project, queue/schedules may be seeded cleanly.

Do not restore old `worker_jobs`, `source_poll_runs`, or source schedule rows.

Do not create a giant queue first and then hope the new design is efficient.

Incrementally bootstrap and observe.

---

# 22. Egress-safe worker design

Supabase outgoing traffic is expensive relative to the 5 GB Free allowance.

The normal ingestion design should avoid:

`source -> DB full payload -> worker downloads DB payload -> scorer -> DB`

Prefer:

`source -> worker memory -> normalize/evaluate -> compact DB + compressed archive upload`

Upload into Supabase is ingress.

Repeatedly reading large source bodies back OUT of Supabase is egress.

Avoid corpus-wide external reads.

Monitoring should use SQL-side aggregation such as:

- count;
- min/max;
- sum;
- grouped metrics.

Do not fetch tens of thousands of rows just to count them.

Feed/API endpoints must paginate compact cards.

Opening a single opportunity may fetch the full archived description on demand.

---

# 23. Backup strategy — redesign for egress

The old repository contains an encrypted full logical backup workflow.

Do not schedule a full 150-200 MB `pg_dump` every day on a 5 GB/month egress budget.

At 150 MB/day, daily full backups alone could approach 4.5 GB/month.

Implement two classes:

## Frequent authoritative-state backup

Back up only irreplaceable Founder-generated/configuration state, such as:

- Founder activity;
- triage;
- feedback;
- outbound/application records;
- settings/preferences;
- CV selection state;
- other genuinely unique state.

Encrypt it.

Keep it small.

## Less frequent broad integrity backup

Run a broader encrypted logical backup only at a cadence supported by measured size/egress budget.

Derived data need not receive the same backup frequency because it can be rebuilt from:

- source registry;
- canonical Truth Pack;
- private cold objects.

Make sure the encrypted backup workflow eventually lives on the default/integrated branch so its schedule actually runs. The previous branch-only backup workflow had no scheduled runs.

Do not solve backups by silently consuming the entire monthly egress allowance.

---

# 24. Egress/capacity observability

Add a compact runtime/cost evidence path.

At minimum each hosted bootstrap/recovery run should report:

- DB size;
- top relation sizes;
- top index sizes;
- hot opportunity count;
- cold opportunity count;
- archive object count;
- archive compressed bytes uploaded/downloaded during the run;
- feed row count;
- queue counts;
- source poll counts.

Do not include secrets/private payloads.

When possible, log bytes uploaded/downloaded by Storage V2 client.

Provider billing egress remains the ultimate number, but application-level byte counters help explain it.

---

# 25. W22.5 runtime/session correction remains frozen

Do not regress:

- one enqueue phase;
- exactly five drain shards for protected proof;
- unique worker IDs;
- PostgreSQL `SKIP LOCKED`;
- normal 30 jobs / 480 sec per shard;
- 35-minute job envelope;
- bounded SQLAlchemy pools;
- max worker DB connections <=10;
- `expire_on_commit=False` claim-session correction;
- stale RUNNING recovery before normal pending work;
- bounded/coalesced `evaluate_new`;
- commit-aligned concurrency correctness.

Clean database does not justify removing those fixes.

---

# 26. Clean project auth / Founder setup

Recreate only the minimum Founder authentication/runtime state required by the current product.

Do not fabricate historical sessions.

Old sessions were disposable.

If the product uses its own Founder password/session system rather than Supabase Auth, preserve that design.

If two old Supabase Auth users are visible only in the deleted project, do not assume they need migration. Create only identities actually required by current runtime/test acceptance.

Keep single-Founder scope.

---

# 27. RLS/security

Do not reintroduce the previously discovered table-level RLS defect.

Historical known defect:

`founder_activity_events` had Founder SELECT policy while table-level RLS was disabled in the deleted project.

On this clean project, the final schema must prove:

- RLS enabled where the intended contract requires it;
- anon/non-Founder denied;
- Founder/server paths function correctly;
- Storage buckets private;
- service role never exposed to client;
- no permissive accidental public policies.

Because this is a clean environment, there is no justification for knowingly recreating a broken security state.

Use a new migration after 0021 if necessary rather than editing deployed-history migration files.

---

# 28. Real PostgreSQL CI before hosted bootstrap

Use disposable PostgreSQL CI.

Required proof includes:

- fresh Alembic upgrade to head;
- exactly one head;
- schema integrity;
- Storage V2 direct-tier persistence;
- content-change invalidation;
- cold checksum verification;
- truth-pack re-evaluation from real archive truth;
- no persistent hot rehydration;
- corrupt archive fail-closed;
- current-only lean feed semantics;
- compact search behavior;
- Founder-history preservation;
- RLS/security contract where testable;
- queue concurrency/durability;
- bounded evaluation/coalescing;
- capacity guard;
- retention cleanup;
- backup selection logic.

No SQLite-only acceptance.

If local PostgreSQL is unavailable, GitHub Actions service containers are mandatory.

---

# 29. Bootstrap size proof — do not wait until all sources finish

After the representative source:

capture:

- opportunity count;
- DB size;
- relation sizes;
- index sizes;
- Storage object count/bytes.

Derive bytes per opportunity for:

- hot records;
- cold records;
- current feed.

If extrapolation to the expected source corpus predicts >200 MiB PostgreSQL, STOP SOURCE BOOTSTRAP.

Fix architecture first.

Do not knowingly fill the fresh database and compact later.

---

# 30. Full source bootstrap acceptance

After all intended read-allowed sources have been polled:

require:

- physical PostgreSQL <=200 MiB;
- preferred <=150 MiB;
- object storage <=500 MiB;
- no duplicate `active` projection corpus;
- no duplicate full-text feed corpus;
- COLD rows use Storage V2;
- HOT/PROTECTED rows retain necessary product detail;
- current feed behavior correct;
- search behavior correct;
- source rows are real, not fixtures.

If DB >200 MiB:

inspect top relations/indexes and fix the architecture.

Do not raise the limit.

---

# 31. Runtime queue bootstrap

Because old queue state was deleted, do not recreate historical backlog.

Seed only current due work based on current source registry/cadence.

Let scheduler produce valid work naturally.

The acceptance objective is a healthy current queue, not reproducing the old 500+ stale jobs.

Require:

- no expired leases;
- oldest due <900 sec after bootstrap convergence;
- no dead-letter surprise beyond contract;
- no connection saturation.

---

# 32. Final exactly-five-shard protected proof

Run the accepted W22.5-style protected proof on the NEW database.

Require:

- exactly 5 worker shards;
- normal 30 jobs / 480 sec settings;
- every shard within 35-minute envelope;
- max tagged worker connections <=10;
- persistent idle-in-transaction =0;
- unattributed DB connections =0;
- observer failures =0;
- expired leases =0;
- oldest due <900 sec;
- no new `EMAXCONNSESSION`;
- no new `UniqueViolation`;
- no new `ReadOnlySqlTransaction`;
- PostgreSQL <=200 MiB;
- incremental egress behavior consistent with W23 budget.

Do not weaken thresholds.

---

# 33. FULL monitor and issue #137

Run FULL monitor against the new project.

All active hardcoded old-project URLs must already be removed.

Require:

- no runtime FAIL/BLOCKED;
- queue healthy;
- capacity healthy;
- correct project URL;
- source health per existing contract.

Issue #137 must resolve through the normal incident processor `RESOLVE` path.

Do not manually close it.

---

# 34. Web/live deployment smoke

Update deployment/environment variables that still reference the deleted Supabase project.

Then verify the actual Founder surface against the new database:

- login;
- API health;
- feed;
- filters;
- opportunity detail;
- Founder activity actions;
- CV selection;
- artifact retrieval where applicable.

Do not call the product “live-verified” from database tests alone.

Use the existing status language precisely:

implemented -> reviewed -> integrated -> deployed -> live-verified

Do not merge as part of this sprint.

Hosted staging can still be acceptance-tested from the branch/environment.

---

# 35. Do not accidentally generate unnecessary egress in acceptance

Connection observers should query `pg_stat_activity`/small aggregates.

Queue monitors should query counts/ages.

Size monitors should query catalogs.

Do not download the corpus for evidence.

Artifacts uploaded to GitHub should contain metrics, not source payloads.

---

# 36. Checkpoint discipline

This sprint is expected to be long.

Context compaction is not a blocker.

Maintain:

`reports/evidence/FR-007/W23_CLEAN_REBUILD_EXECUTION_CHECKPOINT.md`

After each major phase record:

- branch;
- current SHA;
- new Supabase ref;
- completed phase;
- CI run IDs;
- hosted run IDs;
- database size;
- storage object bytes/count;
- queue state;
- egress-relevant counters;
- exact next action;
- any failure diagnosis.

After context compaction:

READ THE CHECKPOINT FIRST.

Do not re-investigate the project from zero.

---

# 37. Expected phase order

Execute in this order unless a concrete failure requires a corrective iteration:

### Phase A — credentials/config cutover

- GitHub environment secrets;
- project URLs;
- stale-ref purge;
- service role;
- connection mode.

### Phase B — canonical CV lane reconciliation

- canonical nine-CV repo metadata;
- canonical truth snapshot;
- upload exact private files if available;
- hash verification.

### Phase C — schema/storage redesign completion

- migration 0022+ if needed;
- direct HOT/COLD tiering;
- lean feed;
- compact search;
- compact evaluation;
- retention;
- RLS correction.

### Phase D — deterministic PostgreSQL proof

Everything green before broad live ingestion.

### Phase E — live migration/bootstrap

Apply schema to new Supabase DB.

### Phase F — representative source

Measure actual bytes/opportunity.

### Phase G — full source bootstrap

Incremental, measured, stop if extrapolated budget fails.

### Phase H — queue convergence

Clean current scheduler/worker state.

### Phase I — final five-shard acceptance

W22.5 connection proof reproduced.

### Phase J — FULL monitor + issue resolution

Normal RESOLVE only.

### Phase K — live Founder smoke

New project/deployment actually works.

### Phase L — evidence + State

Final report, then final State-only commit.

---

# 38. Fallbacks / blocker navigation

## GitHub workflow dispatch registration

If a branch-only `workflow_dispatch` is not registered:

use the already-established default-registered launcher + feature-ref pattern.

Do not merge just to register a workflow.

## GitHub environment secrets inaccessible through CLI

Use browser UI.

This is an authorized project setup action.

Do not print secret values.

## New Supabase direct connection temporarily unavailable

Check:

- project status;
- direct host;
- pooler host/mode;
- password;
- SSL;
- IPv4/pooler requirements.

Use Supabase dashboard-generated connection strings rather than inventing them.

## Source adapter ordinary failure

Diagnose and repair source-specific parsing/policy issues.

Do not weaken registry/SSRF policy.

## Storage upload fails due MIME

Use the already-created allowed MIME set or correct the client content type.

Do not make bucket public.

## Canonical CV package missing

Exhaust:

- prior local Codex workspaces;
- project attachments/library;
- prior generated files;
- known final ZIP paths.

If genuinely unavailable, continue infrastructure/source work and report the exact missing canonical package as the only external artifact blocker.

Do not regenerate “equivalent” CVs.

## Size exceeds 200 MiB

Stop ingestion.

Inspect top relations/indexes.

Fix the representation.

Do not invoke emergency compaction as the primary steady-state mechanism.

## Egress appears too high

Identify the read path causing it.

Typical fixes:

- aggregate in SQL;
- paginate;
- stop reading full descriptions from DB;
- stop full-corpus external scans;
- cache immutable archive reads where safe;
- evaluate before persistence.

Do not accept a 5 GB/month steady-state design.

## Ordinary tests fail

Fix them and continue.

## Context compacts

Resume from W23 checkpoint.

Not a blocker.

---

# 39. Prohibited shortcuts

Do not:

- create another paid provider;
- upgrade Supabase;
- recreate the old 1.5 GB design;
- restore derived old database dumps wholesale;
- retain synthetic `active` feed copies;
- store full description search vectors twice;
- store cold provenance relationally by default;
- expose service-role credentials;
- make private buckets public;
- manually fabricate queue/history state;
- manually close #137;
- weaken W22.5 connection thresholds;
- merge;
- claim seven-day soak;
- call PASS without measured live size.

---

# 40. Final evidence

Create:

`reports/evidence/FR-007/W23_CLEAN_REBUILD_STORAGE_V2_REPORT.md`

It must include:

## Provider identity

- project ref;
- region;
- plan;
- project URL;
- confirmed $0/month project creation.

No secret values.

## Baselines

- fresh DB baseline: ~10 MB;
- previous failed DB baseline: ~1503 MiB;
- previous egress observation: 3.87/5 GB.

## Repository

- final branch;
- final SHA;
- migration head;
- CI runs.

## Storage V2

- architecture implemented;
- hot/cold/protected rules;
- archive hash behavior;
- CV bucket status;
- opportunity bucket status.

## Source bootstrap

- sources attempted;
- source results;
- real opportunity counts;
- hot/cold counts.

## Physical footprint

Before/after/current:

- total DB bytes;
- top 20 relations;
- index bytes;
- feed projection bytes;
- opportunities bytes;
- provenance bytes;
- evaluation bytes.

Compute reduction versus 1503 MiB.

## Object storage

- object count;
- compressed bytes;
- average compressed bytes per cold opportunity;
- largest object;
- integrity verification result.

## Egress

- provider usage baseline;
- application-measured upload/download bytes during sprint where available;
- evidence that no corpus-wide Supabase export was used;
- expected steady-state egress design.

## Runtime acceptance

- queue convergence;
- five-shard run ID;
- observer metrics;
- source health;
- FULL monitor;
- issue #137 RESOLVE.

## Web smoke

- staging URL;
- login/feed/detail/activity/CV checks.

## Safety

Confirm:

- no paid infrastructure;
- no old-project data dependency;
- no source truth silently discarded;
- Founder history contract preserved for future use;
- no merge;
- seven-day soak not claimed.

---

# 41. Final State-only commit

Only after every code/evidence change is stable:

`STATE_PRESERVE_TIMESTAMP=1 python scripts/generate_state.py`

Commit **only**:

`docs/STATE.md`

No non-excluded code/evidence commit may follow it.

Push.

Confirm remote SHA.

---

# 42. Terminal PASS contract

Return **PASS** only when ALL are true:

1. GitHub staging secrets target `sunjfepvdzfknglrjwhm`.
2. Active code/workflows contain no stale old-project runtime reference.
3. Canonical nine-CV repo lane is reconciled.
4. Canonical CV binaries are uploaded and hash-verified, or the exact external artifact blocker is the only remaining blocker.
5. Fresh Supabase schema reaches repository head with one Alembic head.
6. Direct-tier Storage V2 ingestion is implemented.
7. Cold source truth uses private object storage.
8. No synthetic active projection corpus exists.
9. Search has one compact authoritative representation.
10. Cold provenance/evaluation detail is not duplicated in hot PostgreSQL.
11. Full intended source bootstrap completes with real data.
12. PostgreSQL <=200 MiB.
13. Preferred <=150 MiB is achieved unless evidence documents why the lean correct representation legitimately needs more while remaining <=200 MiB.
14. Object storage <=500 MiB.
15. No uncontrolled egress pattern remains.
16. Queue converges with expired leases =0 and oldest due <900 sec.
17. Final exactly-five-shard proof passes.
18. Max worker connections <=10.
19. Persistent idle-in-transaction =0.
20. Unattributed connections =0.
21. Observer failures =0.
22. No new EMAXCONNSESSION.
23. No new UniqueViolation.
24. No new ReadOnlySqlTransaction.
25. FULL monitor passes.
26. Issue #137 resolves via normal RESOLVE.
27. Founder staging surface is live-smoked against the new project.
28. Final W23 evidence report exists.
29. State-only commit is last.
30. Remote SHA confirmed.
31. No paid infrastructure.
32. No merge.
33. Seven-day soak not claimed.

If an ordinary implementation/runtime failure occurs, repair it and continue.

Do not return another partial infrastructure report.

Own the sprint end-to-end.
