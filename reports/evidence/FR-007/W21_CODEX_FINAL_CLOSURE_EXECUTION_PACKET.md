# W21 — CODEX FINAL PORTABILITY / MIGRATION CLOSURE EXECUTION PACKET

## ROLE

You are the **Codex implementation executor** for one bounded FR-007 closure lane.

The Overseer has already done the architectural reasoning. Treat the decisions, invariants, and acceptance criteria below as frozen unless direct repository evidence proves an internal contradiction. Your job is to inspect the real repository state, execute the lane completely, self-remediate deterministic failures, push an auditable branch, and return **one final PASS or genuine BLOCKED report**.

Do not stop for routine implementation questions. Do not ask the user to choose between ordinary engineering alternatives when the acceptance contract below resolves the choice.

## REPOSITORY / BRANCH

- Repository: `m7mdehab/opportunityos`
- Required branch: `work/fr007-codex-final-closure`
- Parent / authoritative Overseer integration SHA: `b9e18098af32cf27af738348ba44b9e5ca2e417d`
- This branch was created specifically for this lane.
- Read `AGENTS.md` and repository governance before editing.
- Do **not** merge to `work/fr007-overseer-integration` or `main`.
- Do **not** force-push shared/protected history.
- Push your final branch and verify the **remote SHA**, not only the local SHA.

## OBJECTIVE

Close the deterministic **portability + migration + provider-execution-bundle + related CI** portion of FR-007 so that:

1. repository migration authority and the committed provider bundle both end at `0014_backup_heartbeat`;
2. the disposable provider-neutral PostgreSQL proof executes the committed bundle successfully;
3. the live-provider-exit workflow's target-role bootstrap is valid PostgreSQL;
4. provider-neutral export/restore/parity tooling remains fail-closed and deterministic;
5. no test, RLS rule, security boundary, or acceptance criterion is weakened to obtain green CI.

Your lane is successful only when the code/evidence is internally consistent and the relevant deterministic gates pass.

## CURRENT AUTHORITATIVE STATE

At branch creation:

- Repository Alembic head is `0014_backup_heartbeat`.
- Live Supabase project `lrrcpwaapwynzdsxzwhy` has already been independently verified by the Overseer at `public.alembic_version = 0014_backup_heartbeat`.
- The committed generated provider bundle under `reports/evidence/FR-007/provider-execution/` is stale at `0013_hosted_poll_now_cadence`.
- `scripts/test_fr007_supabase_execution_bundle.py` already expects `0014_backup_heartbeat`.
- `scripts/test_fr007_supabase_execution_postgres.py` already expects `0014_backup_heartbeat`.
- GitHub Actions run `35480707783` exposed two concrete defects:
  - `live-supabase-exit / Prepare provider-neutral target roles` failed with PostgreSQL syntax error because the heredoc contains invalid `DO $ BEGIN ... END $;` instead of valid dollar quoting.
  - `disposable-postgres` reached the committed provider bundle and failed because the committed bundle stopped at `0013_hosted_poll_now_cadence` while the test correctly expected `0014_backup_heartbeat`.
- The generator `scripts/fr007_supabase_execution_bundle.py` discovers the Alembic chain dynamically and should render 0014 once regenerated. Do not hard-code a fake PASS around stale generated output.
- The integration branch currently keeps `.github/workflows/fr007-integration-state-regenerator.yml` manual-only to avoid a bot-authored terminal PR head. Final canonical `docs/STATE.md` regeneration belongs to the Overseer after parallel lane integration.

## SOURCE OF TRUTH

Read at minimum:

- `briefs/BRIEF-FR-007.md` — especially A-9, A-10, A-12, A-15, A-17
- `storage/migrations/versions/0012_hosted_policy_alignment.py`
- `storage/migrations/versions/0013_hosted_poll_now_cadence.py`
- `storage/migrations/versions/0014_backup_heartbeat.py`
- `scripts/fr007_supabase_execution_bundle.py`
- `scripts/test_fr007_supabase_execution_bundle.py`
- `scripts/test_fr007_supabase_execution_postgres.py`
- `scripts/db_migration_restore.py`
- `scripts/live_portability_proof.py`
- `scripts/test_live_portability_postgres.py`
- `scripts/migration_acceptance.py`
- `scripts/test_migration_acceptance_postgres.py`
- `.github/workflows/fr007-portability-proof.yml`
- current `reports/evidence/FR-007/provider-execution/**`

