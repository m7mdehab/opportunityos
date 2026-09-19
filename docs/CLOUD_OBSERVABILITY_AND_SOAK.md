# FR-007 Cloud Observability & 7-Day Soak Runbook

This runbook documents the operational architecture, health checks, alerting lifecycle, soak evidence generation, and cost control procedures for OpportunityOS cloud runtime under BRIEF-FR-007.

---

## 1. Observability Cadence & Triggers

External monitoring operates from GitHub Actions via `.github/workflows/fr007-cloud-observability.yml`:

- **Scheduled Cadence**: `*/30 * * * *` (runs every 30 minutes).
- **Execution Surface**: `ubuntu-slim` hosted runner (consuming 1 billed minute per run = 1,440 billed min/month out of the 2,000 minute free allowance, leaving 560 minutes of CI headroom).
- **Manual Dispatch Modes**:
  - `MONITOR`: Performs live end-to-end health check across all configured subsystems, captures an immutable soak snapshot (even during failures), and processes alert mutations.
  - `TEST_ALERT`: Injects a synthetic, non-destructive incident into the alerting pipeline to verify notification and issue creation without disrupting production.
  - `VALIDATE`: Executes deterministic verification gates (`validate_hosted_acceptance.py` and `validate_cloud_cost_quota.py`).
  - `SOAK_SUMMARY`: Downloads remote snapshot artifacts via `scripts/fetch_soak_artifacts.py`, evaluates the 7-day window via `scripts/fr007_soak_verify.py` as a fail-closed gate, and generates the release evidence index.

---

## 2. Health Checks & Threshold Matrix

| Subsystem / Check | Target Endpoint / Query | Normal / PASS | Warning / WARN | Failure / FAIL |
|---|---|---|---|---|
| **Web Liveness** | `GET https://<web_host>/` | HTTP 200 OK, valid TLS certificate, OpportunityOS signal in HTML body. | Latency > 2.5s | HTTP status != 200, TLS certificate expired/invalid, unreachable host. |
| **API Liveness** | `GET https://<api_host>/api/auth/me` | HTTP 401 Unauthorized (unauthenticated probe proves API responds without credentials). | Latency > 1.5s | HTTP 5xx, connection timeout, connection refused, or unexpected redirect. |
| **Database Connection** | `SELECT 1` | Immediate connection success (< 500ms). | Latency >= 1.0s | Connection refused, authentication failure, or pool timeout. |
| **Alembic Version** | `SELECT version_num FROM alembic_version` | Valid migration revision string present. | - | Empty table, missing table, or unapplied core migrations. |
| **Queue Dead Letters** | `status = 'failed'` in `worker_jobs` | 0 dead-letter jobs. | - | > 0 jobs in terminal failed status. |
| **Expired Worker Leases** | `locked_until < NOW()` while `status = 'running'` | 0 expired leases. | - | > 0 orphaned locked jobs. |
| **Queue Due Age** | `NOW() - scheduled_for` for oldest pending job | < 15 minutes. | >= 15 minutes. | >= 60 minutes (stalled queue worker). |
| **Scheduler Heartbeat** | `NOW() - MAX(last_polled_at)` in `source_schedules` | < 15 minutes. | >= 15 minutes. | >= 60 minutes (stalled scheduler). |
| **Source Freshness** | Per-source `NOW() > next_due` in `source_schedules` | All active sources within cadence. | 1 source overdue by > `1.5 * cadence_hours`. | >= 2 sources overdue by > `1.5 * cadence_hours`. |
| **Backup Heartbeat** | Sanitized backup manifest in storage | Manifest age < 24h, `result: "SUCCESS"`. | Manifest age >= 24h. | Manifest age >= 36h, missing manifest, or `result: "FAILED"`. |

---

## 3. Incident Alerting Lifecycle

Alerts are routed through GitHub Issues using deterministic deduplication:

1. **Deduplication Marker**:
   Every incident issue body contains the immutable HTML marker:
   `<!-- opos-monitor-incident-key: fr007-cloud-runtime -->`

2. **Canonical Action Schema**:
   `scripts/fr007_cloud_monitor.py` outputs a structured incident action consumed by `scripts/process_incident_alert.py`:
   ```json
   {
     "action": "CREATE | UPDATE | RESOLVE | NONE",
     "title": "...",
     "body": "...",
     "issue_number": null,
     "marker": "<!-- opos-monitor-incident-key: fr007-cloud-runtime -->",
     "is_synthetic": false
   }
   ```

