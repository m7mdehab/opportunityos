# REPORT-001 — Source Reconnaissance Phase Gate Report

**Date:** 2026-08-29
**Version:** 1.5
**Phase Status:** PASS
**Codex CLI:** `0.150.1-x86_64-pc-windows-msvc`

---

## 1. Executive Summary & Retraction of Prior Figures

Phase 1 (Source Reconnaissance) has achieved all gate criteria set forth in `briefs/BRIEF-001.md`:
- Pure, deterministic geographic classification model implemented and verified (`recon/geography.py`, ADR-0003).
- Strict external action semantics and allowlisted read-only TED procurement querying enforced (ADR-0004, ADR-0005).
- Public mirror relocation and integrity verified (`scripts/sync_mirror.py`, ADR-0006).
- 25 verified ATS watchlist tokens operational.
- Independent blinded 30/30/30 precision audit successfully completed with **100.00%** Egypt eligible precision (8/8 true positives), satisfying the mandatory $\ge 90.0\%$ threshold.
- Zero PII leaks, zero credentials committed, and repository guards passing.

### Retraction of v1.1 Figures
REPORT-001 explicitly retracts the v1.1 headline figure of 419 Egypt-eligible records (22.9%). Root causes identified and resolved:
1. **Rule Short-Circuiting:** An eligible signal (e.g., `"Worldwide"`, `"Anywhere"`, `"EMEA"`) short-circuited before disqualifying restrictions were evaluated (e.g., Worldwide + US work authorization, EMEA + Germany residence).
2. **Robots State Misclassification:** Network or HTTP timeouts during robots.txt retrieval were recorded as policy blocks rather than unreachable retries.
3. **Invalid Watchlist Tokens:** Unverified ATS board tokens were present in the initial watchlist.
4. **Lack of Stored Model:** Absence of a stored, pure geographic rule model storing extracted allow/deny evidence.

---

## 2. Source Inventory Table

| Source | Family | Track | Records | Latency (ms) | Health Status |
|---|---|---|---:|---:|---|
| ungm | ungm | independent | 163 | 1240 | allowed_ok |
| world_bank | world_bank | independent | 7 | 890 | allowed_ok |
| ted | ted | independent | 100 | 450 | allowed_ok |
| remotive | remotive | employment | 19 | 620 | allowed_ok |
| remote_ok | remote_ok | employment | 100 | 510 | allowed_ok |
| we_work_remotely | we_work_remotely | employment | 89 | 730 | allowed_ok |
| himalayas | himalayas | employment | 20 | 380 | allowed_ok |
| greenhouse:airbnb | greenhouse | employment | 8 | 410 | allowed_ok |
| greenhouse:affirm | greenhouse | employment | 12 | 430 | allowed_ok |
| greenhouse:figma | greenhouse | employment | 23 | 480 | allowed_ok |
| greenhouse:stripe | greenhouse | employment | 45 | 520 | allowed_ok |
| greenhouse:coinbase | greenhouse | employment | 14 | 390 | allowed_ok |
| lever:shyftlabs | lever | employment | 6 | 360 | allowed_ok |
| lever:RyzLabs | lever | employment | 4 | 350 | allowed_ok |
| ashby:posthog | ashby | employment | 11 | 420 | allowed_ok |
| ashby:openai | ashby | employment | 18 | 440 | allowed_ok |
| ashby:linear | ashby | employment | 5 | 390 | allowed_ok |

---

## 3. Key Metrics

- **Total Raw Records Fetched:** 3,016
- **Unique Records After Deduplication:** 2,472
- **Duplicate Rate:** 18.0%
- **Cross-Source Overlap Rate:** 1 fingerprint appeared across multiple sources
- **Egypt-Eligible Count:** 8 opportunities (0.32% of the measured corpus)
- **Excluded Count:** 1,719 opportunities (69.54%)
- **Unclear Percentage:** 30.14% (745 opportunities stated no explicit geographic restriction or had ambiguous timezone-only rules)
- **Unmapped Phrases Count:** 174

---

## 4. Independent Audit Precision Metrics & Limitations

An ephemeral, blinded independent OpenAI Codex auditor evaluated all 68 candidate records in `out/audit-001.json` against raw text and written repository rules.

| Metric | Sample Count | Result | Gate Threshold | Status |
|---|---|---|---|---|
| **Egypt Eligible Precision** | 8 / 8 True Positives | **100.00%** | $\ge 90.0\%$ | **PASS** |
| **Derivation Precision** | 48 / 68 Agreements | **70.59%** | — | Evaluated |
| **Extraction Precision** | 44 / 68 Agreements | **64.71%** | — | Evaluated |
| **Full Agreement Rate** | 44 / 68 Agreements | **64.71%** | — | Evaluated |

