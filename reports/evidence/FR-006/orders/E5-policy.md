# Work order E5 — Council review #4's source-policy findings

**Brief:** BRIEF-FR-006 §4, council review 4; AGENTS.md hard rules. **Wave:** 4.
**Depends on:** E1, E23 (integrated).
**Worktree/branch:** `wt/fr006-e5` **Test DB:** `opportunityos_test_e5`
**Turn budget:** 90. **At most 10 read/grep calls.**

**First action, not optional:** `git merge --no-edit feat/brief-fr-006-nothing-missed`. Your
worktree is branched from `main` and is many work orders behind. Every file and symbol named below
exists only after that merge. If you check for something before merging and do not find it, the
cause is the unmerged worktree — merge, then look again.

**Make no network request during this work order.** Everything here is fixable offline, and the
sources involved include several that have already refused us.

## Why this order exists

Council review #4 enumerated all 110 registry entries and all 20 bound adapters offline and
confirmed six properties as genuinely satisfied: every entry has `prepare`/`submit` disabled;
`AGENT_PERMISSIONS.yaml` is byte-identical to baseline; no adapter binds to a `manual_only` or
`disabled` source; User-Agents are truthful and non-browser; `manual_only` deep links are
string-templated with no fetch path; and the discovery sweep's limiter is keyed by ATS kind.

It then found six MAJOR and several MINOR defects. **Two of them mean the product currently
claims a policy control it does not implement, and one means an adapter fetches outside every
gate.** The Master has independently verified findings 10 and 11 in the source before writing this.

## The findings

### Finding 10 — MAJOR. An unpoliced fetch path. Fix this first.

`opportunity/adapters/hacker_news.py:73-108`. `fetch_who_is_hiring_payload` uses raw
`urllib.request.urlopen` (line 83), bypassing `SourceRegistry.validate_preflight`,
`AcquisitionService`, and every rate limiter — up to 1 + 60 + 200 = **261 unpaced GETs** to
`hacker-news.firebaseio.com`. It never consults `is_read_allowed`, so flipping the registry entry
to `disabled` **would not stop it**. A 403 or 429 mid-loop raises an uncaught `HTTPError` and
records nothing.

This is the "coverage is not permission" rule failing at the code level: the registry is supposed
to be the authority the fetch path consults, and this path does not consult it.

Fix: route every GET through `AcquisitionService.acquire("hacker_news_who_is_hiring", url)`, which
enforces the `/v0/` endpoint rule at `opportunity/registry.py`. Stop and return the partial payload
on any 403 or 429, recording the outcome. Pace with the shared limiter. Add a test that flipping
the registry entry to `read: disabled` makes the fetch refuse.

### Finding 11 — MAJOR. The bound adapter yields nothing, and the evidence overstates it.

`opportunity/adapters/hacker_news.py:118` sets `feed_url` to
`https://hacker-news.firebaseio.com/v0/user/whoishiring.json`. `OpportunityPipeline.execute_discovery`
fetches exactly that and hands the result to `parse_payload`, which requires a `comments` key —
so in production the adapter yields **0 rows** and permanent `has_schema_drift=True` health. The
`192 rows` figure in `docs/SOURCE_EVIDENCE.md` came from a manual smoke run of
`fetch_who_is_hiring_payload`, not from the bound path.

Fix: wire `fetch_who_is_hiring_payload` into the poll path for this `source_id` so the bound
adapter actually produces rows. **And amend the evidence row** so it states what the bound path
does. If you cannot wire it within budget, the evidence row must still be corrected to say the
bound adapter is not yet producing rows — the correction is not optional and is not contingent on
the fix.

### Finding 9 — MAJOR. The registry asserts a control the code does not implement.

The 36 generated board entries carry `rate_limits.documented: shared_per_ats_host`. The production
poll path does not do that: `AcquisitionService.acquire` paces by `source_id` (per board), and
`worker/handlers.py:302` constructs a fresh `OpportunityPipeline`, and therefore a fresh
`RateLimiter`, per job — so nothing is shared even per board across jobs.

