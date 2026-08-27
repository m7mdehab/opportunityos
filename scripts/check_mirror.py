#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*command: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mirror", help="public mirror git URL or local checkout")
    parser.add_argument("--source-sha", default="")
    args = parser.parse_args()
    source_sha = args.source_sha or run("git", "rev-parse", "HEAD", cwd=ROOT).stdout.strip()
    if not source_sha:
        raise SystemExit("RULE MIRROR_SOURCE_SHA FAILED: source SHA is unavailable. REMEDY: run from a committed private repository checkout or pass --source-sha.")

    mirror_path = Path(args.mirror)
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if mirror_path.is_dir():
        checkout = mirror_path.resolve()
        run("git", "fetch", "origin", cwd=checkout)
        if (checkout / ".git" / "shallow").exists():
            run("git", "fetch", "--deepen", "100", "origin", cwd=checkout)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="opportunityos-mirror-")
        checkout = Path(temporary.name) / "mirror"
        cloned = run("git", "clone", "--depth", "100", args.mirror, str(checkout))
        if cloned.returncode != 0:
            raise SystemExit(f"RULE MIRROR_FETCH FAILED: {cloned.stderr.strip()}. REMEDY: verify repository access and deploy-key health, then retry.")

    subject = run(
        "git", "log", "--format=%s", "--grep=^sync: ", "-1", cwd=checkout
    ).stdout.strip()
    match = re.fullmatch(r"sync:\s+([0-9a-fA-F]{7,40})", subject)
    mirror_sha = match.group(1) if match else "missing"
    current = source_sha.lower().startswith(mirror_sha.lower()) or mirror_sha.lower().startswith(source_sha.lower())
    if temporary:
        temporary.cleanup()
    if current:
        print(f"Mirror current: source {source_sha[:7]}, mirror {mirror_sha[:7]}.")
        return
    print(f"Mirror drift detected: source {source_sha[:7]}, mirror {mirror_sha[:7]}. Re-sync required.")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
