# A-23 bounded live production-ingestion evidence

Executed 2026-09-13 from a fresh PostgreSQL database named
`opportunityos_a23_alpha`. Each source was already registered, read-allowed,
and live-probed. `scripts/fr006_a23_live_ingest.py` resolved the dynamically
bound production adapter, called `make_poll_source_handler`, persisted through
the production repository, and evaluated through the production inline seam
against the repository's synthetic founder graph. No private Founder Truth Pack
or fixture response was read.

| Source ID | HTTP/product status | Raw | Unique | Inserted | Persisted | Evaluated | Persisted URL host |
|---|---:|---:|---:|---:|---:|---:|---|
| `greenhouse:ada18` | ok | 9 | 9 | 9 | 9 | 9 | `job-boards.greenhouse.io` |
| `greenhouse:ampsortation` | ok | 17 | 17 | 17 | 17 | 17 | `job-boards.greenhouse.io` |
| `greenhouse:aquaticcapitalmanagement` | ok | 8 | 8 | 8 | 8 | 8 | `job-boards.greenhouse.io` |
| `lever:brilliant` | ok | 4 | 4 | 4 | 4 | 4 | `jobs.lever.co` |
| `lever:demiurgestudios` | ok | 2 | 2 | 2 | 2 | 2 | `jobs.lever.co` |
| `lever:gauntlet` | ok | 6 | 6 | 6 | 6 | 6 | `jobs.lever.co` |
| `lever:teleo` | ok | 11 | 11 | 11 | 11 | 11 | `jobs.lever.co` |
| `lever:vailsys` | ok | 3 | 3 | 3 | 3 | 3 | `jobs.lever.co` |

Result: **8/8 newly registered sources produced real persisted and evaluated
Opportunity rows**. Total rows inserted and evaluated across the bounded set:
60/60. There were zero example/fixture URLs and no 403/429 response.

The governed Hacker News Who-Is-Hiring production path was then run against the
same fresh database with `FR006_LIVE_SOURCE_ID=hacker_news_who_is_hiring` and
`scripts/fr006_live_poll.py`. Result: status `ok`, raw=189, unique=127,
inserted=127, persisted=127, evaluated=127, fixture_rows=0, persisted host
`news.ycombinator.com`. The live production path therefore closes the earlier
0-row measurement.

Reddit remains `BLOCKED_POLICY`/manual-only after the existing single 403 and was
not retried. The permitted freelance manual deep-link alternative remains
`mostaql` and `khamsat`; no source-policy authority was broadened.

Root cause of the previous 0/8 result: the exact-link closure job stopped after
probing and registering live boards. It never invoked the product ingestion,
persistence, or evaluation seam, so its 0/8 was an unexecuted measurement, not
evidence that the registered adapters yielded no rows.