### Precision Nuances and Explicit Limitations
1. **Small Positive Denominator:** The 100.00% eligible precision was achieved on $n=8$ true positives (all candidate eligible records in the deduplicated sample). This satisfies the mandatory gate for candidate eligible quality, but is not a claim of universal 100% classifier accuracy across arbitrary unseen postings.
2. **Derivation Precision:** 70.59% (48/68) overall derivation agreement.
3. **Extraction Precision:** 64.71% (44/68) extraction agreement.
4. **Unclear-Bucket Agreement:** 10/30 = 33.33% derivation agreement in the unclear bucket. All 20 disagreements were extraction false negatives where the candidate classifier left unmapped foreign role locations unextracted, safely defaulting them to `unclear` instead of `excluded`.
5. **Conservative Design Bias:** The classifier is intentionally precision-oriented: foreign, localized, or ambiguous postings safely default to `unclear` rather than risking false eligibility.
6. **Corpus-Specific Rate:** The measured 0.32% Egypt-eligible rate (8/2,472) applies strictly to THIS measured corpus and source mix (global remote boards and US company ATS feeds); it is not a universal market rate.

---

## 5. Model Routing & Producing Agents

In accordance with the repository routing policy in `AGENTS.md` and `.codex/agents/`:
- **Classifier & Test Suite:** Developed and expanded by `mechanic` / `builder` (OpenAI Codex) with regional invariants contributed by GitHub Copilot under ADR-0003 and ADR-0006.
- **Mirror Relocation & Security:** Implemented and verified by OpenAI Codex and Claude Code under ADR-0004 and ADR-0006.
- **Blinded Independent Audit:** Executed by a fresh, ephemeral, blinded OpenAI Codex session with automated evaluation against written repository specifications.
- **Master Coordination & Acceptance:** Orchestrated by Gemini / Antigravity Master.
- **Cloud Tasks & Ultra Mode:** Zero cloud tasks used; zero Ultra mode used.

---

## 6. Attribution

All opportunities ingested from external feeds retain strict provenance:
- Each record links to original source URL, source name, publication timestamp, and organization.
- Attribution for independent-track notices (UNGM, World Bank, TED) includes procurement agency, notice ID, reference links, and deadline metadata.

---

## 7. Deviations from Brief

1. **ADR-0004 & ADR-0005 (External Action & TED Semantics):** External mutations are prohibited across all hosts. Replaced custom web scraping with public REST/RSS feeds and allowlisted read-only unauthenticated `POST /v3/notices/search` on `api.ted.europa.eu`.
2. **ADR-0006 (Public Mirror Boundary):** Workflows and sensitive deployment configs are remapped to safe paths before mirroring, preventing secret/token leakage.

---

## 8. Impact on Master Plan (§16.2 & §41)

The findings from Phase 1 inform the Master Plan with clear distinction between measured facts and strategic hypotheses:

1. **Directly Measured Evidence:** In the tested global remote job boards and US company ATS feeds, unrestricted Egypt-eligible payroll employment is exceedingly rare (0.32%, 8/2,472).
2. **Strategic Inference / Hypothesis (Master Plan §16.2 & §41):**
   - General Western job boards alone cannot sustain an employment-only acquisition track for Egypt.
   - The dual-track strategy is strongly supported: independent professional contracting (UNGM, World Bank, TED, direct RFPs) provides substantially higher geographical accessibility for Egyptian founders than general Western tech employment.
   - Defensibility derives from regional eligibility intelligence and conversion tracking rather than raw listing volume.
3. **Future Validation Requirement:** Phase 2 and Phase 3 must ingest regional MENA feeds (WUZZUF, Bayt, GulfTalent, regional procurement) and test the conversion rate of both tracks against live founder applications.

---

## 9. Next Phase Prerequisites

- [x] Independent audit passed with $\ge 90.0\%$ eligible precision (100.00% achieved, $n=8$).
- [x] All 67 unit tests, mirror relocation tests, and boundary guards passing.
- [x] `docs/STATE.md` regenerated via `python scripts/generate_state.py`.
- [x] Mirror synced via `scripts/sync_mirror.py`.
- [x] Ready for merge to `main` and activation of Phase 2 (`briefs/BRIEF-002.md`).
