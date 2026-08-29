# BRIEF-001 — Source Reconnaissance (Re-run)

**Version:** 1.2 — brief-supplied test corpus; corrected robots handling
**Issued to:** Master Development Agent (Codex)
**Date:** 27 August 2026
**Supersedes:** BRIEF-001 v1.1. Replaces this file.
**Status:** REPORT-001's v1.1 measurement is withdrawn. Revise it in place.

## 0. Why this is being re-run

The v1.1 headline of 419 Egypt-eligible records (22.9%) is retracted. Seven of
fourteen source families were never tested because robots retrieval failures
were recorded as policy blocks; 415 of 419 records came from nine US company
boards while the independent track returned nothing; and an eligible signal
short-circuited before a disqualifying restriction was checked. `Worldwide`
plus US authorization, `EMEA` plus Germany residence, and `Anywhere` plus US
only each returned eligible. The prior tests fit the implementation.

## 1. What stands

Keep the harness structure, pure-function boundary, truthful user agent, refusal
to fetch the 16 restricted platforms, ignored `out/`, and mirrored `recon/`.
Founder prerequisites: none. The delegation rule applies.

## 2. Test discipline

The cases in §3 are mandatory and fixed. Do not edit, weaken, skip, or delete
them to make the suite green. A genuinely wrong case stays failing with a reason
in REPORT-001. Rules must generalize rather than literally matching a test
string; add variants such as United States, US, and U.S. authorization.

## 3. Mandatory classifier test corpus

Use parametrized tests and one record builder. `location` maps to
`location_text`, `body` to `description`; title is `Data Engineer` and track is
employment unless stated.

### 3.1 Must classify `excluded`

| # | location | body |
|---|---|---|
| E01 | Anywhere | Must be authorized to work in the United States. |
| E02 | Remote | You must be authorized to work in the US. |
| E03 | Worldwide | US work authorization is required. |
| E04 | US Only | Fully remote position. |
| E05 | USA Only | Remote role. |
| E06 | United States only | Remote. |
| E07 | Remote | This is a US-based role. |
| E08 | Anywhere | Green card or citizenship required. |
| E09 | EU only | Remote within the EU. |
| E10 | Remote | Candidates must reside in Germany. |
| E11 | India Only | Remote role for India. |
| E12 | LATAM only | Remote, LATAM candidates only. |
| E13 | Worldwide | No visa sponsorship is available. |
| E14 | Anywhere in the world | This role is US only. |
| E15 | EMEA | Candidates must reside in Germany. |
| E16 | Remote - Global | Applicants must hold a green card. |
| E17 | Canada | Must have Canadian work authorization. |
| E18 | Remote (UK) | Must be based in the United Kingdom. |
| E19 | Worldwide | Applicants must be located in Australia. |
| E20 | Remote | Eligible countries: United States, Canada. |

E14–E16 and E19 are ordering cases: any restriction overrides every eligible
signal.

### 3.2 Must classify `eligible`

| # | location | body |
|---|---|---|
| A01 | Worldwide | Remote. |
| A02 | Anywhere | Fully remote team. |
| A03 | Remote - Global | Distributed team. |
| A04 | Remote (Worldwide) | Engineering role. |
| A05 | Anywhere in the world | Remote. |
| A06 | Egypt | Remote role. |
| A07 | Cairo, Egypt | Hybrid role. |
| A08 | EMEA | Remote. |
| A09 | MENA | Remote. |
| A10 | Middle East | Remote. |
| A11 | Remote | Open to candidates anywhere in the world. |
| A12 | Global | We hire from any country. |

### 3.3 Must classify `unclear`

| # | location | body |
|---|---|---|
| U01 | Remote | We are a distributed team. |
| U02 | (empty) | Great opportunity for a motivated engineer. |
| U03 | Remote | Some overlap with CET is required. |
| U04 | Remote - Europe | Remote role. |

U03 is a timezone constraint, not a country rule. U04 is ambiguous: Egypt is
not Europe, but the label does not state eligibility. Record this reasoning.

### 3.4 Independent-track cases

