# BRIEF-FR-005 — Truthful Documents, Honest Scores, Founder-Controlled Filters

**Version:** 1.1 — supersedes the draft `briefs/BRIEF-FR-005.md` committed on `fix/fr-004-erratum` (that draft's D1/D2/D3/D5 map to this brief's D1/D4/D5/D7; its §5 and §9 rules are adopted below verbatim in spirit)
**Date:** 2026-09-02
**Overseer:** external independent auditor (author of the FR-004 review)
**Master:** Claude Code main session, model `opus`
**Status:** ACTIVE (starting main = the merge commit of `fix/fr-004-erratum`; record the actual SHA in pre-flight)
**Merge authority:** per the founder's standing instruction recorded in the FR-004 Addendum, the Master merges once every §8 gate is green. The Overseer reviews post-merge. That Addendum remains a record, not a grant; the authority comes from this brief's own §2 D8, issued by the Overseer at the founder's direction.

---

## 0. Why this brief exists

FR-004 delivered the product surface and, in doing so, exposed three latent defects in frozen engine briefs that fixtures had hidden:

1. **Documents cannot be generated.** The compiler emits composite claims the truth model cannot back, and the validator treats connective words and the target employer's name as claims about the founder. Every realistic pack gets a 409. (BRIEF-004 defect.)
2. **Scores ignore the founder's experience.** The scorer and qualifier read predicates (`responsibility.item`, `achievement.description`, `employment.role_description`, `experience.summary`) that the graph never projects; the graph emits `employment.responsibility` and `achievement.statement`. The "responsibility scope" dimension is a flat 0.50 for every founder. (BRIEF-004 vs BRIEF-002 vocabulary drift.)
3. **The live path is unproven.** FR-004's "really-polled data" was Case U test residue in the test database. No job board has been polled through `poll_source → persist_batch → evaluate_new` on the founder's machine.

And one founder requirement, stated after seeing the product: **nothing may filter opportunities out of view without a visible, switchable control.** The founder deliberately declines to pre-commit to salary floors, project-size limits, or hours; those are on-the-spot decisions. The system's job is to rank and label, and to hide only what the founder has chosen to hide.

The founder's real truth pack now exists (`private/truth_pack.yaml`, loads clean, scores a remote Data Engineer role at 80). This brief ends with the founder running the acceptance script over it, with documents working.

---

## 1. Frozen and unfrozen

- **Frozen:** BRIEF-002 graph semantics (evidence support rule, identity-sensitive predicates), FR-002 fail-closed invariant (A-0 stays 12/12), FR-003 and FR-004 deliverables except where named below.
- **Unfrozen for named deliverables only:** `matching/compiler_employment.py`, `matching/compiler_independent.py`, `truth/validator.py` (D1); `matching/scorer.py`, `matching/qualification.py` (D2, D3); `storage/models.py` + `storage/migrations/` via revision `0003` (D3, D5); `api/routes_api.py`, `web/` (D3); `scripts/alpha.py`, `worker/handlers.py` (D4); `reports/REPORT-FR-004.md` erratum only (D6).
- BRIEF-004's *tests* are not authority: where a compiler or scorer test passes only because a hand-built fixture uses the scorer's private vocabulary, that test is replaced, and the replacement is noted in the report.

---

## 2. Deliverables