A policy file that describes a control which does not exist is worse than one that admits the gap.
Fix: either key `AcquisitionService`'s limiter by `urlparse(url).netloc` (or ATS kind) and hold one
process-wide limiter in the worker, **or** change the template value to something the code
actually enforces. Prefer the first. Whichever you choose, the registry and the code must agree.

### Finding 7 — MAJOR. A fail-open path to a disabled source.

`opportunity/discovery/boards.py:283,346,355,362` and `opportunity/discovery/__main__.py:40-43`.
`load_founder_watchlist_candidates` accepts `kind: ashby` because `ATS_HOSTS` includes it, so a
founder watchlist entry would make the sweep probe `api.ashbyhq.com` and write an `ashby:*` entry
with `automation.read: allowed` — while Ashby is registered **disabled** on a recorded HTTP 401.
`__main__.py:41-42` asserts the seeds are "Greenhouse/Lever only by construction", which is false
for the watchlist. `recon/test_registry_generated.py:65` only guards `greenhouse:`/`lever:`
prefixes, so a generated `ashby:*` entry would pass.

Fix: restrict `load_founder_watchlist_candidates` to `("greenhouse", "lever")`, and make
`build_registry_entry` and `run_sweep` **raise** for any kind whose host-level `automation.read` is
not `allowed` in the committed registry. Extend the registry test to catch a generated entry for a
disabled host.

### Finding 8 — MAJOR. The never-retry guarantee does not survive a crash.

`opportunity/discovery/boards.py:316-327`. `save_progress` writes non-atomically via `write_text`;
a crash mid-write leaves invalid JSON, and `load_progress` returns `{}` on `JSONDecodeError` —
silently re-probing every candidate, **including ones already recorded as blocked**.

Fix: write to a temporary path and `os.replace`. On a corrupt progress file, **raise** rather than
returning `{}` — refusing to run is the correct behaviour when the record of what is blocked has
been lost.

Related, finding 16 — MINOR: a crash after a 403 is returned but before `save_progress` also loses
the record. Persist a `pending` marker for the candidate before the fetch, then overwrite it with
the classification.

### Finding 12 — MAJOR. 36 registered boards nothing reads.

The 36 new `greenhouse:*`/`lever:*` read-allowed entries have no bound adapter, so
`worker/scheduler.py` enqueues a `poll_source` job for each and `pipeline.py` records
`Unregistered adapter` (status 400). Policy-safe, but the coverage is not read by the product and
the health table will show 36 perpetual failures.

Fix: derive the Greenhouse and Lever adapter bindings from the read-allowed registry entries rather
than a hard-coded list, so a registered board is polled by construction.

### Finding 20 — MINOR, but it is the never-retry rule again.

`opportunity/health.py:33-37` with `worker/scheduler.py:149-154`: a 403 or 429 on a scheduled poll
only sets health status, and the scheduler re-enqueues the source after `interval_hours` with **no
gate**. So a blocked source is automatically re-requested on a later tick.

Fix: on 403/429 write a `blocked_until_reviewed` marker that the scheduler consults before
enqueueing. The session-scoped rule is already honoured; this closes the across-session hole.

### Finding 13 — MAJOR. An unresolved question about whether we breached robots.

`docs/SOURCE_REGISTRY.yaml` (`reddit_forhire`) and `docs/SOURCE_EVIDENCE.md`. The record says
robots.txt was fetched (200) and then `/r/forhire.json` was requested, but **does not record what
robots.txt permitted for `User-agent: *`**. Without the directive text nobody can tell whether the
body request was robots-compliant before it hit the 403 — and if robots disallowed `/`, the body
request itself was the breach and the 403 is secondary.

Fix, **offline only**: you may not re-fetch Reddit's robots.txt — that host has already returned
403 to us this session. Amend the evidence to state plainly that the directive text was not
recorded, that compliance at the time of the request therefore cannot be established from the
evidence, and that the source is `manual_only` regardless. Recording an unresolved question
honestly is the correct outcome; do not guess what robots said.

### Finding 14 — MINOR. A machine-readable field that lies.

Six inferred subreddit entries carry `observed.status: http_403` — identical to the one actually
observed on `reddit_forhire`. Only the free-text `detail` says "not independently requested", so any
consumer of `status` (such as `/sources/health`) renders an inference as an observation.

