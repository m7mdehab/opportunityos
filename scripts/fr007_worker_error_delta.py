"""Run a bounded hosted worker shard and emit only sanitized error deltas."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ERROR_TOKENS = (
    "EMAXCONNSESSION",
    "UniqueViolation",
    "ReadOnlySqlTransaction",
)


def count_error_tokens(lines) -> dict[str, int]:
    counts = {token: 0 for token in ERROR_TOKENS}
    for line in lines:
        for token in ERROR_TOKENS:
            counts[token] += len(re.findall(re.escape(token), line, flags=re.IGNORECASE))
    return counts


def run_shard(*, max_jobs: int, time_budget_seconds: int, worker_id: str, shard: int, output: Path) -> dict:
    if max_jobs != 30 or time_budget_seconds != 480:
        raise ValueError("protected FR-007 proof shard must use exactly 30 jobs / 480 seconds")
    if not worker_id.startswith("w227-recovery-"):
        raise ValueError("protected worker shard identity is invalid")
    if shard not in range(1, 6):
        raise ValueError("protected worker shard number must be 1 through 5")
    command = [
        sys.executable,
        str(Path(__file__).resolve().with_name("fr007_hosted_bootstrap.py")),
        "--mode", "drain",
        "--max-jobs", str(max_jobs),
        "--time-budget-seconds", str(time_budget_seconds),
        "--worker-id", worker_id,
    ]
    child = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=os.environ.copy(),
    )
    assert child.stdout is not None
    counts = count_error_tokens(child.stdout)
    return_code = child.wait()
    errors = {
        token: {"baseline": 0, "final": value, "delta": value}
        for token, value in counts.items()
    }
    result = {
        "status": "PASS" if return_code == 0 and all(value == 0 for value in counts.values()) else "FAIL",
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "worker_id": worker_id,
        "shard": shard,
        "jobs_limit": max_jobs,
        "time_budget_seconds": time_budget_seconds,
        "child_exit_code": return_code,
        "error_counts_since_shard_start": errors,
        "raw_worker_logs_recorded": False,
    }
    output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise RuntimeError("protected shard failed or observed a forbidden new PostgreSQL error")
    return result


def aggregate_shard_results(directory: Path, *, run_id: str) -> dict:
    files = sorted(directory.glob("*.json"))
    if len(files) != 5:
        raise ValueError(f"expected exactly five sanitized shard evidence files; found {len(files)}")
    results = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    shards = [int(result.get("shard", 0)) for result in results]
    if sorted(shards) != [1, 2, 3, 4, 5]:
        raise ValueError("shard evidence does not contain each of the five unique shards")
    if any(str(result.get("run_id")) != str(run_id) for result in results):
        raise ValueError("shard evidence belongs to a different hosted proof run")
    if any(result.get("jobs_limit") != 30 or result.get("time_budget_seconds") != 480 for result in results):
        raise ValueError("shard evidence does not match normal W22.5 worker settings")
    deltas = {
        token: sum(int(item["error_counts_since_shard_start"][token]["delta"]) for item in results)
        for token in ERROR_TOKENS
    }
    report = {
        "status": "PASS" if all(result.get("status") == "PASS" for result in results) and all(value == 0 for value in deltas.values()) else "FAIL",
        "run_id": str(run_id),
        "shards": 5,
        "normal_jobs_per_shard": 30,
        "normal_time_budget_seconds_per_shard": 480,
        "new_error_delta_since_proof_start": {
            token: {"baseline": 0, "final": value, "delta": value}
            for token, value in deltas.items()
        },
        "raw_worker_logs_recorded": False,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-jobs", type=int, default=30)
    parser.add_argument("--time-budget-seconds", type=int, default=480)
    parser.add_argument("--worker-id")
    parser.add_argument("--shard", type=int)
    parser.add_argument("--aggregate-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.aggregate_dir is not None:
            result = aggregate_shard_results(
                args.aggregate_dir,
                run_id=os.environ.get("GITHUB_RUN_ID", ""),
            )
            args.output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(result, sort_keys=True))
            if result["status"] != "PASS":
                raise RuntimeError("aggregate worker error delta failed")
        else:
            if args.worker_id is None or args.shard is None:
                parser.error("shard mode requires --worker-id and --shard")
            run_shard(
                max_jobs=args.max_jobs,
                time_budget_seconds=args.time_budget_seconds,
                worker_id=args.worker_id,
                shard=args.shard,
                output=args.output,
            )
    except Exception as exc:
        raise SystemExit(f"protected worker shard failed ({type(exc).__name__}); details suppressed") from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
