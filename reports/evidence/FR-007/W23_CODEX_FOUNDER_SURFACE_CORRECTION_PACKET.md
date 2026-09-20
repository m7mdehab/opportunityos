# W23 — CODEX FOUNDER SURFACE / FEED CORRECTION EXECUTION PACKET

## ROLE

You are the Codex implementation executor for a new FR-007 Founder-surface correction lane.

The Founder has now exercised the real hosted site and reported six concrete product/runtime issues. The Overseer has already inspected the live Supabase data, the deployed hosted API code, the feed views, dashboard path, source registry, queue state, and current stale-posting logic. The diagnosis and implementation decisions below are frozen.

Your job is to implement the corrections completely, self-remediate deterministic failures, push the branch, and return one final PASS/BLOCKED completion report. Do not redesign the product from scratch and do not stop for routine engineering choices already resolved below.

## REPOSITORY / BRANCH

- Repository: `m7mdehab/opportunityos`
- Required branch: `work/fr007-codex-founder-surface-corrections`
- Branch parent / Overseer integration SHA: `1d231ee9f8949893da4458dc45a9327deb62b417`
- Read `AGENTS.md`, `briefs/BRIEF-FR-007.md`, and existing FR-006/FR-007 UI contracts before editing.
- Do not merge.
- Do not force-push.
- Do not modify Antigravity's queue-capacity lane files except where explicitly allowed below.

## FOUNDER FEEDBACK BEING CORRECTED

1. Founder asked what `Poll now` actually does and found its behavior opaque.
2. Job detail opens in a narrow right Sheet/drawer. On desktop and mobile it is cramped, too tall, difficult to read, and wastes screen width. Founder wants a centered overlay modal using screen width/height intelligently and closing when clicking outside it.
3. Founder wants a source overview/filter: where current jobs are coming from, counts by source, and ability to filter by source family such as Greenhouse, Reddit, etc.
4. No fit scores are visible on the job cards and the header numbers `Fetched — New — Qualified — High fit — Opened — Labelled — Applied — Hidden` are blank.
5. Nearly every visible job is Greenhouse; Founder believes source diversity is wrong.
6. Many Greenhouse links have shown the exact page text: `Page not found. The job board you were viewing is no longer active.` Founder wants those listings not to appear, but explicitly prefers **false negatives over false positives**: never mark a legitimate job inactive from weak/ambiguous evidence.

## OVERSEER LIVE DIAGNOSIS

### Poll Now

Current Cloudflare hosted behavior:

- `POST /api/worker/poll-now` calls Supabase RPC `enqueue_poll_now`.
- It is **due-only**.
- It respects `source_schedules.next_due_at`.
- It respects cooldown.
- It refuses duplicate active `PENDING/RETRY/RUNNING` jobs for the same source.
- It does **not** bypass cadence.
- It does **not** fetch a source itself.
- It does **not** drain the queue itself.
- It queues eligible due source jobs for the background worker fleet.
- Current UI immediately refreshes the feed/dashboard after enqueue, which can make the button appear to have done nothing because workers have not completed yet.

Preserve these safety semantics.

### Hosted dashboard bug

In `web/app/api/[...path]/route.ts`, hosted `GET /api/dashboard/daily` currently returns:

`{ days, high_fit_threshold: 80, series: [] }`

This is why the header renders em dashes instead of real numbers.

The real database already contains data for the counters. At the Overseer's point-in-time inspection for UTC 2026-09-20, representative counts included:

- fetched > 0
- new > 0
- evaluations > 0
- opened/labelled/applied legitimately may be 0

The endpoint must return real daily series, not a stub.

### Fit-score bug / duplicate hosted feed rows

Live database:

- opportunities: ~2.3k and changing as workers run
- evaluated opportunities: >2.1k
- match evaluations contain real fit scores
- example Founder-inspected job `greenhouse:coursera:5721735004` has a real latest evaluation:
  - decision = `ineligible`
  - fit score = `40`
  - full dimension-score JSON exists
  - full evaluation-detail JSON exists

But `public.founder_feed` currently directly exposes every `feed_projection` row.

Live defect:

- every evaluated opportunity currently has **two** founder_feed rows:
  - an older unscored projection with `fit_score=NULL`
  - a later scored projection
- 2,124 opportunity IDs were duplicated at inspection time.
- Hosted list order is `priority_score.desc,opportunity_id.asc`.
- PostgreSQL/PostgREST descending NULL ordering puts the NULL-priority rows first.
- The first hosted page therefore contained 50/50 unscored rows and 0 scored rows even though the database had >2.1k scored opportunities.

This is the direct cause of the Founder seeing no fit scores.

### Hosted detail serialization is also incomplete

`founder_opportunity_detail` exposes:

