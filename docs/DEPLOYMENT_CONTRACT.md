# OpportunityOS Cloud Deployment Contract

This document defines the canonical, provider-neutral operational deployment contract for OpportunityOS across all supported runtime roles. It specifies lifecycle, scaling, networking, storage, configuration, and shutdown invariants for cloud orchestrators (Kubernetes, AWS ECS, Google Cloud Run, Azure Container Apps, Nomad, Docker Swarm, and bare OCI engines).

---

## 1. Operational Role Matrix & Topology

OpportunityOS operates as a set of decoupled, purpose-specific roles packaged in a single production OCI image (`python:3.12-slim-bookworm`):

| Role | Operational Function | Scaling Constraint | Ingress / Network | State Persistence |
| :--- | :--- | :--- | :--- | :--- |
| **`api`** | HTTP REST & session service | **Horizontal (N replicas)** | Ingress on port `PORT` (`0.0.0.0`) | Stateless |
| **`worker`** | Durable background queue consumer | **Horizontal (N replicas)** | No inbound ingress; egress to DB/APIs | Stateless; ephemeral scratch `/tmp` |
| **`scheduler`** | Periodic poll timer & job generator | **Strict Singleton (1 replica)** | No inbound ingress; egress to DB | Durable DB state (`worker_jobs`) |
| **`migrate`** | Schema migration to `head` | **One-Shot / Serial Execution** | No inbound ingress; egress to DB | Modifies DB schema |

---

## 2. Role Specifications

### 2.1 Role: `api`

- **Command / Entrypoint**: `python scripts/container_entrypoint.py api`
  - Internally dispatches to: `python -m uvicorn api.app:app --host 0.0.0.0 --port <PORT> --proxy-headers --forwarded-allow-ips=*`
- **Scaling Contract**:
  - Fully stateless. May scale horizontally to arbitrary replica counts ($N \ge 1$) behind an L7 reverse proxy or load balancer.
  - Cloud sessions are durable PostgreSQL session records keyed by hashed opaque cookie tokens; revocation survives replica/process restarts. `OPPORTUNITYOS_SESSION_SECRET` protects token digests and must be shared consistently across API replicas.
- **Network Ingress**:
  - Listens on `0.0.0.0` on configurable port (`PORT` or `OPPORTUNITYOS_API_PORT`, default `8000`).
  - Expects standard reverse proxy headers (`X-Forwarded-Proto`, `X-Forwarded-For`).
- **Required Environment Variables**:
  - `CLOUD_DATABASE_URL` (or `OPPORTUNITYOS_DB_URL`): PostgreSQL connection string (postgresql or postgresql+psycopg2 dialect).
  - Cloud: `OPPORTUNITYOS_FOUNDER_PASSWORD_HASH` (scrypt v1; plaintext Founder password is forbidden in the cloud runtime).
  - `OPPORTUNITYOS_SESSION_SECRET`: server-side session/token secret.
  - Cloud: `OPPORTUNITYOS_PUBLIC_ORIGIN`: canonical HTTPS frontend origin used for Origin/CSRF enforcement.
  - Cloud: `OPPORTUNITYOS_TRUTH_PACK_URI`, `OPPORTUNITYOS_TRUTH_PACK_HASH`, and private Storage API credential(s) for the remote Founder Truth Pack.
- **Optional Environment Variables**:
  - `PORT` (or `OPPORTUNITYOS_API_PORT`): Port number to bind (default: `8000`).
  - `HOST` (or `OPPORTUNITYOS_API_HOST`): Host address to bind (default: `0.0.0.0`).
  - `OPPORTUNITYOS_HIGH_FIT_THRESHOLD`: Numeric threshold (default: `70.0`).
  - Local/dev only: `OPPORTUNITYOS_TRUTH_PACK_PATH`. Cloud mode refuses local filesystem fallback.
  - `OPPORTUNITYOS_FORCE_SECURE_COOKIES`: Force Secure flag on session cookies (`1` or `0`).
- **Health / Readiness Probes**:
  - Liveness: `python scripts/container_entrypoint.py liveness` (or HTTP request to `/api/auth/me`).
  - Readiness: `python scripts/container_entrypoint.py readiness` (proves PostgreSQL reachability and migration revision without scanning corpus).
- **Graceful Shutdown**:
  - Uvicorn replaces entrypoint as PID 1 via `os.execvp`.
  - On `SIGTERM`: ceases accepting new connections, allows in-flight requests up to 30s to complete, and exits 0.
- **Restart Policy**: `always` or `unless-stopped`.

---

### 2.2 Role: `worker`

