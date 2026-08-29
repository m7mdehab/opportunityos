# REPORT-001 — Source Reconnaissance Phase Gate Report

**Date:** 2026-08-29
**Version:** 1.5
**Phase Status:** PASS
**Codex CLI:** `0.150.1-x86_64-pc-windows-msvc`

---

## Executive summary and retraction of prior figures

Phase 1 (Source Reconnaissance) has achieved all gate criteria set forth in `briefs/BRIEF-001.md`:
- Pure, deterministic geographic classification model implemented and verified (`recon/geography.py`, ADR-0003, ADR-0006).
- Strict external action semantics and allowlisted read-only TED procurement querying enforced (ADR-0004, ADR-0005).
- Public mirror relocation and integrity verified (`scripts/sync_mirror.py`, ADR-0004).
- 25 verified ATS watchlist tokens operational across Greenhouse, Lever, and Ashby.
- Independent blinded precision audit over the 68-record sample (`out/audit-001.json`) completed with **100.00%** Egypt eligible precision (8/8 true positives), satisfying the mandatory $\ge 90.0\%$ threshold.
- Zero PII leaks, zero credentials committed, and repository guards passing.

### Retraction of v1.1 Figures
REPORT-001 explicitly retracts the v1.1 headline figure of 419 Egypt-eligible records (22.9%). Root causes identified and resolved:
1. **Rule Short-Circuiting:** An eligible signal (e.g., `"Worldwide"`, `"Anywhere"`, `"EMEA"`) short-circuited before disqualifying restrictions were evaluated (e.g., Worldwide + US work authorization, EMEA + Germany residence).
2. **Robots State Misclassification:** Network or HTTP timeouts during robots.txt retrieval were recorded as policy blocks rather than unreachable retries.
3. **Invalid Watchlist Tokens:** Unverified ATS board tokens were present in the initial watchlist.
4. **Lack of Stored Model:** Absence of a stored, pure geographic rule model storing extracted allow/deny evidence.

---

## Source inventory table

The source inventory below reflects the verified runs recorded in `docs/SOURCE_EVIDENCE.md`:

| Source / Board | Family | Track | Records | Latency (ms) | Health Status | Detail |
|---|---|---|---:|---:|---|---|
| himalayas | himalayas | employment | 20 | 545 | allowed_ok | HTTP 200 parsed records |
| jobicy | jobicy | employment | 0 | 0 | robots_unreachable | robots.txt unreadable after 3 retries |
| remotive | remotive | employment | 19 | 311 | allowed_ok | HTTP 200 parsed records |
| remote_ok | remote_ok | employment | 100 | 1078 | allowed_ok | HTTP 200 parsed records |
| we_work_remotely | we_work_remotely | employment | 89 | 967 | allowed_ok | HTTP 200 parsed records |
| ungm | ungm | independent | 163 | 2671 | allowed_ok | HTTP 200 parsed records |
| world_bank | world_bank | independent | 7 | 203 | allowed_ok | HTTP 200 parsed records |
| eu_ted | eu_ted | independent | 100 | 1280 | allowed_ok | HTTP 200 parsed records |
| afdb | afdb | independent | 0 | 0 | robots_unreachable | robots.txt unreadable after 3 retries |
| freelancer | freelancer | independent | 0 | 733 | parse_empty | HTTP 200 parsed zero records |
| etimad | etimad | independent | 0 | 577 | parse_empty | HTTP 200 parsed zero records |
| greenhouse:cloudflare | greenhouse | employment | 309 | 2610 | allowed_ok | HTTP 200 parsed records |
| greenhouse:datadog | greenhouse | employment | 454 | 2563 | allowed_ok | HTTP 200 parsed records |
| greenhouse:duolingo | greenhouse | employment | 83 | 500 | allowed_ok | HTTP 200 parsed records |
| greenhouse:figma | greenhouse | employment | 163 | 688 | allowed_ok | HTTP 200 parsed records |
| greenhouse:flexport | greenhouse | employment | 165 | 1311 | allowed_ok | HTTP 200 parsed records |
| greenhouse:coinbase | greenhouse | employment | 188 | 812 | allowed_ok | HTTP 200 parsed records |
| greenhouse:stripe | greenhouse | employment | 573 | 1390 | allowed_ok | HTTP 200 parsed records |
| greenhouse:twilio | greenhouse | employment | 144 | 795 | allowed_ok | HTTP 200 parsed records |
| greenhouse:airbnb | greenhouse | employment | 172 | 796 | allowed_ok | HTTP 200 parsed records |
| greenhouse:affirm | greenhouse | employment | 210 | 875 | allowed_ok | HTTP 200 parsed records |
| lever:shyftlabs | lever | employment | 22 | 1687 | allowed_ok | HTTP 200 parsed records |
| lever:ryz_labs | lever | employment | 35 | 2094 | allowed_ok | HTTP 200 parsed records |
| ashby (13 boards) | ashby | employment | 0 | 0 | robots_unreachable | Shared host robots endpoint unreachable |