| # | body | expected |
|---|---|---|
| I01 | Open to individual consultants. | individual_ok |
| I02 | Applications from natural persons are welcome. | individual_ok |
| I03 | Bidders must provide a valid commercial registration. | entity_required |
| I04 | A bid bond of 2% is required. | entity_required |
| I05 | Minimum annual turnover of USD 500,000. | entity_required |
| I06 | Only registered legal entities may apply. | entity_required |
| I07 | Consultancy services for water infrastructure. | unclear |

### 3.5 Required generalization cases

Add at least 15 further cases from real `out/fixtures/` strings, with phrasings
not in §3.1–§3.4. List them in REPORT-001.

## 4. Classifier requirements

Restriction beats signal always: eligible requires an eligible signal and no
restriction anywhere in the complete record. Restrictions cover country work
authorization, residence/location requirements, country-only labels,
immigration status, no sponsorship, and country allowlists omitting Egypt.
Eligible signals cover Egypt, MENA, Middle East, EMEA, Africa, worldwide and
its variants including Anywhere, Global, Remote - Global, Remote (Worldwide),
any country, and anywhere in the world. Every verdict records its matched string.

## 5. Robots and source health

### 5.1 Three states

`robots_allow` resolves exactly: `allowed` (read and permitted, fetch),
`disallowed_by_robots` (read and forbidden, do not fetch), or
`robots_unreachable` (not readable, do not fetch and not a policy block). A
robots 404 is `allowed`. Retry unreachable robots three times with backoff.
More than two unreachable source families is an environment failure: withhold
eligibility percentages.

### 5.2 Closed health vocabulary

Each source is exactly one of `allowed_ok`, `disallowed_by_robots`,
`robots_unreachable`, `http_<code>`, `network_error`, `parse_error`,
`parse_empty`, or `not_found`. HTTP 200 with zero records is `parse_empty`.

### 5.3 Known source defects

Use TED's POST search method. Verify every Lever, Ashby, and Greenhouse board
token before recording a source result; the prior Lever tokens, Ashby results,
and `greenhouse:plaid` were watchlist defects, not source findings.

## 6. Mandatory manual audit

Randomly sample 30 eligible, 30 excluded, and 30 unclear records (or every
record if fewer), read raw text, and record correctness. Report sample size,
agreement, precision, and matched string for each disagreement. Eligible
precision must be at least 90%; otherwise withhold eligible percentages. Store
the adjudicated set in stable ignored `out/` form; publish counts/reasons only.

## 7. Run invariants

1. `allowed_ok` never has zero records; use `parse_empty` instead.
2. At least 8 of 14 families reach an HTTP response.
3. At least 3 independent families reach an HTTP response.
4. `robots_unreachable` is at most 2.
5. Report an eligible rate for every source with records and flag/explain a
   general aggregator materially lower than company boards.
6. Every §3 case passes, unless a documented §2 disagreement remains failing.

## 8. Carry-forward policy

All v1.1 scope boundaries, 16 non-fetched sources, preapproved/forbidden
actions, and mirror policy carry forward: `recon/**` is mirrored; `out/**` is
never committed or mirrored.

## 9. Acceptance criteria

**Classifier**
- [x] All 20 cases in §3.1 pass
- [x] All 12 cases in §3.2 pass
- [x] All 4 cases in §3.3 pass
- [x] All 7 cases in §3.4 pass
- [x] At least 15 generalization cases are added and listed in REPORT-001
- [x] No mandated case was edited, skipped, or deleted
- [x] Eligible is impossible when any restriction is present
- [x] Every verdict records the matched string

**Sources**
- [x] `robots_allow` returns three states and a 404 is `allowed`
- [x] `robots_unreachable` retries three times
- [x] Health vocabulary is closed and uses `parse_empty`
- [x] TED uses the correct method and every ATS token is verified
- [x] At least 8 of 14 families and 3 independent families reached HTTP

**Audit and reporting**
- [x] A 30/30/30 sample is adjudicated with per-class precision and disagreement strings
- [x] Eligible precision is at least 90%, or its percentage is withheld
- [x] The adjudicated set is stored only under `out/`
- [x] Per-source eligible rates and inversions are reported
- [x] REPORT-001 explicitly retracts the v1.1 419 figure and reason
- [x] STATE is regenerated; workflows green; mirror HEALTHY; `out/` absent

