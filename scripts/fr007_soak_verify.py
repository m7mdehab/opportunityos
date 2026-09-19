"""FR-007 7-Day Soak Period Verifier.

Verifies a collection of immutable soak snapshots to prove:
1. Duration spans >= 7 days (>= 168 hours) continuously.
2. Monotonic timestamps without unrecorded gaps exceeding threshold.
3. All health states are PASS or WARN (zero FAIL states).
4. Zero founder PC dependency across all records.
5. Backup heartbeat freshness if required.

Outputs structured machine-readable JSON evaluation.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class FailedInterval:
    index: int
    timestamp_utc: str
    overall_state: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class SoakVerificationResult:
    result: str  # PASS, FAIL, INSUFFICIENT_DATA
    start_time_utc: str | None
    end_time_utc: str | None
    duration_hours: float
    snapshot_count: int
    max_gap_hours: float
    workflow_run_ids: list[str]
    monitor_run_ids: list[str]
    failed_intervals: list[dict[str, Any]]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_iso_utc(ts_str: str) -> datetime:
    """Parse ISO-8601 string to timezone-aware UTC datetime."""
    cleaned = ts_str.rstrip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def verify_soak_snapshots(
    snapshots: Sequence[dict[str, Any]],
    min_hours: float = 168.0,
    max_gap_hours: float = 4.0,
    min_snapshots: int = 2,
    require_backup_pass: bool = False,
    enforce_full_hosted: bool = True,
) -> SoakVerificationResult:
    """Analyze an ordered or unordered list of soak snapshots."""
    reasons: list[str] = []
    failed_intervals: list[dict[str, Any]] = []
    workflow_run_ids: set[str] = set()
    monitor_run_ids: set[str] = set()

    if not snapshots:
        return SoakVerificationResult(
            result="INSUFFICIENT_DATA",
            start_time_utc=None,
            end_time_utc=None,
            duration_hours=0.0,
            snapshot_count=0,
            max_gap_hours=0.0,
            workflow_run_ids=[],
            monitor_run_ids=[],
            failed_intervals=[],
            reasons=["No soak snapshots provided."],
        )

    # Sort snapshots by parsed timestamp
    try:
        parsed_items = []
        for idx, snap in enumerate(snapshots):
            ts = parse_iso_utc(snap["timestamp_utc"])
            parsed_items.append((ts, idx, snap))
        parsed_items.sort(key=lambda x: x[0])
    except Exception as exc:
        return SoakVerificationResult(
            result="FAIL",
            start_time_utc=None,
            end_time_utc=None,
            duration_hours=0.0,
            snapshot_count=len(snapshots),
            max_gap_hours=0.0,
            workflow_run_ids=[],
            monitor_run_ids=[],
            failed_intervals=[],
            reasons=[f"Failed to parse snapshot timestamps: {exc}"],
        )

    if len(parsed_items) < min_snapshots:
        reasons.append(
            f"Snapshot count ({len(parsed_items)}) is below required minimum ({min_snapshots})."
        )

    start_dt = parsed_items[0][0]
    end_dt = parsed_items[-1][0]
    duration_hours = max(0.0, (end_dt - start_dt).total_seconds() / 3600.0)

    if duration_hours < min_hours:
        reasons.append(
            f"Total duration ({duration_hours:.2f}h) is less than required ({min_hours:.2f}h)."
        )

    # Check consecutive gaps and individual health
    observed_max_gap = 0.0
    for i in range(len(parsed_items)):
        ts, orig_idx, snap = parsed_items[i]

        wf_id = snap.get("workflow_run_id")
        if wf_id:
            workflow_run_ids.add(str(wf_id))
        mon_id = snap.get("monitor_run_id")
        if mon_id:
            monitor_run_ids.add(str(mon_id))

        interval_failures = []

        # 1. Enforce proof scope (STATIC or SYNTHETIC data cannot count toward live soak)
        scope = snap.get("proof_scope", "UNKNOWN")
        if enforce_full_hosted and scope != "FULL_HOSTED":
            interval_failures.append(
                f"Invalid proof_scope '{scope}'; only FULL_HOSTED snapshots count toward A-14 soak"
            )

        # 2. Check overall state
        overall = snap.get("overall_state", "UNKNOWN")
        if overall not in ("PASS", "WARN"):
            interval_failures.append(f"Unhealthy overall state: {overall}")
        if overall == "NOT_CONFIGURED":
            interval_failures.append("NOT_CONFIGURED overall state cannot count as healthy soak")

        # 3. Check for unconfigured critical subsystems
        for sub in ("database_state", "queue_state", "web_state"):
            sub_st = snap.get(sub)
            if sub_st == "NOT_CONFIGURED":
                interval_failures.append(f"Subsystem {sub} is NOT_CONFIGURED (cannot masquerade as healthy hosted runtime)")

        # 4. Check founder PC dependency
        if snap.get("founder_pc_dependency", False) is True:
            interval_failures.append("Founder PC dependency detected (must be fully cloud-autonomous)")

        # 5. Check backup state if required
        if require_backup_pass:
            b_state = snap.get("backup_state", "NOT_CONFIGURED")
            if b_state not in ("PASS", "WARN"):
                interval_failures.append(f"Unhealthy backup state: {b_state}")

        if interval_failures:
            failed_intervals.append(
                asdict(
                    FailedInterval(
                        index=orig_idx,
                        timestamp_utc=snap.get("timestamp_utc", ts.isoformat()),
                        overall_state=overall,
                        reasons=interval_failures,
                    )
                )
            )

        if i > 0:
            prev_ts = parsed_items[i - 1][0]
            gap = (ts - prev_ts).total_seconds() / 3600.0
            if gap < 0:
                reasons.append(f"Non-monotonic timestamp detected between index {i-1} and {i}.")
            if gap > observed_max_gap:
                observed_max_gap = gap
            if gap > max_gap_hours:
                reasons.append(
                    f"Gap of {gap:.2f}h between {prev_ts.isoformat()} and {ts.isoformat()} exceeds max allowable gap ({max_gap_hours:.2f}h)."
                )

    if failed_intervals:
        reasons.append(f"{len(failed_intervals)} snapshot(s) exhibited unhealthy, static, or defective states.")

    # Determine final result
    if duration_hours < min_hours or len(parsed_items) < min_snapshots:
        final_result = "INSUFFICIENT_DATA" if not failed_intervals else "FAIL"
    elif reasons:
        final_result = "FAIL"
    else:
        final_result = "PASS"

    return SoakVerificationResult(
        result=final_result,
        start_time_utc=start_dt.isoformat(),
        end_time_utc=end_dt.isoformat(),
        duration_hours=round(duration_hours, 2),
        snapshot_count=len(parsed_items),
        max_gap_hours=round(observed_max_gap, 2),
        workflow_run_ids=sorted(workflow_run_ids),
        monitor_run_ids=sorted(monitor_run_ids),
        failed_intervals=failed_intervals,
        reasons=reasons,
    )


def load_snapshots_from_directory(dir_path: Path) -> list[dict[str, Any]]:
    """Load all JSON snapshots from a directory."""
    snapshots = []
    if not dir_path.is_dir():
        return []
    for p in sorted(dir_path.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "timestamp_utc" in data:
                    snapshots.append(data)
        except Exception:
            continue
    return snapshots


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify 7-day continuous soak health evidence."
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="",
        help="Directory containing soak snapshot JSON files.",
    )
    parser.add_argument(
        "--input-file",
        type=str,
        default="",
        help="Single JSON file containing an array of soak snapshots.",
    )
    parser.add_argument(
        "--min-hours",
        type=float,
        default=168.0,
        help="Minimum required continuous soak duration in hours (default: 168.0 = 7 days).",
    )
    parser.add_argument(
        "--max-gap-hours",
        type=float,
        default=4.0,
        help="Maximum allowed gap in hours between consecutive snapshots (default: 4.0).",
    )
    parser.add_argument(
        "--require-backup",
        action="store_true",
        default=False,
        help="Require backup_state to be PASS or WARN.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Path to write verification report JSON.",
    )

    args = parser.parse_args()

    snapshots: list[dict[str, Any]] = []
    if args.input_file:
        p = Path(args.input_file)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    snapshots = data
                elif isinstance(data, dict):
                    snapshots = [data]
    elif args.input_dir:
        snapshots = load_snapshots_from_directory(Path(args.input_dir))
    else:
        default_dir = REPO_ROOT / "reports" / "evidence" / "FR-007" / "soak"
        snapshots = load_snapshots_from_directory(default_dir)

    result = verify_soak_snapshots(
        snapshots=snapshots,
        min_hours=args.min_hours,
        max_gap_hours=args.max_gap_hours,
        require_backup_pass=args.require_backup,
    )

    out_json = json.dumps(result.to_dict(), indent=2) + "\n"

    if args.output:
        out_p = Path(args.output).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(out_json, encoding="utf-8")
        print(f"Verification report written to {out_p}")
    else:
        sys.stdout.write(out_json)

    if result.result == "PASS":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
