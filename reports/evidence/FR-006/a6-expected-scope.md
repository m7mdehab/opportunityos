# A-6 — Expected scope set

**Written by the Master before `git diff --name-only main...HEAD` was run for the first time**,
and before any implementer had reported. This is the closed set the observation is compared
against. If the observed set is larger, A-6 is `NOT_CLOSED` and the extra paths are
dispositioned in the report — the set below is **never** edited to admit something after it was
seen. FR-004 failed this row and recorded it as PASS; FR-005 recorded it honestly as
`NOT_CLOSED` with 8 of 83 paths outside the set. This file exists so the third brief in a row
does not have to discover the rule again.

Starting `main` = `bf25d93`.

---

## 1. Named in §1's unfrozen list

- `opportunity/**` — adapters, normalization, models, persistence, pipeline, registry, dedupe (A1, A2, E1-E3)
- `matching/scorer.py`, `matching/qualification.py`, `matching/compiler_employment.py`,
  `matching/compiler_independent.py`, `matching/artifact_validation.py`,
  `matching/binary_export.py`, `matching/ats_quality.py`, `matching/models.py`,
  `matching/mapping.py` (B, D)
- `api/**` (C, D)
- `web/**` (C, D)
- `storage/models.py` and `storage/migrations/versions/0004_*.py` (A, C, D2)
- `storage/repository.py` — persistence of the new columns and the facet/saved-view tables
- `worker/handlers.py`, `worker/scheduler.py`, `worker/__main__.py` (E4, F3)
- `docs/SOURCE_REGISTRY.yaml` and `recon/**` (E)
- `truth/predicates.py` (D/F1 identity predicates)
- `truth/ingest.py`, `truth/models.py`, `truth/graph.py` — **only** for the new `identity` and
  `approved_phrases` sections named by F1. Any other change to these three is a finding.
- `docs/templates/truth_pack.template.yaml`, `scripts/truth_check.py` (F1)
- `scripts/dev_env.py`, `scripts/alpha.py` (F2)

## 2. Governance and generated paths

- `docs/AGENT_EXECUTION_PROTOCOL.md`, `AGENTS.md` (D0 — the one authorised AGENTS.md line)
- `.claude/agents/*.md` (D0, Appendix B)
- `briefs/BRIEF-FR-006.md`
- `docs/adr/ADR-0016-*.md` (B1), `docs/adr/ADR-0017-*.md` (D1)
- `reports/REPORT-FR-006.md`, `reports/evidence/FR-006/**`
- `reports/FOUNDER_READINESS_MATRIX.json` and `.md` (F4)
- `docs/STATE.md` (generated, final commit alone)
- `docs/SOURCE_EVIDENCE.md` (E recon outcomes)
- `docs/AGENT_PERMISSIONS.yaml` — **read-only additions only**; a `prepare` or `submit`
  permission appearing here is a hard stop, not a scope deviation.

## 3. New files a deliverable creates

- `opportunity/inference_rules.yaml` and its test (A1)
- `opportunity/fixtures/**` — the committed raw-payload corpus (A1)
- `opportunity/clustering.py` (A2)
- `opportunity/discovery/boards.py` and the generated board registry entries (E1)
- `matching/title_families.yaml` (B3)
- `matching/seniority.py` (B1)
- `matching/document_model.py` and the three ATS templates (D1)
- `api/facets.py`, `api/search.py`, `api/saved_views.py` (C1, C2)
- `private/watchlist.yaml.template` — the **template** is tracked; `private/watchlist.yaml`
  itself is never tracked and never read by an agent.
- New `test_*.py` beside each of the above

## 4. Test files a deliverable is required to change

§1 states that BRIEF-003/004 tests passing only on fixtures shaped to the old behaviour are
replaced, and each replacement is listed in the report. That licence covers:

- `matching/test_scorer.py`, `matching/test_qualification.py`, `matching/test_adversarial.py`
- `opportunity/test_normalization.py`, `opportunity/test_adapters.py`,
  `opportunity/test_models.py`, `opportunity/test_persistence.py`
- `api/test_api.py`, `storage/test_postgres_integration.py`
- `truth/test_predicates.py`, `truth/fixtures.py` (F1 identity block on the founder-shaped pack)
- `matching/test_compiler.py`, `matching/test_artifacts_e2e.py`, `matching/test_binary_export.py`
- `web/tests/e2e/**`, `web/eslint.config.mjs`

## 5. Paths the Master expects to need but §1 does not name

Declared **in advance** as anticipated deviations, so that if they appear they are a
disposition rather than a discovery:

- **`scripts/backup_restore.py`** — adding a table to `Base.metadata` trips the
  backup-completeness invariant from BRIEF-FR-003. `0004` adds several. This bit FR-005 and
  is declared here rather than rediscovered. Expected.
- **`api/settings.py`** — new facet/search settings very likely need a home. Expected.
- **`pyproject.toml`** — only if a genuinely new dependency is required. The Master has
  already ruled that reportlab covers PDF, so a new dependency here needs a reason in the
  report. Expected but disfavoured.
- **`.gitignore`** — the corpus and digest output directories. Expected.
- **`docs/MASTER_PLAN.md`** — the readiness-matrix rows F4 touches may reference it. If it
  appears, it is a disposition; the plan's content is not rewritten by a brief under review.

## 6. Explicitly NOT expected — appearance here is a finding

- `truth/validator.py` — the truth-lock. D1 makes documents prettier by **selection and
  ordering**; if the validator changed, the suspicion is that the lock was loosened to make a
  document look better, which §9 makes a hard stop. Any change here must be justified line by
  line in the report and must survive A-11.
- `truth/connective_terms.txt` — same reasoning. Adding words here weakens guard 9.
- `storage/migrations/versions/0001_*`, `0002_*`, `0003_*` — released revisions.
- `storage/migrations/versions/0005_*` or later — the brief requires exactly one `0004`.
- `docs/PRODUCT_CONSTITUTION.md` — non-negotiable rules; a brief does not widen its own authority.
- `CLAUDE.md` — governing document.
- Anything under `private/` other than the tracked `.template` file.
- `.github/workflows/**` — a branch under review does not edit the checks that judge it.
