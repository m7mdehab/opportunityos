# OpportunityOS OCI Container Role Runtime

## 1. Overview and Purpose

OpportunityOS provides a production-grade OCI container image packaging the Python runtime for cloud and orchestrator environments (Kubernetes, AWS ECS, Google Cloud Run, Azure Container Apps, or Docker Compose).

The container runtime enforces:
- **No Founder-PC Dependency**: Eliminates local file paths, localhost databases, and desktop session requirements.
- **Explicit Role Separation**: Distinct execution roles (`api`, `worker`, `scheduler`, `migrate`) so no role silently starts another.
- **Fail-Closed Security**: Missing required secrets, misconfigured credentials, or conflicting endpoints exit non-zero immediately.
- **Least-Privilege Execution**: Container runs as non-root user `appuser` (UID/GID 1000).
- **Secret Isolation**: Secrets are injected strictly at runtime via environment variables or secret managers; zero credentials or private files are baked into the image.

---

## 2. Container Architecture

### 2.1 Base Image and Environment
- Base image: `python:3.12-slim-bookworm`
- Non-root user: `appuser` (`uid=1000`, `gid=1000`)
- Working directory: `/app`
- Unbuffered output: `PYTHONUNBUFFERED=1`
- Bytecode disabled: `PYTHONDONTWRITEBYTECODE=1`
- Entrypoint: `python scripts/container_entrypoint.py`

### 2.2 Role Matrix

| Role | Responsibility | Default Network Binding | Typical Deployment Type |
| :--- | :--- | :--- | :--- |
| **`api`** | Uvicorn FastAPI server | `0.0.0.0:8000` (or `PORT`) | Web service / Ingress target |
| **`worker`** | Background queue consumer | None (internal DB queue) | Worker service / Replica deployment |
| **`scheduler`** | Periodic poll timer | None (enqueues DB jobs) | Singleton daemon / Cron service |
| **`migrate`** | Alembic schema migrations (`upgrade head`) | None | One-shot initialization job / Pre-deploy hook |
| **`readiness`**| Lightweight DB & migration check | None | Orchestrator readiness probe |
| **`liveness`** | Fast process health probe | None | Orchestrator liveness probe |

---

## 3. Environment Variables & Secret Classification

Secrets MUST be injected dynamically at runtime via your orchestrator secret store (e.g. AWS Secrets Manager, Kubernetes Secrets, Vault). Never bake secrets into container images or commit them to Git.

### 3.1 Role Configuration Matrix

| Variable Name | Role(s) | Classification | Purpose | Default |
| :--- | :--- | :--- | :--- | :--- |
| `CLOUD_DATABASE_URL` | All roles | Secret | Cloud PostgreSQL connection string. Aliased to `OPPORTUNITYOS_DB_URL`. | None (Required) |
| `OPPORTUNITYOS_DB_URL` | All roles | Secret | Direct PostgreSQL connection string. | None (Required if cloud DB unset) |
| `OPPORTUNITYOS_FOUNDER_PASSWORD` | `api` | Secret | Founder authentication password. | None (Required for API) |
| `OPPORTUNITYOS_SESSION_SECRET` | `api` | Secret | Cryptographic session signing key. | None (Required for API) |
| `PORT` | `api` | Config | Port to bind Uvicorn. | `8000` |
| `HOST` | `api` | Config | Host address to bind Uvicorn. | `0.0.0.0` |
| `OPPORTUNITYOS_API_PORT` | `api` | Config | Alternative port variable. | `8000` |
| `OPPORTUNITYOS_POLL_INTERVAL_HOURS` | `scheduler` | Config | Polling interval for due sources. | `6.0` |
| `OPPORTUNITYOS_TRUTH_PACK_PATH` | `api`, `worker` | Config / Path | Path to truth pack YAML if volume-mounted. | `private/truth_pack.yaml` |
| `OPPORTUNITYOS_FORCE_SECURE_COOKIES`| `api` | Config | Force secure cookie flag behind reverse proxies. | `0` (or auto-detected) |

---

## 4. Health and Readiness Probes

The container entrypoint provides lightweight, deterministic probes that avoid scanning or rebuilding the opportunity feed:

### 4.1 Readiness Probe (`scripts/container_entrypoint.py readiness`)
- Executes:
  1. `SELECT 1` on the PostgreSQL connection.
  2. `SELECT version_num FROM alembic_version LIMIT 1` to verify schema migrations.
- **Invariants**:
  - Does NOT query `opportunities` table.
  - Does NOT load the founder truth pack into memory.
  - Does NOT rebuild feed projections.
  - Proves connectivity and schema health in <10ms.

### 4.2 Liveness Probe (`scripts/container_entrypoint.py liveness`)
- Verifies process execution and interpreter health.
- Exits `0` on success.

### 4.3 HTTP Health Check (API role)
- `GET /api/auth/me` verifies HTTP listener and session serializer readiness (returns `401 Unauthorized` without session cookie, proving endpoint is active and fail-closed).

---

## 5. Deployment Examples

### 5.1 One-Shot Migration Job (Run Prior to Deployment)
Run schema migrations to `head` before starting new service replicas:
```bash
docker run --rm \
  -e CLOUD_DATABASE_URL \
  opportunityos:fr007 migrate
```

### 5.2 API Web Service
Deploy with port mapping and required credentials:
```bash
docker run -d \
  --name opportunityos-api \
  -p 8000:8000 \
  -e CLOUD_DATABASE_URL \
  -e OPPORTUNITYOS_FOUNDER_PASSWORD \
  -e OPPORTUNITYOS_SESSION_SECRET \
  -e PORT=8000 \
  opportunityos:fr007 api
```

### 5.3 Background Worker Service
Deploy background worker replicas for durable job queue consumption:
```bash
docker run -d \
  --name opportunityos-worker \
  -e CLOUD_DATABASE_URL \
  opportunityos:fr007 worker
```
*(Optionally pass `--max-jobs 100` or `--poll-interval 2.0`)*

### 5.4 Dedicated Poll Scheduler Service
Deploy a single instance (singleton) to enqueue due source polls:
```bash
docker run -d \
  --name opportunityos-scheduler \
  -e CLOUD_DATABASE_URL \
  -e OPPORTUNITYOS_POLL_INTERVAL_HOURS=6.0 \
  opportunityos:fr007 scheduler
```

### 5.5 Kubernetes Pod / Deployment Specification Example
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opportunityos-api
spec:
  replicas: 2
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
          initialDelaySeconds: 5
          periodSeconds: 10
        readinessProbe:
          exec:
            command: ["python", "scripts/container_entrypoint.py", "readiness"]
          initialDelaySeconds: 5
          periodSeconds: 10
```

---

## 6. Shutdown and Signal Handling

- **API Role**: Uvicorn is executed directly via `os.execvp`, making it PID 1. It traps `SIGTERM` / `SIGINT`, completes active requests, and exits cleanly.
- **Worker Role**: `WorkerRunner` is executed directly as PID 1, honoring `SIGTERM` to finish current job processing within lease boundaries before exiting.
- **Scheduler Role**: Registers `SIGTERM` and `SIGINT` handlers on an internal `threading.Event`, gracefully stopping the tick loop and releasing resources.