- `dimension_scores_json`
- `reasons_json`
- `evaluation_detail_json`
- real `fit_score`
- real decision
- policy/evaluated/truth hash

But the Cloudflare hosted route currently hard-codes:

- `constraints: []`
- `dimension_scores: []`
- `strengths: []`
- `gaps: []`
- `unknowns: []`
- blank explanation

That means the Founder is not receiving the full fit/qualification detail already persisted.

### Source-mix diagnosis

A live point-in-time snapshot showed >99% of persisted opportunities were Greenhouse. This is real, not just a UI illusion.

Live source scheduling is broader:

- Greenhouse: 266 schedules
- Lever: 68 schedules
- Remotive: 1
- Himalayas: 1
- We Work Remotely: 1
- Remote OK: 1
- Hacker News Who Is Hiring: 1
- plus procurement sources

The worker backlog currently contains Lever and non-Greenhouse poll jobs. Antigravity W22.1 is independently fixing background worker capacity so those jobs can actually be processed. **Do not duplicate Antigravity's capacity work in this lane.**

Reddit is a special case:

- Reddit sources are explicitly `manual_only`
- registry `automation.read = disabled`
- prior governed recon received HTTP 403
- do not turn Reddit automation on or bypass policy
- UI may show Reddit as manual-only / zero automated feed results, but must not imply automated ingestion exists.

### Existing non-Greenhouse errors

Historical initial non-Greenhouse poll errors recorded `No module named 'api'`. That dependency/runtime packaging defect has since been corrected by the repository workflow dependency installation. The pending jobs still need to be processed by Antigravity's worker-capacity lane.

### Inactive Greenhouse defect

Current stale logic:

- `opportunity/reverification.py` marks stale only for HTTP 404/410.
- It waits until an opportunity is older than 14 days.
- HTTP 200 semantic tombstone pages are treated active.
- live `opportunities.is_stale` was 0 across the corpus during inspection.

Therefore a Greenhouse page returning HTTP 200 with the exact semantic tombstone:

`Page not found. The job board you were viewing is no longer active.`

will currently remain visible indefinitely until another stronger signal appears.

The Founder explicitly requires conservative behavior:
- exact/high-confidence tombstone -> hide/mark stale
- ambiguous transport failure, 403, timeout, generic content, redirects, unknown response -> preserve listing
- never delete the record merely because availability is uncertain

## FROZEN ARCHITECTURAL DECISIONS

### D1 — Detail UI becomes a centered modal, not a right drawer

Replace the current `Sheet` detail presentation with a modal/dialog overlay.

Desktop contract:
- centered;
- approximately 88–92vw maximum viewport width but capped around a readable `max-w-6xl`/similar;
- maximum height around 88–92vh;
- own internal scrolling;
- not full-screen;
- use responsive 2-column layout where useful;
- main job description gets the larger column;
- fit/qualification/quick facts/actions use the narrower supporting column;
- header/close affordance must stay easy to find;
- do not create a single narrow vertical strip.

Mobile contract:
- single-column;
- width close to viewport with safe margin;
- height bounded to viewport using `dvh`;
- content scrolls inside modal;
- tapping/clicking outside modal closes it;
- Escape closes it;
- focus trapping/accessibility remains correct.

Use existing shadcn/Radix `Dialog` primitives if available. Do not hand-roll an inaccessible overlay.

Preserve all existing detail actions/artifacts/feedback behavior.

### D2 — Full hosted detail serialization

Parse the real persisted evaluation JSON.

Required mapping:

- `evaluation_detail_json.hard_constraints` -> `qualification.constraints`
  - persisted `passed=true/false/null` maps to `PASS/FAIL/UNKNOWN`
  - preserve reason, required_field, founder_fact, is_hard_failure, provenance_pointer
- `dimension_scores_json` -> `scoring.dimension_scores`
  - persisted `dimension_name` -> `dimension`
  - `raw_score` -> `score`
  - preserve weight, weighted_score, explanation -> rationale
- `evaluation_detail_json.strengths/gaps/unknowns/uncertainty_penalty/explanation`
- latest fit_score / policy_version / evaluated_at / truth_pack_hash

Fail safely on malformed JSON: empty substructures are preferable to breaking the detail endpoint, but never invent data.

### D3 — Canonical Founder feed, one row per opportunity

Create migration **0015** with a clear revision name such as:

`0015_hosted_founder_surface`

Down revision: `0014_backup_heartbeat`.

Alembic remains schema authority.

Replace `public.founder_feed` so there is exactly **one current row per opportunity**.

Required selection semantics:
- choose the newest/best current projection per `opportunity_id`;
- scored projection must win over an older placeholder/unscored projection;
- use deterministic ordering;
- prefer most recent `projected_at/evaluated_at`;
- ensure one row per opportunity.

