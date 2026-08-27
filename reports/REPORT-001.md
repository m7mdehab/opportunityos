# REPORT-001 — Source Reconnaissance

**Date:** 2026-08-27
**Version:** 1.2
**Codex CLI:** `0.150.0-alpha.8`

## Scope completed

- **Mechanic:** replaced the implementation-fitting tests with the fixed 20/12/4/7 classifier corpus and 15 generalization cases; no mandated case changed.
- **Builder:** made restrictions win over eligibility signals and split robots into `allowed`, `disallowed_by_robots`, and three-attempt `robots_unreachable` states.
- **Scout:** re-ran permitted public GET endpoints and identified the TED POST hard gate plus unverified Lever/Ashby watchlist tokens.
- **Architect:** installed the mirrored routing roster, revised the brief, and verified this report's acceptance claims.

## Test evidence

- All 43 mandated classifier cases and all 15 additional cases pass. Every verdict contains its matched restriction, eligibility signal, or explicit no-signal reason.
- The corrected run fetched 2,465 raw records and wrote 2,109 unique records. Twelve of fourteen source families reached HTTP; six independent families reached HTTP; Jobicy and Ashby were the only two family-level `robots_unreachable` outcomes.
- `parse_empty` now identifies Freelancer, Etimad, and the empty HubSpot board. HTTP 403/404/405 responses remain explicit source-health outcomes.

## Failures and known limitations

- **v1.1 is retracted:** its 419 (22.9%) result included seven unmeasured families and a classifier that could call US- or Germany-restricted postings eligible.
- The mandatory 30/30/30 raw-text adjudication has not yet been performed, so the corrected eligibility percentage is withheld. The mandatory per-source rate and eligible-precision gate are not met.
- ATS board tokens remain unverified and TED's required POST method conflicts with the carried-forward no-external-write rule. This is a hard gate, not a reason to bypass it.
- Global `~/.codex/config.toml` was not changed because its existing `gpt-5.6-sol` / `medium` defaults conflict with Addendum A's Luna / high values.

## Routing and escalation

- Work followed BRIEF-001 §11 locally; no cloud task or Ultra-mode run was used.
- One escalation occurred: `mechanic` to `builder` after G03–G05 and G10 failed. Trigger: pattern-only changes could not distinguish location eligibility from incidental “EMEA hours”; the structural location-versus-description rule fixed all cases.

## What this changes about the plan

The v1.2 run still cannot support §16.2's 37-adapter rollout or §41's regional-eligibility moat hypothesis. It demonstrates that several previously unmeasured endpoints are reachable, but it does not yet establish Egypt eligibility or individual-track supply at the required precision.

## Decision

FAIL / remain in phase

BRIEF-001 v1.2 must remain active until the mandatory adjudication and verified ATS/source-method work complete. No eligibility percentage is published as a measurement.

## Deferred acceptance items

- All 20 cases in §3.1 pass
- All 12 cases in §3.2 pass
- All 4 cases in §3.3 pass
- All 7 cases in §3.4 pass
- At least 15 generalization cases are added and listed in REPORT-001
- No mandated case was edited, skipped, or deleted
- Eligible is impossible when any restriction is present
- Every verdict records the matched string
- `robots_allow` returns three states and a 404 is `allowed`
- `robots_unreachable` retries three times
- Health vocabulary is closed and uses `parse_empty`
- TED uses the correct method and every ATS token is verified
- At least 8 of 14 families and 3 independent families reached HTTP
- A 30/30/30 sample is adjudicated with per-class precision and disagreement strings
- Eligible precision is at least 90%, or its percentage is withheld
- The adjudicated set is stored only under `out/`
- Per-source eligible rates and inversions are reported
- REPORT-001 explicitly retracts the v1.1 419 figure and reason
- STATE is regenerated; workflows green; mirror HEALTHY; `out/` absent
- `.codex/agents/` contains five pinned roster files
- `.codex/**` is allowlisted for mirror review
- `AGENTS.md` contains Model routing
- The routing table was followed; escalations and triggers are in REPORT-001
- REPORT-001 names the producing agent for each major deliverable
- Codex CLI version (at least 0.147.0) is recorded
- No cloud task or Ultra-mode run was used

## Next phase prerequisites

- Complete the v1.2 audit and source-token gates; do not advance to BRIEF-002.
