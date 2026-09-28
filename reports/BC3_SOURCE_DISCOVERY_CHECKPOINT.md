# BC-3 Source & Discovery Checkpoint

Date: 2026-09-28  
Base: `f8b5d0429824f2ff20c242fb9d7c02b6a720bed5`  
Checkpoint: built locally on `work/bc3-source-discovery`; not yet landed or live.

## Implemented

- Added a governed, bounded Himalayas search plan for Egypt/worldwide data and AI role families. It uses the documented search URL contract, merges duplicate results deterministically, stops on policy/rate-limit/fetch errors, and remains behind `OPPORTUNITYOS_HIMALAYAS_TARGETED_SEARCH=true`. The default worker route stays on the documented 20-job browse endpoint.
- Corrected Himalayas expiry-date mapping and set Himalayas/Remotive cadences to the documented once-daily / 24-hour freshness cadence.
- Added canonical pre-persistence role admission for broad Greenhouse/Lever sources. Only clearly non-target jobs are excluded; unknown roles remain reviewable and historical rows are untouched.
- Added a Greenhouse title-only early gate before description extraction for the canonical families that are unambiguously non-target without body evidence. Adjacent families and unknown titles remain fully parsed. The parser/pipeline now report this count for accurate poll diagnostics.
- Added an ATS-board seed helper over recent, relevant existing opportunities, and an offline-only Reddit hiring-post parser/canonicalizer. Reddit remains disabled and no Reddit network requests are made.
- Documented official source/API terms and current go/no-go decisions in `docs/BC3_SOURCE_RECON_2026-09-27.md`.

## Safety and rollout

- No source activation, backfill, production poll, persistence, or Founder data write was performed.
- The targeted Himalayas path is off by default. The one ten-query preview was read-only: HTTP 200 for each query, 200 result rows total, 1,269,347 response bytes.
- Current live database measurement: `363,228,307` bytes (~346.40 MiB), approximately 3.60 MiB below the 350 MiB warning line. No write canary is authorized at this margin.
- Jobgether remains excluded under current terms; SmartRecruiters and Personio lack a verified global discovery surface; Teamtailor requires a key; Ashby remains disabled because the project’s prior governed robots check returned 401; Reddit remains disabled pending authorized access.
- BC-2 historical replay acceptance remains pending. No broad activation or corpus backfill may precede that gate.

## Greenhouse runtime diagnosis

The official Greenhouse Job Board API describes `content=true` for full list descriptions and a per-job detail route. One governed, read-only preview of `greenhouse:cloudflare` using the current list request returned 393 jobs, 6,868,782 bytes, and ~3.1 seconds transport latency. In-memory adapter parsing took ~45.9 seconds and classified 11 core, 195 adjacent, 143 non-target, and 44 unknown roles. No persistence/evaluation ran. The title-only gate avoids full extraction work for unambiguously irrelevant families but does not claim to resolve every long poll. A per-job detail fanout was not introduced because the board could require hundreds of additional paced requests. Further runtime diagnosis is required before any claim that long-running Greenhouse polls are fixed.

## Focused verification

Passed locally:

- `python -m unittest opportunity.test_adapters opportunity.test_pipeline matching.test_candidate_admission opportunity.discovery.test_boards opportunity.discovery.test_reddit opportunity.test_himalayas_search worker.test_runner.TestPollSourceHandler worker.test_runner.TestHimalayasGovernedSearch -v` — 79 tests.
- `python -m unittest worker.test_runner -v` — 25 tests.
- `python -m unittest opportunity.test_source_policy opportunity.test_pipeline opportunity.test_deterministic_replay matching.test_candidate_admission -v` — 13 tests.
- `python -m compileall -q matching opportunity worker` — passed.
- `git diff --check` — passed.

Full local unittest discovery ran 1,697 tests and ended with 13 failures, 11 errors, and 78 skips. The surfaced failures included unrelated Founder activity model/API contract mismatches, a SQL-rendering string assertion in `storage.test_feed_regression`, and generated `.open-next` cache hygiene. No failures were in BC-3 changed behavior. This is not reported as a green repository-wide suite; required PR checks remain necessary and the unrelated failures are a separate baseline/runtime issue unless CI ties one to this patch.

The first PostgreSQL-backed FR-007 CI proof run exposed one interaction with existing A5/A6 synthetic Greenhouse rows: both used reliability-only titles that the canonical admission rule intentionally rejects. The proof is about worker source isolation and idempotent persistence, so its synthetic successful rows were changed to canonical data-engineering titles; poll, content-change, and stable-ID assertions remain intact. This is a test-fixture alignment, not a change to production role-admission semantics. The corrected PostgreSQL proof must pass on a rerun before merge.

These are focused local checks, not PR CI, deployment, or authenticated live-product evidence. The BC-3 checkpoint remains subject to review and CI before merge.

## Next

Finish the bounded branch review, push/open the BC-3 PR, obtain required checks, merge and verify deployment. Continue to BC-4 only after BC-3 lands; keep historical replay acceptance for the designated BC-5 gate.
