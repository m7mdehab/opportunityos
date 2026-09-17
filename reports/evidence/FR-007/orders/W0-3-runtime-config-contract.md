# FR-007 Work Order W0.3 — Provider-Neutral Runtime Configuration Contract

## Deliverable

Create a small, provider-neutral runtime configuration contract for the cloud replatform. This is intentionally bounded/mechanical work and must not modify OpportunityOS business logic, feed/query behavior, queue semantics, database schema, source adapters, auth implementation, or deployment provider resources.

The contract must let an operator or CI job answer: **for each runtime role, which environment variable names/configuration fields are required, optional, public-safe, or secret?** It must never contain credential values.

### Required outputs

1. `config/runtime_env.yaml`
   - machine-readable schema for runtime roles: `web`, `api`, `worker`, `scheduler`, `backup`;
   - classify every variable as one of `public`, `secret`, or `internal`;
   - mark `required` vs `optional` per role;
   - preserve existing environment variable names where the repository already depends on them instead of gratuitously renaming them;
   - include target cloud integrations only as configuration contracts, not provisioned resources (Supabase, Cloudflare/R2, monitoring/email where relevant);
   - no values, example secrets, tokens, DSNs, passwords, hostnames containing credentials, or founder data.

2. `scripts/validate_runtime_env.py`
   - loads `config/runtime_env.yaml`;
   - accepts `--role <role>` and optionally `--names-only`;
   - validates presence of required variable **names** in the current environment for that role;
   - never prints secret values;
   - missing variables produce non-zero exit and list names only;
   - unknown role/schema error produces non-zero exit;
   - `--names-only` prints the expected names/classification without requiring values and is safe for CI/logs.

3. `tests/test_runtime_env_contract.py`
   - verifies every declared role parses;
   - verifies missing-required behavior;
   - verifies optional variables do not fail validation;
   - verifies unknown roles fail;
   - verifies validator output never includes supplied secret values;
   - verifies no entry in the YAML contains a credential value field or obvious committed secret material.

4. `docs/CLOUD_RUNTIME_CONFIG.md`
   - concise operator reference generated from or kept exactly consistent with the YAML;
   - explain which variables are browser-public vs server-secret;
   - state explicitly that Supabase service-role/database/R2/email secrets are server-side only;
   - state that founder truth/profile data is data, not environment configuration, and must not be stored in Git or public client variables;
   - describe role separation only; do not prescribe provider dashboards or paid resources.

## Existing-code inspection requirement

Before editing, search the repository for environment-variable reads (especially database/auth/storage/production-start paths). Reuse existing names when compatible. If two existing names represent the same concept, document the compatibility choice rather than silently breaking one.

## Allowed files

- `config/runtime_env.yaml` (new)
- `scripts/validate_runtime_env.py` (new)
- `tests/test_runtime_env_contract.py` (new)
- `docs/CLOUD_RUNTIME_CONFIG.md` (new)
- `.gitignore` only if a narrowly necessary ignore entry is missing; do not relax any ignore rule

No other files may be changed without stopping and reporting the reason.

## Frozen / do not touch

- `api/**`
- `worker/**`
- `storage/**`
- `opportunity/**`
- `matching/**`
- `truth/**`
- `web/**`
- Alembic migrations
- GitHub workflows
- source registry / source evidence
- existing ADRs / brief
- private files

## Acceptance commands

Run from repository root and paste raw output into your return:

```bash
python -m pytest tests/test_runtime_env_contract.py -q
python scripts/validate_runtime_env.py --role web --names-only
python scripts/validate_runtime_env.py --role worker --names-only
python scripts/validate_runtime_env.py --role scheduler --names-only
python scripts/validate_runtime_env.py --role backup --names-only
python scripts/guard_secrets.py
```

If `scripts/guard_secrets.py` does not exist under that exact name, locate the repository's canonical secret/PII guard and run that instead; report the exact command used.

Expected:

- tests pass;
- names-only commands exit 0 and print names/classifications only;
- no output contains actual secret values;
- repository secret guard passes;
- no business/runtime behavior changed.

## Return packet

Return only:

1. commit SHA;
2. changed-file list;
3. raw acceptance-command outputs;
4. any pre-existing env-name ambiguity you discovered;
5. explicit confirmation that no secret values or founder data were added.

Do not merge. Do not modify the FR-007 brief or ADR. Do not provision external services.