"""Freeze and process due FR-007 sources in supervised five-source waves."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opportunity.registry import SourceRegistry
from scripts.db_capacity_guard import inspect_connection
from scripts.fr007_hosted_bootstrap import HOSTED_WORKER_POOL_SIZE
from scripts.fr007_storage_v2_source_gate import _connect, snapshot
from scripts.migration_head_guard import verify_connection_head
from storage.models import SourcePollRunRecord, SourceScheduleRecord, WorkerJobRecord
from worker.scheduler import (
    OVERNIGHT_CATCHUP_CEILING_BYTES,
    enqueue_due_catchup_sources,
)

MAX_COHORT_SOURCES = 50
MAX_PARALLEL_SOURCE_WORKERS = 5
MAX_RETAINED_WORKER_CONNECTIONS = 10
WORKER_TIME_BUDGET_SECONDS = 480
WAVE_TIMEOUT_SECONDS = 75 * 60
COHORT_START_BYTES = 380 * 1024 * 1024
PROACTIVE_MAINTENANCE_BYTES = 380 * 1024 * 1024
COHORT_PREDICTION_MULTIPLIER = 1.5
DEFAULT_MEASURED_BYTES_PER_SOURCE = 147_456
STATE_VERSION = 1


class CatchupSafetyError(RuntimeError):
    """Fatal precondition or production invariant failure."""


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _utc(value)
    return normalized.isoformat() if normalized else None


def freeze_manifest_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    frozen = [
        {
            "source_id": str(item["source_id"]),
            "next_due_at": str(item["next_due_at"]),
            "cadence_hours": float(item["cadence_hours"]),
        }
        for item in entries
    ]
    frozen.sort(key=lambda item: (item["next_due_at"], item["source_id"]))
    ids = [item["source_id"] for item in frozen]
    if len(ids) != len(set(ids)):
        raise ValueError("frozen source manifest contains duplicate IDs")
    return frozen


def manifest_sha256(entries: list[dict[str, Any]]) -> str:
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def cohort_for_index(entries: list[dict[str, Any]], index: int) -> list[dict[str, Any]]:
    if index < 0 or index >= (len(entries) + MAX_COHORT_SOURCES - 1) // MAX_COHORT_SOURCES:
        raise ValueError("cohort index is outside the frozen manifest")
    start = index * MAX_COHORT_SOURCES
    return entries[start : start + MAX_COHORT_SOURCES]


def pending_manifest_sources(entries: list[dict[str, Any]], results: dict[str, Any]) -> list[str]:
    return [entry["source_id"] for entry in entries if entry["source_id"] not in results]


def validate_evaluation_job_rows(rows: list[dict[str, Any]], allowed_ids: set[str]) -> None:
    if any(row["job_type"] != "evaluate_new" or row["id"] not in allowed_ids for row in rows):
        raise CatchupSafetyError("evaluation queue contains work outside the current source wave")


def assert_founder_state_unchanged(before: dict[str, int], after: dict[str, int]) -> None:
    if before != after:
        raise CatchupSafetyError("Founder-state aggregate changed during source catch-up")


def validate_wave_contract(
    *,
    manifest_ids: set[str],
    selected_ids: list[str],
    due_ids: set[str],
    read_allowed_ids: set[str],
    queue_rows: list[dict[str, Any]],
    database_bytes: int,
    worker_count: int,
) -> None:
    if not 1 <= len(selected_ids) <= MAX_PARALLEL_SOURCE_WORKERS:
        raise CatchupSafetyError("wave must contain one to five source identities")
    if len(set(selected_ids)) != len(selected_ids):
        raise CatchupSafetyError("wave contains a duplicate source identity")
    if not set(selected_ids).issubset(manifest_ids):
        raise CatchupSafetyError("wave contains an identity outside the frozen manifest")
    if not set(selected_ids).issubset(due_ids):
        raise CatchupSafetyError("wave contains a source that is not currently due")
    if not set(selected_ids).issubset(read_allowed_ids):
        raise CatchupSafetyError("wave contains a source not allowed for reading")
    if queue_rows:
        raise CatchupSafetyError("wave cannot be scheduled while runnable queue work exists")
    if database_bytes >= OVERNIGHT_CATCHUP_CEILING_BYTES:
        raise CatchupSafetyError("wave refused at the overnight 390 MiB ceiling")
    if worker_count > MAX_PARALLEL_SOURCE_WORKERS:
        raise CatchupSafetyError("wave exceeds five runtime workers")
    if worker_count * HOSTED_WORKER_POOL_SIZE > MAX_RETAINED_WORKER_CONNECTIONS:
        raise CatchupSafetyError("worker database connection envelope exceeds ten")


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("version") != STATE_VERSION:
        raise ValueError("unsupported catch-up state version")
    entries = freeze_manifest_entries(manifest.get("entries", []))
    if entries != manifest.get("entries"):
        raise ValueError("frozen source manifest is not in canonical order")
    if manifest_sha256(entries) != manifest.get("sha256"):
        raise ValueError("frozen source manifest hash mismatch")


def _registry_due_entries(session, registry: SourceRegistry, now: datetime) -> list[dict[str, Any]]:
    return registry_due_entries_from_schedules(
        session.query(SourceScheduleRecord).all(), registry, now
    )


def registry_due_entries_from_schedules(
    schedules: Iterable[Any], registry: SourceRegistry, now: datetime
) -> list[dict[str, Any]]:
    """Pure schedule selector used to freeze only due, non-cooling, readable sources."""
    now_utc = _utc(now)
    result = []
    for schedule in schedules:
        source_id = schedule.source_id
        due_at = _utc(schedule.next_due_at)
        cooldown = _utc(schedule.cooldown_until)
        if (
            source_id in registry._sources
            and registry.is_read_allowed(source_id)
            and due_at is not None
            and due_at <= now_utc
            and (cooldown is None or cooldown <= now_utc)
        ):
            result.append({
                "source_id": source_id,
                "next_due_at": due_at.isoformat(),
                "cadence_hours": float(schedule.cadence_hours),
            })
    return freeze_manifest_entries(result)


def _founder_state(connection) -> dict[str, int]:
    tables = {
        "founder_identity": "founder_identity",
        "feedback": "founder_feedback",
        "activity": "founder_activity_events",
        "opportunity_views": "founder_opportunity_views",
        "triage": "founder_triage_states",
        "filter_settings": "founder_filter_settings",
        "facets": "founder_facets",
        "saved_views": "founder_saved_views",
        "cv_selections": "founder_cv_selections",
        "outbound_actions": "outbound_actions",
    }
    counts = {
        label: int(connection.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one())
        for label, table in tables.items()
    }
    counts["auth_users"] = int(
        connection.execute(text("SELECT count(*) FROM auth.users")).scalar_one()
    )
    distributions = (
        ("feedback_label", "SELECT feedback_label AS value, count(*)::bigint AS count FROM public.founder_feedback GROUP BY feedback_label"),
        ("activity_action", "SELECT action_type || ':' || COALESCE(resulting_state, '') AS value, count(*)::bigint AS count FROM public.founder_activity_events GROUP BY action_type, resulting_state"),
        ("triage_state", "SELECT state AS value, count(*)::bigint AS count FROM public.founder_triage_states GROUP BY state"),
        ("outbound_status", "SELECT action_status AS value, count(*)::bigint AS count FROM public.outbound_actions GROUP BY action_status"),
        ("cv_variant", "SELECT variant AS value, count(*)::bigint AS count FROM public.founder_cv_selections GROUP BY variant"),
    )
    for label, query in distributions:
        rows = connection.execute(text(query)).mappings().all()
        for row in rows:
            counts[f"{label}:{row['value']}"] = int(row["count"])
    return counts


def _queue_counts(connection) -> dict[str, int]:
    rows = connection.execute(text(
        "SELECT status, count(*)::bigint AS count FROM public.worker_jobs GROUP BY status"
    )).mappings().all()
    result = {str(row["status"]).lower(): int(row["count"]) for row in rows}
    for status in ("pending", "retry", "running"):
        result.setdefault(status, 0)
    return result


def _runtime_snapshot(session, *, source_id: str) -> dict[str, Any]:
    connection = session.connection()
    migration = verify_connection_head(connection)
    capacity = inspect_connection(connection)
    core = snapshot(connection, source_id=source_id)
    return {
        "database_bytes": int(capacity.database_size_bytes),
        "capacity_status": capacity.status,
        "capacity_read_only": bool(capacity.read_only),
        "capacity_in_recovery": bool(capacity.in_recovery),
        "migration_heads": list(migration["current_heads"]),
        "queue": _queue_counts(connection),
        "founder_state": _founder_state(connection),
        "lifecycle": {
            key: int(core["counts"][key]) for key in (
                "opportunities", "hot_opportunities", "cold_opportunities",
                "protected_opportunities", "cold_archive_rows", "cold_description_rows",
                "cold_raw_payload_rows", "cold_provenance_rows", "cold_verbose_evaluation_rows",
                "max_projections_per_opportunity", "max_evaluations_per_opportunity",
            )
        },
        "largest_relations": core["top_relations"][:10],
    }


def _require_clean_queue(state: dict[str, Any]) -> None:
    queue = state["queue"]
    if any(queue.get(name, 0) for name in ("pending", "retry", "running")):
        raise CatchupSafetyError("catch-up boundary requires an empty runnable queue")


def _require_capacity(state: dict[str, Any]) -> None:
    if state["capacity_read_only"] or state["capacity_in_recovery"]:
        raise CatchupSafetyError("database is read-only or in recovery")
    if state["database_bytes"] >= OVERNIGHT_CATCHUP_CEILING_BYTES:
        raise CatchupSafetyError("overnight 390 MiB safety ceiling reached")


def freeze_live_manifest(path: Path) -> dict[str, Any]:
    engine, session = _connect()
    try:
        registry = SourceRegistry()
        now = datetime.now(timezone.utc)
        entries = _registry_due_entries(session, registry, now)
        if not entries:
            raise CatchupSafetyError("no read-allowed, non-cooling due sources to freeze")
        state = _runtime_snapshot(session, source_id=entries[0]["source_id"])
        _require_clean_queue(state)
        _require_capacity(state)
        manifest = {
            "version": STATE_VERSION,
            "created_at": now.isoformat(),
            "count": len(entries),
            "sha256": manifest_sha256(entries),
            "entries": entries,
            "database_bytes_at_freeze": state["database_bytes"],
            "founder_state_at_freeze": state["founder_state"],
            "queue_at_freeze": state["queue"],
        }
        result = {"manifest": manifest, "results": {}, "cohorts": [], "failures": []}
        _write_json(path, result)
        return result
    finally:
        session.close()
        engine.dispose()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _read_state(path: Path) -> dict[str, Any]:
    state = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(state["manifest"])
    return state


def _query_jobs(session, job_ids: set[str] | None = None) -> list[dict[str, Any]]:
    query = session.query(WorkerJobRecord)
    if job_ids is not None:
        query = query.filter(WorkerJobRecord.id.in_(job_ids))
    rows = query.filter(WorkerJobRecord.status.in_(("PENDING", "RETRY", "RUNNING"))).all()
    return [{
        "id": row.id,
        "job_type": row.job_type,
        "status": row.status,
        "run_after": _iso(row.run_after),
        "lease_expires_at": _iso(row.lease_expires_at),
        "retry_count": int(row.retry_count),
        "max_retries": int(row.max_retries),
        "error_message": row.error_message,
        "payload": json.loads(row.payload_json or "{}"),
    } for row in rows]


def _job_rows(session, job_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not job_ids:
        return {}
    rows = session.query(WorkerJobRecord).filter(WorkerJobRecord.id.in_(job_ids)).all()
    return {row.id: {
        "id": row.id,
        "job_type": row.job_type,
        "status": row.status,
        "retry_count": int(row.retry_count),
        "max_retries": int(row.max_retries),
        "run_after": _iso(row.run_after),
        "lease_expires_at": _iso(row.lease_expires_at),
        "error_message": row.error_message,
        "payload": json.loads(row.payload_json or "{}"),
    } for row in rows}


def _spawn_workers(*, count: int, worker_id_prefix: str, poll_only: bool) -> list[dict[str, Any]]:
    if not 1 <= count <= MAX_PARALLEL_SOURCE_WORKERS:
        raise CatchupSafetyError("worker count is outside the five-process connection envelope")
    command = [
        sys.executable, str(ROOT / "scripts/fr007_hosted_bootstrap.py"),
        "--mode", "drain", "--max-jobs", "1",
        "--time-budget-seconds", str(WORKER_TIME_BUDGET_SECONDS),
    ]
    if poll_only:
        command.append("--poll-source-only")

    def run(index: int) -> dict[str, Any]:
        worker_id = f"{worker_id_prefix}-{index + 1}"
        try:
            completed = subprocess.run(
                [*command, "--worker-id", worker_id],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=os.environ.copy(),
                timeout=WORKER_TIME_BUDGET_SECONDS + 120,
            )
            return {"worker_id": worker_id, "return_code": int(completed.returncode)}
        except Exception as exc:
            return {"worker_id": worker_id, "return_code": None, "error_class": type(exc).__name__}

    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(run, range(count)))


def _sleep_until_next_attempt(rows: list[dict[str, Any]], *, deadline: float) -> None:
    now = datetime.now(timezone.utc)
    times = []
    for row in rows:
        raw = row.get("run_after") if row["status"] == "RETRY" else row.get("lease_expires_at")
        if raw:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            times.append(parsed.astimezone(timezone.utc))
    delay = min((max(1.0, (value - now).total_seconds()) for value in times), default=5.0)
    if time.monotonic() + delay > deadline:
        raise CatchupSafetyError("wave retry/lease wait exceeded its bounded deadline")
    time.sleep(min(delay, 30.0))


def _drain_poll_jobs(
    job_ids: set[str], *, wave_tag: str, baseline_job_ids: set[str]
) -> dict[str, Any]:
    deadline = time.monotonic() + WAVE_TIMEOUT_SECONDS
    attempt_round = 0
    while time.monotonic() < deadline:
        engine, session = _connect()
        try:
            active = _query_jobs(session)
            allowed_ids = set(job_ids)
            unexpected = [
                row for row in active
                if row["id"] not in allowed_ids
                and (row["job_type"] != "evaluate_new" or row["id"] in baseline_job_ids)
            ]
            if unexpected:
                raise CatchupSafetyError("unexpected non-evaluation queue work appeared during poll wave")
            if any(row["job_type"] != "poll_source" for row in active if row["id"] in allowed_ids):
                raise CatchupSafetyError("poll wave job identity/type mismatch")
            poll_rows = _job_rows(session, job_ids)
            if set(poll_rows) != allowed_ids:
                raise CatchupSafetyError("a source poll job disappeared before terminal status")
            pending = [row for row in poll_rows.values() if row["status"] == "PENDING"]
            due_retry = [
                row for row in poll_rows.values()
                if row["status"] == "RETRY"
                and (_utc(datetime.fromisoformat(row["run_after"])) or datetime.min.replace(tzinfo=timezone.utc)) <= datetime.now(timezone.utc)
            ]
            running = [row for row in poll_rows.values() if row["status"] == "RUNNING"]
            unfinished = [row for row in poll_rows.values() if row["status"] not in {"COMPLETED", "DEAD_LETTER"}]
            if not unfinished:
                return {"job_rows": poll_rows, "worker_rounds": attempt_round}
            runnable = pending + due_retry
            run_count = min(MAX_PARALLEL_SOURCE_WORKERS, len(runnable)) if runnable else 0
        finally:
            session.close()
            engine.dispose()
        if run_count:
            attempt_round += 1
            results = _spawn_workers(
                count=run_count,
                worker_id_prefix=f"due-catchup-{wave_tag}-{attempt_round}",
                poll_only=True,
            )
            if any(result.get("return_code") != 0 for result in results):
                raise CatchupSafetyError("normal source worker exited non-zero during poll wave")
        else:
            _sleep_until_next_attempt(unfinished, deadline=deadline)
    raise CatchupSafetyError("poll wave exceeded its bounded retry deadline")


def _drain_evaluation_jobs(*, wave_tag: str, allowed_ids: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + WAVE_TIMEOUT_SECONDS
    rounds = 0
    seen_ids: set[str] = set()
    while time.monotonic() < deadline:
        engine, session = _connect()
        try:
            active = _query_jobs(session)
            validate_evaluation_job_rows(active, allowed_ids)
            seen_ids.update(row["id"] for row in active)
            if not active:
                return {"job_ids": sorted(seen_ids), "worker_rounds": rounds}
            pending = [row for row in active if row["status"] == "PENDING"]
            due_retry = [
                row for row in active
                if row["status"] == "RETRY"
                and datetime.fromisoformat(row["run_after"]).astimezone(timezone.utc) <= datetime.now(timezone.utc)
            ]
            runnable = pending + due_retry
            runnable_count = len(runnable)
        finally:
            session.close()
            engine.dispose()
        if runnable_count:
            rounds += 1
            # The wave provenance check above proves every runnable row is
            # a coalesced evaluation created by the just-finished polls.
            command = [
                sys.executable, str(ROOT / "scripts/fr007_hosted_bootstrap.py"),
                "--mode", "drain", "--max-jobs", str(runnable_count),
                "--time-budget-seconds", str(WORKER_TIME_BUDGET_SECONDS),
                "--worker-id", f"due-catchup-evaluate-{wave_tag}-{rounds}",
            ]
            completed = subprocess.run(
                command, check=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, env=os.environ.copy(),
                timeout=WORKER_TIME_BUDGET_SECONDS + 120,
            )
            if completed.returncode != 0:
                raise CatchupSafetyError("normal evaluation worker exited non-zero")
        else:
            _sleep_until_next_attempt(active, deadline=deadline)
    raise CatchupSafetyError("evaluation wave exceeded its bounded retry deadline")


def _latest_poll(session, source_id: str) -> dict[str, Any] | None:
    row = (
        session.query(SourcePollRunRecord)
        .filter(SourcePollRunRecord.source_id == source_id)
        .order_by(SourcePollRunRecord.started_at.desc())
        .first()
    )
    if row is None:
        return None
    return {
        "status": str(row.status),
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "raw_ingested": int(row.raw_ingested or 0),
        "unique_opportunities": int(row.unique_opportunities or 0),
        "inserted": int(row.inserted or 0),
        "updated": int(row.updated or 0),
        "unchanged": int(row.unchanged or 0),
        "refusal_reason": row.refusal_reason,
        "error_message": row.error_message,
    }


def _classify_source_terminal(poll: dict[str, Any] | None, job: dict[str, Any]) -> tuple[str, str | None]:
    if poll is None:
        raise CatchupSafetyError("source worker reached a terminal queue state without poll evidence")
    if poll and poll["status"] == "ok":
        return "success", None
    if poll and poll["status"] == "blocked":
        return "deferred", str(poll.get("refusal_reason") or "provider_policy_or_rate_limit")
    if poll and poll["status"] == "refused":
        return "deferred", "runtime_policy_refusal"
    error = " ".join((poll.get("error_message") or "", job.get("error_message") or "")).lower()
    fatal_markers = (
        "capacity", "integrityerror", "uniqueviolation", "programmingerror",
        "schema", "migration", "truth pack", "lifecycle", "foreign key",
        "assertionerror", "keyerror", "typeerror", "valueerror", "sqlalchemy",
        "psycopg", "database", "transaction", "serializationfailure",
    )
    if any(marker in error for marker in fatal_markers):
        raise CatchupSafetyError("data-integrity, capacity, or schema failure in source worker")
    transient_markers = (
        "timeout", "timed out", "connection reset", "connection refused",
        "temporary failure", "temporary unavailable", "http 500", "http 502",
        "http 503", "http 504", "provider error", "remote end closed",
        "name or service not known", "network is unreachable", "connectionerror",
        "connecttimeout", "readtimeout", "ssl error", "temporary name resolution",
        "no address associated with hostname", "nodename nor servname",
        "server disconnected", "http 408", "http 429", "429 client error",
        "http error 408", "http error 429", "500 server error", "http error 500",
        "502 bad gateway", "502 server error", "http error 502",
        "503 service unavailable", "503 server error", "http error 503",
        "504 gateway timeout", "504 server error", "http error 504",
        "rate limit", "too many requests",
    )
    external_http_markers = (
        "http 400", "http 401", "http 403", "http 404", "http 405",
        "http 410", "http 418", "http 422", "400 client error",
        "401 client error", "403 client error", "404 client error",
        "405 client error", "410 client error", "418 client error",
        "422 client error", "http error 400", "http error 401",
        "http error 403", "http error 404", "http error 405",
        "http error 410", "http error 418", "http error 422",
    )
    if poll["status"] == "error" and any(marker in error for marker in transient_markers):
        return "deferred", "transient_source_failure_after_normal_retries"
    if poll["status"] == "error" and any(marker in error for marker in external_http_markers):
        return "deferred", "external_source_http_failure"
    raise CatchupSafetyError("source terminal result was not an evidenced source-local failure")


def _existing_after_freeze(session, source_id: str, frozen_at: datetime) -> dict[str, Any] | None:
    latest = _latest_poll(session, source_id)
    if not latest or not latest["finished_at"]:
        return None
    finished = datetime.fromisoformat(latest["finished_at"])
    if finished <= frozen_at:
        return None
    if latest["status"] == "ok":
        return {"status": "success", "reason": "normal_scheduler_processed_after_manifest_freeze", "poll": latest}
    if latest["status"] == "blocked":
        return {"status": "deferred", "reason": latest.get("refusal_reason") or "provider_cooldown", "poll": latest}
    if latest["status"] == "refused":
        return {"status": "deferred", "reason": "runtime_policy_refusal", "poll": latest}
    if latest["status"] == "error":
        terminal, reason = _classify_source_terminal(
            latest, {"error_message": latest.get("error_message")}
        )
        return {"status": terminal, "reason": reason, "poll": latest}
    return None


def _schedule_and_run_wave(
    source_ids: list[str], *, wave_tag: str, manifest_ids: set[str],
    founder_state_baseline: dict[str, int],
) -> dict[str, Any]:
    engine, session = _connect()
    try:
        before = _runtime_snapshot(session, source_id=source_ids[0])
        _require_clean_queue(before)
        _require_capacity(before)
        assert_founder_state_unchanged(founder_state_baseline, before["founder_state"])
        before_bytes = before["database_bytes"]
        now = datetime.now(timezone.utc)
        schedule_rows = session.query(SourceScheduleRecord).filter(
            SourceScheduleRecord.source_id.in_(source_ids)
        ).all()
        due_ids = {
            row.source_id for row in schedule_rows
            if _utc(row.next_due_at) is not None
            and _utc(row.next_due_at) <= now
            and (_utc(row.cooldown_until) is None or _utc(row.cooldown_until) <= now)
        }
        registry = SourceRegistry()
        read_allowed_ids = {
            source_id for source_id in source_ids
            if source_id in registry._sources and registry.is_read_allowed(source_id)
        }
        validate_wave_contract(
            manifest_ids=manifest_ids,
            selected_ids=source_ids,
            due_ids=due_ids,
            read_allowed_ids=read_allowed_ids,
            queue_rows=_query_jobs(session),
            database_bytes=before_bytes,
            worker_count=len(source_ids),
        )
        baseline_job_ids = {
            row[0] for row in session.query(WorkerJobRecord.id).all()
        }
        scheduled = enqueue_due_catchup_sources(session, source_ids)
        if [item["source_id"] for item in scheduled] != source_ids:
            raise CatchupSafetyError("scheduler did not enqueue exactly the frozen source wave")
        session.commit()
        poll_job_ids = {item["job_id"] for item in scheduled}
    finally:
        session.close()
        engine.dispose()

    poll_drain = _drain_poll_jobs(
        poll_job_ids, wave_tag=wave_tag, baseline_job_ids=baseline_job_ids
    )
    poll_job_rows = poll_drain["job_rows"]

    engine, session = _connect()
    try:
        eval_job_ids = {
            row[0] for row in session.query(WorkerJobRecord.id)
            .filter(WorkerJobRecord.job_type == "evaluate_new")
            .all()
            if row[0] not in baseline_job_ids
        }
    finally:
        session.close()
        engine.dispose()

    eval_result = _drain_evaluation_jobs(wave_tag=wave_tag, allowed_ids=eval_job_ids)

    engine, session = _connect()
    try:
        active = _query_jobs(session)
        if active:
            raise CatchupSafetyError("wave queue failed to converge")
        polls = {source_id: _latest_poll(session, source_id) for source_id in source_ids}
        classifications = {}
        for job_id, row in poll_job_rows.items():
            row = poll_job_rows[job_id]
            source_id = row["payload"].get("source_id")
            if source_id not in source_ids:
                raise CatchupSafetyError("poll job payload escaped the frozen source wave")
            status, reason = _classify_source_terminal(polls[source_id], row)
            classifications[source_id] = {"status": status, "reason": reason, "poll": polls[source_id], "job_id": job_id}
        final = _runtime_snapshot(session, source_id=source_ids[0])
        _require_clean_queue(final)
        _require_capacity(final)
        assert_founder_state_unchanged(founder_state_baseline, final["founder_state"])
        assert_founder_state_unchanged(before["founder_state"], final["founder_state"])
        if final["lifecycle"]["opportunities"] != sum(
            final["lifecycle"][key] for key in ("hot_opportunities", "cold_opportunities", "protected_opportunities")
        ):
            raise CatchupSafetyError("lifecycle tier partition invariant failed")
        if final["lifecycle"]["cold_archive_rows"] != final["lifecycle"]["cold_opportunities"]:
            raise CatchupSafetyError("cold archive cardinality invariant failed")
        for key in (
            "cold_description_rows", "cold_raw_payload_rows", "cold_provenance_rows", "cold_verbose_evaluation_rows",
        ):
            if final["lifecycle"][key] != 0:
                raise CatchupSafetyError(f"cold storage invariant failed: {key}")
        if final["lifecycle"]["max_projections_per_opportunity"] > 1 or final["lifecycle"]["max_evaluations_per_opportunity"] > 1:
            raise CatchupSafetyError("duplicate current projection/evaluation invariant failed")
        wave = {
            "source_ids": source_ids,
            "poll_job_ids": sorted(poll_job_ids),
            "poll_worker_rounds": poll_drain["worker_rounds"],
            "evaluation_job_ids": eval_result["job_ids"],
            "evaluation_worker_rounds": eval_result["worker_rounds"],
            "sources": classifications,
            "database_bytes_before": before_bytes,
            "database_bytes_after": final["database_bytes"],
            "database_growth_bytes": final["database_bytes"] - before_bytes,
            "snapshot": final,
        }
        return wave
    finally:
        session.close()
        engine.dispose()


def _predict_next_cohort_bytes(state: dict[str, Any], current_bytes: int) -> int:
    return _predict_source_batch_bytes(state, current_bytes, MAX_COHORT_SOURCES)


def _predict_source_batch_bytes(state: dict[str, Any], current_bytes: int, source_count: int) -> int:
    historical = []
    for cohort in state["cohorts"]:
        processed_count = max(1, int(
            cohort.get("processed_sources") or len(cohort.get("source_ids", []))
        ))
        delta = max(0, int(cohort.get("database_growth_bytes", 0)))
        historical.append(delta / processed_count)
    last_wave = state.get("last_wave")
    if last_wave:
        count = max(1, len(last_wave.get("source_ids", [])))
        historical.append(max(0, int(last_wave.get("database_growth_bytes", 0))) / count)
    per_source = max([DEFAULT_MEASURED_BYTES_PER_SOURCE, *historical])
    return int(current_bytes + per_source * source_count * COHORT_PREDICTION_MULTIPLIER)


def run_cohort(state_path: Path, cohort_index: int) -> dict[str, Any]:
    state = _read_state(state_path)
    manifest = state["manifest"]
    entries = manifest["entries"]
    cohort = cohort_for_index(entries, cohort_index)
    earlier_ids = {item["source_id"] for item in entries[: cohort_index * MAX_COHORT_SOURCES]}
    if not earlier_ids.issubset(state["results"]):
        raise CatchupSafetyError("cohorts must execute sequentially against the frozen manifest")
    cohort_ids = [item["source_id"] for item in cohort]
    if len(cohort_ids) > MAX_COHORT_SOURCES:
        raise CatchupSafetyError("top-level cohort exceeded fifty source identities")

    engine, session = _connect()
    try:
        pre = _runtime_snapshot(session, source_id=cohort_ids[0])
        _require_clean_queue(pre)
        _require_capacity(pre)
        if pre["database_bytes"] >= COHORT_START_BYTES:
            state["status"] = "MAINTENANCE_REQUIRED"
            state["required_before_next_cohort_bytes"] = COHORT_START_BYTES
            state["last_snapshot"] = pre
            _write_json(state_path, state)
            return state
        projected = _predict_next_cohort_bytes(state, pre["database_bytes"])
        if projected >= COHORT_START_BYTES:
            state["status"] = "MAINTENANCE_REQUIRED"
            state["maintenance_reason"] = "predicted_next_cohort_reaches_380_mib"
            state["next_cohort_projection_bytes"] = projected
            state["last_snapshot"] = pre
            _write_json(state_path, state)
            return state
        founder_before = pre["founder_state"]
        before_bytes = pre["database_bytes"]
    finally:
        session.close()
        engine.dispose()

    frozen_at = datetime.fromisoformat(manifest["created_at"])
    started_ids = []
    cohort_waves = []
    for wave_index, start in enumerate(range(0, len(cohort), MAX_PARALLEL_SOURCE_WORKERS)):
        wave_entries = cohort[start : start + MAX_PARALLEL_SOURCE_WORKERS]
        wave_sources = []
        for entry in wave_entries:
            source_id = entry["source_id"]
            if source_id not in pending_manifest_sources(cohort, state["results"]):
                continue
            engine, session = _connect()
            try:
                existing = _existing_after_freeze(session, source_id, frozen_at)
                if existing:
                    state["results"][source_id] = existing
                    continue
                schedule = session.query(SourceScheduleRecord).filter_by(source_id=source_id).one_or_none()
                now = datetime.now(timezone.utc)
                if schedule is None:
                    raise CatchupSafetyError("frozen manifest source lost its durable schedule")
                due = _utc(schedule.next_due_at)
                cooling = _utc(schedule.cooldown_until)
                if cooling is not None and cooling > now:
                    state["results"][source_id] = {"status": "deferred", "reason": "source_cooldown_active"}
                    continue
                if due is None or due > now:
                    raise CatchupSafetyError("frozen source became not-due without a post-freeze poll")
                wave_sources.append(source_id)
            finally:
                session.close()
                engine.dispose()
        if not wave_sources:
            continue
        if len(wave_sources) > MAX_PARALLEL_SOURCE_WORKERS:
            raise CatchupSafetyError("source worker wave exceeded five identities")
        engine, session = _connect()
        try:
            wave_pre = _runtime_snapshot(session, source_id=wave_sources[0])
            _require_clean_queue(wave_pre)
            _require_capacity(wave_pre)
            predicted_wave_bytes = _predict_source_batch_bytes(
                {**state, "cohorts": state["cohorts"] + cohort_waves},
                wave_pre["database_bytes"],
                len(wave_sources),
            )
            if predicted_wave_bytes >= OVERNIGHT_CATCHUP_CEILING_BYTES:
                state["status"] = "MAINTENANCE_REQUIRED"
                state["maintenance_reason"] = "predicted_next_wave_reaches_390_mib"
                state["next_wave_projection_bytes"] = predicted_wave_bytes
                state["last_snapshot"] = wave_pre
                _write_json(state_path, state)
                return state
        finally:
            session.close()
            engine.dispose()
        wave_tag = f"c{cohort_index}-w{wave_index}"
        wave = _schedule_and_run_wave(
            wave_sources,
            wave_tag=wave_tag,
            manifest_ids={entry["source_id"] for entry in entries},
            founder_state_baseline=manifest["founder_state_at_freeze"],
        )
        cohort_waves.append(wave)
        for source_id, result in wave["sources"].items():
            state["results"][source_id] = result
            started_ids.append(source_id)
        state["last_snapshot"] = wave["snapshot"]
        state["last_wave"] = wave
        _write_json(state_path, state)
        if wave["database_bytes_after"] >= OVERNIGHT_CATCHUP_CEILING_BYTES:
            state["status"] = "SAFETY_PAUSE_390_MIB"
            state["failures"].append({"cohort": cohort_index, "wave": wave_index, "reason": state["status"]})
            _write_json(state_path, state)
            return state

    engine, session = _connect()
    try:
        final = _runtime_snapshot(session, source_id=cohort_ids[0])
        _require_clean_queue(final)
        assert_founder_state_unchanged(manifest["founder_state_at_freeze"], final["founder_state"])
        assert_founder_state_unchanged(founder_before, final["founder_state"])
        after_bytes = final["database_bytes"]
    finally:
        session.close()
        engine.dispose()

    successful = sum(state["results"].get(source_id, {}).get("status") == "success" for source_id in cohort_ids)
    deferred = sum(state["results"].get(source_id, {}).get("status") == "deferred" for source_id in cohort_ids)
    if successful + deferred != len(cohort_ids):
        raise CatchupSafetyError("cohort ended with unresolved manifest source identities")
    cohort_report = {
        "cohort_index": cohort_index,
        "source_ids": cohort_ids,
        "processed_sources": successful + deferred,
        "successes": successful,
        "deferred": deferred,
        "waves": cohort_waves,
        "database_bytes_before": before_bytes,
        "database_bytes_after": after_bytes,
        "database_growth_bytes": after_bytes - before_bytes,
        "next_cohort_projection_bytes": _predict_next_cohort_bytes(
            {**state, "cohorts": state["cohorts"] + [{"processed_sources": len(started_ids), "database_growth_bytes": after_bytes - before_bytes}]},
            after_bytes,
        ),
        "snapshot": final,
        "parallel_source_workers_max": MAX_PARALLEL_SOURCE_WORKERS,
        "max_retained_worker_connections": MAX_PARALLEL_SOURCE_WORKERS * HOSTED_WORKER_POOL_SIZE,
    }
    state["cohorts"] = [item for item in state["cohorts"] if item.get("cohort_index") != cohort_index]
    state["cohorts"].append(cohort_report)
    state["cohorts"].sort(key=lambda item: item["cohort_index"])
    state["last_snapshot"] = final
    state["status"] = "COHORT_COMPLETE"
    if after_bytes >= PROACTIVE_MAINTENANCE_BYTES or cohort_report["next_cohort_projection_bytes"] >= COHORT_START_BYTES:
        state["status"] = "MAINTENANCE_REQUIRED"
        state["maintenance_reason"] = "measured_or_projected_growth_reaches_380_mib"
    _write_json(state_path, state)
    return state


def finalize_live_run(state_path: Path) -> dict[str, Any]:
    state = _read_state(state_path)
    manifest = state["manifest"]
    expected_ids = {entry["source_id"] for entry in manifest["entries"]}
    if set(state["results"]) != expected_ids:
        missing = len(expected_ids - set(state["results"]))
        extra = len(set(state["results"]) - expected_ids)
        raise CatchupSafetyError(
            f"frozen manifest is not reconciled (missing={missing}, extra={extra})"
        )
    if any(item.get("status") not in {"success", "deferred"} for item in state["results"].values()):
        raise CatchupSafetyError("frozen manifest contains an unresolved source result")

    engine, session = _connect()
    try:
        source_id = manifest["entries"][0]["source_id"]
        final = _runtime_snapshot(session, source_id=source_id)
        _require_clean_queue(final)
        assert_founder_state_unchanged(manifest["founder_state_at_freeze"], final["founder_state"])
        if final["database_bytes"] >= 400 * 1024 * 1024:
            raise CatchupSafetyError("final database size is at or above the 400 MiB heavy-work pause")
        if final["lifecycle"]["opportunities"] != sum(
            final["lifecycle"][key] for key in (
                "hot_opportunities", "cold_opportunities", "protected_opportunities"
            )
        ):
            raise CatchupSafetyError("final lifecycle tier partition invariant failed")
        if final["lifecycle"]["cold_archive_rows"] != final["lifecycle"]["cold_opportunities"]:
            raise CatchupSafetyError("final cold archive cardinality invariant failed")
        for key in (
            "cold_description_rows", "cold_raw_payload_rows", "cold_provenance_rows",
            "cold_verbose_evaluation_rows",
        ):
            if final["lifecycle"][key] != 0:
                raise CatchupSafetyError(f"final cold storage invariant failed: {key}")
        if (
            final["lifecycle"]["max_projections_per_opportunity"] > 1
            or final["lifecycle"]["max_evaluations_per_opportunity"] > 1
        ):
            raise CatchupSafetyError("final duplicate projection/evaluation invariant failed")
    finally:
        session.close()
        engine.dispose()

    deferred = {
        source_id: result.get("reason")
        for source_id, result in state["results"].items()
        if result.get("status") == "deferred"
    }
    state["final_snapshot"] = final
    state["final_summary"] = {
        "manifest_count": manifest["count"],
        "manifest_sha256": manifest["sha256"],
        "successes": len(expected_ids) - len(deferred),
        "deferred": deferred,
        "dead_letter_count_at_freeze": manifest["queue_at_freeze"].get("dead_letter", 0),
        "dead_letter_count_final": final["queue"].get("dead_letter", 0),
        "dead_letter_delta": (
            final["queue"].get("dead_letter", 0)
            - manifest["queue_at_freeze"].get("dead_letter", 0)
        ),
        "database_bytes_final": final["database_bytes"],
        "queue_final": final["queue"],
    }
    if final["database_bytes"] >= PROACTIVE_MAINTENANCE_BYTES:
        state["status"] = "FINAL_MAINTENANCE_RECOMMENDED"
    else:
        state["status"] = "FINAL_VERIFIED"
    _write_json(state_path, state)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--freeze", action="store_true")
    group.add_argument("--cohort-index", type=int)
    group.add_argument("--finalize", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.freeze:
            result = freeze_live_manifest(args.state_file)
        elif args.finalize:
            result = finalize_live_run(args.state_file)
        else:
            result = run_cohort(args.state_file, args.cohort_index)
    except CatchupSafetyError as exc:
        print(json.dumps({"status": "SAFETY_STOP", "reason": str(exc)}, sort_keys=True))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error_class": type(exc).__name__}, sort_keys=True))
        return 2
    manifest = result["manifest"]
    print(json.dumps({
        "status": result.get("status", "MANIFEST_FROZEN"),
        "manifest_count": manifest["count"],
        "manifest_sha256": manifest["sha256"],
        "cohort_count": len(result.get("cohorts", [])),
        "result_count": len(result.get("results", {})),
        "database_bytes": (result.get("last_snapshot") or {}).get("database_bytes", manifest["database_bytes_at_freeze"]),
    }, sort_keys=True))
    return 0 if result.get("status", "MANIFEST_FROZEN") in {
        "MANIFEST_FROZEN", "COHORT_COMPLETE", "MAINTENANCE_REQUIRED",
        "FINAL_MAINTENANCE_RECOMMENDED", "FINAL_VERIFIED",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
