"""Incrementally bootstrap a bounded slice of the read-allowed source corpus.

Each source is scheduled and drained through the normal worker implementation,
with physical/storage/queue snapshots and a measured-capacity projection before
and after every source. A run is capped at 125 sources; it never sends one
registry-wide enqueue or performs direct worker-row edits.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import func

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from opportunity.registry import SourceRegistry
from scripts.fr007_hosted_bootstrap import main as hosted_bootstrap_main
from scripts.fr007_storage_v2_source_gate import _connect, snapshot, verify_source_archives
from storage.models import WorkerJobRecord

MODEL_PATH = REPOSITORY_ROOT / "reports/evidence/FR-007/W23_STORAGE_V2_CAPACITY_MODEL.json"
MAX_SOURCES_PER_RUN = 125
WORKER_MAX_JOBS = 2
WORKER_TIME_BUDGET_SECONDS = 480
DATABASE_HARD_BUDGET = 200 * 1024 * 1024
MAX_INCREMENT_ARCHIVE_OBJECTS = 500
MAX_INCREMENT_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_FOLLOWUP_JOBS = 1


def projected_final_database_bytes(current: dict[str, Any], model: dict[str, Any]) -> int:
    """Forecast remaining measured population with a 1% growth reserve."""
    target_opportunities = int(model["target_opportunities"])
    target_sources = int(model["target_read_allowed_sources"])
    measured_growth = int(model["benchmark_growth_bytes"])
    source_growth = int(model["source_overhead_relation_bytes"]["total"])
    if target_opportunities <= 0 or target_sources <= 0 or source_growth >= measured_growth:
        raise ValueError("capacity model has invalid measured population bounds")

    counts = current["counts"]
    current_opportunities = int(counts["opportunities"])
    covered_sources = int(current["successful_source_coverage"])
    remaining_sources = max(0, target_sources - covered_sources)
    remaining_opportunities = max(
        0,
        target_opportunities - current_opportunities,
        math.ceil(target_opportunities * remaining_sources / target_sources),
    )
    non_source_growth = measured_growth - source_growth
    reserve = 1.01
    remaining_bytes = math.ceil(
        non_source_growth * min(1.0, remaining_opportunities / target_opportunities) * reserve
    ) + math.ceil(source_growth * remaining_sources / target_sources * reserve)
    return int(current["database_bytes"]) + remaining_bytes


def select_registry_slice(source_ids: list[str], *, source_offset: int, max_sources: int) -> list[str]:
    if not 1 <= max_sources <= MAX_SOURCES_PER_RUN:
        raise ValueError(f"max_sources must be between 1 and {MAX_SOURCES_PER_RUN}")
    if not 0 <= source_offset < len(source_ids):
        raise ValueError("source_offset must point inside the read-allowed registry")
    return source_ids[source_offset : source_offset + max_sources]


def invariant_failures(state: dict[str, Any], projected_bytes: int) -> list[str]:
    counts = state["counts"]
    queue = state["queue"]
    failures: list[str] = []
    if state["database_revision"] != "0023_alembic_access":
        failures.append("schema_revision")
    if int(state["database_bytes"]) > DATABASE_HARD_BUDGET:
        failures.append("physical_database_budget")
    if projected_bytes > DATABASE_HARD_BUDGET:
        failures.append("projected_database_budget")
    if int(counts["opportunities"]) != int(counts["hot_opportunities"]) + int(counts["cold_opportunities"]) + int(counts["protected_opportunities"]):
        failures.append("lifecycle_tier_partition")
    if int(counts["cold_archive_rows"]) != int(counts["cold_opportunities"]):
        failures.append("cold_archive_cardinality")
    if int(counts["synthetic_active_feed_rows"]) != 0:
        failures.append("synthetic_active_feed")
    if int(counts["max_projections_per_opportunity"]) > 1:
        failures.append("duplicate_current_projection")
    if int(counts["max_evaluations_per_opportunity"]) > 1:
        failures.append("duplicate_current_evaluation")
    if int(counts["cold_description_rows"]) or int(counts["cold_raw_payload_rows"]):
        failures.append("cold_relational_source_body")
    if int(counts["cold_provenance_rows"]):
        failures.append("cold_relational_provenance")
    if int(counts["cold_verbose_evaluation_rows"]):
        failures.append("cold_verbose_evaluation")
    if int(counts["cold_max_reason_bytes"]) > 512:
        failures.append("cold_reason_payload_size")
    if any(int(queue[name] or 0) for name in ("pending", "retry", "running", "expired_leases")):
        failures.append("queue_not_converged_at_source_boundary")
    oldest_due = queue.get("oldest_due_age_seconds")
    if oldest_due is not None and int(oldest_due) >= 900:
        failures.append("oldest_due_age")
    return failures


def _take_snapshot(source_id: str) -> dict[str, Any]:
    engine, session = _connect()
    try:
        return snapshot(session.connection(), source_id=source_id)
    finally:
        session.close()
        engine.dispose()


def _verify_increment_archives(source_id: str, since) -> dict[str, Any]:
    engine, session = _connect()
    try:
        cursor: str | None = None
        verified_objects = 0
        verified_bytes = 0
        pages = 0
        while True:
            page = verify_source_archives(
                session.connection(),
                source_id=source_id,
                since=since,
                max_objects=MAX_INCREMENT_ARCHIVE_OBJECTS,
                max_archive_bytes=MAX_INCREMENT_ARCHIVE_BYTES,
                after_opportunity_id=cursor,
                include_cursor=True,
            )
            pages += 1
            verified_objects += int(page["archive_objects_verified"])
            verified_bytes += int(page["compressed_bytes_downloaded"])
            if not page.get("has_more"):
                break
            next_cursor = page.get("last_verified_opportunity_id")
            if not next_cursor or next_cursor == cursor:
                raise RuntimeError("incremental archive verifier cursor did not advance")
            cursor = str(next_cursor)
        return {
            "source_id": source_id,
            "archive_objects_verified": verified_objects,
            "compressed_bytes_downloaded": verified_bytes,
            "sha256_identity_verified": True,
            "download_scope": "source-scoped-cold-archives-only",
            "page_count": pages,
        }
    finally:
        session.close()
        engine.dispose()


def _runnable_job_type_counts() -> dict[tuple[str, str], int]:
    """Return aggregate runnable job types without reading job payloads."""
    engine, session = _connect()
    try:
        rows = (
            session.query(
                WorkerJobRecord.job_type,
                WorkerJobRecord.status,
                func.count(WorkerJobRecord.id),
            )
            .filter(WorkerJobRecord.status.in_(("PENDING", "RETRY", "RUNNING")))
            .group_by(WorkerJobRecord.job_type, WorkerJobRecord.status)
            .all()
        )
        return {(str(job_type), str(status)): int(count) for job_type, status, count in rows}
    finally:
        session.close()
        engine.dispose()


def _drain_source_followup() -> tuple[int, str | None]:
    """Drain only the single evaluate_new job produced by this source poll.

    A slow source can consume the worker's full 480-second loop budget inside
    its poll handler. The handler still completes under normal worker lease and
    retry semantics, then leaves its coalesced evaluation backfill pending.
    Give that one known follow-up its own bounded normal worker invocation;
    refuse to drain any other job type or an unbounded queue.
    """
    runnable = _runnable_job_type_counts()
    if not runnable:
        return 0, None
    if runnable != {("evaluate_new", "PENDING"): 1}:
        return 0, "unexpected_source_followup_queue"

    followup_result = hosted_bootstrap_main([
        "--mode", "drain",
        "--max-jobs", str(MAX_SOURCE_FOLLOWUP_JOBS),
        "--time-budget-seconds", str(WORKER_TIME_BUDGET_SECONDS),
    ])
    if followup_result != 0:
        return 1, "nonzero_source_followup_exit"
    if _runnable_job_type_counts():
        return 1, "source_followup_queue_not_converged"
    return 1, None


def _latest_status(state: dict[str, Any]) -> str | None:
    poll = state.get("latest_source_poll") or {}
    status = poll.get("status")
    return str(status) if status is not None else None


def _safe_source_result(state: dict[str, Any]) -> dict[str, Any]:
    poll = state.get("latest_source_poll") or {}
    status = str(poll.get("status") or "no_poll")
    if status not in {"ok", "error", "refused"}:
        status = "other"
    return {
        "status": status,
        "raw_ingested": int(poll.get("raw_ingested") or 0),
        "unique_opportunities": int(poll.get("unique_opportunities") or 0),
        "inserted": int(poll.get("inserted") or 0),
        "unchanged": int(poll.get("unchanged") or 0),
        "updated": int(poll.get("updated") or 0),
        "dead_letter_error_class_counts": state["dead_letter_error_class_counts"],
    }


def _compact_metrics(state: dict[str, Any], projected_bytes: int) -> dict[str, Any]:
    counts = state["counts"]
    return {
        "database_bytes": int(state["database_bytes"]),
        "public_relation_total_bytes": int(state["public_relation_total_bytes"]),
        "application_relation_total_bytes": int(state["application_relation_total_bytes"]),
        "projected_final_database_bytes": projected_bytes,
        "opportunities": int(counts["opportunities"]),
        "hot": int(counts["hot_opportunities"]),
        "cold": int(counts["cold_opportunities"]),
        "protected": int(counts["protected_opportunities"]),
        "feed_rows": int(counts["feed_rows"]),
        "evaluation_rows": int(counts["evaluation_rows"]),
        "provenance_rows": int(counts["provenance_rows"]),
        "cold_archive_rows": int(counts["cold_archive_rows"]),
        "compressed_archive_bytes": int(counts["compressed_archive_bytes"]),
        "successful_source_coverage": int(state["successful_source_coverage"]),
        "source_poll_status_counts": state["source_poll_status_counts"],
        "worker_jobs_total": int(counts["worker_jobs_total"]),
        "queue": state["queue"],
        "storage_buckets": state["storage_buckets"],
        "top_relations": state["top_relations"],
        "top_indexes": state["top_indexes"],
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, sort_keys=True, default=str) + "\n", encoding="utf-8")


def run_incremental_bootstrap(*, source_offset: int, max_sources: int, output: Path) -> dict[str, Any]:
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    registry = SourceRegistry()
    read_allowed_ids = sorted(sid for sid in registry._sources if registry.is_read_allowed(sid))
    if len(read_allowed_ids) != int(model["target_read_allowed_sources"]):
        raise RuntimeError("read-allowed registry size differs from the accepted physical capacity model")
    selected = select_registry_slice(
        read_allowed_ids,
        source_offset=source_offset,
        max_sources=max_sources,
    )

    report: dict[str, Any] = {
        "status": "RUNNING",
        "source_offset": source_offset,
        "max_sources": max_sources,
        "registry_source_count": len(read_allowed_ids),
        "selected_source_ids": selected,
        "already_successful_sources_skipped": [],
        "sources": [],
        "failure_count": 0,
        "capacity_model": {
            "representative_workflow_run_id": model["representative_workflow_run_id"],
            "target_opportunities": model["target_opportunities"],
            "target_read_allowed_sources": model["target_read_allowed_sources"],
            "benchmark_growth_bytes": model["benchmark_growth_bytes"],
            "hard_database_budget_bytes": model["hard_database_budget_bytes"],
            "projection_reserve_fraction": model["measurement_contract"]["safety_reserve_fraction_for_incremental_projection"],
        },
    }
    _write_report(output, report)
    fatal_failures: list[str] = []
    source_failures: list[str] = []

    for source_id in selected:
        before = _take_snapshot(source_id)
        before_status = _latest_status(before)
        before_projection = projected_final_database_bytes(before, model)
        before_failures = invariant_failures(before, before_projection)
        if before_failures:
            fatal_failures.extend(before_failures)
            report["status"] = "CAPACITY_OR_INVARIANT_STOP"
            report["fatal_failures"] = sorted(set(fatal_failures))
            _write_report(output, report)
            break
        if before_status == "ok":
            report["already_successful_sources_skipped"].append(source_id)
            report["sources"].append({
                "source_id": source_id,
                "status": "already_successful",
                "before": _compact_metrics(before, before_projection),
                "after": _compact_metrics(before, before_projection),
            })
            _write_report(output, report)
            print(json.dumps({"source_id": source_id, "status": "already_successful", "coverage": before["successful_source_coverage"]}))
            continue
        runner_error: str | None = None
        followup_jobs = 0
        followup_error: str | None = None
        try:
            # One source per normal scheduler/worker cycle guarantees a fresh
            # physical and relational measurement before the next source.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = hosted_bootstrap_main([
                    "--mode", "all",
                    "--source-ids", source_id,
                    "--max-jobs", str(WORKER_MAX_JOBS),
                    "--time-budget-seconds", str(WORKER_TIME_BUDGET_SECONDS),
                ])
            if result != 0:
                runner_error = "nonzero_runner_exit"
            else:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    followup_jobs, followup_error = _drain_source_followup()
        except Exception as exc:
            runner_error = type(exc).__name__

        after = _take_snapshot(source_id)
        after_projection = projected_final_database_bytes(after, model)
        after_failures = invariant_failures(after, after_projection)
        source_result = _safe_source_result(after)
        archive_verification: dict[str, Any] | None = None
        archive_error: str | None = None
        try:
            archive_verification = _verify_increment_archives(
                source_id,
                before["counts"].get("source_latest_archive_at"),
            )
        except Exception as exc:
            archive_error = type(exc).__name__
        source_ok = source_result["status"] == "ok" and runner_error is None
        failures = after_failures[:]
        if runner_error is not None:
            failures.append("worker_runner_" + runner_error)
        if followup_error is not None:
            failures.append(followup_error)
        if archive_error is not None:
            failures.append("cold_archive_verification_" + archive_error)
        if not source_ok:
            source_failures.append(source_id)
        item = {
            "source_id": source_id,
            "status": "ok" if source_ok else "source_failure",
            "runner_error_class": runner_error,
            "followup_worker_jobs": followup_jobs,
            "followup_error_class": followup_error,
            "poll": source_result,
            "archive_verification": archive_verification,
            "before": _compact_metrics(before, before_projection),
            "after": _compact_metrics(after, after_projection),
            "direct_tier_or_capacity_failures": sorted(set(failures)),
        }
        report["sources"].append(item)
        report["failure_count"] = len(source_failures)
        report["last_completed_source"] = source_id
        report["latest_metrics"] = _compact_metrics(after, after_projection)
        if failures:
            fatal_failures.extend(failures)
            report["status"] = "CAPACITY_OR_INVARIANT_STOP"
            report["fatal_failures"] = sorted(set(fatal_failures))
            _write_report(output, report)
            print(json.dumps({"source_id": source_id, "status": report["status"], "failures": report["fatal_failures"], "metrics": item["after"]}))
            break
        _write_report(output, report)
        print(json.dumps({
            "source_id": source_id,
            "status": item["status"],
            "poll": source_result,
            "database_bytes": item["after"]["database_bytes"],
            "projected_final_database_bytes": after_projection,
            "opportunities": item["after"]["opportunities"],
            "hot": item["after"]["hot"],
            "cold": item["after"]["cold"],
            "successful_source_coverage": item["after"]["successful_source_coverage"],
            "queue": item["after"]["queue"],
        }, sort_keys=True))

    if report["status"] == "RUNNING":
        if source_failures:
            report["status"] = "SOURCE_FAILURES_REQUIRE_REPAIR"
            report["failed_source_ids"] = source_failures
        elif len(report["already_successful_sources_skipped"]) + sum(
            item["status"] == "ok" for item in report["sources"]
        ) == len(selected):
            report["status"] = "PASS"
        else:
            report["status"] = "INCOMPLETE"
    _write_report(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-offset", type=int, required=True)
    parser.add_argument("--max-sources", type=int, default=125)
    parser.add_argument("--output", type=Path, default=Path("w23-incremental-source-bootstrap.json"))
    args = parser.parse_args(argv)
    try:
        report = run_incremental_bootstrap(
            source_offset=args.source_offset,
            max_sources=args.max_sources,
            output=args.output,
        )
    except Exception as exc:
        print(json.dumps({"status": "FATAL", "error_class": type(exc).__name__}))
        return 2
    print(json.dumps({
        "status": report["status"],
        "source_offset": report["source_offset"],
        "selected": len(report["selected_source_ids"]),
        "attempted_or_skipped": len(report["sources"]),
        "successful_source_coverage": (report.get("latest_metrics") or {}).get("successful_source_coverage"),
        "failure_count": report["failure_count"],
    }, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