- **Command / Entrypoint**: `python scripts/container_entrypoint.py worker [args...]`
  - Internally dispatches to: `python -m worker [args...]`
- **Scaling Contract**:
  - Stateless queue consumers. May scale horizontally ($N \ge 1$).
  - Workers coordinate through row-level locking (`SELECT ... FOR UPDATE SKIP LOCKED` via `WorkerJobRecord`) and lease expiration timeouts (`--lease-seconds`, default 60s). Multiple worker replicas safely compete for distinct jobs without collisions or duplicate processing.
  - Role Separation: `--schedule` is explicitly prohibited and rejected fail-closed.
- **Network Ingress**:
  - Zero inbound ingress. Requires outbound HTTPS egress to public job boards/transports and outbound TCP to PostgreSQL.
- **Required Environment Variables**:
  - `CLOUD_DATABASE_URL` (or `OPPORTUNITYOS_DB_URL`): PostgreSQL connection string.
- **Optional Environment Variables**:
  - `OPPORTUNITYOS_TRUTH_PACK_PATH`: Path to truth pack YAML if volume-mounted.
  - Command-line flags: `--once`, `--max-jobs <N>`, `--poll-interval <seconds>`, `--lease-seconds <seconds>`.
- **Health / Readiness Probes**:
  - Liveness: `python scripts/container_entrypoint.py liveness`.
  - Readiness: `python scripts/container_entrypoint.py readiness` (checks DB and queue table accessibility).
- **Graceful Shutdown**:
  - `WorkerRunner` runs as PID 1, trapping `SIGTERM` / `SIGINT`.
  - On signal: completes the currently claimed job, releases unclaimed leases, and exits cleanly.
- **Restart Policy**: `always` or `unless-stopped`.

---

### 2.3 Role: `scheduler`

- **Command / Entrypoint**: `python scripts/container_entrypoint.py scheduler`
  - Internally executes: `PollScheduler(session_factory, stop_event=stop_event, tick_interval_seconds=30.0).run_forever()`
- **Scaling Contract**:
  - **STRICT SINGLETON (1 replica)**.
  - Must NOT be scaled horizontally without distributed leader election.
  - In cloud orchestrators, deploy as a singleton Deployment / Service with `replicas: 1` and `strategy: Recreate` (or an orchestrator cron task running `worker --poll-now`).
  - Durable protection: Even if two scheduler instances overlap briefly, `PollScheduler` checks pending/running database rows and suppresses duplicate job enqueues within the source cadence window.
- **Network Ingress**:
  - Zero inbound ingress. Requires outbound TCP egress to PostgreSQL.
- **Required Environment Variables**:
  - `CLOUD_DATABASE_URL` (or `OPPORTUNITYOS_DB_URL`): PostgreSQL connection string.
- **Optional Environment Variables**:
  - `OPPORTUNITYOS_POLL_INTERVAL_HOURS`: Cadence floor in hours (default: `6.0`).
- **Health / Readiness Probes**:
  - Liveness: `python scripts/container_entrypoint.py liveness`.
  - Readiness: `python scripts/container_entrypoint.py readiness`.
- **Graceful Shutdown**:
  - Installs `SIGTERM` / `SIGINT` handler that sets `stop_event: threading.Event`.
  - On signal: waits for current tick iteration to finish, exits cleanly.
- **Restart Policy**: `always` with singleton leader protection (`maxSurge: 0`, `maxUnavailable: 1`).

---

### 2.4 Role: `migrate`

- **Command / Entrypoint**: `python scripts/container_entrypoint.py migrate`
  - Internally dispatches to: `python -m alembic upgrade head`
- **Execution Contract**:
  - **One-Shot / Init-Container / Pre-Deploy Hook**.
  - Executes schema migrations sequentially to `head` and exits immediately with alembic exit code (0 on success).
  - Must complete before new versions of `api` or `worker` start serving traffic.
  - Does NOT start web, API, or worker daemons.
- **Network Ingress**:
  - Zero inbound ingress. Requires outbound TCP egress to PostgreSQL with DDL permissions.
- **Required Environment Variables**:
  - `CLOUD_DATABASE_URL` (or `OPPORTUNITYOS_DB_URL`): PostgreSQL connection string.
- **Restart Policy**: `never` or `on-failure` (max retries: 3).

---

## 3. Storage and Filesystem Expectations

OpportunityOS cloud containers are designed for ephemeral, stateless execution:

1. **No Host Directory Mounts Required**:
   - Zero hardcoded founder-laptop paths (`c:\...`, `/Users/...`).
   - All code, alembic scripts, and static registry YAML (`docs/SOURCE_REGISTRY.yaml`) are baked into the container image.
