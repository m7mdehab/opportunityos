# BRIEF-FR-003 — Claim Ledger

All commands are POSIX-shell, run from the repository root with the project
installed (`pip install -e .`). `PY` denotes the session Python interpreter
(see the report header for the exact version). `PGURL` denotes
`postgresql+psycopg2://opportunityos:testpassword123@localhost:5432/opportunityos_test`.

Verdict columns: `PASS` / `FAIL` / `BLOCKED_ENV` / `CI_VERIFIED_ONLY`.

| ID | Deliverable | Command | Expected | Evidence file | Master | Verifier |
|---|---|---|---|---|---|---|
| D0-1 | D0 | `ls .claude/agents \| wc -l` | `5` | d0-agents.txt | PASS | PASS |
| D0-2 | D0 | `python scripts/check_repository.py` | exit 0, `Repository integrity checks passed.` | d0-agents.txt | PASS | PASS |
| D0-3 | D0 | allowlist test: no `.claude/**` path matches `.mirror-allowlist` | exit 0, empty match list | d0-agents.txt | PASS | PASS |
| D1-1 | D1 | `python -m unittest scripts.test_generate_ci_status -v 2>&1 \| tail -3` | `OK` | d1-ci-status.txt | PASS | PASS |
| D1-2 | D1 | `grep -c "Mandatory" scripts/generate_ci_status.py` | `>= 1` | d1-ci-status.txt | PASS | PASS |
| D1-3 | D1 | `python -c "from scripts.generate_ci_status import WORKFLOWS; print(WORKFLOWS)"` | `('Mandatory Governance & Test Suite', 'State', 'Guard', 'Mirror')` | d1-ci-status.txt | PASS | PASS |
| D2-1 | D2 | `python scripts/generate_state.py && sed -n '/## Source Status Counts/,/## Next Prerequisites/p' docs/STATE.md` | non-empty counts summing to 52 | d2-source-counts.txt | PASS | PASS |
| D2-2 | D2 | `grep -c "observed_status" scripts/generate_state.py` | `0` | d2-source-counts.txt | PASS | PASS |
| D2-3 | D2 | `python -m unittest scripts.test_generate_state -v 2>&1 \| tail -3` | `OK` | d2-source-counts.txt | PASS | PASS |
| D3-1 | D3 | `grep '^Next:' docs/STATE.md` | ends with `.`, no trailing `:` fragment, no `:.` | d3-next-line.txt | PASS | PASS |
| D4-1 | D4 | `ls scripts/__init__.py` | file exists | d4-backup-test.txt | PASS | PASS |
| D4-2 | D4 | `env -u OPPORTUNITYOS_DB_URL CI=true python -m unittest scripts.test_backup_restore 2>&1 \| tail -5; echo exit=$?` | non-zero exit, clear PostgreSQL-required message | d4-backup-test.txt | PASS | PASS |
| D4-3 | D4 | `OPPORTUNITYOS_DB_URL=$PGURL python -m unittest scripts.test_backup_restore -v 2>&1 \| tail -5` | `OK`, 0 skipped | d4-backup-test.txt | PASS | PASS |
| D5-1 | D5 | `grep -n "create_all\|init_db" scripts/backup_restore.py` | no output (exit 1) | d5-restore-alembic.txt | PASS | PASS |
| D5-2 | D5 | `OPPORTUNITYOS_DB_URL=$PGURL python -m unittest storage.test_postgres_integration.PostgresProductionIntegrationTest.test_case_m_backup_wipe_restore_postgres_cycle -v 2>&1 \| tail -4` | `OK` | d5-restore-alembic.txt | PASS | PASS |
| D5-3 | D5 | `grep -n "BackupCompletenessError\|sorted_tables" scripts/backup_restore.py` | both present | d5-restore-alembic.txt | PASS | PASS |
| D6-1 | D6 | `grep -n 'sqlite:///opportunityos.db' storage/test_postgres_integration.py` | no output (exit 1) | d6-integration-fail-loud.txt | PASS | PASS |
| D6-2 | D6 | `env -u OPPORTUNITYOS_DB_URL CI=true python -m unittest storage.test_postgres_integration 2>&1 \| tail -5` | ERROR/FAIL, not `skipped` | d6-integration-fail-loud.txt | PASS | PASS |
| D6-3 | D6 | `OPPORTUNITYOS_DB_URL=$PGURL python -m unittest storage.test_postgres_integration -v 2>&1 \| tail -4` | `OK`, all cases run | d6-integration-fail-loud.txt | PASS | PASS |
| D7-1 | D7 | `grep -n "## Erratum (2026-09-02, BRIEF-FR-003)" reports/REPORT-FR-002.md` | one match | d7-erratum.txt | PASS | PASS |
| D7-2 | D7 | `python -m unittest scripts.test_readiness_matrix -v 2>&1 \| tail -3` | `OK` (enforces every REQ- ID in the erratum exists in the JSON) | d7-erratum.txt | PASS | PASS |
| D8-1 | D8 | `python scripts/generate_readiness_matrix.py --check; echo exit=$?` | `exit=0` | d8-matrix.txt | PASS | PASS |
| D8-2 | D8 | `python -c "import json;d=json.load(open('reports/FOUNDER_READINESS_MATRIX.json',encoding='utf-8'));print(len(d))"` | `143` | d8-matrix.txt | PASS | PASS |
| D8-3 | D8 | `python -m unittest scripts.test_readiness_matrix -v 2>&1 \| tail -3` | `OK` | d8-matrix.txt | PASS | PASS |
| D8-4 | D8 | `grep -c "status_history" reports/FOUNDER_READINESS_MATRIX.json` | `>= 1` | d8-matrix.txt | PASS | PASS |
| D9-1 | D9 | `ls docs/adr/ADR-0012-single-founder-tenancy.md && python scripts/check_repository.py` | file exists, integrity passes | d9-adr-0012.txt | PASS | PASS |
| D10-1 | D10 | `python -m unittest worker.test_runner -v 2>&1 \| tail -3` | `OK` | d10-worker-runner.txt | PASS | PASS |
| D10-2 | D10 | `OPPORTUNITYOS_DB_URL=$PGURL python -m unittest storage.test_postgres_integration.PostgresProductionIntegrationTest.test_case_s_worker_runner_end_to_end -v 2>&1 \| tail -4` | `OK` | d10-worker-runner.txt | PASS | PASS |
| D10-3 | D10 | `OPPORTUNITYOS_DB_URL=$PGURL python -m worker --once; echo exit=$?` | `exit=0`, one idle poll logged | d10-worker-runner.txt | PASS | PASS |
| D10-4 | D10 | `env -u OPPORTUNITYOS_DB_URL python -m worker --once 2>&1 \| tail -3; echo exit=$?` | non-zero, `ProductionDatabaseConfigurationError` | d10-worker-runner.txt | PASS | PASS |
| D10-5 | D10 | `git diff main...HEAD -- docs/AGENT_PERMISSIONS.yaml \| wc -l` | `0` | d10-worker-runner.txt | PASS | PASS |
| D11-1 | D11 | `python -c "..."` — min `last_policy_reviewed` over the 15 re-recon entries | `>= 2026-09-02`, or `BLOCKED_ENV` with the exact error | d11-recon.txt | PASS | PASS |
| D11-2 | D11 | `python -m unittest discover -s recon -t . -v 2>&1 \| tail -3` | `Ran 67 tests`, `OK` | d11-recon.txt | PASS | PASS |
| D12-1 | D12 | `grep -n "actions/checkout@\|actions/setup-python@" .github/workflows/*.yml` | current latest majors, verified against GitHub | d12-ci-hygiene.txt | PASS | PASS |
| D12-2 | D12 | `Mandatory Governance & Test Suite` conclusion on the PR head | `success`, no `Node.js 20 is deprecated` warning | d12-ci-hygiene.txt | PASS | N/A — needs the PR head; the verifier session had no GitHub CLI. Master: PASS (run IDs in the evidence file). |
| D13-1 | D13 | the five-vendor-name `grep -rniE` from BRIEF-FR-003 D13 (pattern given verbatim in `briefs/BRIEF-FR-003.md` D13), run over `reports/REPORT-FR-003.md` and `docs/adr/ADR-0012*.md`. The pattern is referenced rather than quoted here because this ledger is reproduced inside `reports/REPORT-FR-003.md`, and an inline copy would make the check match itself. | no output (exit 1) | d13-vendor-neutral.txt | PASS | PASS |
| D13-2 | D13 | `grep -n "Reports and ADRs name roles, not model vendors." AGENTS.md` | one match | d13-vendor-neutral.txt | PASS | PASS |
| D14-1 | D14 | `ls reports/REPORT-FR-003.md reports/evidence/FR-003/CLAIMS.md` | both exist | d14-close.txt | PASS | PASS |
| D14-2 | D14 | fresh render of `docs/STATE.md` diffed against the committed file | no drift | a5-state-sync.txt | PASS | PASS |
| D14-3 | D14 | PR open to `main`, four workflows green on the PR head | `success` ×4 | d14-close.txt | PASS | N/A — needs the PR head; the verifier session had no GitHub CLI. Master: PASS (run IDs in the evidence file). |
| **A-0** | probe | `OPPORTUNITYOS_DB_URL=$PGURL python -m unittest storage.test_fail_closed_probe -v 2>&1 \| tail -4` | `OK`; 7/7 raise under misconfiguration, 5/5 construct under a valid DSN | a0-fail-closed-probe.txt | PASS | PASS |
| **A-1** | suite | `OPPORTUNITYOS_DB_URL=$PGURL python -m unittest discover -v 2>&1 \| tail -3` | `Ran N tests`, `OK`, N >= 414 + new tests, 0 skipped | a1-full-suite.txt | PASS | PASS |
| **A-2** | counts | per-module counts derived from the A-1 run (no count typed from memory) | table in the report matches the run | a2-module-counts.txt | PASS | PASS |
| **A-3** | migration | `alembic upgrade head && alembic downgrade base && alembic upgrade head` with `OPPORTUNITYOS_DB_URL=$PGURL` | exit 0 for all three | a3-migration-roundtrip.txt | PASS | PASS |
| **A-4** | guard | `python scripts/check_guard.py --allow-missing-patterns` (with `.github/pii-patterns.txt` present) and `python scripts/check_repository.py` | both exit 0. The flag is the one `.github/workflows/test.yml` itself uses: without it the guard exits 1 anywhere the `FOUNDER_NAME_PATTERNS` repository secret is absent, which is every environment except CI. The secret-bearing run is the `Guard` workflow on the PR head (`33574529393`, `success`). | a4-guard-integrity.txt | PASS | PASS |
| **A-5** | state | fresh render of `docs/STATE.md` diffed against the committed file (timestamp line excluded) | no drift | a5-state-sync.txt | PASS | PASS |
| **A-6** | scope | `git diff --stat main...HEAD` | no file outside the paths named in BRIEF-FR-003 §2 | a6-scope-diff.txt | PASS | PASS |
