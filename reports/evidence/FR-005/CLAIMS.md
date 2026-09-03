# BRIEF-FR-005 — Claim Ledger

Written by the Master **before any implementation delegation**, per §5. Nothing below was
edited after an observation. Where an observation contradicts an expected result, the row is
marked `NOT_CLOSED` and the disagreement is recorded in the report — the expected result is
never rewritten to match what was seen (FR-004 A-6's failure mode).

**Rule adopted from FR-004 Erratum 1.1 and restated in §5:** a claim's expected result must
state every property the report will later assert about it. If the report says "real polled
data", the claim must bind where the rows came from. Prose may not assert what no claim tested.

**Rule adopted from §5:** an evidence file that depends on a gitignored or machine-local
artifact is not evidence. Every green must reproduce from a clean clone plus the documented
environment.

---

## Vocabulary bindings (fixed before delegation, so nothing drifts mid-brief)

These are the exact spellings the code uses. Any claim below that names a value uses these.

| Concept | Binding | Source |
|---|---|---|
| Decision level | `qualified` \| `ineligible` \| `uncertain` — **lowercase**, never `UNKNOWN` | `matching/models.py` |
| Constraint level | `HardConstraintResult.passed` is `bool \| None`; `None` is the unknown | `matching/models.py` |
| Constraint serialization | `outcome` is `"PASS"` \| `"FAIL"` \| `"UNKNOWN"` — **uppercase** at the API boundary only | `api/serialization.py:142-151` |
| Fit score scale | `fit_score` is **0–100** (`overall_fit_score`) | `matching/models.py` |
| Dimension score scale | `MatchDimensionScore.raw_score` is **0–1** | `matching/scorer.py` |
| Dimension field names | `dimension_name`, `raw_score`, `weight`, `weighted_score`, `explanation` | `matching/scorer.py` |
| Validator result | `ClaimVerificationResult.allowed` (bool), `.reasons` (tuple) | `truth/models.py:615-636` |
| Provenance column | `raw_pointer`, **not** `source_locator` | `storage/models.py:47-60` |
| Alembic head before this brief | `0002_match_evaluations` | `storage/migrations/versions/` |

**A note on `source_locator`.** §2 D5 of the brief names a unique constraint on
(`opportunity_id`, `field_name`, `source_locator`) "or whatever tuple the model actually
deduplicates on; the Master decides from the code and records it." The model has no
`source_locator`; the corresponding column is `raw_pointer`, and it is **nullable**, which
makes it unusable in a PostgreSQL unique constraint (NULLs do not collide, so duplicates
would still be admitted). The Master's decision, recorded here before implementation:
the unique tuple is **(`opportunity_id`, `field_name`, `record_checksum`)**, all three
`NOT NULL` today. Rationale in the report §7.

---

## Claims

Every row is executed by the Master, then independently re-executed by the `verifier` in a
fresh context. Both must PASS before the row closes.

### A-0 — Fail-closed persistence invariant (frozen from FR-002)
- **Command:** `python -m unittest storage.test_fail_closed -v`
- **Expected:** `Ran 12 tests`, `OK`, 0 skipped. `ProductionDatabaseConfigurationError` still raised when `OPPORTUNITYOS_DB_URL` is absent; no SQLite fallback anywhere.
- **Binds:** that this brief did not weaken the FR-002 invariant while touching `scripts/alpha.py` (D4), which is the module most likely to reintroduce a fallback.

### A-1 — Full suite on real PostgreSQL
- **Command:** `python -m unittest discover -v` with `OPPORTUNITYOS_DB_URL` pointing at `opportunityos_test`
- **Expected:** `Ran N tests`, `OK`, **0 skipped**, and **N > 585** (FR-004's count). The count is stated in the report exactly as printed.
- **Binds:** no test was deleted to make the suite pass, and no test is silently skipped for a missing dependency.

### A-2 — Per-module test counts
- **Command:** `python -m unittest discover -s <module> -v` for each of truth, outbound, scripts, recon, opportunity, matching, storage, api, worker, inbox, core, security, feedback
- **Expected:** a per-module table whose sum equals A-1's N. New modules (`truth/test_predicates.py`, `matching/test_artifacts_e2e.py`) appear with non-zero counts.
- **Binds:** that A-1's growth is where this brief claims it is, not concentrated in one trivially-parameterised file.

### A-3 — Migration round-trip `0001 → 0003`
- **Command:** `alembic upgrade head` (3 revisions), `alembic downgrade base` (3), `alembic upgrade head` (3), each exit 0, against a scratch database that starts empty
- **Expected:** 3 up, 3 down, 3 up, all exit 0. Head is `0003_*`. `field_provenances` carries the unique constraint after upgrade and does not after downgrade.
- **Binds:** `0003` is genuinely reversible, and the D5 constraint is created and dropped by it rather than pre-existing.

### A-4 — Guard boundary and repository integrity
- **Command:** `python scripts/check_guard.py --allow-missing-patterns` and `python scripts/check_repository.py`
- **Expected:** both exit 0. No hard-coded secret-shaped literal in any new file; no mirrored PII.
- **Binds:** the new fixture pack (D1) contains no real personal data, and `truth/connective_terms.txt` does not trip the guard.

### A-5 — STATE regenerates with zero drift
- **Command:** `STATE_PRESERVE_TIMESTAMP=1 python scripts/generate_state.py && git diff --exit-code -- docs/STATE.md`
- **Expected:** exit 0. The final commit of the branch touches `docs/STATE.md` **alone**, so `source_head()` resolves past it.
- **Binds:** the FR-004 ordering defect (committed twice) is not repeated.

### A-6 — Scope diff against §1's unfrozen list
- **Command:** `git diff --name-only main...HEAD`
- **Expected:** every changed path is either (a) named in §1's unfrozen list, (b) a *new* file created by a deliverable, or (c) a report/evidence/matrix/STATE path. **A larger observed set is `NOT_CLOSED`, never retro-fitted.** The expected set is written out in full in the evidence file before the diff is run.
- **Binds:** the Master did not quietly widen the brief. FR-004 failed this row and marked it PASS; that is the precedent this row exists to avoid repeating.

### A-7 — Web build and lint
- **Command:** `npm ci && npm run build && npm run lint` in `web/`
- **Expected:** build exit 0 with the route list printed; `eslint --max-warnings=0` clean. Routes are `/` and `/login` only (the Filters drawer is a component on `/`, not a new route).
- **Binds:** D3's web work did not add an unreviewed page.

### A-8 — Playwright including the filter toggle
- **Command:** `npx playwright test` in `web/`, from a **clean checkout** with no untracked env file
- **Expected:** all specs pass. At least one spec toggles a filter and asserts the affected-count changes and the feed re-queries. Trace saved.
- **Binds:** the FR-004 defect where a green depended on a gitignored `web/.env.local`. The verifier must reproduce this from a fresh clone.

### A-9 — Live-poll evidence with zero fixture rows
- **Command:** fresh `opportunityos_alpha`; `python scripts/alpha.py up`; `POST /api/worker/poll-now`; wait for the worker; capture `GET /api/sources/health`, `GET /api/dashboard/daily`, and page 1 of `GET /api/opportunities?include_hidden=true`
- **Expected:** the captured feed contains **zero** rows whose `source_url` matches `example.com`, **zero** ids matching `opp-uq-*`, and **zero** `source_id` values matching `src-*`. Every `source_id` present is a real registry id from `docs/SOURCE_REGISTRY.yaml`. Per-source record counts are reported for the read-allowed sources actually attempted. A source returning 403/429 is **recorded, not retried**.
- **Binds:** exactly the property FR-004's prose asserted and no claim tested. This row states the provenance of the rows, not just that a transcript exists. If the poll yields zero opportunities from every source, that is a **PASS of this claim** (the seam ran live and is evidenced) and a separate, reported finding about supply — it is not a licence to fall back to fixtures.

### A-10 — Documents generate
- **Command:** for each of the two synthetic packs (shipped template, founder-shaped fixture), `GET /api/opportunities/{id}/artifacts/cv.docx` and `/cover-letter.docx` against three fixture opportunities
- **Expected:** HTTP **200** with `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document` and a body starting with the ZIP magic `PK`. Zero validator rejections. The extracted DOCX text contains **no** term from the committed forbidden-inflation list unless the pack contains that term verbatim.
- **Binds:** the capability FR-004 recorded as NOT_CLOSED. Note this claim is over **synthetic** packs only; it does **not** bind anything about the founder's own pack, which no session reads.

### A-11 — The tripwire still fires (anti-regression on the safety property)
- **Command:** `python -m unittest api.test_api -k tripwire -v` plus the extended cases
- **Expected:** a claim carrying an **unsupported founder term** still returns 409 and never DOCX bytes. A claim whose only uncovered terms are opportunity-provenanced or connective returns 200. Neutralising the validator makes the tripwire **fail**.
- **Binds:** that D1 relaxed the validator along the axis the brief authorised and no other. This is the row that would catch the §9 hard stop being violated. **If A-11 cannot pass while A-10 passes, A-10 does not close** — a document that generates because the guard stopped guarding is not a delivered document.

### A-12 — Predicate contract
- **Command:** `python -m unittest truth.test_predicates -v`
- **Expected:** every predicate string referenced in `matching/` is in the registry; every registry predicate is either projected by `truth/graph.py` from a profile field or declared assertion-only with the owning pack section. Scoring the founder-shaped pack against a remote Data Engineer fixture yields `responsibility_scope` **> 0.50** with non-empty `evidence_refs`.
- **Binds:** the D2 defect is fixed by reading what the graph emits, not by adding the orphan spellings to the graph.

### A-13 — Filters
- **Command:** `GET /api/opportunities?include_hidden=true` with all filters disabled, compared against `SELECT count(*) FROM opportunities`
- **Expected:** with **all filters off**, the returned total **equals** the `opportunities` row count. With **defaults**, hidden = red-line hits + excluded-industry hits **only**. A red-line hit with `red_lines` toggled off is **shown**, still **labelled**, and its `decision` is **unchanged** — no toggle ever re-classifies.
- **Binds:** the founder's stated requirement that nothing filters opportunities out of view without a visible, switchable control, and the Appendix rule that qualification decisions are not toggleable.

### A-14 — Provenance idempotency
- **Command:** `python -m unittest storage.test_postgres_integration -k case_u -v`
- **Expected:** `persist_batch` re-run on the same batch leaves the `field_provenances` row count **unchanged**, asserted after the **second** run (FR-004 asserted only after the first).
- **Binds:** D5.

---

## Rows the Master expects may not close

Recorded now, before the work, so that a later NOT_CLOSED is not read as a surprise or as a
retro-fit:

1. **A-9 may find little or nothing.** BRIEF-001 measured 8 eligible in 2,472. Nine
   read-allowed sources on one machine on one day may return few rows or none. The claim is
   written so that an honest empty result passes it.
2. **A-8's filter-toggle spec** depends on D3's web work landing complete. If the drawer
   ships without the affected-count, A-8 closes and A-13 does not.
3. **The PR-head half of §8.** `gh` is not authenticated on this machine and PR creation may
   be unavailable. If so, "four workflows green on the PR head" cannot be evidenced, and §8
   is met only in its "green on `main` after merge" half. This is a §8 gate property, not a
   deliverable, and it is recorded here so it is not discovered late.
