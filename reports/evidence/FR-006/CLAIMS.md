# BRIEF-FR-006 — Claim Ledger

Written by the Master **before any implementation dispatch**, per `docs/AGENT_EXECUTION_PROTOCOL.md`
§2 and BRIEF-FR-006 §5. Nothing below is edited after an observation. Where an observation
contradicts an expected result the row is marked `NOT_CLOSED` and the disagreement is recorded
in the report — the expected result is never rewritten to match what was seen.

**Rules in force (restated so they bind here):**
- An expected result must state every property the report will later assert about it. Prose
  may not assert what no claim tested. (FR-004 Erratum 1.1; FR-005 A-9's own failure.)
- Evidence that depends on a gitignored or machine-local artifact is not evidence.
- Editing evidence, fixtures, or templates so a claim validates is an automatic FAIL.
- **Every quantitative acceptance number in the brief's §2 is a row here** (BRIEF-FR-006 §5).
- Tier 2 = evidence-runner capture; Tier 3 = verifier re-execution. A claim is done only with
  both. The Master judges raw output and does not execute claims itself.

## Environment bindings (fixed before dispatch)

| Concept | Binding |
|---|---|
| Python | `py -3.12` = 3.12.10. Bare `python` is 3.10.3 and is never used. |
| Database (suite) | `opportunityos_test`; per-implementer `opportunityos_test_<slug>` |
| Database (alpha) | `opportunityos_alpha`, created empty by `scripts/alpha.py` |
| PDF renderer | **reportlab** — already used by `matching/binary_export.py`, pinned in `pyproject.toml`, pure-Python, no admin rights, deterministic. LibreOffice is not installed and is not required. |
| Alembic head before this brief | `0003_provenance_identity` |
| Alembic head after | `0004_*` — **one** revision shared by A1/A2/C1/C2/D2 |
| Decision vocabulary | `qualified` / `ineligible` / `uncertain` (lowercase) |
| Fit score | 0-100; dimension `raw_score` 0-1 |
| Suite count at FR-005 merge | **672** tests, 0 skipped |
| Pre-existing fields | `Opportunity` already carries `remote_policy` (RemotePolicy enum), `employment_type`, `seniority`, `compensation`, `location_raw`, `geographic_eligibility`, `raw_record_pointer`; the ORM row already stores `raw_payload_json`. The brief's new names extend these rather than duplicating them; wherever a row below says `work_mode` it means the field that ships as the canonical work-mode value, and the report states which name it is. |

---

## Carried invariants (must not regress)

### A-0 — Fail-closed persistence invariant (frozen from FR-002)
- **Command:** `py -3.12 -m unittest storage.test_fail_closed -v`
- **Expected:** `Ran 12 tests`, `OK`, 0 skipped. `ProductionDatabaseConfigurationError` still raised without `OPPORTUNITYOS_DB_URL`; no SQLite fallback anywhere.
- **Evidence:** `a0-fail-closed.txt` — **Tier 3 re-execution: mandatory.**

### A-1 — Full suite on real PostgreSQL
- **Command:** `py -3.12 -m unittest discover -v` with `OPPORTUNITYOS_DB_URL` pointing at `opportunityos_test`
- **Expected:** `OK`, **0 skipped**, and **N > 672**. N is reported exactly as printed.
- **Evidence:** `a1-full-suite.txt` — **Tier 3: mandatory.**

### A-2 — Per-module test counts reconcile to A-1
- **Command:** `py -3.12 -m unittest discover -s <module> -v` for truth, outbound, scripts, recon, opportunity, matching, storage, api, worker, inbox, core, security, feedback
- **Expected:** the per-module sum **equals** A-1's N exactly, at test-id level, zero duplicates. Every new test file appears with a non-zero count.
- **Evidence:** `a2-module-counts.txt`

### A-3 — Migration round-trip `0001` to `0004`
- **Command:** against a scratch database that starts empty: `alembic upgrade head` (4), `alembic downgrade base` (4), `alembic upgrade head` (4)
- **Expected:** 4 up / 4 down / 4 up, each exit 0. Head is `0004_*`. Exactly **one** `0004` revision file exists. Every column, index, constraint and table `0004` adds is present after upgrade and absent after downgrade — asserted per object, not by exit code alone.
- **Evidence:** `a3-migrations.txt` — **Tier 3: mandatory.**

### A-4 — Guard boundary and repository integrity
- **Command:** `py -3.12 scripts/check_guard.py --allow-missing-patterns` and `py -3.12 scripts/check_repository.py`
- **Expected:** both exit 0. No secret-shaped literal in any new file; no mirrored PII. The committed raw-payload fixtures (A1) pass the guard, and `private/watchlist.yaml` is **not** tracked.
- **Evidence:** `a4-guards.txt`

### A-5 — STATE regenerates with zero drift
- **Command:** `STATE_PRESERVE_TIMESTAMP=1 py -3.12 scripts/generate_state.py` then `git diff --exit-code -- docs/STATE.md`
- **Expected:** exit 0, run **at the final head of `main` after merge**. The final commit touches `docs/STATE.md` alone.
- **Evidence:** `a5-state.txt` — **Tier 3: mandatory** (FR-005 recorded this PASS on stale evidence and the verifier overturned it).

### A-6 — Scope diff against §1's unfrozen list
- **Command:** `git diff --name-only main...HEAD`
- **Expected:** every changed path is in the expected set written to `a6-expected-scope.md` **before this diff is first run**. A larger observed set is `NOT_CLOSED` and each extra path is dispositioned; the expected set is never retro-fitted.
- **Evidence:** `a6-scope-diff.md`

### A-7 — Web build and lint
- **Command:** `npm ci`, `npm run build`, `npm run lint` in `web/`
- **Expected:** build exit 0 with the route list printed; `eslint --max-warnings=0` clean **after** a Playwright run has produced its artifact directories (FR-005 found this check order-dependent).
- **Evidence:** `a7-web-build.txt`

### A-8 — Playwright from a clean checkout
- **Command:** `npx playwright test` in `web/`, with no untracked env file
- **Expected:** all specs pass and **N > 0** — a zero-test run is not a pass (FR-005 deviation 8). Covers: a facet include and a facet exclude, a saved view round-trip, keyboard navigation, the PDF preview rendering, and a template switch.
- **Evidence:** `a8-playwright.txt`

### A-17 — Predicate contract (carried from FR-005 A-12)
- **Command:** `py -3.12 -m unittest truth.test_predicates -v`
- **Expected:** `OK`. Every predicate string referenced in `matching/` is in the registry; every registry predicate is projected by `truth/graph.py` or declared assertion-only with its owning pack section. The new `identity.*` and `approved_phrases` predicates (F1) are registered and projected.
- **Evidence:** `a17-predicates.txt`

### A-19 — Provenance idempotency (carried from FR-005 A-14)
- **Command:** `py -3.12 -m unittest storage.test_postgres_integration -k case_u -v`
- **Expected:** `persist_batch` re-run on the same batch leaves the `field_provenances` row count unchanged, asserted after the **second** run. Still true after `0004` and after a `reextract_all` run.
- **Evidence:** `a19-idempotency.txt`

---

## Track A — Understand the job

### A-12 — Extraction metrics on the committed fixture corpus
- **Command:** the A1 corpus-metrics script over the committed corpus. It must print the denominators, not only the percentages.
- **Expected, each number printed by the run and quoted in the report:**
  - corpus size **>= 200** raw payloads, captured from the live sources and committed as fixtures with employer names intact;
  - **>= 90%** of rows have a work mode other than `unspecified`;
  - **>= 85%** of rows have a country **or** a non-unspecified remote scope;
  - the *uncertain* share of qualification decisions over the corpus is **< 25%**, with the before-figure printed alongside;
  - every work-mode value carries a source field saying whether it came from a **native adapter field** or from **text inference**, and the native/inference split is printed.
- **Binds:** the founder's "every visible card said Uncertain". A number that is true only because inference guessed is a different result from one the adapters extracted, so the split is part of the claim.
- **Evidence:** `a12-extraction.txt`

### A-20 — Near-duplicate clustering
- **Command:** the A2 test module, plus a corpus run printing family sizes
- **Expected:** the Cloudflare "Senior Customer Engineer" set in the corpus collapses to **one** family whose member count is printed; **zero** families span two different employers or two different normalized titles, asserted over the whole corpus rather than a sample; `family_key` is deterministic — recomputing over the corpus twice yields identical keys; "show separately" reverses a family.
- **Evidence:** `a20-clustering.txt`

---

## Track B — Honest scores

### A-13 — Scoring metrics, before and after
- **Command:** the B1/B2/B3 metric script over the fixture corpus, run against the **founder-shaped synthetic pack** (`truth.fixtures.founder_shaped_graph`), never the founder's own pack, printing before/after
- **Expected:**
  - **B1:** Staff / Principal / Lead postings receive **no** seniority *strength* for the founder-shaped pack; Mid and Junior data roles do. Boundary cases are tested. The scorer's seniority explanation names months of professional experience, months in the target family, and whether leadership evidence was found, each with evidence refs. The old `is_senior` keyword test (any title containing "lead") is gone — asserted by a test, not by inspection.
  - **B2:** required vs nice-to-have skills are separated; a `basic`/`foundations` skill produces a **partial** match and never a "verified core skill" strength; core-skill strength requires a *required* match at >= working proficiency.
  - **B2 ordering:** the "Senior Customer Engineer" family no longer scores above the founder's data-engineering matches on the corpus — both scores are printed.
  - **B3:** **>= 95%** of corpus titles map to a title family; the remainder map to `other` and are listed by title in evidence.
- **Evidence:** `a13-scoring.txt`

### A-18 — Filters and facets never re-judge (carried from FR-005 A-13, extended by B4)
- **Command:** feed API with all facets off, compared against `SELECT count(*) FROM opportunities`; plus the B4 affected-count run
- **Expected:** with **all facets and filters off**, the `include_hidden` total **equals** the row count. With defaults, hidden = red-line hits + excluded-industry hits **only**. A red-line hit with `red_lines` off is shown, still labelled, `decision` and `fit_score` **unchanged**. `track_preference`, `premium_fulltime_onsite` and `stale_postings` each show a **non-zero** affected count on the corpus, or the report states why zero is correct and prints the query that proves it. `target_roles` default is **`rank_only`** after the data migration (Overseer decision, Appendix 5).
- **Evidence:** `a18-filters.txt`

---

## Track C — Founder control

### A-14 — Facet completeness
- **Command:** the C1 facet API tests plus a live enumeration of the facets endpoint
- **Expected:** every attribute named in §2 C1 is present as a facet — work mode, country, city, remote scope, employment type, seniority level, title family, track, source id, employer, posted-within, compensation-stated, decision, fit-score range, language — plus the existing ten filters. Each supports **include**, **exclude**, and **off**; each returns counts; both include and exclude are exercised through the API for **every** facet, not a sample. A saved view round-trips through the database and survives a process restart. **No facet hides anything by default** except red lines and excluded industries.
- **Evidence:** `a14-facets.txt`

### A-15 — Search
- **Command:** the C2 search tests, plus `pytorch -"customer engineer"` over the corpus, plus a timing run over >= 20,000 rows
- **Expected:** the query returns only rows whose indexed text contains `pytorch` and **none** titled Customer Engineer — asserted by inspecting every returned row, with the result count printed. The GIN index is created **by migration `0004`** and is shown present via `pg_indexes`. p95 latency **< 200 ms** over >= 20,000 rows, with the sample size and the p95 figure printed. Results respect facets; a search term saves into a view.
- **Evidence:** `a15-search.txt`

### A-21 — Cards and hidden-reasons audit
- **Command:** the C3/C4 tests, the axe run, and the Playwright keyboard spec
- **Expected:** axe reports **zero** violations at the levels the run configures, and the configured levels are printed. Every field §2 C3 names is present on the card. Keyboard `j/k/o/a/x` are covered by a spec that asserts the resulting state change, not merely that no error was thrown. Screenshots at 360 and 1280 are committed. The dashboard HIDDEN number links to a reason-to-count table with a working one-click unhide, and a facet or red line hiding more than 10% of new rows in a poll raises a visible warning — asserted by a test that constructs that condition.
- **Evidence:** `a21-cards.txt`

---

## Track D — Documents worth sending

### A-10 — Documents generate, on both synthetic packs, DOCX and PDF
- **Command:** for each of the two synthetic packs (shipped template, founder-shaped fixture) and each of the three templates, fetch `cv.docx`, `cv.pdf`, `cover-letter.docx`, `cover-letter.pdf` for three fixture opportunities
- **Expected:** HTTP **200**; DOCX `Content-Type` `application/vnd.openxmlformats-officedocument.wordprocessingml.document` with a body starting `PK`; PDF `application/pdf` with a body starting `%PDF`. Zero validator rejections. The extracted CV text contains an **identity block** (name plus at least one contact channel), **>= 2 bullets per non-internship role**, **education**, **>= 3 certifications**, **projects with URLs**, and **grouped skills** — each asserted by a named check whose count is printed. PDF text extraction passes the committed ATS-parse check (sections detected, dates parsed, no tables). No term from the committed forbidden-inflation list appears unless the pack contains it verbatim.
- **Scope note:** this binds **synthetic** packs only. No session reads the founder's pack, so nothing here is evidence about it.
- **Evidence:** `a10-documents.txt` — **Tier 3: mandatory.**

### A-11 — The truth-lock still locks (guard-neutralisation mutation)
- **Command:** neutralise the validator's uncovered-term guard by hand, run the suites, restore, diff
- **Expected:** neutralisation makes **>= 2** independent suites FAIL (`api.test_api` artifact routes and `matching.test_artifacts_e2e` at minimum, plus any D1 document suite). Restoring yields a **byte-identical** file and all suites green. A claim carrying an unsupported founder term still returns 409 and never document bytes.
- **Binds:** **if A-11 does not pass, A-10 does not close.** A document that generates because the guard stopped guarding is not a delivered document.
- **Evidence:** `a11-mutation.txt` — **Tier 3: mandatory. The Overseer will re-run this.**

### A-22 — Preview
- **Command:** the D2 tests and the Playwright preview spec
- **Expected:** `cv.pdf` streams with `Content-Disposition: inline`. The drawer renders the PDF, switches template, and downloads DOCX — each asserted. The generation cache is keyed on (opportunity, truth-pack hash, template) and a changed pack hash **invalidates** it, asserted by a test that changes the hash.
- **Evidence:** `a22-preview.txt`

---

## Track E — Sources

### A-16 — Source policy compliance (every new source)
- **Command:** the registry validation test plus a table generated from `docs/SOURCE_REGISTRY.yaml` and `SOURCE_EVIDENCE.md`
- **Expected:** for **every** source added in this brief: a registry entry with `policy_status`, a **dated** recon outcome in `SOURCE_EVIDENCE.md`, and robots/terms/rate rules recorded. **Zero** adapters read a source registered `manual_only` or `disabled` — asserted by a test that enumerates the registry and the adapter bindings, not by inspection. **Zero** requests were made to a source that returned 403/429 in the same session, asserted from the transport log. No source gains a `prepare` or `submit` permission in `docs/AGENT_PERMISSIONS.yaml`.
- **Binds:** "coverage is not permission". A blocked source is a recorded outcome, never a workaround.
- **Evidence:** `a16-source-policy.md`

### A-23 — Source breadth, before and after
- **Command:** registry counts before/after; the E1 board-discovery run; the A-9 live poll
- **Expected, each printed:**
  - **>= 300** employment boards live at the end of the brief, filtered to boards with at least one posting in the founder's title families in the last 90 days — the count, the filter, and the seed directories (cited, public) all in evidence;
  - **>= 8 new read-allowed sources** produce rows in the fixture corpus, **including Hacker News and at least one Reddit route**, listed by id with row counts;
  - **>= 2** freelance sources produce rows or are `manual_only` with a working deep link;
  - the tutoring platforms appear in the feed under `track = tutoring` as `platform_application` cards;
  - every `manual_only` source has a deep link reachable from the UI's "Check manually" panel.
- A source that is blocked is `BLOCKED_POLICY` with its evidence, and that is a valid closure under §8. A target not reached is `NOT_CLOSED` with the number actually reached.
- **Evidence:** `a23-breadth.md`

### A-9 — Live poll on `opportunityos_alpha`, zero fixture rows
- **Command:** fresh `opportunityos_alpha`; `py -3.12 scripts/alpha.py up`; poll-now; wait for the worker; capture sources health, the daily dashboard, and page 1 of the feed with `include_hidden=true`
- **Expected:** **zero** rows whose `source_url` matches `example.com`; **zero** ids matching `opp-uq-*`; **zero** `source_id` matching `src-*`. Every `source_id` present is confirmed a registered id by an **executed** `SourceRegistry` probe — not by reading the YAML by eye (FR-005 A-9 asserted registry membership that no probe tested). Per-source record counts reported for every read-allowed source attempted. A 403/429 is **recorded, not retried**. Source counts **before and after** E1-E3 are both reported (breadth delta).
- A zero-opportunity poll is a **PASS** of this claim (the seam ran live and is evidenced) and a separate reported finding about supply — never a licence to fall back to fixtures.
- **Evidence:** `a9-live-poll.txt` — **Tier 3: mandatory.**

---

## Rows the Master expects may not close (recorded now, before the work)

1. **A-23's >= 300 boards.** Board discovery depends on public seed directories remaining reachable and on per-ATS rate limits. Reaching 300 verified boards in one brief is plausible but not assured; the honest closure is the number actually reached.
2. **A-15's p95 < 200 ms over 20k rows.** The corpus is a few hundred payloads; 20k rows must be synthesised, and a local Windows PostgreSQL is not a performance reference.
3. **A-12's < 25% uncertain.** The threshold depends on corpus composition. If the corpus is drawn from sources that genuinely do not state location, the number can be honest and still miss.
4. **A-8 / A-21 / A-22.** Depend on C3 and D2 landing complete; if the drawer ships without the preview, A-22 does not close and A-8 closes minus that spec.
5. **The PR-head half of §8.** `gh` is unauthenticated on this machine and PR creation needs a browser OAuth flow reserved to the founder. If so, "four workflows green on the PR head" cannot be evidenced and §8 is met only in its "green on `main` after merge" half. Recorded here so it is not discovered late.
6. **E2/E3 individual sources.** `BLOCKED_POLICY` per source is a valid closure under §8.
