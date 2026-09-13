#!/usr/bin/env python3
"""Start the production OpportunityOS API, worker/scheduler, and Founder Web Alpha.

The local alpha runner has always included ``python -m worker --schedule``.
Production must do the same: without the worker the web/API can serve rows already
in PostgreSQL, but ``poll-now`` only enqueues jobs and no process consumes them,
so the deployed feed silently freezes at whatever bounded seed data happened to
be present when the deployment was created.
"""
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
        # API first so health/auth endpoints become available as the worker
        # begins its first scheduler tick.
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

        # Production parity with scripts/alpha.py: run the durable queue
        # consumer and PollScheduler continuously. A fresh scheduler tick
        # enqueues every due read-allowed source; each successful poll also
        # evaluates newly persisted rows against the current private truth
        # pack. Source policy/rate-limit/403/429 fail-closed behavior remains
        # inside the existing scheduler/handler stack.
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "worker", "--schedule"],
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
