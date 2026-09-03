# BRIEF-FR-006 — Nothing Missed, Nothing Hidden, Nothing Ugly

**Version:** 1.1 — executes under `docs/AGENT_EXECUTION_PROTOCOL.md` v2 (DAG dispatch, parallel implementers with isolated databases, tiered verification, council in parallel). Deliverables unchanged from 1.0.
**Date:** 2026-09-03
**Overseer:** external independent auditor
**Master:** Claude Code main session, model `opus`
**Status:** ACTIVE (starting main = `bf25d93` or later; record in pre-flight)
**Merge authority:** Master merges on §8 per the standing instruction; Overseer reviews post-merge.
**Origin:** the founder's first acceptance run over real data (2026-09-03). This brief is scoped from what a real person saw, not from what tests passed.

---

## 0. What the founder saw, and what it means

11,251 fetched · 2,679 new · **4 qualified** · 61 high fit · 375 hidden. Every visible card said *Uncertain*. Twenty near-identical "Senior Customer Engineer" cards at 73. No card said whether the job was remote, hybrid, or on-site, or where it was. The generated CV had no name, no contact details, no bullet points, no education, no formatting.

Root causes, each verified by the Overseer in the code:

| Symptom | Cause | Fix track |
|---|---|---|
| Everything *Uncertain* | `remote_policy` and location are not extracted (Lever's `workplaceType`, Greenhouse's `location.name` are ignored); qualifier correctly says UNKNOWN | A |
| "Senior matches founder experience" on senior/staff/principal roles | `is_senior` = any title containing "lead" — the founder's two "Team Lead" titles make every senior role a match | B |
| "Verified core skill: Javascript" | scorer never reads skill proficiency; CV says *basic* | B |
| 20× "Senior Customer Engineer" | no near-duplicate clustering across locations | A |
| 375 hidden | founder red line `scam` and excluded industry `fraud` hit fraud-detection roles (pack fixed by Overseer; see §6) — and hidden reasons are not shown | C |
| No work-mode / location / title / type filters | filter model has ten fixed ids; no faceting | C |
| Search only matches title/organization | no full-text index | C |
| 11,251 fetched, mostly Cloudflare | 9 live employment boards, 5 of them one ATS; no aggregate discovery | E |
| CV unusable | compiler emits atomic claims as bare lines; no identity, no bullets, no sections, no styling, no PDF, no preview | D |

**Founder's governing instruction, verbatim in spirit:** *I can exclude something close that isn't right for me; I can't get back something suitable that was excluded before I saw it.* Everything in this brief errs toward showing more and letting the founder cut.

---

## 1. Frozen and unfrozen

- **Frozen:** BRIEF-002 evidence-support rule; FR-002 fail-closed invariant (A-0 stays green); the truth-lock (no generated sentence without evidence); the founder's real pack is never read by an agent.
- **Unfrozen (named deliverables only):** `opportunity/` adapters, normalization, models (A); `matching/` scorer, qualification, compilers, artifact validation, export (B, D); `api/`, `web/` (C, D); `storage/` via revisions `0004…` (A, C); `worker/` handlers and scheduler (E); `docs/SOURCE_REGISTRY.yaml` and `recon/` (E); `truth/predicates.py` (D identity predicates).
- BRIEF-003/004 tests that pass only on fixtures shaped to the old behaviour are replaced, and each replacement is listed in the report.

---

## 2. Deliverables

### Track 0 — Protocol and environment (first, sequential, ≤ 1 hour)

**D0 — Adopt the execution protocol.** Commit `docs/AGENT_EXECUTION_PROTOCOL.md` (provided by the Overseer) and add one line to AGENTS.md: "Briefs execute under docs/AGENT_EXECUTION_PROTOCOL.md." Update `.claude/agents/*.md` to Appendix B of this brief (effort levels, concurrency notes, `maxTurns`). Write every work order to `reports/evidence/FR-006/orders/` before dispatching wave 1.

**F2 (moved here) — `scripts/dev_env.py`.** `up` verifies Python ≥ 3.12, Node LTS, PostgreSQL reachable, Playwright browsers, and a PDF renderer, and prints exactly what to fix; `testdb <slug>` creates `opportunityos_test_<slug>` and prints the DSN; `testdb --drop-all`; `doctor` is the founder-facing alias. `alpha.py` and every child process use `sys.executable`. Run `dev_env.py up` **before wave 1**; if it fails, fix the environment first — no implementer is dispatched into a broken environment.

### Track A — Understand the job

