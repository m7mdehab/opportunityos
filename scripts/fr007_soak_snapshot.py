"""FR-007 Soak Health Snapshot Generator.

Transforms an external cloud monitor report into a sanitized, immutable
soak record. Ensures all required subsystem states are captured without
credentials, personal data, or founder PC dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STATES = ("PASS", "WARN", "FAIL", "BLOCKED", "NOT_CONFIGURED")

CHECK_TO_STATE_KEY: Mapping[str, str] = {
    "web_liveness": "web_state",
    "api_liveness": "api_state",
    "database_connection": "database_state",
    "database_connectivity": "database_state",
    "database_and_queue": "database_state",
    "queue_state": "queue_state",
    "queue_health": "queue_state",
    "scheduler_state": "scheduler_state",
    "source_freshness": "source_freshness_state",
    "backup_heartbeat": "backup_state",
}


def get_current_git_sha() -> str:
    """Derive git commit SHA from environment or git CLI."""
    env_sha = os.environ.get("GITHUB_SHA") or os.environ.get("GIT_SHA")
    if env_sha:
        return env_sha.strip()
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "UNKNOWN_SHA"


def build_soak_snapshot(
    report_data: Mapping[str, Any],
    repository_sha: str | None = None,
    deployment_identifier: str | None = None,
    founder_pc_dependency: bool = False,
    monitor_run_id: str | None = None,
    workflow_run_id: str | None = None,
    proof_scope: str | None = None,
) -> dict[str, Any]:
    """Transform raw monitor report dictionary into a canonical soak snapshot."""
    timestamp_utc = report_data.get("timestamp_utc")
    if not timestamp_utc:
        timestamp_utc = datetime.now(timezone.utc).isoformat()

    sha = repository_sha or get_current_git_sha()
    deployment_id = (
        deployment_identifier
        or os.environ.get("DEPLOYMENT_IDENTIFIER")
        or "cloudflare-aca-staging"
    )
    run_id = (
        monitor_run_id
        or os.environ.get("GITHUB_RUN_ID")
        or f"run-{uuid.uuid4().hex[:12]}"
    )
    wf_run_id = (
        workflow_run_id
        or os.environ.get("GITHUB_RUN_ID")
        or "local-run"
    )

    # Derive proof scope: FULL -> FULL_HOSTED, STATIC -> STATIC_LOCAL, TEST_ALERT -> TEST_SYNTHETIC
    report_mode = report_data.get("mode", "FULL")
    if proof_scope:
        effective_scope = proof_scope
    elif report_mode == "FULL":
        effective_scope = "FULL_HOSTED"
    elif report_mode == "STATIC":
        effective_scope = "STATIC_LOCAL"
    elif report_mode == "TEST_ALERT":
        effective_scope = "TEST_SYNTHETIC"
    else:
        effective_scope = f"CUSTOM_{report_mode}"

    # Initialize check states to NOT_CONFIGURED
    subsystem_states: dict[str, str] = {
        "web_state": "NOT_CONFIGURED",
        "api_state": "NOT_CONFIGURED",
        "database_state": "NOT_CONFIGURED",
        "queue_state": "NOT_CONFIGURED",
        "scheduler_state": "NOT_CONFIGURED",
        "source_freshness_state": "NOT_CONFIGURED",
        "backup_state": "NOT_CONFIGURED",
    }

    # Extract checks from report
    checks = report_data.get("checks", [])
    for check in checks:
        if isinstance(check, dict):
            c_name = check.get("name")
            c_status = check.get("status", "NOT_CONFIGURED")
            if c_name in CHECK_TO_STATE_KEY:
                state_key = CHECK_TO_STATE_KEY[c_name]
                subsystem_states[state_key] = (
                    c_status if c_status in STATES else "FAIL"
                )

    if (
        subsystem_states["scheduler_state"] == "NOT_CONFIGURED"
        and subsystem_states["source_freshness_state"] != "NOT_CONFIGURED"
    ):
        subsystem_states["scheduler_state"] = subsystem_states["source_freshness_state"]

    overall_state = report_data.get("overall_status", "NOT_CONFIGURED")
    if overall_state not in STATES:
        overall_state = "FAIL"

    snapshot = {
        "timestamp_utc": timestamp_utc,
        "repository_sha": sha,
        "deployment_identifier": deployment_id,
        "workflow_run_id": str(wf_run_id),
        "monitor_run_id": str(run_id),
        "proof_scope": effective_scope,
        "web_state": subsystem_states["web_state"],
        "api_state": subsystem_states["api_state"],
        "database_state": subsystem_states["database_state"],
        "queue_state": subsystem_states["queue_state"],
        "scheduler_state": subsystem_states["scheduler_state"],
        "source_freshness_state": subsystem_states["source_freshness_state"],
        "backup_state": subsystem_states["backup_state"],
        "overall_state": overall_state,
        "founder_pc_dependency": bool(founder_pc_dependency),
    }
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate sanitized, immutable soak health snapshot."
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default="",
        help="Path to MonitorReport JSON file (or '-' for stdin).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Path to save soak snapshot JSON file (or '-' for stdout).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="Directory to save timestamped soak snapshot JSON file.",
    )
    parser.add_argument(
        "--deployment-id",
        type=str,
        default="",
        help="Deployment identifier string.",
    )
    parser.add_argument(
        "--sha",
        type=str,
        default="",
        help="Repository commit SHA.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default="",
        help="External monitor run ID.",
    )
    parser.add_argument(
        "--workflow-run-id",
        type=str,
        default="",
        help="GitHub Actions workflow run ID.",
    )
    parser.add_argument(
        "--proof-scope",
        type=str,
        default="",
        help="Explicit proof scope (FULL_HOSTED, STATIC_LOCAL, TEST_SYNTHETIC).",
    )
    parser.add_argument(
        "--founder-pc-dependency",
        action="store_true",
        default=False,
        help="Flag if execution required founder PC (defective in automated cloud soak).",
    )

    args = parser.parse_args()

    report_data: dict[str, Any] = {}
    if args.report_file == "-":
        report_data = json.load(sys.stdin)
    elif args.report_file:
        with open(args.report_file, "r", encoding="utf-8") as f:
            report_data = json.load(f)
    else:
        # If no report file is passed, run a local STATIC monitor probe
        from scripts.fr007_cloud_monitor import run_monitor

        report = run_monitor(mode="STATIC")
        report_data = report.to_dict()

    snapshot = build_soak_snapshot(
        report_data=report_data,
        repository_sha=args.sha or None,
        deployment_identifier=args.deployment_id or None,
        founder_pc_dependency=args.founder_pc_dependency,
        monitor_run_id=args.run_id or None,
        workflow_run_id=args.workflow_run_id or None,
        proof_scope=args.proof_scope or None,
    )

    formatted_json = json.dumps(snapshot, indent=2) + "\n"

    if args.output == "-":
        sys.stdout.write(formatted_json)
        return 0

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(formatted_json, encoding="utf-8")
        print(f"Saved soak snapshot to {out_path}")
        return 0

    if args.output_dir:
        out_dir = Path(args.output_dir).resolve()
    else:
        out_dir = REPO_ROOT / "reports" / "evidence" / "FR-007" / "soak"

    out_dir.mkdir(parents=True, exist_ok=True)
    # Sanitize timestamp for filename
    ts_str = snapshot["timestamp_utc"].replace(":", "-").replace("+", "Z")
    filename = f"soak-{ts_str}.json"
    out_file = out_dir / filename
    out_file.write_text(formatted_json, encoding="utf-8")
    print(f"Saved soak snapshot to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
