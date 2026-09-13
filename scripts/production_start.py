#!/usr/bin/env python3
"""Start the migrated API and Founder Web Alpha in one production container."""
from __future__ import annotations

import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    port = os.environ.get("PORT", "10000")
    subprocess.run(["alembic", "upgrade", "head"], cwd=ROOT, check=True)

    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm executable not found")

    processes: list[subprocess.Popen[bytes]] = []
    try:
        processes.append(subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "api.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--proxy-headers",
                "--forwarded-allow-ips=127.0.0.1",
            ],
            cwd=ROOT,
        ))
        processes.append(subprocess.Popen(
            [npm, "run", "start", "--", "--hostname", "0.0.0.0", "--port", port],
            cwd=ROOT / "web",
        ))
    except Exception:
        for process in processes:
            process.terminate()
        raise

    def stop(_signum: int | None = None, _frame: object | None = None) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    finally:
        stop()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    return next((process.returncode or 0 for process in processes if process.returncode), 0)


if __name__ == "__main__":
    raise SystemExit(main())