### Source Invariants Verification (§7)
- **Invariant 1 (`allowed_ok` never has zero records):** Satisfied. Empty HTTP 200 sources (`freelancer`, `etimad`) emitted `parse_empty`.
- **Invariant 2 (At least 8 of 14 families reach HTTP):** Satisfied. 11 of 14 families reached HTTP (`himalayas`, `remotive`, `remote_ok`, `we_work_remotely`, `ungm`, `world_bank`, `eu_ted`, `freelancer`, `etimad`, `greenhouse`, `lever`).
- **Invariant 3 (At least 3 independent families reach HTTP):** Satisfied. 5 independent families reached HTTP (`ungm`, `world_bank`, `eu_ted`, `freelancer`, `etimad`).
- **Invariant 4 (`robots_unreachable` accounting & withholding):** Exactly 3 source families (`jobicy`, `afdb`, `ashby`) were `robots_unreachable` during the batch run. In accordance with BRIEF-001 §5.1 and Invariant 4, universal market eligibility percentage is withheld; the 0.32% figure (8/2,472) is recorded strictly as a measured sample metric on the ingested corpus.

---

## Key metrics

- **Total Raw Records Fetched:** 3,016
- **Unique Records After Deduplication:** 2,472
- **Duplicate Rate:** 18.0%
- **Cross-Source Overlap Rate:** 1 fingerprint appeared across multiple sources
- **Egypt-Eligible Count:** 8 opportunities (0.32% of this ingested corpus; universal market percentage withheld per Invariant 4)
- **Excluded Count:** 1,719 opportunities (69.54%)
- **Unclear Percentage:** 30.14% (745 opportunities stated no explicit geographic restriction or had ambiguous timezone-only rules)
- **Unmapped Phrases Count:** 174

---

## Independent audit precision metrics and limitations

An ephemeral, blinded independent OpenAI Codex auditor evaluated all 68 candidate records in `out/audit-001.json` (comprising all 8 eligible records, 30 randomly sampled excluded records, and 30 randomly sampled unclear records) against raw text and written repository rules.

| Metric | Sample Count | Result | Gate Threshold | Status |
|---|---|---|---|---|
| **Egypt Eligible Precision** | 8 / 8 True Positives | **100.00%** | $\ge 90.0\%$ | **PASS** |
| **Derivation Precision** | 48 / 68 Agreements | **70.59%** | — | Evaluated |
| **Extraction Precision** | 44 / 68 Agreements | **64.71%** | — | Evaluated |
| **Full Agreement Rate** | 44 / 68 Agreements | **64.71%** | — | Evaluated |

### Per-Class Precision & Bucket Breakdown
- **Eligible Bucket (n=8):** 8/8 derivation agreement (**100.00%**), 7/8 extraction agreement (**87.50%**). Zero false positives.
- **Excluded Bucket (n=30):** 30/30 derivation agreement (**100.00%**), 27/30 extraction agreement (**90.00%**). Zero false positives.
- **Unclear Bucket (n=30):** 10/30 derivation agreement (**33.33%**), 10/30 extraction agreement (**33.33%**). All 20 disagreements were extraction false negatives where the classifier left unmapped foreign role locations unextracted, safely defaulting them to `unclear` instead of `excluded`. Zero non-eligible records were misclassified as eligible.

### Precision Nuances and Explicit Limitations
1. **Small Positive Denominator:** The 100.00% eligible precision was achieved on $n=8$ true positives (all candidate eligible records in the deduplicated sample). This satisfies the mandatory gate for candidate eligible quality, but is not a claim of universal 100% classifier accuracy across arbitrary unseen postings.
2. **Conservative Design Bias:** The classifier is intentionally precision-oriented: foreign, localized, or ambiguous postings safely default to `unclear` rather than risking false eligibility.
3. **Corpus-Specific Rate & Withholding:** The measured 0.32% Egypt-eligible rate (8/2,472) applies strictly to THIS measured corpus and source mix; universal market eligibility is withheld per §5.1 / §7.

---

## Required generalization cases

The 15 generalization cases mined from fixtures and verified in `recon/test_classification.py` are:

| # | Location | Body | Expected |
|---|---|---|---|
| G01 | Remote | Right to work in the U.S. is mandatory. | `excluded` |
| G02 | Global | Applicants need US citizenship. | `excluded` |
| G03 | Remote | Based in France only. | `excluded` |
| G04 | Anywhere | Australian residents only. | `excluded` |
| G05 | Remote | Applicants must live in Japan. | `excluded` |
| G06 | Africa | Remote team. | `eligible` |
| G07 | Middle East | Distributed engineering. | `eligible` |
| G08 | Remote | Candidates from any country are welcome. | `eligible` |
| G09 | Global | Work from anywhere. | `eligible` |
| G10 | Remote | EMEA hours preferred. | `unclear` |
| G11 | Remote - Europe | CET overlap. | `unclear` |
| G12 | (empty) | Distributed company. | `unclear` |
| G13 | MENA | No sponsorship available. | `excluded` |
| G14 | Worldwide | Must be located in Brazil. | `excluded` |
| G15 | Anywhere | Eligible countries: Egypt, Jordan. | `eligible` |

---

## Model routing and producing agents

In accordance with the repository routing policy in `AGENTS.md` and `.codex/agents/`:
- **Classifier & Test Suite:** Developed and expanded by `mechanic` / `builder` (OpenAI Codex) with regional invariants contributed by GitHub Copilot under ADR-0003 and ADR-0006.
- **Mirror Relocation & Security:** Implemented and verified by OpenAI Codex and Claude Code under ADR-0004.
- **Blinded Independent Audit:** Executed by a fresh, ephemeral, blinded OpenAI Codex session with automated evaluation against written repository specifications.
- **Master Coordination & Acceptance:** Orchestrated by Gemini / Antigravity Master.
- **Cloud Tasks & Ultra Mode:** Zero cloud tasks used; zero Ultra mode used.

---

## Attribution

All opportunities ingested from external feeds retain strict provenance:
- Each record links to original source URL, source name, publication timestamp, and organization.
- Attribution for independent-track notices (UNGM, World Bank, TED) includes procurement agency, notice ID, reference links, and deadline metadata.

---

## Deviations from brief

1. **ADR-0004 & ADR-0005 (External Action & TED Semantics):** External mutations are prohibited across all hosts. Replaced custom web scraping with public REST/RSS feeds and allowlisted read-only unauthenticated `POST /v3/notices/search` on `api.ted.europa.eu`.
2. **ADR-0004 (Public Mirror Execution Boundary):** Workflows and sensitive deployment configs are remapped to safe paths before mirroring, preventing secret/token leakage.

---

## Known limitations and future work

- **Unclear-Bucket False Negatives:** 20/30 sample records in the unclear bucket contained unextracted foreign location clauses in unstructured prose, defaulting to `unclear` rather than `excluded`. This preserves safety (zero false positives) while leaving a bounded recall improvement backlog for Phase 2.
- **Ashby Robots Host:** The shared ashbyhq.com `/robots.txt` endpoint is unreachable due to host-level network resets, though all 13 Ashby board tokens were independently verified.

---

## What this changes about the plan

The findings from Phase 1 inform the Master Plan with clear distinction between measured facts and strategic hypotheses:

1. **Directly Measured Evidence:** In the tested global remote job boards and US company ATS feeds, unrestricted Egypt-eligible payroll employment is exceedingly rare (0.32%, 8/2,472). In this initial unranked pass, UNGM, World Bank, and TED notices also returned 0 individual-eligible records due to organizational registration/turnover requirements on general tenders.
2. **Strategic Inference / Hypothesis (Master Plan §16.2 & §41):**
   - General Western job boards alone cannot sustain an employment-only acquisition track for Egypt.
   - Dual-track hypothesis: Specialized consultant calls, individual RFP opportunities, and regional MENA/Gulf employment feeds are hypothesized to offer substantially higher conversion for Egyptian founders than general Western tech boards.
   - Defensibility derives from regional eligibility intelligence and conversion tracking rather than raw listing volume.
3. **Future Validation Requirement:** Phase 2 and Phase 3 must ingest regional MENA feeds (WUZZUF, Bayt, GulfTalent, regional procurement) and test the conversion rate of both tracks against live founder applications.

---

## Decision

PASS

BRIEF-001 acceptance criteria have been verified against stored repository evidence. The independent audit achieved 100.00% Egypt eligible precision ($n=8$), all unit and regression tests pass, repository guards are green, and the brief is closed.

---

## Deferred acceptance items

- None.

---

## Next phase prerequisites

- [x] Independent audit passed with $\ge 90.0\%$ eligible precision (100.00% achieved, $n=8$).
- [x] All 67 unit tests, mirror relocation tests, and boundary guards passing.
- [x] `docs/STATE.md` regenerated via `python scripts/generate_state.py`.
- [x] Mirror synchronization workflow verified ready for post-merge publication.
- [x] Ready for merge to `main` and activation of Phase 2 (`briefs/BRIEF-002.md`).
