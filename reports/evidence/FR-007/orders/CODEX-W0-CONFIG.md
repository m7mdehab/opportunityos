# Work Order — CODEX-W0-CONFIG

## Purpose

Implement the small, isolated W0.3 infrastructure configuration contract for BRIEF-FR-007. This is intentionally bounded so it can run in parallel with Wave 1 data-path work.

## Read first

- `AGENTS.md`
- `docs/AUTHORITY_INDEX.md`
- `docs/CI_EFFICIENCY_POLICY.md`
- `briefs/BRIEF-FR-007.md`
- `docs/adr/ADR-0022-cloud-native-runtime-and-supabase-data-plane.md`

Do not read or print anything under `private/`. Do not create accounts, paid resources, secrets, tokens, or external infrastructure.

## Deliverable

Create a provider-neutral runtime/deployment configuration contract that documents and validates the environment variables/secrets required by the cloud architecture without containing any secret values.

### Required outputs

1. `docs/CLOUD_RUNTIME_CONFIG.md`
   - Separate variables into: database/data plane, auth, storage, worker/queue, scheduler, frontend/public, monitoring, notifications, backup/DR.
   - For every variable specify: name, required/optional, consumer(s), secret/non-secret, startup-vs-runtime use, and fail-closed behavior.
   - Clearly distinguish browser-safe public variables from server-only secrets.
   - Include migration/cutover ordering and secret-rotation notes.
   - Use provider-neutral names for core domain configuration; provider-specific aliases may be documented separately.

2. `.env.cloud.example`
   - Placeholder names only; no values that could be mistaken for real credentials.
   - Must be safe to commit publicly.
   - Do not duplicate local-only obsolete variables unless the compatibility bridge still requires them.

3. `scripts/validate_cloud_config.py`
   - Pure stdlib if practical.
   - Validates names/presence/obvious malformed placeholders for a requested role (`web`, `api`, `worker`, `scheduler`, `backup`) without printing secret values.
   - `--help` must work without environment setup.
   - Missing required secrets must produce a concise list of variable names only and non-zero exit.
   - Must never dump `os.environ` or values.

4. `scripts/test_validate_cloud_config.py`
   - Unit tests for at least: valid worker role, missing DB URL, missing server-only auth/storage secret, web role does not require worker secrets, and failure output contains names but not supplied secret values.

## Allowed files

- `docs/CLOUD_RUNTIME_CONFIG.md`
- `.env.cloud.example`
- `scripts/validate_cloud_config.py`
- `scripts/test_validate_cloud_config.py`
- this work-order evidence directory only for raw test output

Do not modify application/domain/storage models, migrations, API routes, workers, frontend, existing auth, `docs/STATE.md`, `docs/ARCHITECTURE_CURRENT.md`, `docs/ROADMAP_CURRENT.md`, the active brief, or ADRs.

## Acceptance commands

Run and capture raw output in `reports/evidence/FR-007/codex-w0-config-tests.txt`:

```bash
python scripts/validate_cloud_config.py --help
python -m unittest scripts.test_validate_cloud_config -v
python scripts/validate_cloud_config.py --role worker
```

Expected:
- help exits 0;
- unit tests all pass;
- the final command may fail because real secrets are intentionally absent, but it must fail cleanly and list only missing variable names, never values.

Also run:

```bash
git diff --check
git grep -nE '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|service_role[^A-Za-z0-9_]|postgres(ql)?://[^[:space:]]+:[^[:space:]]+@)' -- . ':!reports/evidence/**' || true
```

Inspect any grep hit; committed files must contain no real credentials.

## Return packet

Return:
- commit SHA;
- changed-file list;
- raw acceptance output path;
- any compatibility assumption that needs Overseer review.

Do not merge the branch and do not broaden scope.