Fix: use a distinct status such as `inferred_from_sibling_403`, keeping `http_403` only on the entry
that actually received it. Update any status-count consumer accordingly.

### Finding 15 — MINOR. A test that cannot fail.

`recon/test_e23_transport_log.py` claims to replay "the actual, dated 2026-09-03 recon requests
(see `reports/evidence/FR-006/e23-recon-log.md`)". **That file does not exist**, and the probe
scripts it cites are not committed. The test asserts a hand-typed constant against itself.

This matters more than its severity suggests: it is the test that was cited as proving no blocked
source was retried.

Fix: either commit the probe script and its raw log, or reword the docstring to state the log is a
manual transcription and drop the file reference. Do not leave it claiming evidence that is not
there.

### Findings 17, 18, 19, 21, 22 — MINOR and NIT

- **17:** `opportunity/transport.py:165-174` — `urlopen` follows redirects by default, so a 30x
  from an ATS host to any other host is followed with no allowlist check. Install an opener that
  refuses cross-host redirects.
- **18:** `opportunity/manual_sources.py:62-67` lists `hacker_news_who_is_hiring` as `manual_only`
  while the registry has it read-allowed with an adapter bound, contradicting the module docstring.
  Remove it or give it a distinct type.
- **19:** the `freelancer` note says the registry entry was "left as-is"; it was corrected to
  `disabled` on 2026-09-03. Update the note.
- **21:** `docs/SOURCE_EVIDENCE.md` says each 403 host "was requested exactly once";
  `www.reddit.com` received two (robots 200, then the body 403). Reword precisely.
- **22:** quote `source_id` in the registry entry template so `greenhouse:gitlab` does not depend on
  YAML's plain-scalar rule.

## Allowed files

`opportunity/adapters/hacker_news.py` · `opportunity/adapters/__init__.py` ·
`opportunity/discovery/**` · `opportunity/transport.py` · `opportunity/acquisition.py` ·
`opportunity/manual_sources.py` · `opportunity/health.py` · `opportunity/registry.py` ·
`worker/scheduler.py`, `worker/handlers.py` · `recon/**` · `docs/SOURCE_REGISTRY.yaml` ·
`docs/SOURCE_EVIDENCE.md` · tests beside each.

## Frozen — touching any of these is a FAIL

`docs/AGENT_PERMISSIONS.yaml` — council #4 confirmed it byte-identical to baseline and it stays
that way · `truth/**` · `matching/**` · `storage/**` · any migration · `api/**` · `web/**` ·
`private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| E5.1 | `py -3.12 -m unittest opportunity.test_source_policy -v` | `OK`; still zero adapters on a `manual_only`/`disabled` source; zero non-disabled `prepare`/`submit` |
| E5.2 | the registry-gate test for HN | flipping `hacker_news_who_is_hiring` to `read: disabled` makes `fetch_who_is_hiring_payload` **refuse**, not fetch |
| E5.3 | the watchlist test | a watchlist entry with `kind: ashby` **raises**; no `ashby:*` entry can be generated while Ashby is disabled |
| E5.4 | the progress-file tests | a corrupt progress file **raises** instead of returning `{}`; a crash before `save_progress` does not lose a blocked record |
| E5.5 | `py -3.12 -m unittest discover -s opportunity -p "test_*.py" -v` and `discover -s recon` | `OK`, counts stated |
| E5.6 | `py -3.12 -m unittest discover -s worker -p "test_*.py" -v` | `OK`; a 403/429 source is not re-enqueued on a later tick |
| E5.7 | the rate-limiter test | pacing is shared per ATS host across boards **and across jobs**, or the registry template no longer claims it |
| E5.8 | `py -3.12 scripts/check_repository.py` and `check_guard.py --allow-missing-patterns` | both exit 0 |
| E5.9 | `git diff docs/AGENT_PERMISSIONS.yaml` | **empty** |

State in your return, for each of findings 7-22, whether you fixed it, deferred it, or judged it
already correct — and for anything deferred, say why. Report the HN bound-path row count you
actually achieve; if it stays 0, the evidence must say 0.