2. **Ephemeral Directories**:
   - `/tmp` is used for temporary scratch files during document generation.
   - `/app/out` is pre-created and owned by `appuser` (UID 1000) for digest generation.
3. **Truth Pack Storage**:
   - Cloud API/worker roles require a credential-free private HTTPS object URI plus SHA-256 integrity binding; local/container filesystem fallback is rejected in cloud mode.
   - Local development may continue to use `OPPORTUNITYOS_TRUTH_PACK_PATH`; that compatibility path is not a cloud deployment contract.

---

## 4. Secret & Configuration Management

1. **Classification**:
   - **Secrets** (`CLOUD_DATABASE_URL`, `OPPORTUNITYOS_FOUNDER_PASSWORD_HASH`, `OPPORTUNITYOS_SESSION_SECRET`, private Truth Pack API credentials, private registry pull token): Must be injected via orchestrator secret stores. Plaintext `OPPORTUNITYOS_FOUNDER_PASSWORD` is local/test compatibility only and must not be deployed to the cloud API.
   - **Configuration** (`PORT`, `HOST`, `OPPORTUNITYOS_POLL_INTERVAL_HOURS`): Injected via environment variables or ConfigMaps.
2. **Value Redaction**:
   - The runtime entrypoint and validation scripts redact all secret values in error and log output.
   - Placeholders (`replace_me`, `<...>`, `${...}`) are rejected fail-closed.
3. **No Secrets Baked into Image**:
   - `.dockerignore` excludes `.env*`, `private/`, `*.db`, `*.sql`, `*.dump`, and VCS directories.

---

## 5. Generic Orchestrator Examples

### 5.1 Docker Compose (Local / Self-Hosted Cloud)
```yaml
version: "3.8"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: opportunityos
      POSTGRES_USER: opos
      POSTGRES_PASSWORD: secretpassword
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "opos"]
      interval: 5s
      timeout: 5s
      retries: 5

  migrate:
    image: opportunityos:fr007
    command: ["migrate"]
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      CLOUD_DATABASE_URL: ${CLOUD_DATABASE_URL}

  api:
    image: opportunityos:fr007
    command: ["api"]
    depends_on:
      migrate:
        condition: service_completed_successfully
    ports:
      - "8000:8000"
    environment:
      CLOUD_DATABASE_URL: ${CLOUD_DATABASE_URL}
      OPPORTUNITYOS_FOUNDER_PASSWORD: ${OPPORTUNITYOS_FOUNDER_PASSWORD}
      OPPORTUNITYOS_SESSION_SECRET: ${OPPORTUNITYOS_SESSION_SECRET}
      PORT: "8000"

  worker:
    image: opportunityos:fr007
    command: ["worker"]
    depends_on:
      migrate:
        condition: service_completed_successfully
    environment:
      CLOUD_DATABASE_URL: ${CLOUD_DATABASE_URL}

  scheduler:
    image: opportunityos:fr007
    command: ["scheduler"]
    depends_on:
      migrate:
        condition: service_completed_successfully
    environment:
      CLOUD_DATABASE_URL: ${CLOUD_DATABASE_URL}

volumes:
  pgdata:
```

### 5.2 Kubernetes Pre-Deploy Job & Services
```yaml
# 1. Migration Job (Run before rollout)
apiVersion: batch/v1
kind: Job
metadata:
  name: opportunityos-migrate
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: migrate
        image: opportunityos:fr007
        args: ["migrate"]
        envFrom:
        - secretRef:
            name: opportunityos-secrets

---
# 2. API Deployment (Horizontal)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opportunityos-api
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: api
        image: opportunityos:fr007
        args: ["api"]
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: opportunityos-secrets
        livenessProbe:
          exec:
            command: ["python", "scripts/container_entrypoint.py", "liveness"]
        readinessProbe:
          exec:
            command: ["python", "scripts/container_entrypoint.py", "readiness"]

---
# 3. Worker Deployment (Horizontal)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opportunityos-worker
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: worker
        image: opportunityos:fr007
        args: ["worker"]
        envFrom:
        - secretRef:
            name: opportunityos-secrets

---
# 4. Scheduler Deployment (Strict Singleton)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opportunityos-scheduler
spec:
  replicas: 1
  strategy:
    type: Recreate
  template:
    spec:
      containers:
      - name: scheduler
        image: opportunityos:fr007
        args: ["scheduler"]
        envFrom:
        - secretRef:
            name: opportunityos-secrets