Inspect additional directly relevant files as needed.

## FROZEN ARCHITECTURAL DECISIONS / INVARIANTS

1. **Alembic repository migrations are schema authority.**
2. The current required head is **`0014_backup_heartbeat`**.
3. Supabase-specific provider execution artifacts are generated derivatives; they must never become an alternate schema authority.
4. PostgreSQL remains the portable canonical database.
5. Founder/browser RLS restrictions and provider-security hardening must remain at least as strict as today.
6. No credentials, DSNs with secrets, tokens, private truth payloads, object bodies, or production secrets may enter Git or generated evidence.
7. Provider-exit proof must test a real independent PostgreSQL target, not a mocked success path.
8. Never weaken or delete a failing assertion merely to make the lane green.
9. Do not rewrite historical migrations merely because generated output is stale. Historical migration source may be changed only if a real correctness defect in that source is proven and the change is necessary for the frozen acceptance contract.
10. Final `docs/STATE.md`, `reports/REPORT-FR-007.md`, queue/runtime behavior, monitoring, and live worker recovery belong outside this lane.

## PRIMARY WORK

### C1 — Repair provider-neutral role bootstrap

Fix `.github/workflows/fr007-portability-proof.yml` so the `Prepare provider-neutral target roles` heredoc uses valid PostgreSQL PL/pgSQL dollar quoting.

Required behavioral result:

- roles `anon`, `authenticated`, and `service_role` are created only when absent;
- the command runs with `ON_ERROR_STOP=1`;
- failure remains fail-closed;
- do not hide SQL failures with `|| true`.

### C2 — Regenerate the committed provider bundle through 0014

Run the repository generator, not hand-editing of generated SQL as the primary mechanism.

The committed bundle must include:

- migration 14 for `0014_backup_heartbeat`;
- `migration-manifest.json.expected_final_revision = "0014_backup_heartbeat"`;
- execution manifest migration step through `14_*.sql`;
- correct hashes for every generated file;
- deterministic verification success;
- no stale 0013 head assertions.

If generation exposes a real generator defect, repair the generator and add/adjust deterministic tests; do not patch only the output.

### C3 — Execute the provider bundle against real disposable PostgreSQL

The committed bundle itself—not a freshly generated temporary substitute—must execute cleanly in the existing real PostgreSQL proof.

Required assertions include:

- final `alembic_version = 0014_backup_heartbeat`;
- RLS/provider-security assertions remain valid;
- browser roles retain no forbidden broad privileges;
- 0014 `backup_heartbeats` exists as expected;
- no regression in earlier migration behavior.

If the test currently fails for another genuine 0014-related incompatibility, diagnose and repair it inside this lane.

### C4 — Provider-neutral export / restore / parity confidence

Run the existing portability / restore / acceptance test family. Repair only defects genuinely exposed by the new head or the portability workflow.

The final design must still prove:

- database backup can be created without persisting a DSN;
- archive integrity is verified before restore;
- restore requires explicit target confirmation;
- source/target parity failures fail closed;
- unsupported provider-only concepts are explicitly classified rather than silently ignored;
- canonical relation counts/revision checks include the 0014 heartbeat relation where appropriate.

Do not manufacture live-provider evidence. Deterministic local/disposable proof is your scope; live Supabase provider actions are Overseer-owned.

## PREFERRED FILE OWNERSHIP

You may modify only what is necessary for this lane, preferentially:

- `.github/workflows/fr007-portability-proof.yml`
- `scripts/fr007_supabase_execution_bundle.py`
- `scripts/test_fr007_supabase_execution_bundle.py`
- `scripts/test_fr007_supabase_execution_postgres.py`
- directly related portability/restore/acceptance scripts and tests if a real defect is found
- `reports/evidence/FR-007/provider-execution/**`
- one lane completion evidence file, if useful

