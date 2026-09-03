# Work order E4F3 — Poll cadence, freshness, and the daily digest

**Brief:** BRIEF-FR-006 §2 Track E node **E4** and Track F node **F3**, combined.
**Wave:** 3. **Depends on:** E1 and E23 (integrated).
**Worktree/branch:** `wt/fr006-e4f3` **Test DB:** `opportunityos_test_e4f3`

**First action:** `git merge --no-edit feat/brief-fr-006-nothing-missed` from your worktree root.

**Master's note on the merge:** both nodes live in `worker/`. Two worktrees editing
`worker/handlers.py` and `worker/scheduler.py` conflict for no parallelism gain. Recorded as a
deviation.

## Deliverable text (verbatim from the brief)

> **E4 — Poll cadence and freshness.** Per-source cadence (hourly for HN/Reddit/remote boards,
> 6-hourly for ATS boards, daily for procurement); `stale_postings` re-verification for anything
> older than 14 days; a **"new since you last looked"** marker driven by
> `founder_opportunity_views`.
>
> **F3 — Daily digest.** `python -m worker --digest` writes a Markdown/HTML digest of new
> high-fit items to `out/digest/`; the API exposes it; email delivery is FR-007 (needs the inbox
> mailbox).

## Facts established by the Master — do not re-derive

- `worker/scheduler.py:113-154`: cadence today is a **single global interval**,
  `OPPORTUNITYOS_POLL_INTERVAL_HOURS` or 6 hours, with a 30-second tick and duplicate
  suppression at lines 158-177. There is **no per-source rate limiting**.
- `worker/handlers.py:199-393`: the poll handler checks `registry.is_read_allowed(source_id)`
  and records a refusal for a disabled source. Keep that gate exactly where it is.
- Work order E1 added shared **per-ATS-host** rate limiting. Cadence is a different thing from
  rate limiting and both must hold: a source may be scheduled hourly and still be throttled by
  its host's shared limiter. Do not collapse the two.
- **Migration `0004_founder_control` already exists** and is frozen. **Do not write a migration.**
- **`founder_opportunity_views` already existed before this brief**, created by
  `0002_match_evaluations`, and its shape is **not** what an earlier draft of this order said:
  it has a **surrogate `id` primary key**, not `opportunity_id` as the primary key. Read the
  actual model in `storage/models.py` before writing against it. `0004` deliberately did not
  touch it.
- FR-005 established that `stale_postings` is a guaranteed no-op because **nothing in the
  codebase writes `is_stale = True`**. `opportunity/reverification.py` exists. Your E4
  re-verification is the writer that makes that filter mean something — that is the point of
  this node, and work order C1 is reporting the same gap from the query side.
- `alpha.py` and every child process use `sys.executable` (work order F2). Follow that.

## Required behaviour

1. **Per-source cadence**, declared in `docs/SOURCE_REGISTRY.yaml` as a field on each entry
   (so cadence is policy data next to the rate limits, not a Python table), with a default when
   absent. Hourly for HN / Reddit / remote boards, 6-hourly for ATS boards, daily for
   procurement. The scheduler reads it per source. Duplicate suppression must keep working.
2. **Cadence is a floor, not a licence.** A source that returned 403 or 429 is not rescheduled in
   the same session regardless of its cadence. Assert this.
3. **Staleness re-verification**: anything older than 14 days is re-verified, and a posting that
   is gone is marked `is_stale = True`. This is the writer `stale_postings` has never had.
   Re-verification obeys the same policy gate and the same rate limits as a poll, and a source
   that forbids reading is never re-verified — it is left alone and recorded.
4. **"New since you last looked"**: `founder_opportunity_views` records when the founder last
   viewed the feed; the API marks rows newer than that. Marking a row seen must never change its
   `decision`, `fit_score`, or hidden state.
5. **`python -m worker --digest`** writes a Markdown **and** HTML digest of new high-fit items to
   `out/digest/`, named deterministically by date, and the API exposes the latest. Content is
   generated from stored rows only — the digest must not fetch anything. **No email delivery**;
   that is FR-007 and needs a mailbox the founder has not provided.
6. `out/digest/` is build output: make sure it is gitignored and that `scripts/check_repository.py`
   still passes.

## Allowed files

`worker/**` · `opportunity/reverification.py` and its test ·
`docs/SOURCE_REGISTRY.yaml` (adding a cadence field to entries only — do not change any
`policy_status`, `automation`, or `access` value) · `api/routes_api.py` and `api/test_api.py`
(the digest endpoint and the "new since" marker only) · `storage/repository.py` and
`storage/test_postgres_integration.py` (the views table only) · `.gitignore` ·
`reports/evidence/FR-006/e4f3-run.md`.

## Frozen — touching any of these is a FAIL

Any migration · `storage/models.py` · `opportunity/` other than `reverification.py` ·
`opportunity/registry.py` · `matching/**` · `truth/**` · `api/facets.py`, `api/search.py`,
`api/filters.py`, `api/saved_views.py` (other work orders own them) · `web/**` ·
`docs/AGENT_PERMISSIONS.yaml` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| E4F3.1 | `py -3.12 -m unittest discover -s worker -p "test_*.py" -v` | `OK`, count stated |
| E4F3.2 | the cadence test | each source class scheduled at its declared cadence; the registry field is the source of truth; a source with no field gets the default |
| E4F3.3 | the 403/429 test | a source that returned 403 or 429 is **not** rescheduled in the same session, whatever its cadence |
| E4F3.4 | the re-verification test | a posting older than 14 days that is gone becomes `is_stale = True`; one still present does not; a read-forbidden source is never re-verified |
| E4F3.5 | the "new since" test | rows newer than the last view are marked; marking seen changes no `decision`, `fit_score`, or hidden state |
| E4F3.6 | `py -3.12 -m worker --digest` | Markdown and HTML written to `out/digest/`; the run makes **zero** network requests (assert it) |
| E4F3.7 | `py -3.12 -m unittest discover -s api -p "test_*.py" -v` and `py -3.12 scripts/check_repository.py` | `OK` and exit 0 |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim.

## Addition from the Master (after E23 integrated)

**Wire the Hacker News live-fetch seam.** Work order E23 shipped
`opportunity/adapters/hacker_news.py` with `HackerNewsWhoIsHiringAdapter.parse_payload` (tested
offline against a committed fixture) **and** a live multi-step Firebase fetch
`fetch_who_is_hiring_payload()` that is **not wired into `worker/handlers.py`** — that file was
outside E23's allowed list, so it left a documented seam for integration. `worker/handlers.py` is
yours.

Wire it, subject to the same gates as every other source: the `registry.is_read_allowed`
check stays exactly where it is; the shared rate limiter applies; a 403/429 is recorded and the
source is not requested again this session. Hacker News is the **only** new read-allowed source
in the brief that produces rows, so if it is not wired, the live poll claim A-9 shows no breadth
delta at all.

Cadence for it, per the brief: **hourly**. The monthly thread changes within a day.

Add one acceptance row and paste its output:

**E4F3.8** — a poll of `hacker_news_who_is_hiring` through the normal worker path, against a
mocked or recorded payload (no live network in a test): rows are ingested, the registry gate is
exercised, and the rate limiter is consulted. Print the row count.

Also note: `opportunity/manual_sources.py` now exists and holds the deep-link catalogue for every
`manual_only` source. You do not own it and must not poll anything in it — a `manual_only` source
is never fetched. Claim A-16 has a test that asserts exactly that (`opportunity/test_source_policy.py`);
keep it green.