**A1 — Work mode, location, employment type, seniority, compensation extraction.**
- `Opportunity` gains: `work_mode` (remote | hybrid | onsite | unspecified, with `work_mode_source` field provenance), `location_country` (ISO-2), `location_city`, `location_region`, `remote_scope` (worldwide | region-restricted with the region list | unspecified), `employment_type` populated (full_time | part_time | contract | freelance | internship | unspecified), `seniority_level` populated from title *and* description, `compensation_min/max/currency/period` when stated.
- Every adapter maps its native fields first (Lever `workplaceType` + `categories.location`; Greenhouse `location.name` + `offices`; Himalayas `locationRestrictions`; Remotive `candidate_required_location`; RemoteOK `location`; WWR region; UNGM/World Bank/TED duty station / buyer country). Only then does text inference run, and inference is recorded as such in provenance.
- Text inference rules are a committed, tested table (`opportunity/inference_rules.yaml`): e.g. "Remote (US only)" → remote, region-restricted [US]; "Hybrid — Cairo" → hybrid, EG/Cairo; "Egypt, Saudi Arabia, or UAE" → onsite, multi-country.
- Migration `0004`: new columns; backfill job `reextract_all` re-parses every stored `raw_payload_json` so the founder's existing 11k rows get the new fields without re-polling.
- Qualifier: geographic eligibility now resolves for any row with a country or a remote scope; `UNKNOWN` only when both are absent. Per-country eligibility uses the founder's work authorizations and service regions; region-restricted remote roles that exclude EG are *labelled* "remote but region-restricted", never hidden.
- **Acceptance:** on the founder-shaped synthetic corpus (≥ 200 real raw payloads captured from the nine live sources and committed as fixtures with employer names intact — these are public postings), ≥ 90% of rows have a non-unspecified `work_mode`, ≥ 85% a country or remote scope; the *Uncertain* share of qualification decisions drops below 25%. Numbers reported from the actual run.

**A2 — Near-duplicate clustering.**
- Postings with the same employer + normalized title and differing only in location/team suffix collapse into one *family* card with a location list ("Senior Customer Engineer — 14 locations"); the family carries the best-fit member's score and expands in the drawer. Clustering is deterministic (`family_key`), stored (`0004`), and reversible per family from the UI ("show separately").
- **Acceptance:** the Cloudflare "Senior Customer Engineer" set in the fixture corpus collapses to one family; families never merge different employers or different normalized titles.

### Track B — Honest scores

**B1 — Seniority from experience, not keywords.**
- Founder seniority derived from the truth graph: total professional months since first non-internship role, months in the target role family, and whether any role carried people leadership (from responsibilities, not title tokens). Encoded as a small model with committed thresholds and an ADR (`ADR-0016`). "Team Lead" titles at group companies count as leadership evidence; they do not make a 20-month-tenure founder "senior" for a Staff/Principal engineering role.
- Scorer output must say what it computed: "Founder: ~2 years professional, 8 months in data engineering; role asks Senior (5+). Gap: 3 years." — with evidence refs.
- **Acceptance:** on the fixture corpus, Staff/Principal/Lead roles no longer receive a seniority *strength* for the founder-shaped pack; Mid and Junior data roles do. Tests cover the boundaries.

**B2 — Proficiency-aware, requirement-aware skills.**
- Skill match consults the founder's proficiency (`basic`, `foundations` are *partial* matches, shown as such); the posting's required vs nice-to-have skills are separated (Greenhouse/Lever descriptions use headed lists; inference rules in `inference_rules.yaml`); core-skill strength requires a *required* match at ≥ working proficiency.
- Reasons are specific: "Required: Python, SQL, Airflow → you have Python (expert-evidence: 3 roles), SQL (3 roles); Airflow not in your pack." Never "Verified core skill: Javascript" for a basic skill.
- **Acceptance:** fixture tests for required/nice-to-have split and proficiency tiers; the "Senior Customer Engineer" family no longer scores above the founder's data-engineering matches on the fixture corpus.

**B3 — Target-role families and title normalization.**
- `matching/title_families.yaml`: committed families (data engineering, data science, ML/AI engineering, analytics/BI, data migration, tutoring, web/frontend, …) with alias lists and regexes; every posting title normalizes to a family + level; the founder's `career.target_role` assertions map onto families. Title-family match becomes a scored dimension *and* a facet for filtering (C1).
- `target_roles` filter default reverts to `rank_only` (Overseer decision, FR-005 review §3.1) via data migration.
- **Acceptance:** ≥ 95% of fixture-corpus titles map to a family (the rest to `other`, listed in evidence); the family assignment for the top 50 fixture titles is committed and reviewed by the council.

