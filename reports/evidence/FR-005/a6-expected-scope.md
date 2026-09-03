# A-6 — Expected scope set

**Written by the Master before `git diff --name-only main...HEAD` was run for the first
time.** This is the closed set the observation will be compared against. If the observed set
is larger, A-6 is `NOT_CLOSED` and the extra paths are dispositioned in the report — the set
below is **never** edited to admit something after it was seen. FR-004 failed exactly this
row and recorded it as PASS; that is the precedent this file exists to avoid repeating.

Timestamp of writing: before any Batch A implementer had reported.

---

## 1. Carried from the unmerged `fix/fr-004-erratum` branch

`main` is `b563102` and does **not** contain the FR-004 erratum: that branch was never merged
because `gh` lost its authentication and PR creation was unavailable. This branch is based on
it, so `main...HEAD` necessarily shows those commits too. Expected, and declared here rather
than explained away later:

- `.gitignore`
- `briefs/BRIEF-FR-005.md`
- `reports/REPORT-FR-004.md`
- `reports/FOUNDER_READINESS_MATRIX.json`
- `reports/FOUNDER_READINESS_MATRIX.md`
- `reports/evidence/FR-004/a9-alpha-transcript.txt`
- `docs/STATE.md`

## 2. Named in §1's unfrozen list

- `matching/compiler_employment.py` (D1)
- `matching/compiler_independent.py` (D1)
- `truth/validator.py` (D1)
- `matching/scorer.py` (D2, D3)
- `matching/qualification.py` (D2, D3)
- `storage/models.py` (D3, D5)
- `storage/migrations/versions/0003_provenance_identity.py` (D3, D5 — one revision, shared)
- `api/routes_api.py` (D3)
- `web/**` (D3)
- `scripts/alpha.py` (D4)
- `worker/handlers.py` (D4)
- `reports/REPORT-FR-004.md` (D6 — erratum only; already listed in §1 above)

## 3. New files created by a deliverable

- `truth/connective_terms.txt` (D1)
- `matching/test_artifacts_e2e.py` (D1)
- `docs/adr/ADR-0014-claim-classes.md` (D1)
- `truth/predicates.py` (D2)
- `truth/test_predicates.py` (D2)
- `docs/adr/ADR-0015-predicate-contract.md` (D2)
- `reports/REPORT-FR-005.md` (D8)
- `reports/evidence/FR-005/**` (D8)

## 4. Test files a deliverable is required to change

§1 line 30 states that BRIEF-004's tests are not authority and that a test passing only
because its fixture speaks the scorer's private vocabulary is to be replaced. That licence
implies these, which are therefore expected:

- `truth/fixtures.py` (D1 — one added founder-shaped pack; existing fixtures untouched)
- `matching/test_compiler.py` (D1)
- `api/test_api.py` (D1 tripwire, D3 filter routes)
- `matching/test_scorer.py` (D2)
- `matching/test_qualification.py` (D2)
- `storage/test_postgres_integration.py` (D5 Case U)
- `scripts/test_alpha.py` (D4 — the `_test` refusal unit test)
- `opportunity/test_persistence.py` (D5, if dedup changes `persist_batch`)

## 5. Paths the Master expects to need but §1 does not name

Declared **in advance** as anticipated scope deviations, so that if they appear they are a
disposition rather than a discovery:

- **`api/serialization.py`** — D3 requires `hidden_by` and `flagged_by` on every feed item
  and `hidden_by_filters` on the daily series. §1 unfreezes `api/routes_api.py` but the item
  shape lives here. Expected.
- **`opportunity/persistence.py`** and/or **`storage/repository.py`** — D5 requires
  re-persist to be idempotent, not merely constrained. A unique constraint alone converts a
  duplicate into an `IntegrityError`, which is a crash rather than idempotency, so the write
  path very likely must change. Expected.
- **`matching/models.py`** — D1 may need a narrative-segment marker. The implementer was
  told this file is out of scope and to report a scope question rather than edit it. If it
  appears, it is a **failure of instruction**, not an expected path.

## 6. Explicitly NOT expected — appearance here is a finding

- `truth/graph.py`, `truth/models.py` — BRIEF-002 semantics, frozen. D2's fix direction is
  one-way: `matching/` must read what the graph emits. If either appears, D2 fixed the defect
  from the wrong end.
- `truth/ingest.py` — the relation-ordering defect noted in FR-004's next-prerequisites is
  real and is **not** in this brief.
- `storage/migrations/versions/0001_baseline_schema.py`, `0002_match_evaluations.py` —
  released revisions.
- `storage/migrations/versions/0004_*` — the brief requires one shared `0003`.
- `docs/MASTER_PLAN.md`, `docs/PRODUCT_CONSTITUTION.md` — §0 non-goal.
- `AGENTS.md`, `CLAUDE.md` — governing documents; a branch under review does not widen its
  own authority.
- Anything under `private/`.