### D1 — Documents that generate (ADR-0014: claim classes)
- **Compiler:** every generated claim is atomic — one evidence-bound founder fact per claim. Where prose joins two facts (title + skill), emit two claims, or one claim citing a declared graph relation if one exists. No composite claim is ever emitted without a relation to cite. Narrative connective text (greetings, "I am writing to…", "this role") is emitted as `NARRATIVE` segments, not claims.
- **Validator:** claim text is classified into three term classes before material-term extraction: (a) **founder-claim terms** — must be supported by cited evidence, exactly as today; (b) **opportunity-provenanced terms** — employer name, role title, and any field carried from the `Opportunity` with its own field provenance, admissible when the claim cites that provenance; (c) **connective boilerplate** — a fixed, committed stop-list (`truth/connective_terms.txt`) of function words and letter-form phrases that carry no factual weight. Only class (a) can reject. The tripwire test (`test_artifact_409_never_returns_docx_bytes`) is kept and extended: a claim with an unsupported founder term still 409s; a claim whose only "unsupported" terms are class (b)/(c) does not.
- **Prohibited-concept and red-line checks are unchanged** and still run on the full text including narrative.
- **End-to-end tests** (`matching/test_artifacts_e2e.py`): for each of (i) the shipped synthetic template and (ii) a second synthetic pack shaped like the founder's — nine roles including internships and three concurrent group roles, five certifications, 38 skills, preferences as assertions — compile CV and cover letter against three fixture opportunities (employment remote, employment on-site, procurement) and assert: zero validator rejections; every non-narrative sentence in the DOCX text maps to a claim with evidence ids; no term from a committed "forbidden inflation" list (senior, lead, expert, guaranteed, Fortune 500…) appears unless the pack contains it verbatim.
- **Matrix:** `REQ-ART-001/002/003` PARTIAL → DONE only on that evidence.

**Acceptance:** e2e tests pass; `GET /api/opportunities/{id}/artifacts/cv.docx` returns 200 with DOCX bytes for both packs over fixture opportunities; tripwire still 409s on a deliberately unsupported founder claim. Owner: implementer. **Council: YES (validator semantics).**

### D2 — Scores that see the founder (ADR-0015: predicate contract)
- `truth/predicates.py`: a single committed registry of every predicate the graph projects from profiles plus every assertion predicate the engine reads (`career.target_role`, `preference.track`, `career.goal`, `residence.*`, `preference.fulltime_onsite_premium_monthly`, …). Scorer and qualifier import from it; no string literals.
- Fix the responsibility/achievement mismatch by reading what the graph emits. Contract test: every predicate string referenced in `matching/` is in the registry, and every registry predicate is either projected by `truth/graph.py` from a profile field or listed as assertion-only with the profile section that owns it.
- Re-score the founder-shaped synthetic pack: `responsibility_scope` must no longer be a flat 0.50 when responsibilities exist.
- **Premium full-time rule:** implemented as a *ranking* signal, not a constraint: if the opportunity is full-time and on-site and states compensation below the founder's `preference.fulltime_onsite_premium_monthly` threshold (currency-aware; unknown compensation → `UNKNOWN`, never a penalty), the `compensation_fit` dimension records the gap. Toggleable under D3.

**Acceptance:** contract test passes; scoring the founder-shaped pack against a remote Data Engineer fixture shows `responsibility_scope` > 0.50 with evidence refs; unit tests for the premium rule cover EGP, USD, unknown, and non-full-time cases. Owner: implementer. Council: no (ADR only).

### D3 — Founder-controlled filters (the toggle requirement)
- **Model:** `founder_filter_settings` (migration `0003`): one row per named filter — `filter_id`, `enabled`, `mode` (`hide` | `rank_only` | `label_only`), `params_json`, `updated_at`. Named filters, with defaults:

  | filter_id | source | default enabled | default mode |
  |---|---|---|---|
  | `geo_eligibility` | qualifier hard constraint | on | `label_only` |
  | `work_mode_onsite` | qualifier hard constraint | on | `label_only` |
  | `red_lines` | truth pack red lines | on | `hide` |
  | `excluded_industries` | truth pack | on | `hide` |
  | `track_preference` | preference.track order | on | `rank_only` |
  | `target_roles` | career.target_role | on | `rank_only` |
  | `premium_fulltime_onsite` | D2 rule | on | `rank_only` |
  | `stale_postings` | `is_stale` | on | `label_only` |
  | `min_fit_score` | founder param | off | `hide` |
  | `compensation_floor` | founder param | off | `rank_only` |

  Note the default: the only things hidden by default are the founder's own red lines and excluded industries. Everything else labels or ranks. Qualification decisions (`qualified` / `ineligible` / `UNKNOWN`) are **never changed** by a toggle; a toggle changes only whether the row is hidden, ranked, or merely labelled.
