# BC replay and source decision — 2026-10-01

> This replay report preserves the source and candidate evidence collected on October 1. Its “Remaining work” list records the state at that time and is superseded by [`BC-CLOSURE-LIVE-2026-10-02.md`](BC-CLOSURE-LIVE-2026-10-02.md), which records completion, deployment, and live verification.

## Result

The audited evidence now contains six clean candidates through the corrected BC pipeline, with Founder history preserved. They come from three employers and three source families (Greenhouse, Lever, and Hacker News). This clears the replay supply/diversity gate only; it does not authorize production writes or release. No production rows, projections, schedules, or queue jobs were changed.

## Five candidate audit

| Candidate | Role | Job-specific geography | Credentials | Application route | Founder state | Corrected recommendation |
|---|---|---|---|---|---|---|
| Canonical — Engineering Manager - Data Platform (`greenhouse:canonical:5667860`) | Core data platform | Posting says EMEA / Americas; EMEA explicitly includes Egypt under the Founder policy | No mandatory clearance, license, or certification detected | Greenhouse job page and application form returned HTTP 200 | No feedback, activity, or triage record | For You |
| Canonical — Lead Data Governance Engineer (`greenhouse:canonical:6394147`) | Core data governance | Posting says role is based remotely in EMEA | No mandatory clearance, license, or certification detected | Greenhouse job page returned HTTP 200 and contained the application form | No feedback, activity, or triage record | For You |
| Canonical — MLOps Field Engineer (`greenhouse:canonical:6783943`) | Adjacent MLOps / technical solutions | Posting says worldwide | No mandatory clearance, license, or certification detected | Greenhouse job page and application form returned HTTP 200 | No feedback, activity, or triage record | For You |
| VRChat — Senior Data Scientist (`lever:vrchat:f6d04b6b-8d9f-4261-9d1c-4fbf867d636c`) | Core data science | Lever source-native location is “Anywhere”; public description describes a remote role | No mandatory clearance, license, or certification detected | Public Lever application form returned HTTP 200; no account or payment gate | No feedback, activity, or triage record | For You |
| VRChat — Staff Engineer - Recommendations (`lever:vrchat:93875494-9d42-446d-a069-9c14296e46ed`) | Adjacent data / ML recommendations engineering | Lever source-native location is “Anywhere”; public description describes a remote role | No mandatory clearance, license, or certification detected | Public Lever application form returned HTTP 200; no account or payment gate | No feedback, activity, or triage record | For You |

The five candidates above passed role relevance, geography, credential, access, dedupe, and recommendation checks. A narrow classifier rule now recognizes a generic software title as adjacent only when a Job Overview / Position Overview / The Role block explicitly says the role seeks a data/ML engineer. Company boilerplate alone does not trigger it. Focused replay, parser, and classifier tests now pass: 20 passed, 61 subtests passed.

### LiveKit — Software Engineer, Agents (`hacker_news_who_is_hiring:49570095_software-engineer-agents`)

The existing live Hacker News opportunity `hacker_news_who_is_hiring:49570095` was re-read from the official item endpoint; its comment links this specific LiveKit job and lists `NAMER, EMEA, APJ (Remote)`. The linked current public Ashby page identifies the job as “Software Engineer, Agents,” confirms remote location choices North America, APJ, and EMEA, and describes engineering core abstractions/infrastructure for AI-agent frameworks and LLM-based systems. The application tab loaded publicly and exposed its form without sign-in or payment. It asks applicants whether they are legally authorized in their country of residence and whether sponsorship is required; these are applicant questions, not a posting restriction or mandatory credential. No application was submitted. A read-only Founder-state query for the HN parent found no feedback, activity, or triage rows.

The role was initially classified non-target because the title was a generic software-engineering family. A narrow classifier case now marks only a software/platform/infrastructure engineer role with “Agents” in the title and explicit AI-agent engineering scope as adjacent. A negative test keeps a generic “Software Engineer” title with company-level AI-agent boilerplate non-target. The replay uses a deterministic HN comment + Ashby job identity, keeps the original HN item as the source route, and records the direct public Ashby application route. The HN item response is preserved at `tests/fixtures/bc_hn_livekit_item_49570095_2026-10-01.json` (SHA-256 `D0E8D8B283C771B7A52268F9D11CD190F8C237B4B26DF69073E67E91842241BF`).

Combined deterministic replay result: 6 distinct For You candidates, all 6 role-relevant, Egypt-compatible, credential-clean, and actionable, across Canonical, VRChat, and LiveKit and three independent source families. The combined fixture is `tests/fixtures/bc_clean_candidate_replay_2026-10-01.json`.

Founder history exclusions checked separately and not counted as supply:

- Canonical MLOps & Analytics Manager (`greenhouse:canonical:4810491`): `irrelevant_role`, dismissed.
- Canonical Python/Kubernetes Engineer (`greenhouse:canonical:5703396`): `good_match`, applied/submitted.
- Deeter Analytics ML Engineer (`hacker_news_who_is_hiring:49571280`): already marked applied/submitted.

The candidate evidence is retained in `tests/fixtures/bc_clean_candidate_replay_2026-10-01.json`. The original five-job subset covers Greenhouse and Lever; the verified LiveKit child candidate adds Hacker News as a third contributing family and clears the offline diversity gate.

## Bounded source findings

### Jobicy

The existing first-party public API permission remains valid for the documented API only. The historical September 2 robots.txt 403 remains recorded for that robots path; it does not override the newer API documentation. One request at `2026-10-01T18:49:58Z` to `GET /api/v2/remote-jobs?count=20&geo=emea&industry=data-science` returned seven jobs. Relevant records were tied to Italy, UK, Portugal/Denmark/Spain, France, or Poland. No listing had explicit Egypt-compatible applicant scope. For You contribution: zero. No listing was persisted. Response SHA-256: `a2a43e6a88a5ac2363a805dd83c72373d7fb98426d9b7040302373484ed7e72e`.

First-party policy references: [Jobicy public API documentation](https://jobicy.com/jobs-rss-feed), [Jobicy terms](https://jobicy.com/terms). These describe public no-key API access, preserved attribution/canonical listing links, a 1–200 result bound, and a minimum hourly interval; this execution keeps to a 12-hour interval.

### Remotive

One query at `2026-10-01T18:41:08Z` returned 16 records. AI/data target roles had explicit applicant-location allow-lists that excluded Egypt; no candidate passed all BC gates. No rows were persisted. Response SHA-256: `34f2f1dc4d40760959c4014ba0bfbd2543b1193c1b641543242b0e6b74889591`.

Policy references: [Remotive API](https://remotive.com/remote-jobs/api) and [official API documentation](https://github.com/remotive-com/remote-jobs-api). The public feed requires attribution and observes its published request budget. No additional Remotive query was made.

### Remote OK

One request at `2026-10-01T18:51:25Z` to `GET /api?tags=data,python` returned 68 raw records (67 normalized). Thirteen passed the role relevance classifier; none passed the complete strict geography and verified-access gates. A public Junior Data Analyst listing explicitly required U.S. work authorization. A Data Analyst Assistant listing was remote but had no explicit worldwide/Egypt applicant scope and only a Remote OK tracking route. Neither was counted. No listing was persisted. Response SHA-256: `0d10fc00fc82771a2ea2a5697d5fdc4c96011a6d57ee7caceccba1a41d6daed1`.

Current first-party policy references: [Remote OK FAQ](https://remoteok.com/faq) documents its unauthenticated JSON feed and requires credit plus links to original postings; [Remote OK terms](https://remoteok.com/legal). Registry policy now reflects permitted attributed reads, while this probe contributed zero candidates.

### Other captured evidence

- The Deeter HN comment was recovered from the official Firebase item API and retained, but production Founder history shows it is already Applied/Submitted. The linked Ashby page was not used to override that terminal state.
- The captured AiMi HN comment is a relevant worldwide AI engineering role, but its Join application URL returned HTTP 410; its email fallback is manual-only. It does not count as For You supply.
- The captured WorkHero HN comment names separate engineering roles and says “US + international for engineering.” Its specific Voice AI & Data Infrastructure application page returned HTTP 200 but rendered an empty Ashby job page; the employer careers page showed no other open roles. It is not an actionable survivor. Exact source item retained at `tests/fixtures/bc_hn_workhero_item_49524167_2026-10-01.json` (SHA-256 `4bf5b7d3b50d1f8485259c1e24da7407f344bae00f83d274ee78d71c7e18be1e`).
- We Work Remotely was not used as a new feed: its current [API terms](https://weworkremotely.com/api-terms-and-guidelines) prohibit using WWR data to build a job search service and require applications to remain on WWR. Existing captured WWR records were not converted into a third source contribution.
- Himalayas remains deferred after its previously observed 403. Teamtailor and Workable watchlist requests remain within their documented weekly cadence; no repeat requests were made.

## Remaining work

1. Exercise the new role-specific HN adapter output through the canonical persistence service in a dry-run, then recheck live freshness and capacity before any write. The frozen replay alone does not create production supply.
2. Trigger real branch CI and adjudicate the recorded 12 failures + 18 errors against current `main`; do not call them baseline until CI comparison evidence exists.
3. Before any production write, remeasure database capacity and snapshot Founder state. Keep any canary at five new rows maximum and below the established 398 MiB transaction abort line.
4. No broad source scheduling or full projection refresh; refresh only the validated canary and affected prior For You rows.
