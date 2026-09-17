# FR-007 Work Order — Antigravity W4 Container Packaging

## Goal

Produce a provider-neutral OCI/container packaging scaffold for OpportunityOS so the Python runtime can run on a managed cloud container/job service with no founder-PC dependency.

This is deliberately bounded and mechanical. Do **not** redesign the application, queue, feed, database, auth, or deployment architecture.

## Branch

`work/fr007-antigravity-container`

## Deliverables

1. Add a production-oriented root `Dockerfile` for the Python OpportunityOS runtime.
2. Add a root `.dockerignore` that excludes Git metadata, local/private state, caches, virtualenvs, node_modules, test artifacts, database dumps, `.env*`, `private/`, generated local output, and other files that must never enter an image build context.
3. Add `scripts/container_entrypoint.py` with explicit safe roles only:
   - `api`
   - `worker`
   - `worker-once`
   - `scheduler`

   It must dispatch to existing application entrypoints rather than reimplement domain logic. Unknown/missing roles must fail closed with a non-zero exit code and a concise message.
4. Add `scripts/test_container_contract.py` covering role validation/dispatch construction without requiring Docker itself.
5. Add `docs/CONTAINER_RUNTIME.md` documenting:
   - image purpose;
   - required runtime environment variable *names only*;
   - role commands;
   - non-root/container filesystem assumptions;
   - health/readiness expectations already supported by the current app (do not invent endpoints);
   - provider-neutral examples for running the image locally and on a generic managed container platform;
   - explicit statement that secrets are injected at runtime and never baked into the image.
6. Capture acceptance output in `reports/evidence/FR-007/antigravity-container.txt`.

## Allowed files

You may create or edit only:

- `Dockerfile`
- `.dockerignore`
- `scripts/container_entrypoint.py`
- `scripts/test_container_contract.py`
- `docs/CONTAINER_RUNTIME.md`
- `reports/evidence/FR-007/antigravity-container.txt`

Do not edit any other file.

## Frozen / prohibited

- No edits under `api/`, `worker/`, `storage/`, `opportunity/`, `matching/`, `truth/`, `web/`, `private/`, `.github/`, or migration files.
- Do not create, rotate, inspect, or commit any real secret.
- Do not add provider-specific SDKs.
- Do not create external cloud resources.
- Do not add a new scheduler or queue implementation.
- Do not change acceptance criteria or governance docs.
- Do not merge.

## Container requirements

- Base image should be an official slim Python image compatible with the repository's declared Python version.
- Build must be deterministic enough for CI/repeatability; install dependencies from the repository's existing package metadata rather than inventing a parallel requirements file.
- Run as a non-root user.
- Use unbuffered Python output.
- No secret or private file may be copied deliberately into the image.
- Entrypoint must preserve normal signal handling by using `os.exec*`/equivalent process replacement rather than wrapping child processes indefinitely.
- Do not bundle PostgreSQL, Redis, Node, Cloudflare tunnel, or other infrastructure in this image.

## Acceptance

Run and capture raw output for at least:

```bash
python -m unittest scripts.test_container_contract -v
python scripts/container_entrypoint.py definitely-not-a-role
```

Expected:

- unit tests pass;
- invalid role exits non-zero;
- `.dockerignore` contains explicit exclusions for `.env*`, `private/`, `.git/`, `*.db`, `*.dump`, `*.sql`, caches, virtualenvs, and `node_modules`;
- `Dockerfile` contains a non-root `USER` directive;
- no real credential/token/connection-string value appears in any changed file.

If Docker is available, additionally run:

```bash
docker build -t opportunityos:fr007 .
```

and record the result. Docker availability is optional for this work order; do not install system Docker just to satisfy it.

## Return to Overseer

Commit the completed work to `work/fr007-antigravity-container` and return only:

- commit SHA;
- changed files;
- test/acceptance output path;
- whether an actual Docker build was executed and its result;
- any concrete compatibility issue discovered in the existing entrypoints.

Do not merge or broaden scope.