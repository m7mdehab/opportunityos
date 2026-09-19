"""Aggregate durable FR-007 soak snapshots from GitHub Actions artifacts.

Only artifacts emitted by MONITOR runs use the `soak-snapshot-*` prefix.
This collector paginates the entire artifact history, fails closed when GitHub
cannot be queried/downloaded, and extracts only canonical `soak-*.json`
snapshot files (never monitor reports or synthetic-alert payloads).
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


Runner = Callable[..., subprocess.CompletedProcess[Any]]


def fetch_soak_artifacts(target_dir: Path, runner: Runner | None = None) -> int:
    """Download every unexpired soak artifact and flatten only soak snapshots.

    Returns the number of snapshot JSON files extracted. Any GitHub API or
    artifact-download failure raises RuntimeError so SOAK_SUMMARY fails closed.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    exec_cmd = runner or subprocess.run

    list_cmd: list[str] = [
        "gh",
        "api",
        "--paginate",
        "/repos/{owner}/{repo}/actions/artifacts?per_page=100",
        "--jq",
        '.artifacts[] | select((.name | startswith("soak-snapshot-")) and (.expired == false)) | {id: .id, name: .name, created_at: .created_at}',
    ]
    try:
        res = exec_cmd(
            list_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except Exception as exc:
        raise RuntimeError(f"GitHub artifact listing failed: {exc}") from exc

    if res.returncode != 0:
        stderr = (res.stderr or "").strip()
        raise RuntimeError(
            f"GitHub artifact listing failed with exit {res.returncode}: {stderr}"
        )

    lines = [line.strip() for line in (res.stdout or "").splitlines() if line.strip()]
    snapshots_written = 0

    for line in lines:
        try:
            art = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid artifact-list JSON from gh api: {line[:160]}") from exc

        art_id = art.get("id")
        art_name = art.get("name")
        if not art_id or not art_name:
            raise RuntimeError(f"Artifact listing omitted id/name: {art!r}")

        dl_cmd = [
            "gh",
            "api",
            f"/repos/{{owner}}/{{repo}}/actions/artifacts/{art_id}/zip",
        ]
        try:
            dl_res = exec_cmd(
                dl_cmd,
                capture_output=True,
                text=False,
                check=False,
                timeout=30,
            )
        except Exception as exc:
            raise RuntimeError(f"Artifact {art_id} download failed: {exc}") from exc

        if dl_res.returncode != 0:
            stderr_raw = dl_res.stderr or b""
            stderr = (
                stderr_raw.decode("utf-8", errors="replace")
                if isinstance(stderr_raw, (bytes, bytearray))
                else str(stderr_raw)
            ).strip()
            raise RuntimeError(
                f"Artifact {art_id} download failed with exit {dl_res.returncode}: {stderr}"
            )

        archive = dl_res.stdout or b""
        if isinstance(archive, str):
            archive = archive.encode("utf-8")

        try:
            with zipfile.ZipFile(io.BytesIO(archive), "r") as zf:
                members = [
                    name
                    for name in zf.namelist()
                    if PurePosixPath(name).name.startswith("soak-")
                    and PurePosixPath(name).name.endswith(".json")
                ]
                for member in members:
                    raw = zf.read(member)
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception as exc:
                        raise RuntimeError(
                            f"Artifact {art_id} contains invalid soak snapshot {member}"
                        ) from exc
                    if not isinstance(payload, dict) or "timestamp_utc" not in payload:
                        raise RuntimeError(
                            f"Artifact {art_id} contains malformed soak snapshot {member}"
                        )
                    basename = PurePosixPath(member).name
                    destination = target_dir / f"{art_id}-{basename}"
                    destination.write_bytes(raw)
                    snapshots_written += 1
        except zipfile.BadZipFile as exc:
            raise RuntimeError(f"Artifact {art_id} is not a valid zip archive") from exc

    print(f"Extracted {snapshots_written} durable soak snapshot(s) into {target_dir}")
    return snapshots_written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-dir",
        type=str,
        default=str(REPO_ROOT / ".monitor_output" / "soak"),
        help="Directory to save flattened soak snapshot JSON files",
    )
    args = parser.parse_args(argv)

    target_p = Path(args.target_dir).resolve()
    try:
        fetch_soak_artifacts(target_p)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