**B4 — Exercise every filter against the founder-shaped pack.** `track_preference`, `premium_fulltime_onsite`, `stale_postings` must each show a non-zero affected count on the fixture corpus, or the report explains why zero is correct (FR-005 review §3.2).

### Track C — Founder control

**C1 — Facets for everything.**
- A generic facet engine replaces the fixed ten-filter table: every extracted attribute is a facet with include/exclude lists and counts — `work_mode`, `location_country`, `location_city`, `remote_scope`, `employment_type`, `seniority_level`, `title_family`, `track`, `source_id`, `employer`, `posted_within`, `compensation_stated`, `decision`, `fit_score` range, `language`, plus the existing ten. Each facet supports **include**, **exclude**, and **off**; exclusions are visible as chips with counts; excluded items are always one click away ("Show N excluded by Location").
- Facet state persists server-side (`0004` replaces `founder_filter_settings` with `founder_facets`), with **saved views** (named facet sets, e.g. "Remote data eng, EU/US, last 7 days") and a default view.
- **Nothing hides by default except the founder's own red lines and excluded industries**, unchanged from FR-005; hidden rows show *why* ("hidden by red line: gambling").
- **Acceptance:** with every facet off, `include_hidden` total equals the row count; each facet's include and exclude are tested through the API and one is exercised in Playwright; a saved view round-trips.

**C2 — Search.**
- Full-text search over title, employer, description, requirements, and location with PostgreSQL `tsvector` (GIN index, `0004`), phrase and negative terms (`"data engineer" -customer`), ranked by relevance × fit; results respect facets; search terms can be saved into a view.
- **Acceptance:** searching `pytorch -"customer engineer"` on the fixture corpus returns only rows whose text contains pytorch and none titled Customer Engineer; index built in migration; p95 query < 200 ms on 20k rows locally.

**C3 — Cards that answer the founder's first three questions.**
- Card shows: title (family badge), employer, **work mode + location + remote scope**, employment type, seniority, compensation if stated, posted age, source, decision, score, the top three *specific* reasons (B2), family size if clustered, action state, feedback state. Employer logo/domain when available. Keyboard navigation between cards; `j/k`, `o` open, `a` mark applied, `x` dismiss.
- Drawer: full description (sanitised HTML), requirements split required/nice-to-have with your match against each, geography reasoning, every field's provenance, artifacts panel (D), tracker panel (mark applied / dismiss / snooze / notes), feedback panel.
- **Acceptance:** axe clean; Playwright covers keyboard flow; screenshots at 360/1280 in evidence.

**C4 — Hidden-reasons audit.** The dashboard's HIDDEN number links to a table: reason → count → one-click "unhide all by this reason". Any facet or red line hiding more than 10% of new rows in a poll triggers a visible warning.

### Track D — Documents worth sending

