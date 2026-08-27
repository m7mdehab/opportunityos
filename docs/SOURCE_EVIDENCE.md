# SOURCE_EVIDENCE — BRIEF-001

**Run date:** 2026-08-27

## Required numbers

1. **Total raw records fetched:** 2465.

| Source family | Raw records | Unique eligible | Individual-eligible |
|---|---:|---:|---:|
| afdb | 0 | 0 | 0 |
| ashby | 0 | 0 | 0 |
| etimad | 0 | 0 | 0 |
| eu_ted | 0 | 0 | 0 |
| freelancer | 0 | 0 | 0 |
| greenhouse | 2069 | 765 | 0 |
| himalayas | 20 | 3 | 0 |
| jobicy | 0 | 0 | 0 |
| lever | 0 | 0 | 0 |
| remote_ok | 99 | 13 | 0 |
| remotive | 18 | 14 | 0 |
| ungm | 163 | 0 | 0 |
| we_work_remotely | 89 | 36 | 0 |
| world_bank | 7 | 0 | 0 |

2. **Unique records after deduplication:** 2109; **duplicate rate:** 14.4%.
3. **Cross-source overlap:** 0 fingerprints appeared on more than one source.
4. **Egypt-eligible percentage:** withheld pending the mandatory precision audit.
5. **Unclear percentage:** 0.0% (0/2109) stated no geography at all.
6. **Individual-eligible count:** per-source counts are in the table above.

## Source health

| Source | Status | Latency ms | Records | Detail |
|---|---|---:|---:|---|
| himalayas | allowed_ok | 264 | 20 | HTTP 200 parsed records |
| jobicy | robots_unreachable | 0 | 0 | robots.txt could not be read after three attempts |
| remotive | allowed_ok | 343 | 18 | HTTP 200 parsed records |
| remote_ok | allowed_ok | 1062 | 99 | HTTP 200 parsed records |
| we_work_remotely | allowed_ok | 969 | 89 | HTTP 200 parsed records |
| ungm | allowed_ok | 1531 | 163 | HTTP 200 parsed records |
| world_bank | allowed_ok | 219 | 7 | HTTP 200 parsed records |
| eu_ted | http_405 | 280 | 0 | {"message":"Request method 'GET' is not supported","error":null} |
| afdb | http_403 | 172 | 0 | <!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title><meta http-equiv="Content-Type" content="text/html; charset=UTF-8"><meta http-equiv="X-UA-Compatible" content="IE=Edge"><meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scal |
| freelancer | parse_empty | 702 | 0 | HTTP 200 parsed zero records |
| etimad | parse_empty | 578 | 0 | HTTP 200 parsed zero records |
| greenhouse:cloudflare | allowed_ok | 2234 | 311 | HTTP 200 parsed records |
| greenhouse:datadog | allowed_ok | 2046 | 451 | HTTP 200 parsed records |
| greenhouse:duolingo | allowed_ok | 531 | 83 | HTTP 200 parsed records |
| greenhouse:figma | allowed_ok | 1562 | 160 | HTTP 200 parsed records |
| greenhouse:flexport | allowed_ok | 2968 | 161 | HTTP 200 parsed records |
| greenhouse:coinbase | allowed_ok | 750 | 182 | HTTP 200 parsed records |
| greenhouse:hubspot | parse_empty | 202 | 0 | HTTP 200 parsed zero records |
| greenhouse:plaid | http_404 | 219 | 0 | {"status":404,"error":"Job not found"} |
| greenhouse:stripe | allowed_ok | 2000 | 577 | HTTP 200 parsed records |
| greenhouse:twilio | allowed_ok | 812 | 144 | HTTP 200 parsed records |
| lever:coursera | http_404 | 859 | 0 | {"ok":false,"error":"Document not found"} |
| lever:mixpanel | http_404 | 858 | 0 | {"ok":false,"error":"Document not found"} |
| lever:postman | http_404 | 860 | 0 | {"ok":false,"error":"Document not found"} |
| lever:samsara | http_404 | 1030 | 0 | {"ok":false,"error":"Document not found"} |
| lever:sourcegraph | http_404 | 1187 | 0 | {"ok":false,"error":"Document not found"} |
| lever:netlify | http_404 | 1000 | 0 | {"ok":false,"error":"Document not found"} |
| lever:sentry | http_404 | 859 | 0 | {"ok":false,"error":"Document not found"} |
| lever:docker | http_404 | 890 | 0 | {"ok":false,"error":"Document not found"} |
| ashby:notion | robots_unreachable | 0 | 0 | robots.txt could not be read after three attempts |
| ashby:ramp | robots_unreachable | 0 | 0 | robots.txt could not be read after three attempts |
| ashby:webflow | robots_unreachable | 0 | 0 | robots.txt could not be read after three attempts |
| ashby:posthog | robots_unreachable | 0 | 0 | robots.txt could not be read after three attempts |
| ashby:deepl | robots_unreachable | 0 | 0 | robots.txt could not be read after three attempts |
| ashby:openai | robots_unreachable | 0 | 0 | robots.txt could not be read after three attempts |
| ashby:linear | robots_unreachable | 0 | 0 | robots.txt could not be read after three attempts |
| ashby:vanta | robots_unreachable | 0 | 0 | robots.txt could not be read after three attempts |
| ashby:calendly | robots_unreachable | 0 | 0 | robots.txt could not be read after three attempts |

## ATS company watchlist

cloudflare, datadog, duolingo, figma, flexport, coinbase, hubspot, plaid, stripe, twilio, coursera, mixpanel, postman, samsara, sourcegraph, netlify, sentry, docker, notion, ramp, webflow, posthog, deepl, openai, linear, vanta, calendly

The list contains 27 remote-friendly organizations selected for plausibility across data engineering, data science, analytics, and AI engineering. Each was probed only through the named public ATS endpoint; an absent board is recorded as an observed shortfall, not inferred as no hiring.

## Scope and policy

Only unauthenticated HTTP GET requests were made with the truthful `OpportunityOS-SourceRecon/1.1` user agent after a robots.txt check. No accounts, credentials, writes, submissions, retries after a block, or listing fetches from the 16 deliberately skipped platforms were used. Raw responses and normalized rows remain only under ignored `out/`; this report publishes aggregate measurements, not source corpus content.

## What this changes about the plan

This is a one-pass availability measurement, not a validation of the 37-source Phase 1 build-out or the regional-eligibility moat. The measured eligible share and the number of policy-blocked or unreadable routes should determine whether to build any adapter next. It contradicts any assumption that all 37 source families should be implemented before their permitted access and Egypt eligibility are measured.
