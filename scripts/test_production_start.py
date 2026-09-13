from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from scripts import production_start


class _FakeProcess:
    def __init__(self, args: list[str], *, exit_immediately: bool = False) -> None:
        self.args = args
        self.returncode = 1 if exit_immediately else None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        if self.returncode is None:
            self.returncode = 0

    def wait(self, timeout: float | None = None):
        return self.returncode or 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class ProductionStartTests(unittest.TestCase):
    def test_production_runtime_starts_worker_scheduler_alongside_api_and_web(self) -> None:
        created: list[_FakeProcess] = []

        def fake_popen(args, **_kwargs):
            # The first child (API) is already exited when the supervision
            # loop begins so main() terminates deterministically instead of
            # sleeping forever. We still record all three spawn commands.
            proc = _FakeProcess(list(args), exit_immediately=(len(created) == 0))
            created.append(proc)
            return proc

        with (
            patch.object(production_start.subprocess, "run") as run,
            patch.object(production_start.subprocess, "Popen", side_effect=fake_popen),
            patch.object(production_start.shutil, "which", return_value="/usr/bin/npm"),
            patch.object(production_start.signal, "signal"),
            patch.object(production_start.time, "sleep"),
        ):
            exit_code = production_start.main()

        self.assertEqual(exit_code, 1)
        run.assert_called_once()
        commands = [proc.args for proc in created]
        self.assertEqual(len(commands), 3)
        self.assertTrue(any(cmd[:3] == [sys.executable, "-m", "uvicorn"] for cmd in commands))
        self.assertTrue(
            any(
                cmd[:3] == [sys.executable, "-m", "worker"] and "--schedule" in cmd
                for cmd in commands
            ),
            commands,
        )
        self.assertTrue(any(cmd[:3] == ["/usr/bin/npm", "run", "start"] for cmd in commands))


if __name__ == "__main__":
    unittest.main()