**D1 — A real CV compiler (ADR-0017: document model).**
- Identity block from `identity.*` assertions (name, headline, email, phone, LinkedIn, GitHub, website, location) — the founder's pack already carries them.
- Sections, each truth-locked: Summary (the approved summary, optionally tailored by selecting the sentence variant whose evidence best matches the role); Experience with the **founder's actual bullet points** (responsibilities and achievements from the pack), ordered and selected by relevance to the posting's requirements, dates rendered "Jan 2026 – Present"; Projects (portfolio with URLs); Education; Certifications; Skills grouped by the pack's categories, ordered by relevance, with proficiency shown honestly for basic/foundations; Languages.
- Tailoring = **selection and ordering**, never rewording. Every rendered sentence maps to a claim with evidence ids (A-10 rule unchanged). A "what was left out and why" panel lists the bullets not selected.
- Three committed ATS-safe templates (single column, real heading styles, consistent fonts, no tables for layout, no text boxes): *Classic*, *Compact*, *Modern*. DOCX via `python-docx` with proper styles; **PDF** via a deterministic renderer (LibreOffice headless if present, else a pure-Python HTML→PDF path — the Master picks one that works on the founder's Windows machine and records it).
- Cover letter: same identity block; a narrative skeleton with **the founder's own approved sentences** slotted in; opportunity-provenanced facts (employer, role, location) cited with their provenance; never invents motivation text beyond a committed, founder-editable phrase bank in the pack (new optional section `approved_phrases`, documented in the template).
- **Acceptance:** on the founder-shaped synthetic pack, the CV DOCX and PDF contain: identity block, ≥ 2 bullets per non-internship role, education, ≥ 3 certifications, projects with URLs, grouped skills; text extraction of the PDF passes a committed ATS-parse check (sections detected, dates parsed, no tables); the truth-lock e2e suite and the guard-neutralisation mutation still fail correctly; the Overseer will re-run the mutation.

**D2 — In-browser preview.**
- `GET /api/opportunities/{id}/artifacts/cv.pdf` streams inline (`Content-Disposition: inline`); the drawer's artifacts panel shows the PDF in an embedded viewer with template switcher and download buttons for PDF/DOCX; generation cached per (opportunity, truth-pack hash, template) in `0004` so re-opening is instant.
- **Acceptance:** Playwright opens a card, sees the PDF preview render, switches template, downloads DOCX.

### Track E — Sources: everywhere legitimate remote work actually is

**E0 — Rules that do not change.** Every new source goes through the BRIEF-001 recon path: robots, terms, rate rules, `SOURCE_REGISTRY.yaml` entry with `policy_status`, evidence in `SOURCE_EVIDENCE.md`. AGENTS.md stop rules apply (403/429/CAPTCHA → stop, record, never work around). A source whose terms forbid automated reading is registered `manual_only` with a deep-link route the founder can open, not scraped. Reading is the only automation; no source gets `prepare`/`submit`.

**E1 — ATS board discovery at scale.**
- Greenhouse, Lever, and Ashby host tens of thousands of company boards with public, documented JSON endpoints. Build `opportunity/discovery/boards.py`: seed lists from committed public directories (the Master finds and cites them), plus a **founder watchlist** (`private/watchlist.yaml`, template provided) of companies to track. Each discovered board is a registry entry generated from a template, with per-ATS rate limits shared across boards. Target: **≥ 300 employment boards** live by the end of the brief, filtered to boards with ≥ 1 posting in the founder's title families in the last 90 days.
- Ashby re-recon with the documented public posting API host (the FR-003 result was a 401 on the wrong host); if it permits, flip.

**E2 — Aggregators and communities.**
- Recon and, where permitted, adapters for: **Hacker News "Who is hiring"** (monthly thread via the public Firebase API — a primary channel for AI-engineering roles); **Reddit** via the public JSON/RSS endpoints within its API terms and rate limits for `r/forhire`, `r/remotejobs`, `r/MachineLearningJobs`, `r/datajobs`, `r/hiring`, `r/jobbit`, `r/bigdatajobs`; **Y Combinator Work at a Startup** public listings; **Working Nomads**, **Remote.co**, **JustRemote**, **Wellfound** (alerts route if API forbids), **Arc**, **ai-jobs.net**, **Otta** (alerts), **Jobicy** (403 — deep link only). The Master documents each outcome; blocked ≠ failed.
- Regional and Arabic-language: **Wuzzuf**, **Bayt**, **GulfTalent**, **Naukrigulf** (alert-mailbox routes are already built — this brief configures a real alert mailbox the founder controls, read-only, via the FR-004 inbox adapter, if the founder provides one; otherwise deep-link routes), **LinkedIn** and **Indeed** alerts (same).
- **Acceptance:** each source has a registry entry with a dated recon outcome; at least **8 new read-allowed sources** produce rows in the fixture corpus, including HN and at least one Reddit route; every `manual_only` source has a working deep link in the UI (a "Check manually" panel listing them with the founder's search prefilled).

**E3 — Independent and tutoring tracks.**
- Freelance: recon **Mostaql** and **Khamsat** (Arabic-market platforms — high relevance for the founder), **Contra**, **PeoplePerHour**, **Toptal** (application-based; deep link), **Upwork** (API is partner-only; RSS search feeds exist — recon them); **Freelancer** stays credential-gated.
- Tutoring: **Preply**, **Superprof**, **Wyzant**, **Tutor.com**, **Chegg**, **Cambly** are platform applications, not postings — register each as a `platform_application` opportunity type with a deep link and the founder's readiness checklist, surfaced under the tutoring facet.
- **Acceptance:** at least two freelance sources produce rows or are `manual_only` with deep links; the tutoring platforms appear in the feed under `track = tutoring` as platform cards.

**E4 — Poll cadence and freshness.** Per-source cadence (hourly for HN/Reddit/remote boards, 6-hourly for ATS boards, daily for procurement); `stale_postings` re-verification for anything older than 14 days; a **"new since you last looked"** marker driven by `founder_opportunity_views`.

### Track F — Pack and process

**F1 — Predicate registry gains `identity.*` and `approved_phrases`;** template and `truth_check.py` updated; the shipped synthetic template gains an identity block and phrase bank.
**F3 — Daily digest.** `python -m worker --digest` writes a Markdown/HTML digest of new high-fit items to `out/digest/`; the API exposes it; email delivery is FR-007 (needs the inbox mailbox).
**F4 — Readiness matrix, STATE, report, evidence, merge** as before; matrix rows for 1B/1H/2A/2B/2C/3C/3E/1G updated one at a time with history.

---

## 3. Execution order — dependency graph (dispatch every ready node at once)

```
Wave 0 (sequential, Master):  pre-flight → D0 → F2 → dev_env up → work orders written → CLAIMS.md skeleton
Wave 1 (parallel ×4):         A1-extract   B1-seniority   B3-families   E1-discovery
                              (A1 captures the fixture corpus first thing; other nodes start on existing fixtures)
Wave 2 (parallel ×4):         A2-cluster(A1)   B2-skills(A1,B3)   C1-facets(A1,B3)   E2-communities   E3-freelance/tutoring   F1-identity
                              council #1 (B1+B3 diff) and council #4 (E1 registry entries) dispatched as soon as wave-1 diffs are stable
Wave 3 (parallel ×4):         C2-search(A1)   C3-cards(C1,B2)   C4-hidden-audit(C1)   D1-compiler(F1)   E4-cadence(E1–E3)   B4-filters(C1)
                              council #3 (migration 0004 — A1/A2/C1/C2 schema) once those are integrated
Wave 4 (parallel):            D2-preview(D1)   F3-digest(C1)   evidence-runners over all integrated claims
                              council #2 (D1 document model) once D1 is integrated
Final (sequential):           integrate → full suite once → web build/lint/Playwright once → verifier → remediate → F4 → merge → STATE on main
```

Rules: a node is dispatched the moment its dependencies are integrated; the Master never waits for a whole wave. Concurrency cap 4 implementers + any number of haiku runners + all four council reviews in parallel. Each implementer gets its own worktree, database (`dev_env.py testdb <slug>`), and, for web orders, its own port pair. Integration per wave; full suite once per wave.

## 4. Roles and model routing
Per `docs/AGENT_EXECUTION_PROTOCOL.md` §1. Council invocations: four, in parallel as their diffs stabilise — (1) B1+B2+B3 scoring semantics (ADR-0016), (2) D1 document model and truth-lock (ADR-0017), (3) migration `0004`, (4) E0–E3 source policy compliance.

## 5. Master loop
Per `docs/AGENT_EXECUTION_PROTOCOL.md` §3–§8: work orders before dispatch, DAG dispatch, per-wave integration, 3-loop defect cap with resume-same-subagent, three verification tiers, report ≤ 400 lines. Additional rule for this brief: **every quantitative acceptance number in §2 is a claim row with the command that produced it.**

## 6. Environment and inputs from the founder
- The Overseer has updated the founder's pack (`private/truth_pack.yaml`): identity/contact assertions added; the `scam`/`fraud` over-exclusion fixed. The founder replaces the file before running.
- Founder-provided, optional, any time: `private/watchlist.yaml` (companies to track) and an alert mailbox for the regional boards. Absence blocks nothing.
- PDF renderer: the Master installs and records one that works on Windows without admin rights.

## 7. Claim ledger — mandatory rows
A-0…A-8 as FR-005 · A-9 live poll on `opportunityos_alpha` with source counts before/after E1–E3 (breadth delta reported) · A-10 documents on both synthetic packs (DOCX + PDF) · A-11 guard-neutralisation mutation fails ≥ 2 suites · **A-12 extraction metrics** (A1) · **A-13 scoring metrics** (B1/B2 on the fixture corpus, before/after) · **A-14 facet completeness** (C1) · **A-15 search** (C2) · **A-16 source policy** (every new source: recon date, outcome, policy_status).

## 8. Definition of done
All deliverables closed or explicitly `NOT_CLOSED` with history (E2/E3 sources may be `BLOCKED_POLICY` individually — that is a valid closure with evidence); A-0…A-16 PASS by Master and verifier; four council reviews fixed or dispositioned; four workflows green on the PR head and on `main`; STATE regenerated; §9 founder packet blank and ready.

## 9. Hard stops
As FR-005 §9, plus: any adapter that reads a source registered `manual_only` or `disabled`; any request to a source that has returned 403/429 in this session; any change that lowers the truth-lock (a generated sentence without an evidence id) to make a document look better.

## 10. Report format
As FR-005 §10, plus: §7 gains the source-breadth table (before/after, per source, per track), the extraction and scoring metric tables, and the family-assignment review; §9 is the founder packet with the same two numbers plus a third: **"Cards where I couldn't tell where the job was or whether it was remote: ___"** (target: zero).

## Appendix — Overseer decisions embedded
1. Show more, cut later: no new default-hide; facets exclude only by founder action.
2. Truth-lock is not negotiable for prettier documents; tailoring is selection and ordering only.
3. Source breadth follows recon rules; a blocked source is a recorded outcome, never a workaround.
4. Seniority is derived from tenure and leadership evidence, not title tokens (ADR-0016).
5. `target_roles` back to `rank_only`.
6. Reddit and HN are in scope via their public APIs within terms; no browser automation against them.
7. This is the largest brief so far by design; `PASS_WITH_NOT_CLOSED` with an honest list is preferred over scope trimming.

## Appendix B — `.claude/agents/` v2 (effort and budgets)

```markdown
<!-- implementer.md -->
---
name: implementer
description: Implements one work order with tests in an isolated worktree and database. Use for any code, test, doc, or fixture change scoped to a single deliverable ID.
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch
model: sonnet
effort: high
maxTurns: 60
isolation: worktree
---
You execute exactly one work order (reports/evidence/<brief>/orders/<ID>.md). Read it, AGENTS.md, and nothing else unless the order names it.
- Use only the database DSN and ports in the order. Never touch files outside the order's allowed list; if impossible, stop and say why.
- Write tests with the change. Run the narrow tests, then the acceptance commands, and paste raw output: the `Ran N tests` line and the final OK/FAILED line verbatim. Never summarise results in words.
- Never edit evidence, fixtures, or templates to make a claim validate; that is an automatic FAIL.
- Return: files changed; raw acceptance outputs; anything you could not verify. If a defect list comes back, fix only what it names and re-run only what it names plus the acceptance rows.
```

```markdown
<!-- evidence-runner.md -->
---
name: evidence-runner
description: Executes claim commands verbatim and writes raw outputs to evidence files. Mechanical; no judgment. Run several in parallel over disjoint claim groups.
tools: Bash, Read, Grep, Glob, Write
model: haiku
effort: low
maxTurns: 25
---
Execute each assigned claim's command exactly as written in CLAIMS.md, from the repository root, with the environment the order specifies. Save stdout+stderr to the named evidence file under reports/evidence/<brief>/. Return a table: claim id, exit code, first line, last line. Do not modify commands, retry with variations, or interpret.
```

```markdown
<!-- verifier.md -->
---
name: verifier
description: Independent verification of a claim ledger from captured evidence, re-executing high-consequence claims. Use after final integration.
tools: Read, Grep, Glob, Bash
model: opus
effort: high
maxTurns: 40
---
You are not told what the Master or implementers concluded. Read CLAIMS.md and the evidence files.
For every claim: compare evidence to the expected result → PASS/FAIL with the observed line. Re-execute yourself: the fail-closed probe, the full suite, migrations round-trip, document generation on both synthetic packs, the guard-neutralisation mutation, and any claim whose evidence is inconsistent, missing, or depends on machine-local state. Flag any claim whose command does not test what its expected result asserts. Check `git diff --stat main...HEAD` against the brief's unfrozen list. Return one table and nothing else.
```

```markdown
<!-- council-reviewer.md -->
---
name: council-reviewer
description: Independent high-consequence review of one diff against one requirement (migrations, concurrency, auth, scoring semantics, source policy, document truth-lock). Runs in parallel with other reviews.
tools: Read, Grep, Glob, Bash
model: fable
effort: high
maxTurns: 30
---
You receive one requirement and one diff. Do not read implementer or Master reasoning. Look for: correctness under concurrency and restart; migration ordering and reversibility; silent fallbacks and fail-open paths; tests that pass without exercising the requirement; policy violations in source registry entries; any generated sentence without evidence. Return numbered findings with severity (BLOCKER/MAJOR/MINOR/NIT), file:line, and the specific resolving change. If none, say so in one line.
```

```markdown
<!-- Explore.md -->
---
name: Explore
description: Fast read-only codebase search.
tools: Read, Grep, Glob
model: haiku
effort: low
---
Search and summarise. Never edit.
```