3. **Lifecycle Transitions**:
   - **`CREATE`**: When any check transitions to `FAIL` and no open incident issue exists, the monitor creates an issue titled:
     `[FR-007 Monitor] Cloud runtime incident`
   - **`UPDATE`**: If an open incident issue already exists and the system remains in `FAIL`, an update comment is appended with the timestamp and failing checks.
   - **`RESOLVE`**: When all checks return to `PASS` (or `WARN`), the open issue is automatically closed with a resolution summary comment.

4. **Fail-Closed Execution**:
   `scripts/process_incident_alert.py` checks all GitHub CLI return codes. If an issue creation or comment operation fails, it exits non-zero, preventing silent alert delivery failures.

---

## 4. Synthetic Incident Verification (`TEST_ALERT`)

To verify alerting without causing production disruption:
```bash
# Run synthetic alert test locally or via workflow_dispatch
python scripts/fr007_cloud_monitor.py \
  --mode TEST_ALERT \
  --output-report .monitor_output/report.json \
  --output-incident .monitor_output/incident.json

# Execute synthetic alert action
python scripts/process_incident_alert.py --incident-file .monitor_output/incident.json
```
This generates a controlled payload titled `[FR-007 Monitor] SYNTHETIC TEST ALERT: Incident pipeline verification` containing the deduplication marker and verifying that the alert creation/comment logic operates correctly.

---

## 5. Soak Snapshots & 7-Day Verification (A-14)

### Snapshot Generation
Each 30-minute monitor cycle produces an immutable JSON snapshot, even during failure conditions:
```bash
python scripts/fr007_soak_snapshot.py \
  --report-file .monitor_output/report.json \
  --deployment-id "staging-cloudflare-aca" \
  --workflow-run-id "$GITHUB_RUN_ID" \
  --output-dir .monitor_output/soak/
```
Output schema:
```json
{
  "timestamp_utc": "2026-09-19T02:00:00Z",
  "repository_sha": "ce58a9bb779a1a69aaafa9d0ca8c7e88825a1f8f",
  "deployment_identifier": "staging-cloudflare-aca",
  "workflow_run_id": "12345678",
  "monitor_run_id": "run-a1b2c3d4e5f6",
  "proof_scope": "FULL_HOSTED",
  "web_state": "PASS",
  "api_state": "PASS",
  "database_state": "PASS",
  "queue_state": "PASS",
  "scheduler_state": "PASS",
  "source_freshness_state": "PASS",
  "backup_state": "PASS",
  "overall_state": "PASS",
  "founder_pc_dependency": false
}
```

### Artifact Persistence & Aggregation
Snapshots are persisted as GitHub Actions workflow artifacts with a **90-day retention window** (`retention-days: 90`). In `SOAK_SUMMARY` mode:
```bash
# Aggregate remote snapshot artifacts across workflow runs
python scripts/fetch_soak_artifacts.py --target-dir .monitor_output/soak/

# Verify 7-day continuous soak (fail-closed release gate)
python scripts/fr007_soak_verify.py \
  --input-dir .monitor_output/soak/ \
  --min-hours 168.0 \
  --max-gap-hours 4.0 \
  --require-backup
```
Acceptance Predicates:
1. **Proof Scope**: All evaluated snapshots must have `proof_scope == "FULL_HOSTED"`. STATIC or synthetic records cannot count toward live soak.
2. **Duration**: $\ge 168.0\text{ hours}$ (7 full continuous days) between earliest and latest snapshot.
3. **Continuity**: Maximum gap between consecutive snapshots $\le 4.0\text{ hours}$.
4. **Health**: 0 snapshots exhibiting `overall_state == "FAIL"` or `NOT_CONFIGURED`.
5. **Backup**: Latest backup manifest must be `PASS` or `WARN`.
6. **Founder Independence**: All snapshots have `founder_pc_dependency == false`. Any `true` value immediately fails the gate.

---

## 6. Cost & Quota Audit (A-17)

Before closing releases, execute cost validation:
```bash
# Validate staging resource allocations
python scripts/validate_cloud_cost_quota.py --staging

# Enforce strict zero out-of-pocket production policy
python scripts/validate_cloud_cost_quota.py --production
```

All allocations must adhere to `docs/CLOUD_COST_QUOTA_ENVELOPE.md`:
- Supabase: < 500 MB DB, < 1 GB storage, < 5 GB egress (permanent free allowance).
- Azure Container Apps: 0.25 vCPU, 0.5 GiB covered under Azure for Students credit (temporary credit, $0 out-of-pocket).
- Cloudflare Workers: < 100k daily requests (permanent free allowance).
- GitHub Actions: 30-min cadence = 1,440 billed min/month, leaving 560 minutes of CI headroom under the 2,000 minute free allowance.
- Net Founder Out-of-Pocket: **$0.00**.
