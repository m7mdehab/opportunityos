"""Comprehensive Test Suite for FR-007 Cloud Observability & Release Gates.

Covers:
- URL safety and credential rejection
- Alert sanitization (DSN, tokens, cookies, paths)
- Web, API, Database, Queue, Scheduler, and Backup probes
- Incident payload construction and lifecycle actions
- Soak snapshot building and 7-day verification
- Hosted acceptance manifest validation
- Cloud cost & quota envelope enforcement
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.fetch_soak_artifacts import fetch_soak_artifacts
from scripts.fr007_cloud_monitor import (
    INCIDENT_MARKER,
    CheckResult,
    MonitorReport,
    build_incident_payload,
    determine_alert_action,
    probe_api_liveness,
    probe_backup_heartbeat,
    probe_database_and_queue,
    probe_web_liveness,
    run_monitor,
    sanitize_alert_text,
    validate_monitor_url,
)
from scripts.fr007_release_evidence import (
    build_release_evidence_index,
    format_markdown_summary,
)
from scripts.fr007_soak_snapshot import build_soak_snapshot
from scripts.fr007_soak_verify import (
    SoakVerificationResult,
    parse_iso_utc,
    verify_soak_snapshots,
)
from scripts.process_incident_alert import execute_incident_action
from scripts.validate_cloud_cost_quota import validate_cost_quota
from scripts.validate_hosted_acceptance import validate_hosted_acceptance_manifest
from scripts.validate_workflow_contracts import validate_workflow_contract



class TestUrlValidation(unittest.TestCase):
    """1. validate_monitor_url tests."""

    def test_valid_https_url(self) -> None:
        ok, msg = validate_monitor_url("https://staging.opportunityos.m7mdehab.com/health")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_insecure_http_rejected(self) -> None:
        ok, msg = validate_monitor_url("http://example.com")
        self.assertFalse(ok)
        self.assertIn("Insecure HTTP is prohibited", msg)

    def test_localhost_rejected(self) -> None:
        ok, msg = validate_monitor_url("https://localhost:8000")
        self.assertFalse(ok)
        self.assertIn("Localhost and loopback endpoints are prohibited", msg)

    def test_loopback_ip_rejected(self) -> None:
        ok, msg = validate_monitor_url("https://127.0.0.1:8000")
        self.assertFalse(ok)
        self.assertIn("Localhost and loopback endpoints are prohibited", msg)

    def test_credentials_in_url_rejected(self) -> None:
        ok, msg = validate_monitor_url("https://user:pass@service-host/api")
        self.assertTrue(not ok)
        self.assertIn("URL credentials", msg)

    def test_userinfo_at_syntax_rejected(self) -> None:
        ok, msg = validate_monitor_url("https://admin@service-host/api")
        self.assertTrue(not ok)
        self.assertIn("prohibited", msg)

    def test_sensitive_query_param_token_rejected(self) -> None:
        ok, msg = validate_monitor_url("https://service-host/data?token=secret123")
        self.assertFalse(ok)
        self.assertIn("Sensitive query parameter", msg)

    def test_sensitive_query_param_api_key_rejected(self) -> None:
        ok, msg = validate_monitor_url("https://service-host/data?api_key=secret123")
        self.assertFalse(ok)
        self.assertIn("Sensitive query parameter", msg)

    def test_url_fragment_rejected(self) -> None:
        ok, msg = validate_monitor_url("https://service-host/path#fragment")
        self.assertFalse(ok)
        self.assertIn("URL fragments are prohibited", msg)

    def test_empty_or_malformed_url_rejected(self) -> None:
        ok, _ = validate_monitor_url("")
        self.assertFalse(ok)
        ok2, _ = validate_monitor_url("not_a_url")
        self.assertFalse(ok2)


class TestAlertSanitization(unittest.TestCase):
    """2. sanitize_alert_text tests."""

    def test_redact_postgresql_password(self) -> None:
        pg_scheme = "postgres" + "ql://"
        raw = f"Error connecting to {pg_scheme}opos_user:SuperSecret123@db-host:5432/postgres"
        sanitized = sanitize_alert_text(raw)
        self.assertNotIn("SuperSecret123", sanitized)
        self.assertIn(f"{pg_scheme}opos_user:[REDACTED]@db-host", sanitized)

    def test_redact_bearer_token(self) -> None:
        raw = "Request failed with Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        sanitized = sanitize_alert_text(raw)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", sanitized)
        self.assertIn("Bearer [REDACTED]", sanitized)

    def test_redact_session_cookie(self) -> None:
        raw = "Cookie found: oos_session=abc123def456ghi789 in header"
        sanitized = sanitize_alert_text(raw)
        self.assertNotIn("abc123def456ghi789", sanitized)
        self.assertIn("oos_session=[REDACTED]", sanitized)

    def test_redact_private_path(self) -> None:
        raw = "Failed reading key from private/founder/credentials.yaml"
        sanitized = sanitize_alert_text(raw)
        self.assertNotIn("private/founder/credentials.yaml", sanitized)
        self.assertIn("[REDACTED_PRIVATE_PATH]", sanitized)

    def test_clean_text_preserved(self) -> None:
        clean = "Database connection pool healthy. Active connections: 4."
        self.assertEqual(sanitize_alert_text(clean), clean)

    def test_empty_string(self) -> None:
        self.assertEqual(sanitize_alert_text(""), "")


class TestHttpProbes(unittest.TestCase):
    """3. probe_web_liveness & probe_api_liveness tests."""

    def test_web_liveness_pass(self) -> None:
        def mock_client(url: str, **kwargs: Any) -> tuple[int, Mapping[str, str], str]:
            return 200, {}, "<html><title>OpportunityOS - Executive Search</title></html>"

        res = probe_web_liveness("https://staging.opportunityos.m7mdehab.com", client=mock_client)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.metrics.get("status_code"), 200)

    def test_web_liveness_http_500_fail(self) -> None:
        def mock_client(url: str, **kwargs: Any) -> tuple[int, Mapping[str, str], str]:
            return 500, {}, "Internal Server Error"

        res = probe_web_liveness("https://staging.opportunityos.m7mdehab.com", client=mock_client)
        self.assertEqual(res.status, "FAIL")
        self.assertEqual(res.metrics.get("status_code"), 500)

    def test_web_liveness_timeout_fail(self) -> None:
        def mock_client(url: str, **kwargs: Any) -> tuple[int, Mapping[str, str], str]:
            raise TimeoutError("Connection timed out after 10.0s")

        res = probe_web_liveness("https://staging.opportunityos.m7mdehab.com", client=mock_client)
        self.assertEqual(res.status, "FAIL")
        self.assertIn("timed out", res.message)

    def test_web_liveness_missing_signal_warn(self) -> None:
        def mock_client(url: str, **kwargs: Any) -> tuple[int, Mapping[str, str], str]:
            return 200, {}, "<html><title>Default Gateway</title></html>"

        res = probe_web_liveness("https://staging.opportunityos.m7mdehab.com", client=mock_client)
        self.assertEqual(res.status, "WARN")
        self.assertIn("marker was absent", res.message)

    def test_web_liveness_not_configured(self) -> None:
        res = probe_web_liveness("")
        self.assertEqual(res.status, "NOT_CONFIGURED")

    def test_api_liveness_pass_401(self) -> None:
        def mock_client(url: str, **kwargs: Any) -> tuple[int, Mapping[str, str], str]:
            return 401, {}, '{"detail": "Not authenticated"}'

        res = probe_api_liveness("https://api.opportunityos.m7mdehab.com", client=mock_client)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.metrics.get("status_code"), 401)

    def test_api_liveness_pass_200(self) -> None:
        def mock_client(url: str, **kwargs: Any) -> tuple[int, Mapping[str, str], str]:
            return 200, {}, '{"status": "ok"}'

        res = probe_api_liveness("https://api.opportunityos.m7mdehab.com", client=mock_client)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.metrics.get("status_code"), 200)

    def test_api_liveness_fail_502(self) -> None:
        def mock_client(url: str, **kwargs: Any) -> tuple[int, Mapping[str, str], str]:
            return 502, {}, "Bad Gateway"

        res = probe_api_liveness("https://api.opportunityos.m7mdehab.com", client=mock_client)
        self.assertEqual(res.status, "FAIL")
        self.assertEqual(res.metrics.get("status_code"), 502)

    def test_api_liveness_not_configured(self) -> None:
        res = probe_api_liveness("")
        self.assertEqual(res.status, "NOT_CONFIGURED")


class MockJob:
    def __init__(
        self,
        status: str,
        run_after: datetime | None = None,
        created_at: datetime | None = None,
        lease_expires_at: datetime | None = None,
        payload_json: str | None = None,
    ):
        self.status = status
        self.run_after = run_after
        self.created_at = created_at
        self.lease_expires_at = lease_expires_at
        self.payload_json = payload_json


class MockSchedule:
    def __init__(
        self,
        source_id: str,
        cadence_hours: float,
        next_due: datetime | None,
    ):
        self.source_id = source_id
        self.cadence_hours = cadence_hours
        self.next_due = next_due


class MockPollRun:
    def __init__(self, started_at: datetime | None):
        self.status = "ok"
        self.started_at = started_at


class MockQuery:
    def __init__(self, items: list[Any]):
        self._items = items

    def all(self) -> list[Any]:
        return self._items

    def filter_by(self, **kwargs: Any) -> MockQuery:
        return self

    def order_by(self, *args: Any) -> MockQuery:
        return self

    def first(self) -> Any:
        return self._items[0] if self._items else None


class MockSession:
    def __init__(
        self,
        jobs: list[MockJob] | None = None,
        schedules: list[MockSchedule] | None = None,
        poll_run: MockPollRun | None = None,
        alembic_version: str | None = "0003_cloud_baseline",
    ):
        self.jobs = jobs or []
        self.schedules = schedules or []
        self.poll_run = poll_run
        self.alembic_version = alembic_version

    def execute(self, statement: Any) -> Any:
        class RowResult:
            def __init__(self, version: str | None):
                self._v = version
            def fetchone(self) -> tuple[str] | None:
                return (self._v,) if self._v else None
        return RowResult(self.alembic_version)

    def query(self, model: Any) -> MockQuery:
        name = getattr(model, "__name__", str(model))
        if "WorkerJobRecord" in name:
            return MockQuery(self.jobs)
        if "SourceScheduleRecord" in name:
            return MockQuery(self.schedules)
        if "SourcePollRunRecord" in name:
            return MockQuery([self.poll_run] if self.poll_run else [])
        return MockQuery([])

    def close(self) -> None:
        pass


class TestDatabaseAndQueueProbes(unittest.TestCase):
    """4. probe_database_and_queue tests."""

    def test_db_not_configured(self) -> None:
        results = probe_database_and_queue(None)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "NOT_CONFIGURED")

    def test_healthy_db_and_queue_pass(self) -> None:
        now_dt = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
        now_naive = now_dt.replace(tzinfo=None)

        session = MockSession(
            jobs=[
                MockJob(status="PENDING", run_after=now_naive - timedelta(minutes=2)),
            ],
            schedules=[
                MockSchedule(source_id="un_jobs", cadence_hours=24, next_due=now_naive + timedelta(hours=10)),
            ],
            poll_run=MockPollRun(started_at=now_naive - timedelta(minutes=5)),
        )

        results = probe_database_and_queue(
            "dummy_url",
            connection_factory=lambda: session,
            clock=lambda: now_dt,
        )
        status_map = {r.name: r.status for r in results}
        self.assertEqual(status_map["database_connectivity"], "PASS")
        self.assertEqual(status_map["queue_health"], "PASS")
        self.assertEqual(status_map["source_freshness"], "PASS")

    def test_db_dead_letters_warn(self) -> None:
        now_dt = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
        session = MockSession(
            jobs=[
                MockJob(status="DEAD_LETTER"),
            ]
        )
        results = probe_database_and_queue(
            "dummy_url",
            connection_factory=lambda: session,
            clock=lambda: now_dt,
        )
        status_map = {r.name: r.status for r in results}
        self.assertEqual(status_map["queue_health"], "WARN")

    def test_db_expired_leases_fail(self) -> None:
        now_dt = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
        now_naive = now_dt.replace(tzinfo=None)
        session = MockSession(
            jobs=[
                MockJob(
                    status="RUNNING",
                    lease_expires_at=now_naive - timedelta(minutes=5),  # expired lease!
                ),
            ]
        )
        results = probe_database_and_queue(
            "dummy_url",
            connection_factory=lambda: session,
            clock=lambda: now_dt,
        )
        status_map = {r.name: r.status for r in results}
        self.assertEqual(status_map["queue_health"], "FAIL")

    def test_db_queue_due_age_warn_and_fail(self) -> None:
        now_dt = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
        now_naive = now_dt.replace(tzinfo=None)

        # 20 min age -> WARN
        session_warn = MockSession(
            jobs=[
                MockJob(status="PENDING", run_after=now_naive - timedelta(minutes=20)),
            ]
        )
        results_warn = probe_database_and_queue(
            "dummy_url",
            connection_factory=lambda: session_warn,
            clock=lambda: now_dt,
        )
        status_map = {r.name: r.status for r in results_warn}
        self.assertEqual(status_map["queue_health"], "WARN")

        # 70 min age -> FAIL
        session_fail = MockSession(
            jobs=[
                MockJob(status="PENDING", run_after=now_naive - timedelta(minutes=70)),
            ]
        )
        results_fail = probe_database_and_queue(
            "dummy_url",
            connection_factory=lambda: session_fail,
            clock=lambda: now_dt,
        )
        status_map2 = {r.name: r.status for r in results_fail}
        self.assertEqual(status_map2["queue_health"], "FAIL")

    def test_db_source_overdue_warn(self) -> None:
        now_dt = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
        now_naive = now_dt.replace(tzinfo=None)

        # Overdue beyond cadence + grace
        session = MockSession(
            schedules=[
                MockSchedule(source_id="overdue_src", cadence_hours=6.0, next_due=now_naive - timedelta(hours=10)),
            ]
        )
        results = probe_database_and_queue(
            "dummy_url",
            connection_factory=lambda: session,
            clock=lambda: now_dt,
        )
        status_map = {r.name: r.status for r in results}
        self.assertEqual(status_map["source_freshness"], "WARN")


class TestBackupHeartbeatProbe(unittest.TestCase):
    """5. probe_backup_heartbeat tests."""

    def test_backup_pass(self) -> None:
        now_str = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        manifest = {
            "backup_completed_at": now_str,
            "database_snapshot_sha": "a1b2c3d4",
            "encryption": "aes256",
            "destination_class": "s3_glacier",
            "result": "SUCCESS",
        }
        res = probe_backup_heartbeat(heartbeat=manifest)
        self.assertEqual(res.status, "PASS")

    def test_backup_warn_future_timestamp(self) -> None:
        now_str = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        manifest = {
            "backup_completed_at": now_str,
            "encryption": "aes256",
            "result": "SUCCESS",
        }
        res = probe_backup_heartbeat(heartbeat=manifest)
        self.assertEqual(res.status, "WARN")

    def test_backup_fail_40h(self) -> None:
        now_str = (datetime.now(timezone.utc) - timedelta(hours=40)).isoformat()
        manifest = {
            "backup_completed_at": now_str,
            "encryption": "aes256",
            "result": "SUCCESS",
        }
        res = probe_backup_heartbeat(heartbeat=manifest)
        self.assertEqual(res.status, "FAIL")

    def test_backup_fail_result(self) -> None:
        now_str = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        manifest = {
            "backup_completed_at": now_str,
            "encryption": "aes256",
            "result": "FAILED",
        }
        res = probe_backup_heartbeat(heartbeat=manifest)
        self.assertEqual(res.status, "FAIL")

    def test_backup_not_configured(self) -> None:
        res = probe_backup_heartbeat(heartbeat=None)
        self.assertEqual(res.status, "NOT_CONFIGURED")


class TestIncidentAndAlertLifecycle(unittest.TestCase):
    """6. build_incident_payload & determine_alert_action tests."""

    def test_alert_action_pass_without_open_issue(self) -> None:
        report = MonitorReport(
            overall_status="PASS",
            mode="FULL",
            timestamp_utc="2026-09-19T00:00:00Z",
            checks=[],
        )
        action_res = determine_alert_action(report, open_issues=[])
        self.assertEqual(action_res["action"], "NONE")

    def test_alert_action_fail_without_open_issue_creates(self) -> None:
        report = MonitorReport(
            overall_status="FAIL",
            mode="FULL",
            timestamp_utc="2026-09-19T00:00:00Z",
            checks=[CheckResult(name="web", status="FAIL", message="500")],
        )
        action_res = determine_alert_action(report, open_issues=[])
        self.assertEqual(action_res["action"], "CREATE")
        self.assertIn("title", action_res)
        self.assertIn("body", action_res)

    def test_alert_action_fail_with_open_issue_updates(self) -> None:
        report = MonitorReport(
            overall_status="FAIL",
            mode="FULL",
            timestamp_utc="2026-09-19T00:00:00Z",
            checks=[CheckResult(name="web", status="FAIL", message="500")],
        )
        open_issues = [
            {"number": 42, "state": "open", "body": f"Incident\n{INCIDENT_MARKER}"}
        ]
        action_res = determine_alert_action(report, open_issues=open_issues)
        self.assertEqual(action_res["action"], "UPDATE")
        self.assertEqual(action_res["issue_number"], 42)

    def test_alert_action_pass_with_open_issue_resolves(self) -> None:
        report = MonitorReport(
            overall_status="PASS",
            mode="FULL",
            timestamp_utc="2026-09-19T00:00:00Z",
            checks=[],
        )
        open_issues = [
            {"number": 42, "state": "open", "body": f"Incident\n{INCIDENT_MARKER}"}
        ]
        action_res = determine_alert_action(report, open_issues=open_issues)
        self.assertEqual(action_res["action"], "RESOLVE")
        self.assertEqual(action_res["issue_number"], 42)

    def test_incident_payload_contains_marker(self) -> None:
        report = MonitorReport(
            overall_status="FAIL",
            mode="FULL",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            checks=[CheckResult(name="web_liveness", status="FAIL", message="500 Internal Error")],
        )
        payload = build_incident_payload(report)
        self.assertIn(INCIDENT_MARKER, payload["body"])
        self.assertIn("web_liveness", payload["body"])

    def test_synthetic_test_alert_mode(self) -> None:
        report = run_monitor(mode="TEST_ALERT")
        self.assertEqual(report.overall_status, "FAIL")
        payload = build_incident_payload(report, is_synthetic=True)
        self.assertIn("SYNTHETIC TEST ALERT", payload["title"])
        self.assertIn(INCIDENT_MARKER, payload["body"])


def _make_snapshot(ts_iso: str, **kwargs: Any) -> dict[str, Any]:
    base = {
        "timestamp_utc": ts_iso,
        "proof_scope": "FULL_HOSTED",
        "overall_state": "PASS",
        "web_state": "PASS",
        "api_state": "PASS",
        "database_state": "PASS",
        "queue_state": "PASS",
        "scheduler_state": "PASS",
        "source_freshness_state": "PASS",
        "backup_state": "PASS",
        "founder_pc_dependency": False,
        "workflow_run_id": "123456",
        "monitor_run_id": "mon-123456",
    }
    base.update(kwargs)
    return base


class TestSoakSnapshotAndVerification(unittest.TestCase):
    """7. fr007_soak_snapshot & fr007_soak_verify tests."""

    def test_build_soak_snapshot_schema(self) -> None:
        report = MonitorReport(
            overall_status="PASS",
            mode="FULL",
            timestamp_utc="2026-09-19T01:00:00Z",
            checks=[
                CheckResult(name="web_liveness", status="PASS", message="OK"),
                CheckResult(name="api_liveness", status="PASS", message="OK"),
                CheckResult(name="database_connection", status="PASS", message="OK"),
                CheckResult(name="queue_state", status="PASS", message="OK"),
                CheckResult(name="scheduler_state", status="PASS", message="OK"),
                CheckResult(name="source_freshness", status="PASS", message="OK"),
                CheckResult(name="backup_heartbeat", status="PASS", message="OK"),
            ],
        )
        snap = build_soak_snapshot(
            report_data=report.to_dict(),
            repository_sha="abcdef123456",
            deployment_identifier="test-deploy",
            founder_pc_dependency=False,
            monitor_run_id="run-001",
            proof_scope="FULL_HOSTED",
            workflow_run_id="wf-999",
        )
        self.assertEqual(snap["overall_state"], "PASS")
        self.assertEqual(snap["web_state"], "PASS")
        self.assertEqual(snap["backup_state"], "PASS")
        self.assertFalse(snap["founder_pc_dependency"])
        self.assertEqual(snap["repository_sha"], "abcdef123456")
        self.assertEqual(snap["proof_scope"], "FULL_HOSTED")
        self.assertEqual(snap["workflow_run_id"], "wf-999")

    def test_soak_verify_insufficient_data(self) -> None:
        base_ts = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            _make_snapshot((base_ts + timedelta(hours=i)).isoformat())
            for i in range(24)  # Only 24 hours
        ]
        result = verify_soak_snapshots(snapshots, min_hours=168.0)
        self.assertEqual(result.result, "INSUFFICIENT_DATA")
        self.assertAlmostEqual(result.duration_hours, 23.0, delta=0.5)

    def test_soak_verify_pass_7_days(self) -> None:
        base_ts = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
        # 169 hours of snapshots every 2 hours
        snapshots = [
            _make_snapshot((base_ts + timedelta(hours=i * 2)).isoformat())
            for i in range(85)  # 85 * 2 = 170 hours
        ]
        result = verify_soak_snapshots(snapshots, min_hours=168.0, max_gap_hours=4.0)
        self.assertEqual(result.result, "PASS")
        self.assertGreaterEqual(result.duration_hours, 168.0)
        self.assertEqual(len(result.failed_intervals), 0)

    def test_soak_verify_gap_exceeded_fail(self) -> None:
        base_ts = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            _make_snapshot(base_ts.isoformat()),
            _make_snapshot((base_ts + timedelta(hours=10)).isoformat()),  # 10h gap!
            _make_snapshot((base_ts + timedelta(hours=170)).isoformat()),
        ]
        result = verify_soak_snapshots(snapshots, min_hours=168.0, max_gap_hours=4.0)
        self.assertEqual(result.result, "FAIL")
        self.assertTrue(any("exceeds max allowable gap" in r for r in result.reasons))

    def test_soak_verify_fail_overall_state(self) -> None:
        base_ts = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            _make_snapshot((base_ts + timedelta(hours=i * 2)).isoformat())
            for i in range(85)
        ]
        snapshots[40]["overall_state"] = "FAIL"
        result = verify_soak_snapshots(snapshots, min_hours=168.0, max_gap_hours=4.0)
        self.assertEqual(result.result, "FAIL")
        self.assertEqual(len(result.failed_intervals), 1)

    def test_soak_verify_founder_pc_dependency_fail(self) -> None:
        base_ts = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            _make_snapshot((base_ts + timedelta(hours=i * 2)).isoformat())
            for i in range(85)
        ]
        snapshots[20]["founder_pc_dependency"] = True
        result = verify_soak_snapshots(snapshots, min_hours=168.0, max_gap_hours=4.0)
        self.assertEqual(result.result, "FAIL")
        self.assertTrue(any("Founder PC dependency" in err for interval in result.failed_intervals for err in interval["reasons"]))

    def test_soak_verify_rejects_static_scope(self) -> None:
        base_ts = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            _make_snapshot((base_ts + timedelta(hours=i * 2)).isoformat(), proof_scope="STATIC_LOCAL")
            for i in range(85)
        ]
        result = verify_soak_snapshots(snapshots, min_hours=168.0)
        self.assertEqual(result.result, "FAIL")
        self.assertTrue(any("only FULL_HOSTED snapshots count" in err for interval in result.failed_intervals for err in interval["reasons"]))

    def test_soak_verify_rejects_not_configured_database(self) -> None:
        base_ts = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
        snapshots = [
            _make_snapshot((base_ts + timedelta(hours=i * 2)).isoformat(), database_state="NOT_CONFIGURED")
            for i in range(85)
        ]
        result = verify_soak_snapshots(snapshots, min_hours=168.0)
        self.assertEqual(result.result, "FAIL")
        self.assertTrue(any("database_state is NOT_CONFIGURED" in err for interval in result.failed_intervals for err in interval["reasons"]))


class TestHostedAcceptanceValidator(unittest.TestCase):
    """8. validate_hosted_acceptance tests."""

    def test_canonical_manifest_valid(self) -> None:
        manifest_path = REPO_ROOT / "reports" / "evidence" / "FR-007" / "hosted-acceptance-manifest.json"
        self.assertTrue(manifest_path.exists())
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        valid, errors = validate_hosted_acceptance_manifest(data, repo_root=REPO_ROOT)
        self.assertTrue(valid, f"Errors: {errors}")

    def test_missing_criterion_rejected(self) -> None:
        manifest_path = REPO_ROOT / "reports" / "evidence" / "FR-007" / "hosted-acceptance-manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        del data["criteria"]["A-5"]
        valid, errors = validate_hosted_acceptance_manifest(data, repo_root=REPO_ROOT)
        self.assertFalse(valid)
        self.assertTrue(any("Missing required criterion: A-5" in e for e in errors))

    def test_unearned_pass_rejected(self) -> None:
        manifest_path = REPO_ROOT / "reports" / "evidence" / "FR-007" / "hosted-acceptance-manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Attempt to claim PASS on A-14 without hosted proof
        data["criteria"]["A-14"]["status"] = "PASS"
        data["criteria"]["A-14"]["hosted_verified"] = False
        valid, errors = validate_hosted_acceptance_manifest(data, repo_root=REPO_ROOT)
        self.assertFalse(valid)
        self.assertTrue(any("hosted_verified is False" in e for e in errors))


class TestCostQuotaValidator(unittest.TestCase):
    """9. validate_cloud_cost_quota tests."""

    def test_canonical_envelope_staging_and_production(self) -> None:
        quota_path = REPO_ROOT / "reports" / "evidence" / "FR-007" / "cloud-cost-quota.json"
        self.assertTrue(quota_path.exists())
        with open(quota_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        valid_stg, err_stg = validate_cost_quota(data, mode="staging")
        self.assertTrue(valid_stg, f"Staging errors: {err_stg}")
        valid_prod, err_prod = validate_cost_quota(data, mode="production")
        self.assertTrue(valid_prod, f"Production errors: {err_prod}")

    def test_unapproved_paid_resource_fails_production(self) -> None:
        quota_path = REPO_ROOT / "reports" / "evidence" / "FR-007" / "cloud-cost-quota.json"
        with open(quota_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["services"]["cloudflare"]["unapproved_paid_resource"] = True
        data["summary"]["unapproved_paid_resources_count"] = 1
        valid, errors = validate_cost_quota(data, mode="production")
        self.assertFalse(valid)
        self.assertTrue(any("Unapproved paid resource" in e for e in errors))

    def test_credit_backed_gross_charge_is_rejected(self) -> None:
        quota_path = REPO_ROOT / "reports" / "evidence" / "FR-007" / "cloud-cost-quota.json"
        with open(quota_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        service = data["services"]["supabase"]
        service["gross_provider_charge_usd"] = 5.0
        service["student_credit_absorbed_usd"] = 5.0
        service["covered_by_student_credit"] = True
        data["summary"]["total_gross_provider_charge_usd"] = 5.0
        data["summary"]["total_student_credit_applied_usd"] = 5.0
        data["summary"]["credit_dependency"] = True
        valid, errors = validate_cost_quota(data, mode="production")
        self.assertFalse(valid)
        self.assertTrue(any("gross provider charge must be $0.00" in e for e in errors))
        self.assertTrue(any("may not depend on student/trial credits" in e for e in errors))

    def test_azure_provider_is_rejected(self) -> None:
        quota_path = REPO_ROOT / "reports" / "evidence" / "FR-007" / "cloud-cost-quota.json"
        with open(quota_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["services"]["azure"] = {
            "provider": "Microsoft Azure",
            "covered_by_permanent_allowance": True,
            "covered_by_student_credit": False,
            "gross_provider_charge_usd": 0.0,
            "student_credit_absorbed_usd": 0.0,
            "net_founder_out_of_pocket_usd": 0.0,
            "unapproved_paid_resource": False,
        }
        valid, errors = validate_cost_quota(data, mode="production")
        self.assertFalse(valid)
        self.assertTrue(any("Unapproved provider" in e for e in errors))

    def test_private_repo_runner_assumption_is_rejected(self) -> None:
        quota_path = REPO_ROOT / "reports" / "evidence" / "FR-007" / "cloud-cost-quota.json"
        with open(quota_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["services"]["github_actions"]["projected_usage"]["repository_visibility"] = "private"
        valid, errors = validate_cost_quota(data, mode="production")
        self.assertFalse(valid)
        self.assertTrue(any("requires the repository to remain public" in e for e in errors))


class TestReleaseEvidenceIndexer(unittest.TestCase):
    """10. fr007_release_evidence tests."""

    def test_indexer_execution(self) -> None:
        index = build_release_evidence_index(repo_root=REPO_ROOT)
        self.assertEqual(index["brief"], "FR-007")
        self.assertGreater(index["evidence_files_count"], 10)
        self.assertEqual(index["acceptance_criteria_summary"]["PASS"], 2)
        self.assertEqual(index["acceptance_criteria_summary"]["REPOSITORY_VERIFIED"], 14)
        self.assertEqual(index["acceptance_criteria_summary"]["NOT_EXECUTED"], 2)

        md = format_markdown_summary(index)
        self.assertIn("# FR-007 Release Evidence Index", md)
        self.assertIn("antigravity-durable-scheduling.txt", md)


class TestProcessIncidentAlert(unittest.TestCase):
    """11. process_incident_alert tests."""

    def test_action_none_does_nothing(self) -> None:
        calls = []
        def mock_runner(cmd):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        payload = {"action": "NONE"}
        code = execute_incident_action(payload, runner=mock_runner)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 0)

    def test_action_create_success(self) -> None:
        calls = []
        def mock_runner(cmd):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="https://github.com/org/repo/issues/100", stderr="")

        payload = {
            "action": "CREATE",
            "title": "[INCIDENT] System Down",
            "body": "Details here",
        }
        code = execute_incident_action(payload, runner=mock_runner)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("issue", calls[0])
        self.assertIn("create", calls[0])

    def test_action_create_failure_returns_nonzero(self) -> None:
        calls = []
        def mock_runner(cmd):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="permission denied")

        payload = {
            "action": "CREATE",
            "title": "[INCIDENT] System Down",
            "body": "Details here",
        }
        code = execute_incident_action(payload, runner=mock_runner)
        self.assertEqual(code, 1)

    def test_action_update_success(self) -> None:
        calls = []
        def mock_runner(cmd):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        payload = {
            "action": "UPDATE",
            "issue_number": 42,
            "body": "Update here",
        }
        code = execute_incident_action(payload, runner=mock_runner)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ["gh", "issue", "comment", "42", "--body", "Update here"])

    def test_action_resolve_success(self) -> None:
        calls = []
        def mock_runner(cmd):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        payload = {
            "action": "RESOLVE",
            "issue_number": 42,
            "body": "Resolution note",
        }
        code = execute_incident_action(payload, runner=mock_runner)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("close", calls[0])
        self.assertIn("--comment", calls[0])


class TestCloudMonitorCliIntegration(unittest.TestCase):
    """12. fr007_cloud_monitor CLI subprocess integration tests."""

    def test_cli_help(self) -> None:
        cmd = [sys.executable, str(REPO_ROOT / "scripts" / "fr007_cloud_monitor.py"), "--help"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 0)
        self.assertIn("--output-report", res.stdout)
        self.assertIn("--output-incident", res.stdout)
        self.assertIn("--backup-heartbeat-path", res.stdout)

    def test_cli_execution_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rep_path = Path(tmpdir) / "report.json"
            inc_path = Path(tmpdir) / "incident.json"
            cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "fr007_cloud_monitor.py"),
                "--output-report",
                str(rep_path),
                "--output-incident",
                str(inc_path),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            # Both output files must exist even if probe fails (because endpoints are not set)
            self.assertTrue(rep_path.exists())
            self.assertTrue(inc_path.exists())

            with open(rep_path, "r", encoding="utf-8") as f:
                rep = json.load(f)
            self.assertIn("overall_status", rep)

            with open(inc_path, "r", encoding="utf-8") as f:
                inc = json.load(f)
            self.assertIn("action", inc)


class TestWorkflowContracts(unittest.TestCase):
    """13. Workflow contract validator tests."""

    def test_observability_workflow_contract(self) -> None:
        wf = REPO_ROOT / ".github" / "workflows" / "fr007-cloud-observability.yml"
        self.assertTrue(wf.exists())
        text = wf.read_text(encoding="utf-8")
        valid, errors = validate_workflow_contract(text)
        self.assertTrue(valid, f"Workflow contract errors: {errors}")


class TestFetchSoakArtifacts(unittest.TestCase):
    """14. fetch_soak_artifacts tests."""

    def test_fetch_is_paginated_and_extracts_only_nested_soak_snapshots(self) -> None:
        snapshot = {
            "timestamp_utc": "2026-09-19T00:00:00+00:00",
            "proof_scope": "FULL_HOSTED",
            "overall_state": "PASS",
        }
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as zf:
            zf.writestr("soak/soak-2026-09-19T00-00-00.json", json.dumps(snapshot))
            zf.writestr("report.json", json.dumps({"timestamp_utc": snapshot["timestamp_utc"]}))
            zf.writestr("incident.json", json.dumps({"action": "NONE"}))
        archive_bytes = archive_buffer.getvalue()

        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append(list(cmd))
            if "actions/artifacts?per_page=100" in " ".join(cmd):
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout=json.dumps(
                        {
                            "id": 123,
                            "name": "soak-snapshot-1-1",
                            "created_at": "2026-09-19T00:00:00Z",
                        }
                    )
                    + "\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(cmd, 0, stdout=archive_bytes, stderr=b"")

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir)
            count = fetch_soak_artifacts(target_dir=target, runner=fake_runner)
            self.assertEqual(count, 1)
            files = list(target.glob("*.json"))
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].name.endswith("soak-2026-09-19T00-00-00.json"))
            self.assertEqual(json.loads(files[0].read_text(encoding="utf-8"))["proof_scope"], "FULL_HOSTED")

        self.assertIn("--paginate", calls[0])

    def test_fetch_fails_closed_when_github_listing_fails(self) -> None:
        def fake_runner(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unauthorized")

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(RuntimeError):
                fetch_soak_artifacts(Path(tmpdir), runner=fake_runner)


if __name__ == "__main__":
    unittest.main()