- **API:** `GET /api/filters` (all filters with state and, per filter, the count of currently affected opportunities); `PUT /api/filters/{filter_id}` (`enabled`, `mode`, `params`); `GET /api/opportunities` accepts `?include_hidden=true` and returns, on every item, `hidden_by: [filter_id…]` and `flagged_by: [filter_id…]`. Dashboard adds `hidden_by_filters` to the daily series.
- **Web:** a **Filters** drawer on the feed: one row per filter with an on/off switch, a mode selector, params where applicable, and the live affected-count. Hidden items are reachable via a "Show N hidden" control at the bottom of the feed; each card shows chips for `flagged_by`. Changing a toggle re-queries; no page reload.
- Tests: migration round-trip through `0003`; API tests for each filter's three modes; a test that a red-line hit with `red_lines` toggled off is shown, labelled, and never re-classified; Playwright smoke extended to toggle one filter and see the count change.

**Acceptance:** with all filters off, `GET /api/opportunities?include_hidden=true` total equals the `opportunities` row count; with defaults, hidden = red-line + excluded-industry hits only. Owner: implementer (API + web may be two implementers in worktrees). **Council: YES (migration `0003`, together with D5).**

### D4 — Live-poll proof on a clean database
- `scripts/alpha.py` targets `opportunityos_alpha` (creates it if absent), **refuses** any URL whose database name ends in `_test`, and never attaches to an already-running server without checking the database name.
- On the Master's machine: fresh `opportunityos_alpha`, `alpha.py up`, `POST /api/worker/poll-now`, wait for the worker, then capture `GET /api/sources/health` and `GET /api/dashboard/daily` and the first page of `GET /api/opportunities?include_hidden=true`. Evidence must show per-source record counts from the nine read-allowed sources and **zero** `example.com` / `src-*` / `opp-uq-*` rows. Obey AGENTS.md rate and stop rules; a source that 403s is recorded, not retried.
- Tests: `alpha.py` refuses `_test` databases (unit); an integration test that `persist_batch` from a real adapter fixture produces rows whose `source_id` matches the registry id.

**Acceptance:** evidence file with real source ids and counts; `alpha.py up` against `…/opportunityos_test` exits non-zero. Owner: implementer. Council: no.

### D5 — `field_provenances` primary key
- Migration `0003` adds a surrogate primary key and a unique constraint on (`opportunity_id`, `field_name`, `source_locator`) — or whatever tuple the model actually deduplicates on; the Master decides from the code and records it. `persist_batch` re-run on the same batch leaves provenance row count unchanged (Case U extended to assert the count after the *second* run).

**Acceptance:** Case U extended assertion passes. Owner: implementer. Council: with D3.

### D6 — REPORT-FR-004 erratum (already discharged)
- The erratum, the A-9 evidence correction, the `REQ-ART-001/002/003` downgrade and the four-table disposition were committed on `fix/fr-004-erratum` and merged before this brief started. **Do not redo them.** Pre-flight verifies they are present on `main` (`grep -c 'Erratum 1' reports/REPORT-FR-004.md` ≥ 1; matrix shows ART rows PARTIAL). Add one sentence to that erratum recording the D2 scorer-vocabulary defect as a second latent BRIEF-004 finding.

**Acceptance:** pre-flight check passes; the one added sentence present. Owner: Master. Council: no.

### D7 — Founder acceptance packet (in the report, blank for the founder)
Exact steps: save `private/truth_pack.yaml` (already produced by the Overseer) → `python scripts/truth_check.py` → `python scripts/alpha.py up` → the 13-step script with a result column → download one CV and one cover letter and read every sentence against the CV → open the Filters drawer, turn one filter off, watch the count → **"Opportunities worth opening today: ___"** and **"Sentences in the generated CV I would not have written: ___"**.