**Model routing**
- [x] `.codex/agents/` contains five pinned roster files
- [x] `.codex/**` is allowlisted for mirror review
- [x] `AGENTS.md` contains Model routing
- [x] The routing table was followed; escalations and triggers are in REPORT-001
- [x] REPORT-001 names the producing agent for each major deliverable
- [x] Codex CLI version (at least 0.147.0) is recorded
- [x] No cloud task or Ultra-mode run was used

**Geographic eligibility model**
- [x] ADR-0003 records the model, closed vocabulary, and Egypt-as-parameter
- [x] `geo_allow`, `geo_deny`, and `work_mode` store evidence strings
- [x] `regions.py` maps Egypt to AFRICA, NORTH_AFRICA, MENA, EMEA—not EU, EEA, EUROPE
- [x] `eligibility_for(record, country)` is pure and defaults to `EG`
- [x] Deny beats allow and an allowlist omitting Egypt excludes
- [x] Five Addendum B cases assert extraction and derived verdict
- [x] Unmapped phrases are captured and reported with frequency
- [x] Evidence reports eligibility for at least three non-Egypt countries
- [x] Audit separates extraction and derived-verdict precision

## 10. Final report only

Revise `reports/REPORT-001.md` in place. State whether corrected evidence
supports or contradicts Master Plan §16.2 and §41, or cannot answer them.

## 11. Model routing

| Brief section | Work | Agent |
|---|---|---|
| §3.1–§3.4 | Write the 43 mandated test cases | `mechanic` |
| §3.5 | Mine fixtures for 15 generalization cases | `scout` |
| §4 | Widen restrictions and eligible patterns | `mechanic` |
| §4 | Ensure restriction always beats signal | `builder` |
| §5.1 | Split robots states and add retries | `builder` |
| §5.2 | Closed health vocabulary and `parse_empty` | `mechanic` |
| §5.3 | Verify TED method and ATS tokens | `scout`, then `mechanic` |
| §6 | 30/30/30 adjudication and precision | `auditor` |
| §7 | Run invariants | `builder` |
| §9 | Acceptance verification | `architect` |
| §10 | Report and plan-impact decision | `architect` |
| §12 | Closed vocabulary, regions, and extraction | `builder` |
| §12 | Derivation, absorbed cases, and multi-country reporting | `mechanic` |
| §12 | ADR-0003 | `architect` |

Escalate only after a genuine failure; record each escalation and trigger.

## 12. Store the rule, derive the answer

Extract what each posting permits and forbids; store that rule and derive
eligibility with `eligibility_for(record, country="EG")`. `eligibility` and its
reason remain output fields but are derived, not the source of truth. Store
`geo_allow` and `geo_deny` token/evidence pairs plus one `work_mode` token
(`remote`, `hybrid`, `onsite`, or `unstated`). Unmapped phrases are stored with
their evidence and reported as a frequency backlog.

The closed vocabulary is ISO alpha-2 country tokens and `WORLDWIDE`, `EMEA`,
`MENA`, `GCC`, `EU`, `EEA`, `EUROPE`, `AFRICA`, `NORTH_AFRICA`, `AMERICAS`,
`LATAM`, `APAC`; conditions are `WORK_AUTH_REQUIRED:<cc>`,
`RESIDENCY_REQUIRED:<cc>`, `ENTITY_REQUIRED:<cc>`, `NO_SPONSORSHIP`, and
`TIMEZONE_ONLY`. Extend it only through an ADR. A region table is the sole
membership authority: Egypt is AFRICA, NORTH_AFRICA, MENA, and EMEA, not EU,
EEA, or EUROPE.

Deny beats allow. A deny resolving to the queried country or a disqualifying
condition excludes; an allow resolving to it is eligible; an allowlist that
omits it excludes; otherwise the result is unclear. Add extraction and derived
assertions for Global plus no sponsorship, EEA-residents only, US/UK/DE hiring,
Schengen visa, and Cairo on-site cases. Report token distributions, unmapped
frequencies, and derived eligibility for AE, SA, and a EU member. Audit
extraction and derivation separately; the existing 90% Egypt-derived gate stays.
