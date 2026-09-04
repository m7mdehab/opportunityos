# E1 — ATS board discovery sweep run report

Command: `py -3.12 -m opportunity.discovery` (no `--limit`; the run was interrupted by wall-clock
budget, not by the tool, and is fully resumable via `opportunity/discovery/.progress.json`,
which is machine-local state and is not committed).

## The number reached

**702 candidates probed** (Greenhouse + Lever only; Ashby was out of scope for this sweep --
see below) before the session's time budget required stopping the sweep. Of those:

| Classification | Count |
|---|---:|
| live | 42 |
| empty | 8 |
| absent | 651 |
| blocked | 0 |
| error | 1 |
| **total probed** | **702** |

**36 new boards were registered** into `docs/SOURCE_REGISTRY.yaml` (>= 1 posting in a target
title family within the last 90 days, out of the 42 `live` boards -- the other 6 `live` boards
had postings but none matched a target title family or all matches were older than 90 days).
Combined with the pre-existing 12 Greenhouse + 2 Lever boards from `recon/sources.py:
ATS_WATCHLIST`, employment ATS board coverage in the registry is now **50 Greenhouse/Lever
boards**, short of the brief's 300 target. What limited it: real per-request network latency in
this environment varied widely (single requests ranged from under a second to tens of seconds),
and the seed is a name-guessing candidate list against Greenhouse/Lever's board-token URL
convention, so the majority of candidates (651/702, 92.7%) are legitimately `absent` (HTTP 404 --
the company does not use that ATS, or uses a different token than its name slug). The seed list
itself is fully committed (882 company slugs = 1,764 Greenhouse+Lever candidates once the founder
watchlist and already-registered boards are excluded); 1,057 candidates remain unprocessed and
the sweep resumes from exactly where it stopped on the next invocation.

**Relevance filter used: `title_family_model`** (`matching.title_family.normalize_title`,
backed by the now-present `matching/title_families.yaml` from work order B3) -- **not** the
committed keyword fallback. A `family_id != "other"` counts as a target family. This is a
different (stricter, more precise) number than a keyword-fallback run would produce; the
committed `KeywordFallbackClassifier` in `opportunity/discovery/boards.py` exists and is unit
tested, but was not the classifier this run used.

## Wall-clock

Approximately 20 minutes of sweep time elapsed (background run started, polled at intervals,
then deliberately stopped) for 702 new HTTP requests, i.e. roughly 35 requests/minute averaged
across both hosts combined -- latency-bound, not limiter-bound (the shared per-host pacer's
floor of 0.4s/host was rarely the binding constraint; most individual request latencies observed
were larger than that on their own).

## Seed directories used, with URL and access date

1. **`remoteintech_directory`** -- https://github.com/remoteintech/remote-jobs, accessed
   2026-09-03, license ISC per the repository's README `## License` section. 882 company-name
   slugs were read once from the repository's file tree
   (`https://api.github.com/repos/remoteintech/remote-jobs/git/trees/main?recursive=1`, a single
   GitHub API call) and committed verbatim to
   `opportunity/discovery/seeds/remoteintech_companies.json` alongside this citation and date,
   for reproducibility. Each slug is a discovery *candidate* token tried against Greenhouse and
   Lever's public board endpoints; it is never asserted to be the company's actual ATS token
   until a live HTTP probe confirms it (see the 92.7% `absent` rate above -- most guesses are
   wrong, and the classifier records that honestly rather than fabricating a match).
2. **`founder_watchlist`** -- `private/watchlist.yaml` (founder-private, template committed at
   `private/watchlist.yaml.template`). It did not exist at run time, so it contributed 0
   candidates this run; the loader is unit tested against an explicit temporary file and never
   reads the real path in any test.

`recon/sources.py:ATS_WATCHLIST` (12 Greenhouse + 2 Lever + 13 Ashby boards, already registered
by FR-003) was deliberately **not** used as a seed for new-board discovery: every Greenhouse/Lever
board on it is already registered (nothing new to discover), and probing its Ashby members would
have produced live-and-relevant boards this sweep has no policy basis to register as
`read: allowed` (Ashby stays disabled -- see below). The loader function
(`load_watchlist_ats_candidates`) is still implemented and unit tested for future use once Ashby
policy changes.

## Sources returning 403 or 429

**None.** `blocked_ids` is empty across all 702 probed candidates. Since the classification
breakdown is empty for `blocked`, there is nothing to confirm was "never requested again" beyond
the general guarantee built into `opportunity/discovery/boards.py::run_sweep`: any candidate
classified `blocked` is recorded in the resumable progress file keyed by its exact
`{kind}:{token}` id and is skipped (not re-requested) on every subsequent invocation for the
lifetime of that progress file, unit tested in
`test_resumed_sweep_skips_already_processed_and_never_reprobes_blocked`.

## Ashby re-recon

Re-checked 2026-09-03 against **`api.ashbyhq.com`**, the documented public posting-API host
(the same host `recon/sources.py:ats_sources()` already calls for every `ashby:*` entry's
`/posting-api/job-board/{token}` reads). One unauthenticated `GET
https://api.ashbyhq.com/robots.txt`, not retried: **HTTP 401**, identical to the 2026-09-02
FR-003 D11 finding already in `docs/SOURCE_REGISTRY.yaml`. As a secondary, non-authoritative
check, `GET https://jobs.ashbyhq.com/robots.txt` (Ashby's candidate-facing career-page host --
a *different* host from the documented posting API) returned HTTP 200 with `Disallow: /meeting/`,
`Disallow: /b/`, `Disallow: /api/`; it is not blanket-disallowed, but it is not the posting-API
host and says nothing about `api.ashbyhq.com`'s policy, so it cannot substitute for the required
permission.

**Decision: `automation.read` stays `disabled` for every `ashby:*` entry.** Per the E1 order,
"if robots is still unreachable or forbids, Ashby stays disabled and that is a valid closure" --
robots.txt on the documented posting-API host is unreachable (401) exactly as before, so the
flip condition (robots AND terms both permit) is not met. No `ashby:*` entry in
`docs/SOURCE_REGISTRY.yaml` was modified by this re-recon; the existing 2026-09-02 record already
reflects this state. Full write-up: `docs/SOURCE_EVIDENCE.md`, "Re-recon 2026-09-03
(BRIEF-FR-006 E1)".

## Assumptions named

1. **Ashby excluded from the new-board discovery sweep entirely** (not merely from
   registration): since Ashby `automation.read` is policy-disabled this brief, there is no basis
   to spend request budget classifying new Ashby boards that could not be registered as
   read-allowed regardless of outcome. Only Greenhouse and Lever candidates were generated from
   both seeds.
2. **Company-name slug == ATS board token** is the candidate-generation heuristic for the
   `remoteintech_directory` seed. This is a guess, honestly labeled as such, and validated only
   by a live HTTP 200/404 probe -- never asserted true without that probe.
3. **A posting whose date field could not be parsed is treated as within the 90-day window**
   rather than dropped, on the reasoning that a missing/malformed timestamp is not evidence of
   staleness (`opportunity/discovery/boards.py::relevant_postings`).
4. **`recon.sources.ATS_WATCHLIST` is not a discovery seed** (see above) -- its Greenhouse/Lever
   members are all already registered, and it is retained in `boards.py` only as a loader
   function for potential future use, exercised by its own unit test.
5. **The sweep was stopped by session time budget, not by exhausting the seed list or by any
   policy signal.** 1,057 of 1,759 deduplicated Greenhouse/Lever candidates remain unprocessed
   and are resumable in a future invocation of `py -3.12 -m opportunity.discovery`.
