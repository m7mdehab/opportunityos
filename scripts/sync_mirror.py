#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import shutil
import subprocess
from pathlib import Path


README = """# OpportunityOS Documentation Mirror

This repository is a read-only, derived documentation mirror for OpportunityOS, an opportunity-acquisition platform for MENA. The private `opportunityos` repository is the authoritative source of truth. Pull requests against this mirror are not accepted.

Only allowlisted documentation, briefs, reports, and agent instructions are published here after content guards pass. Working code and private founder data are not included.

This mirror is disposable. If content is ever exposed here incorrectly, delete the public repository entirely and recreate it by running the private repository's guarded sync workflow.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--sync-time", required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    if source == destination or not (destination / ".git").is_dir():
        raise SystemExit("RULE MIRROR_TARGET FAILED: destination must be a separate git checkout. REMEDY: clone the public mirror into a clean temporary directory.")

    patterns = [
        line.strip()
        for line in (source / ".mirror-allowlist").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=source, capture_output=True, check=True
    ).stdout.split(b"\0")

    heartbeat_path = destination / "docs" / "CI_STATUS.md"
    heartbeat = heartbeat_path.read_bytes() if heartbeat_path.exists() else None

    for child in destination.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    for raw in tracked:
        if not raw:
            continue
        relative = raw.decode("utf-8")
        if not any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)

    if heartbeat is not None:
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        heartbeat_path.write_bytes(heartbeat)

    state = destination / "docs" / "STATE.md"
    if state.exists():
        text = state.read_text(encoding="utf-8")
        lines = text.splitlines()
        lines = [
            f"- **Mirror sync:** `{args.source_sha}` at {args.sync_time}"
            if line.startswith("- **Mirror sync:**")
            else line
            for line in lines
        ]
        state.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (destination / "README.md").write_text(README, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
