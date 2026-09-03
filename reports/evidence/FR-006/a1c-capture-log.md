# A1C capture log

Work order: `reports/evidence/FR-006/orders/A1C-corpus.md`. All fetches went through the
existing `opportunity.registry.SourceRegistry` preflight and `opportunity.transport.HttpTransport`
/ `AcquisitionService` — no other network path was used, and no custom (browser-like)
`User-Agent` was set; the transport's default `OpportunityOS-Recon/1.0` header was used as-is.

## What "payload" means here (assumption, named)

The order requires ">= 200 real raw payloads ... with employer names intact" across "at least
six distinct sources", and separately requires per-payload work-mode/location/qualification
metrics. A single feed request per source (e.g. one Greenhouse board fetch) returns *one* HTTP
response containing many job postings, not 200 distinct ones. I read "payload" as **one
posting**, matching the granularity the metrics (work-mode share, adapter/inference split,
qualification decision) are computed over.

Each fixture file is `{"source_id", "request_url", "fetched_at", "raw_body"}`, where
`raw_body` is the **real, unmodified job/posting record** returned by the source, wrapped in
the minimal feed envelope its own (frozen, unmodified) adapter's `parse_payload` expects
(e.g. `{"jobs": [job]}` for Greenhouse/Himalayas/Remotive, `[job]` for Lever/RemoteOK, a
single-`<item>` `<rss><channel>...</channel></rss>` for We Work Remotely). This keeps every
fixture independently re-parseable by the adapters that already own that code, and every
record inside it is exactly what the source returned — nothing was edited, reworded, or
filtered by content.

## Capture run (A1C.1) — raw output

One HTTP GET per registered, read-allowed source with an adapter (`get_all_standard_adapters()`
minus UNGM/World Bank/EU TED — see "Sources not attempted" below):

```
=== CAPTURE RESULT ===
total_payloads=2740
distinct_sources=15
--- per-source counts ---
greenhouse:affirm: 202
greenhouse:airbnb: 170
greenhouse:cloudflare: 323
greenhouse:coinbase: 187
greenhouse:datadog: 444
greenhouse:duolingo: 89
greenhouse:figma: 158
greenhouse:flexport: 172
greenhouse:stripe: 601
greenhouse:twilio: 141
himalayas: 20
lever:shyftlabs: 23
remote_ok: 100
remotive: 17
we_work_remotely: 93
--- stopped (403/429/anti-bot, not retried) ---
--- errors (non-stop) ---
{'source_id': 'lever:ryz_labs', 'reason': 'status=404 error=HTTP 404: Not Found'}
```

**403/429/CAPTCHA/MFA/anti-bot outcomes: none.** No source returned 403, 429, or any
anti-bot/CAPTCHA/MFA marker on its single request in this session, so nothing was stopped and
nothing was retried (there is nothing to list in that category).

**Non-stop error:** `lever:ryz_labs` returned `404 Not Found` on its one registered feed URL
(`https://api.lever.co/v0/postings/ryz_labs?mode=json`) — the board token in
`docs/SOURCE_REGISTRY.yaml`/`opportunity/adapters/__init__.py` does not currently resolve on
Lever's public API. This is not a 403/429/anti-bot signal, so the never-retry rule does not
apply to it as a policy matter, but I did not retry it either (single attempt only, as for
every other source). It is excluded from the corpus. `lever:shyftlabs` succeeded (23 postings).

**Sources not attempted:** UNGM, World Bank, and EU TED were left out of this capture run.
UNGM/World Bank return HTML/XML shapes I did not have turn budget to read and split safely
without risking a mis-parse being mistaken for a captured "payload"; EU TED is POST-only under
ADR-0005 and the standing constitution restricts it to `READ_ONLY_QUERY` with a specific search
body I did not have budget to construct correctly. Skipping them is a named assumption, not a
policy refusal — the six-source requirement is already satisfied without them (15 distinct
`source_id`s captured). A later order can add them.

## Committed corpus after truncation (A1C.2)

2740 payloads is far more raw HTML/JSON than a fixture corpus needs and would have added ~34MB
to the repository. I truncated each source's *already-written* fixture files to the first 40
(by original API return order — a positional cut, not a content-based selection) without any
further network access, keeping every source's real ordering intact. Sources that returned
fewer than 40 postings (`himalayas`, `remotive`, `lever:shyftlabs`) are kept in full. This is
disclosed here, not hidden, and it was applied uniformly before any metric was computed — it is
not "selecting payloads to improve a downstream number."

```
greenhouse_affirm 40
greenhouse_airbnb 40
greenhouse_cloudflare 40
greenhouse_coinbase 40
greenhouse_datadog 40
greenhouse_duolingo 40
greenhouse_figma 40
greenhouse_flexport 40
greenhouse_stripe 40
greenhouse_twilio 40
himalayas 20
lever_shyftlabs 23
remote_ok 40
remotive 17
we_work_remotely 40
TOTAL 540
```

Committed corpus: **540 payloads across 15 distinct sources** (>= 200, >= 6 required). The
Cloudflare Greenhouse board is present with 40 postings, including multiple "Senior Customer
Engineer" listings (verified: `opportunity/fixtures/corpus/greenhouse_cloudflare/004.json`,
`022.json`, `023.json`, `024.json`, `025.json`, `029.json`, `030.json` all match
`grep -i "customer engineer"`), which A2 needs.

## Mirror check (A1C.5)

Mechanism checked: `.mirror-allowlist` (fnmatch allowlist), as enforced by
`scripts/check_guard.py --mirror-only`. `opportunity/fixtures/corpus/**` and
`opportunity/fixtures/__init__.py` match none of the patterns in `.mirror-allowlist`
(`docs/**`, `briefs/**`, `reports/**`, `AGENTS.md`, `.codex/**`, `scripts/**`, `recon/**`,
`.github/workflows/**`, `.github/pii-patterns.txt`, `.mirror-allowlist`) — confirmed
programmatically with `fnmatch.fnmatchcase` against every pattern, and confirmed via
`py -3.12 scripts/check_guard.py --mirror-only --allow-missing-patterns` (exit 0; the corpus
files are excluded from the mirrored-file set it scans). Note `scripts/corpus_metrics.py` and
this log file ARE inside `scripts/**` / `reports/**` respectively and so ARE mirrored — that is
expected and fine, since neither contains raw payload bodies.

## Coverage numbers (A1C.3)

`work_mode`, `location_country`, `remote_scope`, and `work_mode_source` do not exist on
`Opportunity` on this worktree — they are added by the concurrent work order A1
(`reports/evidence/FR-006/orders/A1-extract.md`), which had not merged into this branch at
capture time. `scripts/corpus_metrics.py` reports this explicitly for each of those metrics
("NOT AVAILABLE ... re-run after A1's extraction change is merged") instead of printing a
fabricated 0%. See the full raw output pasted under acceptance row A1C.3 in the return.

The qualification-decision "before" distribution does not depend on A1's new fields (it runs
the current, unmodified `matching.qualification.QualificationEngine` over an empty
`TruthGraph`) and was computed for real over the 540-payload corpus:

- `qualified`: 33/540 (6.1%)
- `ineligible`: 405/540 (75.0%)
- `uncertain`: 102/540 (18.9%)

The "after" distribution needs A1's qualifier change (`matching/qualification.py`, frozen for
this order) and is not computable here; the script says so explicitly and names
`scripts/corpus_metrics.py` as the re-run point once A1 is integrated.
