# OpportunityOS Founder Alpha — GitHub Codespaces

This is the temporary private full-stack development/staging path while the normal local execution environment is unavailable. It does not change product scope, source policy, truth-lock, action authority, or the BRIEF-007 gate.

## What the Codespace contains

The dev container starts one application container plus an isolated PostgreSQL 16 service. The application container has Python 3.12, Node 24, the Python package and dev dependencies, the locked web dependencies, Chromium for Playwright, Alembic migrations, the worker/scheduler, FastAPI, and the Next.js Founder Web Alpha.

Ports 3000 (web) and 8000 (API) are forwarded. GitHub Codespaces forwarded ports are private by default; do not make the Founder Web Alpha public merely for convenience.

## Secrets and private Founder material

Exactly two secret values are required to start the authenticated runtime:

- `OPPORTUNITYOS_FOUNDER_PASSWORD`
- `OPPORTUNITYOS_SESSION_SECRET`

They belong in GitHub Codespaces secrets/environment injection, never in Git, issues, PR text, logs, or committed `.env` files.

The real Founder Truth Pack is a private file, not a repository artifact. Put it at `private/truth_pack.yaml` inside the Codespace, or set `OPPORTUNITYOS_TRUTH_PACK_PATH` to another private path. `private/*` is gitignored. Never commit the pack, copy its contents into an issue/PR, or substitute a fixture and call that Founder acceptance evidence.

Credential-gated source keys, if a future permitted source requires them, are handled the same way and are not prerequisites for bringing up the base Founder Alpha.

## Lifecycle

Codespaces runs `bash scripts/codespaces/bootstrap.sh` after creation and `bash scripts/codespaces/start.sh` on start. If the two required authentication secrets are absent, startup stops before launching the authenticated application and prints the missing variable names; it does not invent defaults.

Manual lifecycle commands, when needed inside the Codespace:

```bash
bash scripts/codespaces/start.sh
bash scripts/codespaces/stop.sh
```

Runtime logs and PID files are written only below `out/codespaces/`, which is gitignored.

## Security posture

The PostgreSQL password in `.devcontainer/docker-compose.yml` is an isolated disposable development-service credential, not a Founder secret and not an external database credential. Founder authentication secrets and the Truth Pack remain external to the repository. The Codespace must remain private, and source/platform policy continues to fail closed on 403, 429, CAPTCHA, MFA, verification, unknown permission, or prohibited automation.

BRIEF-007 / multitenancy remains blocked until the Founder personally validates this Founder Web Alpha.
