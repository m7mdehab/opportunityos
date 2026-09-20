"""FR-007 Provider-Neutral Cloud Observability & Health Monitor.

Observes public web availability, API reachability, PostgreSQL health,
durable worker queue state, source freshness, scheduler lag, worker leases,
and backup heartbeats without mutating production resources or requiring
founder PC availability.

States: PASS, WARN, FAIL, BLOCKED, NOT_CONFIGURED.
Never converts BLOCKED or NOT_CONFIGURED into PASS.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STATES = ("PASS", "WARN", "FAIL", "BLOCKED", "NOT_CONFIGURED")
MODES = ("STATIC", "HTTP", "FULL", "TEST_ALERT")

INCIDENT_MARKER = "<!-- opos-monitor-incident-key: fr007-cloud-runtime -->"
INCIDENT_TITLE = "[FR-007 Monitor] Cloud runtime incident"
SYNTHETIC_INCIDENT_TITLE = "[FR-007 Monitor] SYNTHETIC TEST ALERT: Incident pipeline verification"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    message: str
    metrics: dict[str, Any] = field(default_factory=dict)
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if self.status not in STATES:
            raise ValueError(f"Invalid status: {self.status}; must be one of {STATES}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MonitorReport:
    overall_status: str
    mode: str
    timestamp_utc: str
    checks: list[CheckResult]
    summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.overall_status not in STATES:
            raise ValueError(f"Invalid overall status: {self.overall_status}")
        if self.mode not in MODES:
            raise ValueError(f"Invalid mode: {self.mode}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "mode": self.mode,
            "timestamp_utc": self.timestamp_utc,
            "summary": self.summary,
            "checks": [c.to_dict() for c in self.checks],
        }


# ============================================================================
# 1. URL Safety & Sanitization
# ============================================================================

_SENSITIVE_QUERY_PARAMS = frozenset(
    {"token", "key", "secret", "password", "auth", "api_key", "apikey", "session", "access_token"}
)

_SECRET_PATTERNS = (
    re.compile(r"postgres(?:ql)?://([^:]+):([^@]+)@", re.IGNORECASE),
    re.compile(r"Bearer\s+([a-zA-Z0-9_\-\.]+)", re.IGNORECASE),
    re.compile(r"(?:password|secret|api[_-]?key|token)\s*[:=]\s*['\"]?([^\s'\"]+)", re.IGNORECASE),
    re.compile(r"oos_session=([a-zA-Z0-9_\-\.]+)", re.IGNORECASE),
    re.compile(r"private/[\w\-/]+\.(?:yaml|json|pem|key)", re.IGNORECASE),
)


def validate_monitor_url(url: str, name: str = "url") -> tuple[bool, str]:
    """Validate that a monitoring URL is credential-free, HTTPS, and non-loopback."""
    if not url or not isinstance(url, str):
        return False, f"{name}: URL must be a non-empty string"

    url_str = url.strip()
    if url_str.startswith("http://"):
        return False, f"{name}: Insecure HTTP is prohibited; must use HTTPS"
    if not url_str.startswith("https://"):
        return False, f"{name}: Must use HTTPS protocol"

    try:
        parsed = urllib.parse.urlparse(url_str)
    except Exception as exc:
        return False, f"{name}: Malformed URL: {exc}"

    if parsed.username or parsed.password:
        return False, f"{name}: URL credentials (username/password) are strictly prohibited"

    if "@" in url_str.split("/")[2]:
        return False, f"{name}: Userinfo '@' syntax is prohibited"

    host = (parsed.hostname or "").lower()
    if not host:
        return False, f"{name}: URL has missing hostname"

    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost") or host.startswith("127."):
        return False, f"{name}: Localhost and loopback endpoints are prohibited in cloud monitor"

    if parsed.fragment:
        return False, f"{name}: URL fragments are prohibited"

    if parsed.query:
        query_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        for param in query_params:
            if param.lower() in _SENSITIVE_QUERY_PARAMS:
                return False, f"{name}: Sensitive query parameter '{param}' is prohibited"

    return True, ""


def sanitize_alert_text(text: str) -> str:
    """Strip database credentials, bearer tokens, cookies, and secret paths."""
    if not text:
        return ""

    sanitized = text
    # Redact postgresql DSN passwords
    sanitized = re.sub(
        r"(postgres(?:ql)?://[^:]+:)([^@]+)(@)",
        r"\1[REDACTED]\3",
        sanitized,
        flags=re.IGNORECASE,
    )
    # Redact Authorization: Bearer
    sanitized = re.sub(
        r"(Bearer\s+)[a-zA-Z0-9_\-\.]{8,}",
        r"\1[REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )
    # Redact generic secrets
    sanitized = re.sub(
        r"((?:password|secret|api[_-]?key|token)\s*[:=]\s*['\"]?)([^'\";\s]{4,})",
        r"\1[REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )
    # Redact session cookies
    sanitized = re.sub(
        r"(oos_session=)[a-zA-Z0-9_\-\.]{8,}",
        r"\1[REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )
    # Redact private paths
    sanitized = re.sub(
        r"private/[\w\-/]+\.(?:yaml|json|pem|key)",
        r"[REDACTED_PRIVATE_PATH]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


# ============================================================================
# 2. HTTP Probes
# ============================================================================

def default_http_client(url: str, headers: Mapping[str, str] | None = None, timeout: float = 10.0) -> tuple[int, Mapping[str, str], str]:
    """Default stdlib urllib fetcher with strict read-only GET."""
    import urllib.request
    req = urllib.request.Request(
        url,
        headers=dict(headers or {}),
        method="GET",
    )
    req.add_header("User-Agent", "OpportunityOS-External-Monitor/1.0 (+https://opportunityos.m7mdehab.com)")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            resp_headers = dict(response.headers)
            body = response.read().decode("utf-8", errors="replace")
            return status, resp_headers, body
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace") if hasattr(err, "read") else ""
        return err.code, dict(err.headers or {}), body
    except Exception as exc:
        raise RuntimeError(sanitize_alert_text(str(exc))) from None


def probe_web_liveness(
    url: str | None,
    client: Callable[..., tuple[int, Mapping[str, str], str]] | None = None,
    timeout: float = 10.0,
) -> CheckResult:
    """Probe public web root/login route for TLS availability and OpportunityOS branding."""
    if not url:
        return CheckResult(
            name="web_liveness",
            status="NOT_CONFIGURED",
            message="OPOS_MONITOR_WEB_URL is not configured",
        )

    valid, err = validate_monitor_url(url, "web_url")
    if not valid:
        return CheckResult(
            name="web_liveness",
            status="FAIL",
            message=err,
        )

    fetcher = client or default_http_client
    try:
        status_code, headers, body = fetcher(url, timeout=timeout)
        parsed_url = urllib.parse.urlparse(url)
        safe_host = parsed_url.hostname or "unknown_host"

        has_marker = (
            "opportunityos" in body.lower()
            or "opportunity os" in body.lower()
            or "opportunity" in body.lower()
        )

        if status_code == 200:
            if has_marker:
                return CheckResult(
                    name="web_liveness",
                    status="PASS",
                    message=f"Web frontend healthy at {safe_host} (HTTP 200 with OpportunityOS signal)",
                    metrics={"status_code": 200, "host": safe_host, "marker_found": True},
                )
            return CheckResult(
                name="web_liveness",
                status="WARN",
                message=f"Web frontend returned 200 at {safe_host} but OpportunityOS marker was absent",
                metrics={"status_code": 200, "host": safe_host, "marker_found": False},
            )
        return CheckResult(
            name="web_liveness",
            status="FAIL",
            message=f"Web frontend returned unexpected HTTP status {status_code} at {safe_host}",
            metrics={"status_code": status_code, "host": safe_host},
        )
    except Exception as exc:
        clean_err = sanitize_alert_text(str(exc))
        return CheckResult(
            name="web_liveness",
            status="FAIL",
            message=f"Web probe failed to reach endpoint: {clean_err}",
            metrics={"error": clean_err},
        )


def probe_api_liveness(
    url: str | None,
    client: Callable[..., tuple[int, Mapping[str, str], str]] | None = None,
    timeout: float = 10.0,
    supabase_url: str | None = None,
) -> CheckResult:
    """Probe API without credentials; 401 challenge or Supabase health proves connectivity."""
    if not url:
        if supabase_url:
            return probe_supabase_health(supabase_url, client=client, timeout=timeout)
        return CheckResult(
            name="api_liveness",
            status="NOT_CONFIGURED",
            message="Neither standalone nor same-origin API URL is configured",
        )

    valid, err = validate_monitor_url(url, "api_url")
    if not valid:
        return CheckResult(
            name="api_liveness",
            status="FAIL",
            message=err,
        )

    # Append /api/auth/me if base URL is provided
    clean_url = url.rstrip("/")
    probe_endpoint = f"{clean_url}/api/auth/me" if not clean_url.endswith("/me") else clean_url

    fetcher = client or default_http_client
    try:
        status_code, headers, body = fetcher(probe_endpoint, timeout=timeout)
        parsed_url = urllib.parse.urlparse(probe_endpoint)
        safe_host = parsed_url.hostname or "unknown_host"

        # Expected unauthenticated contract is 401 Unauthorized
        if status_code == 401:
            return CheckResult(
                name="api_liveness",
                status="PASS",
                message=f"API reachable at {safe_host} (HTTP 401 unauthenticated challenge verified)",
                metrics={"status_code": 401, "host": safe_host, "connectivity_proven": True},
            )
        if status_code == 200:
            return CheckResult(
                name="api_liveness",
                status="PASS",
                message=f"API reachable at {safe_host} (HTTP 200)",
                metrics={"status_code": 200, "host": safe_host, "connectivity_proven": True},
            )
        # Cloudflare edge returning 404 for legacy proxy: fallback to Supabase health
        if status_code == 404 and supabase_url:
            sb_res = probe_supabase_health(supabase_url, client=client, timeout=timeout)
            if sb_res.status == "PASS":
                return sb_res
        if status_code in (500, 502, 503, 504):
            return CheckResult(
                name="api_liveness",
                status="FAIL",
                message=f"API returned server error {status_code} at {safe_host}",
                metrics={"status_code": status_code, "host": safe_host},
            )
        return CheckResult(
            name="api_liveness",
            status="WARN",
            message=f"API returned non-standard status {status_code} at {safe_host}",
            metrics={"status_code": status_code, "host": safe_host},
        )
    except Exception as exc:
        if supabase_url:
            try:
                sb_res = probe_supabase_health(supabase_url, client=client, timeout=timeout)
                if sb_res.status == "PASS":
                    return sb_res
            except Exception:
                pass
        clean_err = sanitize_alert_text(str(exc))
        return CheckResult(
            name="api_liveness",
            status="FAIL",
            message=f"API probe failed to reach endpoint: {clean_err}",
            metrics={"error": clean_err},
        )


def probe_supabase_health(
    url: str,
    client: Callable[..., tuple[int, Mapping[str, str], str]] | None = None,
    timeout: float = 10.0,
) -> CheckResult:
    """Probe Supabase Auth / REST health without requiring founder credentials."""
    valid, err = validate_monitor_url(url, "supabase_url")
    if not valid:
        return CheckResult(name="api_liveness", status="FAIL", message=err)

    clean_url = url.rstrip("/")
    probe_endpoint = f"{clean_url}/auth/v1/health"
    fetcher = client or default_http_client
    try:
        status_code, _, body = fetcher(probe_endpoint, timeout=timeout)
        parsed_url = urllib.parse.urlparse(probe_endpoint)
        safe_host = parsed_url.hostname or "unknown_host"
        if status_code in (200, 401):
            return CheckResult(
                name="api_liveness",
                status="PASS",
                message=f"Supabase-native health verified at {safe_host} (HTTP {status_code})",
                metrics={"status_code": status_code, "host": safe_host, "supabase_native": True},
            )
        return CheckResult(
            name="api_liveness",
            status="WARN",
            message=f"Supabase health returned non-standard status {status_code} at {safe_host}",
            metrics={"status_code": status_code, "host": safe_host},
        )
    except Exception as exc:
        clean_err = sanitize_alert_text(str(exc))
        return CheckResult(
            name="api_liveness",
            status="FAIL",
            message=f"Supabase probe failed to reach endpoint: {clean_err}",
            metrics={"error": clean_err},
        )


# ============================================================================
# 3. Database & Queue Observability (FULL mode)
# ============================================================================

def _as_aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def probe_database_and_queue(
    db_url: str | None,
    connection_factory: Callable[[], Any] | None = None,
    clock: Callable[[], datetime] | None = None,
    due_age_warn_seconds: float = 900.0,
    due_age_fail_seconds: float = 3600.0,
) -> list[CheckResult]:
    """Query real durable PostgreSQL tables for queue, scheduler, and source metrics."""
    if not db_url and connection_factory is None:
        return [
            CheckResult(
                name="database_and_queue",
                status="NOT_CONFIGURED",
                message="CLOUD_DATABASE_URL is not configured for FULL database observability",
            )
        ]

    now = (clock or (lambda: datetime.now(timezone.utc)))()

    try:
        if connection_factory is not None:
            session = connection_factory()
        else:
            from storage.engine import get_engine, get_session_factory
            engine = get_engine(db_url)
            session = get_session_factory(engine)()
    except Exception as exc:
        clean_err = sanitize_alert_text(str(exc))
        return [
            CheckResult(
                name="database_connectivity",
                status="FAIL",
                message=f"Database connection failed: {clean_err}",
                metrics={"error": clean_err},
            )
        ]

    results: list[CheckResult] = []
    try:
        from sqlalchemy import text
        from storage.models import SourcePollRunRecord, SourceScheduleRecord, WorkerJobRecord

        # 1. Connectivity & Alembic revision
        try:
            rev_row = session.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
            alembic_rev = rev_row[0] if rev_row else "none"
            results.append(
                CheckResult(
                    name="database_connectivity",
                    status="PASS",
                    message="Database connected and responsive",
                    metrics={"alembic_revision": alembic_rev},
                )
            )
        except Exception as exc:
            results.append(
                CheckResult(
                    name="database_connectivity",
                    status="FAIL",
                    message=f"Failed to query alembic_version: {sanitize_alert_text(str(exc))}",
                )
            )
            return results

        # 2. Worker Jobs Metrics
        now_naive = now.astimezone(timezone.utc).replace(tzinfo=None)
        all_jobs = session.query(WorkerJobRecord).all()

        running_jobs = [j for j in all_jobs if j.status == "RUNNING"]
        pending_jobs = [j for j in all_jobs if j.status == "PENDING"]
        retry_jobs = [j for j in all_jobs if j.status == "RETRY"]
        dead_letter_jobs = [j for j in all_jobs if j.status == "DEAD_LETTER"]

        due_jobs = [
            j for j in pending_jobs + retry_jobs
            if j.run_after is None or j.run_after <= now_naive
        ]

        oldest_due_age = 0.0
        for j in due_jobs:
            ref_time = j.run_after or j.created_at
            if ref_time:
                age = (now_naive - ref_time).total_seconds()
                if age > oldest_due_age:
                    oldest_due_age = age

        expired_leases = [
            j for j in running_jobs
            if j.lease_expires_at is not None and j.lease_expires_at < now_naive
        ]

        # Evaluate Queue Status
        queue_metrics = {
            "total_jobs": len(all_jobs),
            "running_count": len(running_jobs),
            "pending_count": len(pending_jobs),
            "retry_count": len(retry_jobs),
            "dead_letter_count": len(dead_letter_jobs),
            "due_count": len(due_jobs),
            "oldest_due_age_seconds": round(oldest_due_age, 1),
            "expired_lease_count": len(expired_leases),
        }

        if len(expired_leases) > 0:
            results.append(
                CheckResult(
                    name="queue_health",
                    status="FAIL",
                    message=f"Worker queue has {len(expired_leases)} expired running lease(s)",
                    metrics=queue_metrics,
                )
            )
        elif oldest_due_age >= due_age_fail_seconds:
            results.append(
                CheckResult(
                    name="queue_health",
                    status="FAIL",
                    message=f"Oldest due job age ({round(oldest_due_age)}s) exceeds FAIL threshold ({round(due_age_fail_seconds)}s)",
                    metrics=queue_metrics,
                )
            )
        elif oldest_due_age >= due_age_warn_seconds or len(dead_letter_jobs) > 0:
            reasons = []
            if oldest_due_age >= due_age_warn_seconds:
                reasons.append(f"due age {round(oldest_due_age)}s >= {round(due_age_warn_seconds)}s")
            if len(dead_letter_jobs) > 0:
                reasons.append(f"{len(dead_letter_jobs)} dead-letter job(s)")
            results.append(
                CheckResult(
                    name="queue_health",
                    status="WARN",
                    message=f"Queue warning: {', '.join(reasons)}",
                    metrics=queue_metrics,
                )
            )
        else:
            results.append(
                CheckResult(
                    name="queue_health",
                    status="PASS",
                    message="Queue healthy; no expired leases or overdue backlogs",
                    metrics=queue_metrics,
                )
            )

        # 3. Source Schedules & Freshness
        schedules = session.query(SourceScheduleRecord).all()
        active_source_ids = {
            j.payload_json and json.loads(j.payload_json).get("source_id")
            for j in pending_jobs + running_jobs + retry_jobs
            if j.payload_json and "source_id" in j.payload_json
        }

        due_sources = []
        overdue_sources_without_job = []

        for sched in schedules:
            sched_next_due = getattr(sched, "next_due_at", None) or getattr(sched, "next_due", None)
            if sched_next_due and sched_next_due <= now_naive:
                due_sources.append(sched.source_id)
                # Overdue threshold: cadence_hours + 1 hour grace
                cadence_hrs = sched.cadence_hours or 6.0
                grace_seconds = max(3600.0, cadence_hrs * 3600.0 * 0.5)
                overdue_threshold = sched_next_due.timestamp() + grace_seconds
                if now_naive.timestamp() > overdue_threshold and sched.source_id not in active_source_ids:
                    overdue_sources_without_job.append({
                        "source_id": sched.source_id,
                        "cadence_hours": cadence_hrs,
                        "next_due": sched_next_due.isoformat(),
                        "overdue_seconds": round(now_naive.timestamp() - sched_next_due.timestamp()),
                    })

        # Latest successful poll age
        latest_ok_poll = (
            session.query(SourcePollRunRecord)
            .filter_by(status="ok")
            .order_by(SourcePollRunRecord.started_at.desc())
            .first()
        )
        last_poll_age = None
        if latest_ok_poll and latest_ok_poll.started_at:
            last_poll_age = round((now_naive - latest_ok_poll.started_at).total_seconds())

        sched_metrics = {
            "total_schedules": len(schedules),
            "due_sources_count": len(due_sources),
            "overdue_without_job_count": len(overdue_sources_without_job),
            "overdue_sources": [s["source_id"] for s in overdue_sources_without_job],
            "last_successful_poll_age_seconds": last_poll_age,
        }

        if len(overdue_sources_without_job) > 0:
            results.append(
                CheckResult(
                    name="source_freshness",
                    status="WARN",
                    message=f"{len(overdue_sources_without_job)} source(s) overdue without active job in flight",
                    metrics=sched_metrics,
                )
            )
        else:
            results.append(
                CheckResult(
                    name="source_freshness",
                    status="PASS",
                    message="Source schedules and freshness within expected cadence",
                    metrics=sched_metrics,
                )
            )

    except Exception as exc:
        clean_err = sanitize_alert_text(str(exc))
        results.append(
            CheckResult(
                name="database_and_queue",
                status="FAIL",
                message=f"Database observability query failed: {clean_err}",
                metrics={"error": clean_err},
            )
        )
    finally:
        session.close()

    return results


# ============================================================================
# 4. Backup Heartbeat Contract
# ============================================================================

def fetch_backup_heartbeat_from_database(
    db_url: str | None,
    connection_factory: Callable[[], Any] | None = None,
) -> Mapping[str, Any] | None:
    """Read the latest sanitized encrypted-backup heartbeat from PostgreSQL."""
    if not db_url and connection_factory is None:
        return None
    session = None
    try:
        if connection_factory is not None:
            session = connection_factory()
        else:
            from storage.engine import get_engine, get_session_factory
            engine = get_engine(db_url)
            session = get_session_factory(engine)()
        from sqlalchemy import text
        exists = session.execute(
            text("SELECT to_regclass('public.backup_heartbeats')")
        ).scalar_one_or_none()
        if not exists:
            return None
        row = session.execute(text("""
            SELECT result, backup_completed_at, encryption, destination_class,
                   database_snapshot_sha, artifact_run_id
            FROM public.backup_heartbeats
            WHERE id='latest'
            LIMIT 1
        """)).mappings().first()
        if not row:
            return None
        completed = row.get("backup_completed_at")
        return {
            "result": row.get("result"),
            "backup_completed_at": completed.isoformat() if hasattr(completed, "isoformat") else str(completed),
            "encryption": bool(row.get("encryption")),
            "destination_class": row.get("destination_class"),
            "database_snapshot_sha": row.get("database_snapshot_sha"),
            "artifact_run_id": row.get("artifact_run_id"),
        }
    except Exception:
        return None
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def probe_backup_heartbeat(
    heartbeat: Mapping[str, Any] | None,
    clock: Callable[[], datetime] | None = None,
    max_age_hours: float = 26.0,
    encryption_required: bool = True,
) -> CheckResult:
    """Evaluate sanitized backup heartbeat metadata."""
    if not heartbeat:
        return CheckResult(
            name="backup_heartbeat",
            status="NOT_CONFIGURED",
            message="No backup heartbeat manifest or record configured",
        )

    result = heartbeat.get("result")
    completed_at_raw = heartbeat.get("backup_completed_at")
    encryption = heartbeat.get("encryption")
    dest_class = heartbeat.get("destination_class", "unknown")
    db_fingerprint = heartbeat.get("database_snapshot_sha")

    metrics = {
        "destination_class": dest_class,
        "encryption": encryption,
        "backup_completed_at": completed_at_raw,
        "snapshot_sha_present": bool(db_fingerprint),
    }

    if result != "SUCCESS":
        return CheckResult(
            name="backup_heartbeat",
            status="FAIL",
            message=f"Latest backup execution failed with result: {result}",
            metrics=metrics,
        )

    if encryption_required and not encryption:
        return CheckResult(
            name="backup_heartbeat",
            status="FAIL",
            message="Backup failed security check: encryption is required but recorded as false",
            metrics=metrics,
        )

    if not completed_at_raw:
        return CheckResult(
            name="backup_heartbeat",
            status="FAIL",
            message="Backup heartbeat missing 'backup_completed_at' timestamp",
            metrics=metrics,
        )

    try:
        now = (clock or (lambda: datetime.now(timezone.utc)))()
        completed_at = datetime.fromisoformat(str(completed_at_raw).replace("Z", "+00:00"))
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)

        age_seconds = (now - completed_at).total_seconds()
        metrics["age_hours"] = round(age_seconds / 3600.0, 1)

        if age_seconds < 0:
            return CheckResult(
                name="backup_heartbeat",
                status="WARN",
                message="Backup timestamp is in the future (clock skew detected)",
                metrics=metrics,
            )

        if age_seconds > max_age_hours * 3600.0:
            return CheckResult(
                name="backup_heartbeat",
                status="FAIL",
                message=f"Backup heartbeat is stale: {round(age_seconds / 3600.0, 1)}h old > {max_age_hours}h limit",
                metrics=metrics,
            )

        return CheckResult(
            name="backup_heartbeat",
            status="PASS",
            message=f"Backup heartbeat healthy ({round(age_seconds / 3600.0, 1)}h old, encrypted={encryption})",
            metrics=metrics,
        )
    except Exception as exc:
        return CheckResult(
            name="backup_heartbeat",
            status="FAIL",
            message=f"Failed to parse backup heartbeat timestamp: {exc}",
            metrics=metrics,
        )


# ============================================================================
# 5. Incident Formatting, Deduplication & Test Alerts
# ============================================================================

def build_incident_payload(report: MonitorReport, is_synthetic: bool = False) -> dict[str, Any]:
    """Construct sanitized GitHub Issue payload for monitor incident."""
    title = SYNTHETIC_INCIDENT_TITLE if is_synthetic else INCIDENT_TITLE
    timestamp = report.timestamp_utc

    failed_checks = [c for c in report.checks if c.status == "FAIL"]
    warn_checks = [c for c in report.checks if c.status == "WARN"]

    lines = [
        f"{INCIDENT_MARKER}",
        f"## {title}",
        "",
        f"**Timestamp (UTC):** `{timestamp}`",
        f"**Overall Status:** `{report.overall_status}`",
        f"**Mode:** `{report.mode}`",
        "",
    ]

    if is_synthetic:
        lines.extend([
            "> [!NOTE]",
            "> **SYNTHETIC TEST ALERT:** This is a planned verification of the external incident notification pipeline.",
            "> No production outage has occurred. No production workers, sources, or databases were affected.",
            "",
        ])

    if failed_checks:
        lines.append("### Failed Checks")
        for c in failed_checks:
            lines.append(f"- **{c.name}**: {sanitize_alert_text(c.message)}")
            if c.metrics:
                clean_metrics = sanitize_alert_text(json.dumps(c.metrics, sort_keys=True))
                lines.append(f"  - Metrics: `{clean_metrics}`")
        lines.append("")

    if warn_checks:
        lines.append("### Warning Checks")
        for c in warn_checks:
            lines.append(f"- **{c.name}**: {sanitize_alert_text(c.message)}")
        lines.append("")

    lines.extend([
        "### Operational Runbook Reference",
        "Refer to `docs/CLOUD_OBSERVABILITY_AND_SOAK.md` for recovery steps.",
        "Monitoring detects and alerts; it does not automatically mutate production resources.",
    ])

    return {
        "title": title,
        "body": "\n".join(lines),
        "labels": ["incident", "monitoring", "fr-007"],
        "is_synthetic": is_synthetic,
    }


def determine_alert_action(
    report: MonitorReport,
    open_issues: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Determine whether to create, update (comment), resolve (close), or no-op an incident."""
    matching_issue = None
    for issue in open_issues:
        body = str(issue.get("body") or "")
        state = str(issue.get("state") or "").lower()
        if INCIDENT_MARKER in body and state != "closed":
            matching_issue = issue
            break

    is_synthetic = (report.mode == "TEST_ALERT")
    default_title = SYNTHETIC_INCIDENT_TITLE if is_synthetic else INCIDENT_TITLE

    if report.overall_status == "FAIL":
        if matching_issue:
            failed_lines = [
                f"- {c.name}: {sanitize_alert_text(c.message)}"
                for c in report.checks if c.status == "FAIL"
            ]
            comment_body = (
                f"**[FR-007 Monitor Incident Update]** at `{report.timestamp_utc}`\n"
                f"Status remains FAIL:\n" + "\n".join(failed_lines)
            )
            return {
                "action": "UPDATE",
                "title": str(matching_issue.get("title") or default_title),
                "body": comment_body,
                "issue_number": matching_issue.get("number"),
                "marker": INCIDENT_MARKER,
                "is_synthetic": is_synthetic,
            }
        else:
            payload = build_incident_payload(report, is_synthetic=is_synthetic)
            return {
                "action": "CREATE",
                "title": payload["title"],
                "body": payload["body"],
                "issue_number": None,
                "marker": INCIDENT_MARKER,
                "is_synthetic": is_synthetic,
            }

    if report.overall_status in ("PASS", "WARN"):
        if matching_issue:
            resolution_body = (
                f"**[FR-007 Monitor Incident Resolved]** at `{report.timestamp_utc}`\n"
                f"System returned to healthy status ({report.overall_status}). All monitor checks passing or clear."
            )
            return {
                "action": "RESOLVE",
                "title": str(matching_issue.get("title") or default_title),
                "body": resolution_body,
                "issue_number": matching_issue.get("number"),
                "marker": INCIDENT_MARKER,
                "is_synthetic": is_synthetic,
            }
        return {
            "action": "NONE",
            "title": "",
            "body": "",
            "issue_number": None,
            "marker": INCIDENT_MARKER,
            "is_synthetic": is_synthetic,
        }

    return {
        "action": "NONE",
        "title": "",
        "body": "",
        "issue_number": None,
        "marker": INCIDENT_MARKER,
        "is_synthetic": is_synthetic,
    }


