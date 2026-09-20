"""Process Incident Alert Actions via GitHub CLI.

Consumes the canonical incident action JSON produced by fr007_cloud_monitor:
{
  "action": "CREATE" | "UPDATE" | "RESOLVE" | "NONE",
  "title": str,
  "body": str,
  "issue_number": int | null,
  "marker": str,
  "is_synthetic": bool
}

Executes fail-closed mutations via gh CLI without silently ignoring errors.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def execute_incident_action(
    action_payload: Mapping[str, Any],
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] | None = None,
) -> int:
    """Execute the incident mutation against GitHub CLI."""
    action = action_payload.get("action", "NONE")
    title = str(action_payload.get("title") or "")
    body = str(action_payload.get("body") or "")
    issue_number = action_payload.get("issue_number")
    is_synthetic = bool(action_payload.get("is_synthetic", False))

    print(f"Executing incident action: {action} (synthetic={is_synthetic})")

    if action == "NONE":
        print("System healthy; no alert actions required.")
        return 0

    def default_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    exec_cmd = runner or default_runner

    if action == "CREATE":
        if not title or not body:
            print("Error: CREATE action requires both non-empty title and body", file=sys.stderr)
            return 1
        cmd = [
            "gh", "issue", "create",
            "--title", title,
            "--body", body,
            "--label", "incident,monitoring,fr-007",
        ]
        res = exec_cmd(cmd)
        if res.returncode != 0:
            err_output = res.stderr.strip() if res.stderr else ""
            err_lower = err_output.lower()
            if "could not add label" in err_lower or ("label" in err_lower and "not found" in err_lower):
                print(
                    f"Warning: GitHub rejected issue creation with labels ({err_output}). Retrying without labels...",
                    file=sys.stderr,
                )
                fallback_cmd = [
                    "gh", "issue", "create",
                    "--title", title,
                    "--body", body,
                ]
                res = exec_cmd(fallback_cmd)
                if res.returncode != 0:
                    print(f"Error executing unlabeled 'gh issue create': {res.stderr.strip()}", file=sys.stderr)
                    return res.returncode or 1
                print(f"Successfully created incident issue without labels: {res.stdout.strip()}")
                return 0

            print(f"Error executing 'gh issue create': {err_output}", file=sys.stderr)
            return res.returncode or 1
        print(f"Successfully created incident issue: {res.stdout.strip()}")
        return 0

    elif action == "UPDATE":
        if not issue_number:
            print("Error: UPDATE action requires an 'issue_number'", file=sys.stderr)
            return 1
        if not body:
            print("Error: UPDATE action requires a non-empty comment body", file=sys.stderr)
            return 1
        cmd = [
            "gh", "issue", "comment",
            str(issue_number),
            "--body", body,
        ]
        res = exec_cmd(cmd)
        if res.returncode != 0:
            print(f"Error executing 'gh issue comment' on #{issue_number}: {res.stderr.strip()}", file=sys.stderr)
            return res.returncode or 1
        print(f"Successfully updated incident issue #{issue_number}")
        return 0

    elif action == "RESOLVE":
        if not issue_number:
            print("Error: RESOLVE action requires an 'issue_number'", file=sys.stderr)
            return 1
        cmd = [
            "gh", "issue", "close",
            str(issue_number),
            "--comment", body,
        ]
        res = exec_cmd(cmd)
        if res.returncode != 0:
            print(f"Error executing 'gh issue close' on #{issue_number}: {res.stderr.strip()}", file=sys.stderr)
            return res.returncode or 1
        print(f"Successfully resolved and closed incident issue #{issue_number}")
        return 0

    else:
        print(f"Error: Unknown incident action '{action}'", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incident-file", required=True, help="Path to incident action JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Print command without executing")
    args = parser.parse_args()

    inc_path = Path(args.incident_file).resolve()
    if not inc_path.is_file():
        print(f"Incident file not found: {inc_path}", file=sys.stderr)
        return 1

    try:
        data = json.loads(inc_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed parsing incident JSON from {inc_path}: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[DRY-RUN] Action payload:\n{json.dumps(data, indent=2)}")
        return 0

    return execute_incident_action(data)


if __name__ == "__main__":
    raise SystemExit(main())