Include these fields in the narrow Founder view if not already present:
- `is_stale`
- `reverified_at`
- `source_family = split_part(source_id, ':', 1)`
- opportunity created timestamp if needed for hosted dashboard/source counts

Keep the view Founder-only under existing RLS/security-invoker rules.

Hosted opportunity list must:
- default to non-stale opportunities;
- explicitly order scored/non-null priority rows correctly using `nullslast`;
- maintain stable deterministic pagination;
- return `is_stale` from storage rather than hard-coding false.

Add a regression test that fails if an evaluated opportunity appears twice or if an older unscored projection shadows its later scored projection.

### D4 — Real hosted dashboard

Add a narrow Founder-only hosted dashboard surface in migration 0015.

Preferred implementation: SECURITY DEFINER RPC guarded by `public.opos_is_founder()`, returning only aggregated daily counts and no private row content.

It must provide the existing `DashboardResponse` contract for N days:

- fetched
- unique_new
- qualified
- high_fit
- opened
- labelled
- applied
- hidden_by_filters

Use the configured high-fit threshold where possible; if RPC receives threshold, validate a finite 0–100 number.

Do not grant browser SELECT on broad private tables merely to implement counters if a narrow aggregate RPC can do it.

The Cloudflare hosted route must call the real aggregate surface and populate `series`, not return an empty stub.

### D5 — Source overview and source filtering

Implement a Founder-visible source control that answers:

- which source families currently supply visible jobs;
- current active opportunity count per family;
- count per concrete source_id/board;
- source health / last poll where available;
- ability to filter feed by source family;
- ability to narrow to a concrete source_id if the Founder chooses.

At minimum support:
- `source_family` query filter (e.g. `greenhouse`, `lever`, `remotive`)
- exact `source_id` query filter (e.g. `greenhouse:coursera`)

Create a narrow Founder-only summary view/RPC from canonical opportunity/feed data, not client-side counting of only the current page.

UI design:
- compact `Source` control near existing feed filters;
- opening it shows family counts;
- family may expand/show concrete source counts;
- selecting one filters the feed and resets pagination;
- `All sources` clears it;
- current selection is visibly shown;
- counts should exclude confidently stale listings by default.

Reddit/manual-only:
- do not enable automated ingestion.
- if the existing manual-source catalogue is surfaced in this control, label Reddit sources `Manual only` / `0 automated` and link to the existing manual flow.
- never show a fake Reddit opportunity count.
- automated filtering for a source with 0 rows legitimately returns 0.

Do not depend on the existing generic facet persistence for this direct Founder feed filter; this source filter must work immediately and transparently in the hosted API.

### D6 — Poll Now UX must tell the truth

Preserve current due-only/cooldown/idempotency semantics.

Improve the UI so the Founder understands the action.

Required behavior after click:
- show a concise inline result/status:
  - e.g. `Queued 12 due sources. Workers are processing them in the background.`
  - or `Nothing new to queue — sources are already queued, cooling down, or not due.`
- summarize skipped reasons where useful without dumping hundreds of rows;
- do not imply all sources were fetched synchronously;
- do not spin until background jobs finish;
- feed may refresh, but the button result must not disappear immediately.

Add tooltip/help copy stating that Poll Now queues **currently due** sources and does not bypass cooldown/cadence.

Do not create a browser-accessible GitHub token or trigger GitHub Actions directly from the client.

### D7 — Conservative inactive Greenhouse handling

Implement a high-confidence semantic tombstone detector.

Exact required marker:
`Page not found. The job board you were viewing is no longer active.`

Matching may be case-insensitive and whitespace-normalized but must remain semantically exact/specific.

Conservative rules:

- HTTP 404/410 -> stale (existing behavior)
- HTTP 200 + exact Greenhouse inactive-board marker -> stale
- timeout/network error -> NOT stale
- 403/429 -> NOT stale
- generic 200 page without marker -> NOT stale
- redirects/other ambiguous state -> NOT stale unless final definitive response is 404/410 or exact marker

Do not delete opportunities. Mark `is_stale=true` and set `reverified_at`.

Prevent confidently stale rows from default Founder feed.

Efficiency:
- do not issue one extra HTTP request per opportunity across thousands of Greenhouse jobs on every poll.
- implement board/source-level probing where safe: one high-confidence board availability probe can classify the board as inactive only when the exact board-inactive marker is observed.
- when a Greenhouse poll succeeds, it is acceptable to validate that board once and apply a definitive inactive result to that source's rows.
- daily/background reverification may also sweep Greenhouse boards source-by-source.
- if a board probe is ambiguous, preserve all listings from that board.

