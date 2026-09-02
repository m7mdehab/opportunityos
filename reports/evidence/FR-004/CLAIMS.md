# BRIEF-FR-004 — Claim ledger

Written **before** any delegation, per §5 step 1. No acceptance command in this file was
authored after seeing a result.

**Pre-flight recorded:** starting `main` = `8423fcb1a97914e9802c17ed60e0e873d68fe88f`
("Merge pull request #67 from m7mdehab/feat/brief-fr-003-reality-refresh") — the FR-003 merge
commit, as §0/§3 require. All five workflows green on it. Working tree clean apart from the
untracked `opportunityos.egg-info/` build artifact. Branch
`feat/brief-fr-004-founder-alpha-local` cut from that commit.

**Environment prelude.** Every command below is run from the repository root in Git Bash with:

```bash
export PATH="/c/Users/M7mdEhab/AppData/Local/Programs/Python/Python312:$PATH"
export OPPORTUNITYOS_DB_URL="postgresql+psycopg2://opportunityos:testpassword123@127.0.0.1:5432/opportunityos_test"
```

Python 3.12.10; PostgreSQL 16.10 from the portable cluster under `%LOCALAPPDATA%\opos-pg\`
(reused, not re-downloaded, per §6); Node v24.18.0 and npm 11.16.0 already present on the host
(no install required — recorded for §10 §4). `PATH` additionally carries
`%LOCALAPPDATA%\opos-gh\bin` for `gh`, authenticated from the founder's existing Git Credential
Manager token via `GH_TOKEN` only, never written to the tree.

**Verdict columns.** `Master` = this session re-running the command itself after the implementer
returned. `Verifier` = an independent `verifier` session in a fresh context, given the brief, this
ledger, the code and the tests, told neither what the implementer nor what the Master concluded,
and barred from reading the report. Both must PASS for a claim to count as closed (§5 step 7).

---

## Vocabulary bindings fixed before delegation

The brief writes `UNKNOWN`; the codebase has two distinct things under that word, and conflating
them would be a defect. Bound here so every deliverable uses the same mapping:

- **Decision level.** `QualificationDecision` is `qualified | ineligible | uncertain`. The brief's
  "`UNKNOWN` is stored as `UNKNOWN`, never coerced" binds to `uncertain`, persisted verbatim as
  the string `uncertain` and never rewritten to `ineligible`.
- **Constraint level.** `HardConstraintResult.passed` is `bool | None`, where `None` means
  unknown. D6 and D7 render `None` as `UNKNOWN`, visually and structurally distinct from `False`
  (`FAIL`).
- **Score scale.** `MatchEvaluation.overall_fit_score` is `0.0–100.0`, not `0–1`. The brief's
  "default 0.7" high-fit threshold binds to `70.0` on that scale, via
  `OPPORTUNITYOS_HIGH_FIT_THRESHOLD` (default `70.0`). `min_score` in the list query uses the
  same scale.
- **Feedback labels.** `FeedbackLabel` is the committed vocabulary
  (`good_match`, `bad_match`, `eligibility_wrong`, `seniority_wrong`, `irrelevant_role`,
  `source_quality_issue`, `duplicate_issue`, `review_required`). D7's five buttons bind to
  `good_match`, `bad_match`, `eligibility_wrong` ("not eligible"), `irrelevant_role`
  ("wrong track") and `duplicate_issue` ("duplicate"). No new label value is introduced.
- **Artifact rejection.** `compile_tailored_cv` / `compile_cover_letter` do not raise on a
  prohibited claim; `ClaimValidator.validate_claim` returns `ClaimVerificationResult` with
  `allowed=False` and `reasons` (corrected after the fact — this cell originally named
  `verified`/`rejection_reasons`, which do not exist on `truth/validator.py`'s
  `ClaimVerificationResult`). D6's 409 is therefore produced by the API validating
  every generated claim and refusing to export when any is unverified — the document is never
  built, per §2 D6 "never a document".
- **Head revision.** The current Alembic head is `0001_baseline_schema`. D4's "downgrade 0001"
  binds to that revision id.

### Amendment, before D4 and D6 were delegated

The brief names **one** new table for migration `0002`, but three D6 responses cannot be
answered from the committed schema, so the D4 rows below were widened before that deliverable
was delegated and before any D4 result existed. Recorded here rather than quietly applied:

| Table | The named requirement that forces it |
|---|---|
| `match_evaluations` | D4, named in the brief |
| `source_poll_runs` | `GET /api/sources/health` — "last poll, last status, last record count" — and the dashboard's `fetched` |
| `founder_opportunity_views` | the dashboard's `opened` |
| `founder_triage_states` | `dismiss` and `snooze` |

`ActionStatus` is `planned | prepared | awaiting_review | submitting | submitted | confirmed |
failed | unknown_outcome | blocked`. It has no `dismissed` or `snoozed`, and no home for a
snooze `until`. Forcing them in — say, as `blocked` with a `blocker_reason` — would corrupt a
vocabulary that records what the *system* did about a submission, not what the founder chose to
triage. Nothing at all persists poll outcomes or detail-view opens today. Each added table is
the minimum needed by a route the brief names; all four are single-workspace with no tenant key,
consistent with ADR-0012; and the whole migration goes to the council review D4 already requires.

The API contract both D6 and D7 are built against was likewise fixed by the Master before either
was delegated, so the two sides agree by construction rather than by later reconciliation.

---

## Ledger

| ID | Claim | Command | Expected | Master | Verifier |
|---|---|---|---|---|---|
| **D1-1** | Stale-lease reclaim increments `retry_count` and dead-letters a poison job | `python -m unittest worker.test_worker -v 2>&1 \| tail -3` | `OK`, and `test_stale_lease_reclaim_dead_letters_poison_job` present in the verbose listing | | |
| **D1-2** | That test is load-bearing | Revert only the reclaim-side `retry_count` increment in `worker/queue.py` in a scratch copy; re-run D1-1 | The reclaim test FAILS; restore leaves it passing | | |
| **D1-3** | `claim_hook` is optional and unused in production callers | `grep -n "claim_hook" worker/queue.py worker/runner.py worker/__main__.py` | present in `worker/queue.py` signature; **no match** in `runner.py` or `__main__.py` | | |
| **D1-4** | Case S is deterministic, 20 consecutive runs | `for i in $(seq 1 20); do python -m unittest storage.test_postgres_integration.PostgresProductionIntegrationTest.test_case_s_worker_runner_end_to_end 2>&1 \| tail -1; done \| sort \| uniq -c` | exactly `20 OK`, no `FAILED` line | | |
| **D1-5** | Case S no longer depends on a wall-clock sleep | `grep -nE "sleep\(0?\.03\)\|time\.sleep" storage/test_postgres_integration.py` | no in-flight `time.sleep` remains inside the Case S handler | | |
| **D2-1** | Column-level backup completeness is enforced | `python -m unittest scripts.test_backup_restore -v 2>&1 \| tail -3` | `OK`, and `test_restore_refuses_dump_with_column_delta` present | | |
| **D2-2** | The refusal names the missing column | Run the column-delta test with `-v` and capture the assertion text | `BackupCompletenessError` message contains the added column name | | |
| **D2-3** | Dump header carries per-table column lists | `python - <<'PY'` dumping a fixture DB and printing `header["columns"]` keys | every `Base.metadata` table name present, each mapping to its column list | | |
| **D2-4** | Case M still passes | `python -m unittest storage.test_postgres_integration.PostgresProductionIntegrationTest.test_case_m_backup_wipe_restore_postgres_cycle 2>&1 \| tail -1` | `OK` | | |
| **D3-1** | `persist_batch` unit tests pass | `python -m unittest opportunity.test_persistence -v 2>&1 \| tail -3` | `OK` | | |
| **D3-2** | Re-running one batch inserts nothing (idempotent on `content_hash`) | Case U: `python -m unittest storage.test_postgres_integration.PostgresProductionIntegrationTest.test_case_u_poll_source_persists_idempotently 2>&1 \| tail -1` | `OK` | | |
| **D3-3** | Provenance rows land with the opportunity | Inside Case U, assert `field_provenances` count > 0 for the persisted opportunity | assertion present and passing | | |
| **D3-4** | A changed posting updates `is_stale` / `reverified_at` rather than duplicating | Case U asserts the re-verification path on a mutated payload | assertion present and passing | | |
| **D3-5** | `python -m worker --once` leaves rows in `opportunities` | Enqueue one fixture `poll_source`, run `python -m worker --once`, then `SELECT count(*) FROM opportunities;` | count > 0 | | |
| **D4-1** | Migration `0002` round-trips | `alembic upgrade head && alembic downgrade 0001_baseline_schema && alembic upgrade head` | exit 0 each step, no error output | | |
| **D4-2** | All four `0002` tables exist at head and are gone at `0001` | `psql -tAc` counting `information_schema.tables` for `match_evaluations`, `source_poll_runs`, `founder_opportunity_views`, `founder_triage_states` after each step | `4` at head, `0` after downgrade, `4` again | | |
| **D4-2b** | `0002` adds exactly those four tables and touches no existing one | table-set diff of `information_schema.tables` across the upgrade | exactly the four added; no existing table altered or dropped | | |
| **D4-3** | Uniqueness on (`opportunity_id`, `truth_pack_hash`) is enforced by the database | `psql -tAc` on `information_schema.table_constraints` / `pg_indexes` for the unique constraint | unique constraint present | | |
| **D4-4** | Case A/B migration smoke still passes | `python -m unittest storage.test_postgres_integration.PostgresProductionIntegrationTest.test_case_a_and_b_alembic_upgrade_downgrade_smoke 2>&1 \| tail -1` | `OK` | | |
| **D4-5** | Case V: evaluate_new persists decisions; a new truth hash adds a row and leaves the first intact | `python -m unittest storage.test_postgres_integration.PostgresProductionIntegrationTest.test_case_v_evaluate_new_persists_match_evaluations 2>&1 \| tail -1` | `OK` | | |
| **D4-6** | `uncertain` is stored verbatim, never coerced | `python -m unittest matching.test_evaluate_persist -v 2>&1 \| tail -3` plus `grep -n "uncertain" matching/evaluate_persist.py` | `OK`; no branch rewrites `uncertain` to `ineligible` | | |
| **D5-1** | `load_founder_pack` unit tests pass | `python -m unittest truth.test_pack -v 2>&1 \| tail -3` | `OK` | | |
| **D5-2** | The shipped template loads with zero validator errors | `python -m unittest truth.test_pack.TruthPackTemplateTest 2>&1 \| tail -1` | `OK` | | |
| **D5-3** | `truth_check.py` exits 0 on a valid pack | `cp docs/templates/truth_pack.template.yaml "$TMP/tp.yaml" && python scripts/truth_check.py --path "$TMP/tp.yaml"; echo "exit=$?"` | `exit=0` | | |
| **D5-4** | `truth_check.py` exits 1 with findings on a broken pack | Corrupt a required field in the temp copy, re-run | `exit=1` and the findings are printed | | |
| **D5-5** | Neither the loader nor the checker prints field values | `python scripts/truth_check.py --path "$TMP/tp.yaml"` output grepped for a distinctive template value | **no match** for the synthetic name/employer string | | |
| **D5-6** | `truth_check.py` never touches `private/` when `--path` is given | `grep -n "private" scripts/truth_check.py` | only the documented default path constant, and it is not read when `--path` is passed | | |
| **D6-1** | App refuses to start with `OPPORTUNITYOS_DB_URL` missing | unset it, `python -c "from api.app import create_app; create_app()"`; `echo "exit=$?"` | non-zero exit, message names the variable | | |
| **D6-2** | App refuses to start with `OPPORTUNITYOS_FOUNDER_PASSWORD` missing | same shape | non-zero exit, message names the variable | | |
| **D6-3** | App refuses to start with `OPPORTUNITYOS_SESSION_SECRET` missing | same shape | non-zero exit, message names the variable | | |
| **D6-4** | Every non-auth route is 401 without a session | `python -m unittest api.test_api.AuthFailClosedTest -v 2>&1 \| tail -3` | `OK`; the test enumerates the router's own route table, not a hand-written list | | |
| **D6-5** | Login / logout / me round-trip | `python -m unittest api.test_api.AuthSessionTest 2>&1 \| tail -1` | `OK` | | |
| **D6-6** | Password compare is constant-time and login is rate-limited to 5/min | `python -m unittest api.test_api.AuthRateLimitTest 2>&1 \| tail -1` plus `grep -n "compare_digest" api/` | `OK`; `hmac.compare_digest` used | | |
| **D6-7** | List and detail routes serve fixture data | `python -m unittest api.test_api.OpportunityRoutesTest 2>&1 \| tail -1` | `OK` | | |
| **D6-8** | Artifact route returns a document on a clean fixture and **409** on a prohibited claim | `python -m unittest api.test_api.ArtifactRoutesTest -v 2>&1 \| tail -3` | `OK`; the 409 body carries the rejection reasons and no docx bytes | | |
| **D6-9** | Feedback and founder-attested actions persist | `python -m unittest api.test_api.FeedbackAndActionTest 2>&1 \| tail -1` | `OK` | | |
| **D6-10** | No idempotency reservation is consumed by a founder-attested action | Inside `FeedbackAndActionTest`, assert `idempotency_reservations` row count unchanged | assertion present and passing | | |
| **D6-11** | Dashboard counts are correct over a seeded 3-day fixture | `python -m unittest api.test_api.DashboardTest 2>&1 \| tail -1` | `OK` | | |
| **D6-12** | Truth status / reload handles a valid and an invalid pack | `python -m unittest api.test_api.TruthRoutesTest 2>&1 \| tail -1` | `OK` | | |
| **D6-13** | Sources health and poll-now | `python -m unittest api.test_api.SourcesAndWorkerTest 2>&1 \| tail -1` | `OK`; poll-now enqueues only read-allowed sources | | |
| **D6-14** | Live smoke against a running server | start `uvicorn` with all three vars, then `curl` `/api/auth/me`, login, `/api/opportunities` | `401`, `200`, `200` | | |
| **D6-15** | No PII in logs | Run the D6-14 smoke with logging captured; grep the log for the fixture founder's name and the session cookie value | **no match** for either | | |
| **D7-1** | `npm run build` clean | `cd web && npm run build 2>&1 \| tail -5` | exit 0, no error | | |
| **D7-2** | `npm run lint` clean | `cd web && npm run lint 2>&1 \| tail -5` | exit 0, no warnings-as-errors | | |
| **D7-3** | Both pages are axe-clean | the axe run the Master installs, over `/login` and `/` | 0 violations | | |
| **D7-4** | Playwright smoke: login → feed → drawer → CV download → feedback → mark applied → dashboard changes | `cd web && npx playwright test 2>&1 \| tail -5` | all passed; trace written to `reports/evidence/FR-004/` | | |
| **D7-5** | Screenshots at 360 px and 1280 px saved, synthetic data only | `ls reports/evidence/FR-004/*.png` and inspect | four files; no real founder data visible | | |
| **D7-6** | `UNKNOWN` is rendered distinctly from `FAIL` | assertion inside the Playwright smoke on the qualification checklist | distinct marker asserted, not merely present | | |
| **D8-1** | Scheduler unit tests pass | `python -m unittest worker.test_scheduler -v 2>&1 \| tail -3` | `OK`; covers interval math, read-disabled sources skipped, one job per source per tick | | |
| **D8-2** | Read-disabled sources are never enqueued | assertion inside `worker/test_scheduler.py` | present and passing | | |
| **D8-3** | `alpha.py status` and `down` subprocess smoke | `python -m unittest scripts.test_alpha 2>&1 \| tail -1` | `OK` | | |
| **D8-4** | `alpha.py up` reaches a logged-in feed with fixture data within 2 minutes | timed transcript of `python scripts/alpha.py up` + login + feed fetch | elapsed < 120 s, feed returns fixture rows | | |
| **D8-5** | `alpha.py down` leaves no processes | `python scripts/alpha.py down` then check for listeners on 8000/3000 and the worker process | none found | | |
| **D9-1** | ADR-0013 exists and is Accepted | `head -12 docs/adr/ADR-0013-alpha-grade-auth-and-local-only-posture.md` | title + `Status: Accepted` | | |
| **D9-2** | ADR-0013 is picked up by the state generator | `grep -n "ADR-0013" docs/STATE.md` | listed under Accepted | | |
| **D10-1** | Readiness matrix regenerates identically from its JSON | `python scripts/generate_readiness_matrix.py --check; echo "exit=$?"` | `exit=0` | | |
| **D10-2** | Matrix totals still sum to 143 | `python -c` summing status counts from the JSON | sum == 143 | | |
| **D10-3** | Every flipped row carries `status_history` | `python -c` asserting each row changed this brief has a non-empty `status_history` | assertion passes | | |
| **D10-4** | Report carries a Founder Acceptance section left blank | `sed -n '/^## 9\. Founder acceptance packet/,/^## 10\./p' reports/REPORT-FR-004.md \| grep -c "Opportunities worth opening today" && grep -cE '^\| (1[0-4]\|[1-9]) \| .+ \| \|$' reports/REPORT-FR-004.md` | `1` (the phrase occurs inside §9, not merely somewhere in the file — this excludes the false-positive match inside this ledger's own D10-4 row) and `14` (the acceptance-script step table has 14 rows, each with an empty result column) | | |
| **A-0** | FR-002 fail-closed probe unchanged and green | `python -m unittest storage.test_fail_closed_probe -v 2>&1 \| tail -3` | `Ran 12 tests`, `OK` | | |
| **A-1** | Full Python suite on real PostgreSQL | `python -m unittest discover -v 2>&1 \| tail -5` | `Ran N tests`, `OK`, **0 skipped**, N > 466 | | |
| **A-2** | Per-module counts from that run | derived from the A-1 verbose output | table published in the report; totals reconcile to A-1's `N` | | |
| **A-3** | Migration round-trip through `0002` (repeat of D4-1 at integration time) | `alembic upgrade head && alembic downgrade 0001_baseline_schema && alembic upgrade head` | exit 0 each step | | |
| **A-4** | Guard and repository integrity | `python scripts/check_guard.py --allow-missing-patterns; echo "exit=$?"` and `python scripts/check_repository.py; echo "exit=$?"` | `exit=0` both; the secret-bearing case is the `Guard` workflow on the PR head | | |
| **A-5** | `STATE.md` zero drift | `STATE_PRESERVE_TIMESTAMP=1 python scripts/generate_state.py` then `git diff --stat docs/STATE.md` | **zero lines** of diff | | |
| **A-6** | Scope diff | `git diff --name-only 8423fcb..HEAD` | every path inside §2's named deliverables, plus only `pyproject.toml`, `.github/workflows/test.yml`, `AGENTS.md`, `briefs/BRIEF-FR-004.md`, `reports/**` | | |
| **A-7** | `npm run build && npm run lint` clean | `cd web && npm run build && npm run lint; echo "exit=$?"` | `exit=0` | | |
| **A-8** | Playwright smoke passes with its trace saved | `cd web && npx playwright test` and `ls reports/evidence/FR-004/*trace*` | pass; trace file present | | |
| **A-9** | `alpha.py up` → logged-in feed → `alpha.py down` → no processes | full transcript captured to `reports/evidence/FR-004/a9-alpha-transcript.txt` | transcript shows all three stages | | |

---

## Evidence files

One captured output file per claim group, in this directory:

`d1-queue-retry.txt` · `d2-backup-columns.txt` · `d3-persistence.txt` · `d4-match-evaluations.txt`
· `d5-truth-pack.txt` · `d6-api.txt` · `d7-web.txt` · `d8-scheduler-alpha.txt` · `d9-adr-0013.txt`
· `d10-matrix.txt` · `a0-fail-closed.txt` · `a1-full-suite.txt` · `a2-module-counts.txt`
· `a3-migration-roundtrip.txt` · `a4-guard-integrity.txt` · `a5-state-sync.txt` · `a6-scope-diff.txt`
· `a7-npm-build-lint.txt` · `a8-playwright.txt` · `a9-alpha-transcript.txt`