# ============================================================================
# 6. Main Monitor Orchestration
# ============================================================================

def run_monitor(
    mode: str = "FULL",
    web_url: str | None = None,
    api_url: str | None = None,
    db_url: str | None = None,
    supabase_url: str | None = None,
    backup_heartbeat: Mapping[str, Any] | None = None,
    backup_heartbeat_path: str | None = None,
    http_client: Callable[..., tuple[int, Mapping[str, str], str]] | None = None,
    db_connection_factory: Callable[[], Any] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> MonitorReport:
    """Execute the cloud monitor across configured probes."""
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    timestamp_utc = now.isoformat()

    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}; choose from {MODES}")

    if mode == "TEST_ALERT":
        checks = [
            CheckResult(
                name="synthetic_alert_probe",
                status="FAIL",
                message="Synthetic test alert triggered to verify external notification pipeline",
                metrics={"synthetic": True, "test_mode": True},
            )
        ]
        return MonitorReport(
            overall_status="FAIL",
            mode="TEST_ALERT",
            timestamp_utc=timestamp_utc,
            checks=checks,
            summary={"tested": "external_alert_publication"},
        )

    checks: list[CheckResult] = []

    # 1. Web Probe (HTTP or FULL mode)
    if mode in ("HTTP", "FULL"):
        effective_web_url = web_url or os.environ.get("OPOS_MONITOR_WEB_URL")
        checks.append(probe_web_liveness(effective_web_url, client=http_client))

        # 2. API Probe (HTTP or FULL mode)
        # In a zero-dollar / Supabase-native deployment, probe same-origin API on web URL or Supabase health
        effective_api_url = api_url or os.environ.get("OPOS_MONITOR_API_URL")
        effective_supabase_url = (
            supabase_url
            or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
            or os.environ.get("OPOS_MONITOR_SUPABASE_URL")
            or os.environ.get("SUPABASE_URL")
        )
        if effective_api_url:
            checks.append(probe_api_liveness(effective_api_url, client=http_client, supabase_url=effective_supabase_url))
        elif effective_web_url:
            checks.append(probe_api_liveness(effective_web_url, client=http_client, supabase_url=effective_supabase_url))
        elif effective_supabase_url:
            checks.append(probe_supabase_health(effective_supabase_url, client=http_client))
        else:
            checks.append(probe_api_liveness(None, client=http_client))

    # 3. Database & Queue Probes (FULL mode)
    if mode == "FULL":
        effective_db_url = db_url or os.environ.get("CLOUD_DATABASE_URL") or os.environ.get("OPPORTUNITYOS_DB_URL")
        db_checks = probe_database_and_queue(
            effective_db_url,
            connection_factory=db_connection_factory,
            clock=clock,
        )
        checks.extend(db_checks)

        # 4. Backup Heartbeat Probe (FULL mode)
        effective_heartbeat = backup_heartbeat
        if effective_heartbeat is None:
            effective_heartbeat = fetch_backup_heartbeat_from_database(
                effective_db_url,
                connection_factory=db_connection_factory,
            )
        if effective_heartbeat is None:
            hb_path = (
                backup_heartbeat_path
                or os.environ.get("OPOS_BACKUP_HEARTBEAT_PATH")
                or os.environ.get("FR007_BACKUP_MANIFEST_PATH")
            )
            if hb_path and Path(hb_path).is_file():
                try:
                    effective_heartbeat = json.loads(Path(hb_path).read_text(encoding="utf-8"))
                except Exception:
                    pass
        checks.append(probe_backup_heartbeat(effective_heartbeat, clock=clock))

    # Static mode: basic configuration presence check
    if mode == "STATIC":
        w_url = web_url or os.environ.get("OPOS_MONITOR_WEB_URL")
        d_url = db_url or os.environ.get("CLOUD_DATABASE_URL")
        checks.append(
            CheckResult(
                name="static_config",
                status="PASS" if (w_url or d_url) else "NOT_CONFIGURED",
                message="Static monitor configuration evaluated",
                metrics={"has_web_url": bool(w_url), "has_db_url": bool(d_url)},
            )
        )

    statuses = {c.status for c in checks}
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "WARN" in statuses:
        overall = "WARN"
    elif "BLOCKED" in statuses:
        overall = "BLOCKED"
    elif statuses == {"NOT_CONFIGURED"}:
        overall = "NOT_CONFIGURED"
    elif "PASS" in statuses:
        overall = "PASS"
    else:
        overall = "NOT_CONFIGURED"

    summary = {
        "total_checks": len(checks),
        "passed": sum(1 for c in checks if c.status == "PASS"),
        "failed": sum(1 for c in checks if c.status == "FAIL"),
        "warned": sum(1 for c in checks if c.status == "WARN"),
        "not_configured": sum(1 for c in checks if c.status == "NOT_CONFIGURED"),
    }

    return MonitorReport(
        overall_status=overall,
        mode=mode,
        timestamp_utc=timestamp_utc,
        checks=checks,
        summary=summary,
    )


