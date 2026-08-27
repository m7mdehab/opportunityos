# SOURCE_EVIDENCE — BRIEF-001

**Run date:** 2026-08-27

## Required numbers

1. **Total raw records fetched:** 2161.

| Source family | Raw records | Unique eligible | Individual-eligible |
|---|---:|---:|---:|
| afdb | 0 | 0 | 0 |
| ashby | 0 | 0 | 0 |
| etimad | 0 | 0 | 0 |
| eu_ted | 0 | 0 | 0 |
| freelancer | 0 | 0 | 0 |
| greenhouse | 2062 | 415 | 0 |
| himalayas | 0 | 0 | 0 |
| jobicy | 0 | 0 | 0 |
| lever | 0 | 0 | 0 |
| remote_ok | 99 | 4 | 0 |
| remotive | 0 | 0 | 0 |
| ungm | 0 | 0 | 0 |
| we_work_remotely | 0 | 0 | 0 |
| world_bank | 0 | 0 | 0 |

2. **Unique records after deduplication:** 1829; **duplicate rate:** 15.4%.
3. **Cross-source overlap:** 0 fingerprints appeared on more than one source.
4. **Egypt-eligible:** 419/1829 (22.9%). Per-source counts are in the table above.
5. **Unclear percentage:** 58.8% (1076/1829) stated no geography at all.
6. **Individual-eligible count:** per-source counts are in the table above.

## Source health

| Source | Status | Latency ms | Records | Detail |
|---|---|---:|---:|---|
| himalayas | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| jobicy | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| remotive | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| remote_ok | http_200 | 843 | 99 | parseable response |
| we_work_remotely | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| ungm | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| world_bank | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| eu_ted | http_405 | 297 | 0 | {"message":"Request method 'GET' is not supported","error":null} |
| afdb | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| freelancer | http_200 | 687 | 0 | parseable response |
| etimad | http_200 | 952 | 0 | parseable response |
| greenhouse:cloudflare | http_200 | 1812 | 309 | parseable response |
| greenhouse:datadog | http_200 | 2250 | 450 | parseable response |
| greenhouse:duolingo | http_200 | 609 | 83 | parseable response |
| greenhouse:figma | http_200 | 735 | 159 | parseable response |
| greenhouse:flexport | http_200 | 1265 | 160 | parseable response |
| greenhouse:coinbase | http_200 | 843 | 182 | parseable response |
| greenhouse:hubspot | http_200 | 202 | 0 | parseable response |
| greenhouse:plaid | http_404 | 202 | 0 | {"status":404,"error":"Job not found"} |
| greenhouse:stripe | http_200 | 1702 | 578 | parseable response |
| greenhouse:twilio | http_200 | 889 | 141 | parseable response |
| lever:coursera | http_404 | 875 | 0 | {"ok":false,"error":"Document not found"} |
| lever:mixpanel | http_404 | 4469 | 0 | {"ok":false,"error":"Document not found"} |
| lever:postman | http_404 | 858 | 0 | {"ok":false,"error":"Document not found"} |
| lever:samsara | http_404 | 2187 | 0 | {"ok":false,"error":"Document not found"} |
| lever:sourcegraph | http_404 | 875 | 0 | {"ok":false,"error":"Document not found"} |
| lever:netlify | http_404 | 1047 | 0 | {"ok":false,"error":"Document not found"} |
| lever:sentry | http_404 | 875 | 0 | {"ok":false,"error":"Document not found"} |
| lever:docker | http_404 | 875 | 0 | {"ok":false,"error":"Document not found"} |
| ashby:notion | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| ashby:ramp | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| ashby:webflow | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| ashby:posthog | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| ashby:deepl | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| ashby:openai | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| ashby:linear | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| ashby:vanta | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |
| ashby:calendly | blocked_robots | 0 | 0 | robots.txt unavailable or disallows the truthful client |

## ATS company watchlist

cloudflare, datadog, duolingo, figma, flexport, coinbase, hubspot, plaid, stripe, twilio, coursera, mixpanel, postman, samsara, sourcegraph, netlify, sentry, docker, notion, ramp, webflow, posthog, deepl, openai, linear, vanta, calendly

The list contains 27 remote-friendly organizations selected for plausibility across data engineering, data science, analytics, and AI engineering. Each was probed only through the named public ATS endpoint; an absent board is recorded as an observed shortfall, not inferred as no hiring.

## Scope and policy

Only unauthenticated HTTP GET requests were made with the truthful `OpportunityOS-SourceRecon/1.1` user agent after a robots.txt check. No accounts, credentials, writes, submissions, retries after a block, or listing fetches from the 16 deliberately skipped platforms were used. Raw responses and normalized rows remain only under ignored `out/`; this report publishes aggregate measurements, not source corpus content.

## What this changes about the plan

This is a one-pass availability measurement, not a validation of the 37-source Phase 1 build-out or the regional-eligibility moat. The measured eligible share and the number of policy-blocked or unreadable routes should determine whether to build any adapter next. It contradicts any assumption that all 37 source families should be implemented before their permitted access and Egypt eligibility are measured.