### D8 — Matrix, STATE, report, evidence, merge
- Matrix flips with `status_history`; `--check` clean. `reports/REPORT-FR-005.md` per §10. Evidence in `reports/evidence/FR-005/` (synthetic packs only; the founder-shaped synthetic pack is committed under `truth/fixtures/` with obviously fake names). Branch `feat/brief-fr-005-truthful-documents`; PR; **merge when §8 is met**; then regenerate STATE on `main`.

---

## 3. Execution order

```
Pre-flight → D6 (erratum, Master, first commit)
D1 ─┐
D2 ─┼─ Batch A (worktrees; D1 and D2 touch different files)   → implementer ×2
D5 ─┘
D3 (after D2's predicate registry; API and web in separate worktrees)   → implementer ×2
D4 (after D3, needs the filters API for the evidence capture)          → implementer
Integrate → A-0 → full suite on real PG → web build/lint/Playwright → verifier
  → council (D1 validator; D3+D5 migration) → remediate → re-verify → D7/D8 → merge
```

## 4. Roles and model routing
As FR-003/FR-004: Master `opus`; implementer `sonnet` (worktrees); evidence-runner `haiku`; verifier `opus`; council-reviewer `fable`, **two invocations** (D1; D3+D5 together). Explore on `haiku`. D3-web implementer gets `maxTurns` 90.

## 5. Master loop
As FR-003 §5, plus two rules learned in FR-004:
- **An evidence file that depends on a gitignored or machine-local artifact is not evidence.** The verifier must be able to reproduce every green from a fresh clone plus the documented environment.
- **A claim's expected result must state every property the report will later assert about it.** If the report says "real polled data", a claim must have bound where the rows came from. Prose may not assert what no claim tested.

## 6. Environment
As FR-004 §6 (Windows, portable PostgreSQL, Node LTS). Two databases now: `opportunityos_test` for the suite, `opportunityos_alpha` for D4. `private/` remains denied to the agent; the founder's pack is never read by any session.

## 7. Claim ledger — mandatory rows
A-0 probe 12/12 · A-1 suite `Ran N`, OK, 0 skipped, N > 585 · A-2 per-module · A-3 migration `0001→0003` round-trip · A-4 guard + integrity · A-5 STATE zero drift · A-6 scope diff against §1's unfrozen list (a larger observed set is `NOT_CLOSED`, never retro-fitted) · A-7 web build + lint · A-8 Playwright incl. the filter toggle · A-9 live-poll evidence with zero fixture rows · **A-10 documents:** DOCX bytes returned for both synthetic packs, and the extracted text contains no forbidden-inflation term.

## 8. Definition of done
D1–D8 closed or explicitly `NOT_CLOSED` with history; A-0…A-10 PASS by Master and verifier; two council reviews fixed or dispositioned; four workflows green on the PR head and again on `main` after merge; STATE regenerated on `main`; the founder acceptance packet blank and ready.

## 9. Hard stops
As FR-004 §9, plus: **any change that makes a claim validate by putting words into the founder's evidence — editing evidence records, templates, or fixtures so that compiler vocabulary appears in them — is an automatic FAIL of the deliverable**, not a fix. Evidence describes the founder; it is never edited to describe the compiler.

## 10. Report format
As FR-004 §10, plus §7 gains the predicate-contract table (registry vs. projected vs. assertion-only) and §9 is the D7 packet.

## Appendix — Overseer decisions embedded
1. Filters default to *labelling and ranking*, not hiding; only the founder's own red lines and excluded industries hide by default. This encodes the founder's instruction that nothing should filter excessively.
2. Qualification decisions are truth-derived and cannot be toggled; only visibility and ranking can.
3. The premium full-time threshold (50,000 EGP / 1,200 USD monthly) is a ranking signal in the pack, toggleable, never a hard filter.
4. Availability is 2026-10-02 (one month notice) in the pack; it informs deadline reasoning only.
5. The Master merges on §8; the Overseer reviews post-merge.