def query_open_incident_issues() -> list[dict[str, Any]]:
    """Query GitHub CLI for open issues matching canonical incident marker."""
    import subprocess
    try:
        res = subprocess.run(
            [
                "gh", "issue", "list",
                "--state", "open",
                "--search", f"in:body {INCIDENT_MARKER}",
                "--json", "number,title,body,state",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            parsed = json.loads(res.stdout)
            if isinstance(parsed, list):
                return parsed
    except Exception:
        pass
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, default="FULL", help="Monitor execution mode")
    parser.add_argument("--web-url", help="Override OPOS_MONITOR_WEB_URL")
    parser.add_argument("--api-url", help="Override OPOS_MONITOR_API_URL")
    parser.add_argument("--db-url", help="Override CLOUD_DATABASE_URL")
    parser.add_argument("--supabase-url", help="Override NEXT_PUBLIC_SUPABASE_URL")
    parser.add_argument("--backup-heartbeat-path", help="Path to backup manifest JSON")
    parser.add_argument("--output-report", help="Path to write sanitized JSON report")
    parser.add_argument("--output-incident", help="Path to write incident action JSON")
    parser.add_argument("--open-issues-file", help="Path to JSON file with open issues")
    # Backwards compatibility flags
    parser.add_argument("--output", help=argparse.SUPPRESS)
    parser.add_argument("--alert-json", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    report_path = args.output_report or args.output

    report = run_monitor(
        mode=args.mode,
        web_url=args.web_url,
        api_url=args.api_url,
        db_url=args.db_url,
        supabase_url=args.supabase_url,
        backup_heartbeat_path=args.backup_heartbeat_path,
    )

    report_json = json.dumps(report.to_dict(), indent=2)
    if report_path:
        out_p = Path(report_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report_json + "\n", encoding="utf-8")
        print(f"Monitor report written to {out_p}")
    else:
        print(report_json)

    # Process incident output if requested
    if args.output_incident or args.alert_json:
        open_issues = []
        if args.open_issues_file:
            try:
                open_issues = json.loads(Path(args.open_issues_file).read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"Warning: Failed reading open issues file: {exc}", file=sys.stderr)
        else:
            open_issues = query_open_incident_issues()

        action_payload = determine_alert_action(report, open_issues)

        if args.output_incident:
            inc_p = Path(args.output_incident).resolve()
            inc_p.parent.mkdir(parents=True, exist_ok=True)
            inc_p.write_text(json.dumps(action_payload, indent=2) + "\n", encoding="utf-8")
            print(f"Incident action written to {inc_p}")

        if args.alert_json and action_payload["action"] != "NONE":
            print("\n--- INCIDENT ACTION ---")
            print(json.dumps(action_payload, indent=2))

    if args.mode == "TEST_ALERT":
        return 0

    exit_map = {"PASS": 0, "WARN": 0, "NOT_CONFIGURED": 0, "FAIL": 1, "BLOCKED": 2}
    return exit_map.get(report.overall_status, 1)


if __name__ == "__main__":
    raise SystemExit(main())