Do not modify unless strictly required by a proven portability defect:

- `worker/**`
- `scripts/fr007_cloud_monitor.py`
- `scripts/process_incident_alert.py`
- `.github/workflows/fr007-cloud-observability.yml`
- `.github/workflows/fr007-worker-drain.yml`
- `web/**`
- `docs/STATE.md`
- `reports/REPORT-FR-007.md`

If an out-of-lane defect is discovered, report it with exact evidence; do not opportunistically take ownership.

## REQUIRED QUALITY GATES

Run all focused tests you invalidate plus the workflow-equivalent portability suite. At minimum:

```bash
python scripts/fr007_supabase_execution_bundle.py generate
python scripts/fr007_supabase_execution_bundle.py verify

python -m unittest   scripts.test_fr007_supabase_execution_bundle   scripts.test_fr007_supabase_execution_postgres   -v
```

For the real PostgreSQL test, supply the repository's expected `OPOS_LIVE_PROOF_TEST=1` environment and a disposable PostgreSQL instance. Reproduce the GitHub workflow locally with Docker/service Postgres if available.

Then run the full existing portability family equivalent to the workflow:

```bash
python -m unittest   scripts.test_migration_baseline   scripts.test_db_migration_restore   scripts.test_portability_integrity   scripts.test_live_portability_proof   scripts.test_production_migration_readiness   scripts.test_migration_acceptance   scripts.test_live_portability_postgres   scripts.test_migration_acceptance_postgres   scripts.test_fr007_supabase_execution_bundle   scripts.test_fr007_supabase_execution_postgres   -v
```

Also run:

```bash
python scripts/check_repository.py
python -m py_compile   scripts/fr007_supabase_execution_bundle.py   scripts/test_fr007_supabase_execution_bundle.py   scripts/test_fr007_supabase_execution_postgres.py
```

Run any additional directly affected tests required by the diff.

If GitHub Actions is available after push, inspect the actual workflow run for this branch and remediate deterministic failures inside the lane. Do not claim remote CI PASS unless you observed it.

## ADVERSARIAL CHECKS

Before declaring PASS, explicitly verify:

- the generated bundle fails verification if a generated SQL/hash is changed;
- final revision is derived from Alembic, not duplicated stale constants;
- role bootstrap SQL is syntactically valid PostgreSQL;
- no `|| true`, ignored SQL exit, or test skip was introduced to bypass portability proof;
- no secret-looking DSN/token/private payload entered the generated bundle;
- 0014 is actually executed by the committed bundle, not only mentioned by a test.

## AUTONOMY / INTERNAL REMEDIATION LOOP

Operate continuously until PASS or a genuine blocker.

Routine failures are yours to diagnose and fix. Re-run invalidated evidence after every material correction.

A failed test, missing local dependency, stale generated file, or ordinary refactor is **not** a blocker.

Return BLOCKED only when you have completed every safely executable part and the remaining obstacle requires unavailable external authority/credential/provider access or contradicts frozen repository policy.

## GIT REQUIREMENTS

- Keep this lane on `work/fr007-codex-final-closure`.
- Produce clean, reviewable commits.
- Push the branch.
- Verify the remote branch SHA after push.
- Do not merge.
- Do not rebase/force-push the Overseer integration branch.
- Leave no untracked scratch artifacts or secrets.

## FINAL OUTPUT ONLY

Return one **MASTER COMPLETION REPORT** containing:

- `STATUS: PASS` or `BLOCKED`
- repository start SHA
- branch
- final local SHA
- verified remote SHA
- acceptance matrix for C1–C4
- exact files changed
- consequential implementation decisions
- exact test commands and exit results
- disposable PostgreSQL version used
- generated provider-bundle final revision and migration count
- GitHub workflow run IDs/conclusions if actually observed
- security/secret scan result
- unresolved items, if any
- out-of-lane defects discovered, if any
- `READY FOR OVERSEER INTEGRATION: YES/NO`

Do not self-declare FR-007 closed or ready for production merge. Only the Overseer can adjudicate that.