If a source later has a successful current poll AND a definitive active board response, rows in the current fetched batch may be restored to `is_stale=false`; do not blindly un-stale historical rows that were independently 404/410.

Add tests for exact marker, near-miss text, 403, timeout, 404, 410, active 200.

### D8 — Source diversity ownership boundary

Do not change scheduler capacity, matrix worker count, queue ordering, or W22.1 worker workflows. Antigravity owns those.

Your responsibility is:
- make the UI accurately expose the current source distribution;
- ensure source filtering works;
- ensure the hosted feed does not structurally suppress scored/non-Greenhouse rows;
- keep source family/filter semantics ready for Lever/RemoteOK/HN/etc as Antigravity drains their jobs.

If you discover an adapter-specific non-Greenhouse defect independent of capacity, report it with evidence rather than expanding into queue architecture.

## UI ACCEPTANCE DETAILS

### Job cards

Keep existing fit-score display, but after the feed repair:
- scored rows show numeric score;
- truly unevaluated rows show em dash;
- no evaluated row should display em dash because an older unscored projection shadowed it.

### Detail modal

Top area should immediately show:
- title
- organization
- source
- decision
- fit score
- work mode/location
- posted/deadline/reverified

Body should use the space intelligently:
- larger reading column: job description
- supporting column: qualification checklist, fit dimensions, strengths/gaps/unknowns, key actions
- artifacts/feedback/triage remain usable
- no huge unbroken narrow text wall

### Source UI

At minimum show:
- source family name
- count
- selected state
- optional per-source expansion
- health indicator if already available

Do not overload the main header with 300 board entries.

## TEST REQUIREMENTS

Run focused tests plus all web/build/governance tests invalidated by this work.

At minimum:

```bash
python -m unittest   storage.test_hosted_runtime_migration   scripts.test_fr007_supabase_execution_bundle   opportunity.test_reverification   worker.test_worker   api.test_api   -v
```

Run any directly relevant migration/PostgreSQL tests against disposable PostgreSQL.

Web:

```bash
cd web
npm ci
npm run lint
npm run build
npx playwright test
```

Add/extend Playwright coverage for:
- detail opens as centered dialog, not right sheet;
- outside click closes;
- mobile viewport dialog remains usable;
- fit score renders for a scored fixture;
- dashboard numbers render;
- source family count/filter works;
- Poll Now result text explains queued vs skipped;
- stale/inactive row does not appear in default feed fixture.

Run:

```bash
python scripts/check_repository.py
python scripts/check_guard.py --allow-missing-patterns
git diff --check
```

## LIVE/DATABASE SAFETY

This lane may inspect live Supabase read-only if credentials are available, but must not mutate production data directly to manufacture evidence.

Do not apply migration 0015 live unless the packet's environment explicitly provides the repository's authorized migration path and the action is already normal for this lane. Otherwise leave live application to the Overseer.

Do not delete opportunities.

Do not weaken RLS.

Do not expose description/private truth-pack data through new summary views.

## PREFERRED FILE OWNERSHIP

Expected files include:

- `web/components/feed/detail-drawer.tsx` (rename to detail-dialog if appropriate)
- `web/components/feed/header-strip.tsx`
- `web/components/feed/filter-bar.tsx` or a dedicated source-filter component
- `web/components/feed/opportunity-card.tsx` only if needed
- `web/app/page.tsx`
- `web/app/api/[...path]/route.ts`
- `web/lib/api/client.ts`
- `web/lib/contract/types.ts`
- relevant web tests
- new `storage/migrations/versions/0015_*.py`
- migration tests / provider-bundle tests as needed
- `opportunity/reverification.py`
- its tests
- `worker/handlers.py` only for bounded Greenhouse board-level stale integration; do not touch queue/runner scheduling capacity
- evidence file for W23

Avoid:
- `.github/workflows/fr007-worker-drain.yml`
- Antigravity W22.1 capacity files
- `worker/queue.py`
- `scripts/fr007_cloud_monitor.py`
- `scripts/process_incident_alert.py`
- `docs/STATE.md`
- `reports/REPORT-FR-007.md`

## FINAL REPORT

Return one W23 MASTER COMPLETION REPORT with:

- STATUS PASS/BLOCKED
- start SHA
- branch
- final local SHA
- verified remote SHA
- acceptance matrix D1–D8
- exact files changed
- migration revision/head
- deterministic tests and results
- Playwright results including mobile
- disposable PostgreSQL migration proof
- feed uniqueness proof
- scored first-page proof
- dashboard contract proof
- source-filter/count proof
- inactive Greenhouse false-positive-safety tests
- Poll Now UX behavior
- unresolved/out-of-lane findings
- READY FOR OVERSEER INTEGRATION YES/NO

Do not declare FR-007 closed and do not merge.
