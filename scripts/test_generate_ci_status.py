#!/usr/bin/env python3
"""Unit tests for scripts/generate_ci_status.py::compute_verdict.

Runs both standalone (python scripts/test_generate_ci_status.py -v) and,
once scripts/__init__.py exists, as a package module
(python -m unittest scripts.test_generate_ci_status -v).
"""
from __future__ import annotations

import sys
import pathlib
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
try:
    from scripts.generate_ci_status import compute_verdict, WORKFLOWS
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from generate_ci_status import compute_verdict, WORKFLOWS


class ComputeVerdictTests(unittest.TestCase):
    def test_all_four_success_and_mirror_current_is_healthy(self) -> None:
        statuses = {name: "success" for name in WORKFLOWS}
        self.assertEqual(compute_verdict(statuses, mirror_current=True), "HEALTHY")

    def test_mandatory_failure_with_others_success_is_not_healthy(self) -> None:
        statuses = {name: "success" for name in WORKFLOWS}
        statuses["Mandatory Governance & Test Suite"] = "failure"
        self.assertNotEqual(compute_verdict(statuses, mirror_current=True), "HEALTHY")
        self.assertEqual(compute_verdict(statuses, mirror_current=True), "CHECKS FAILING")

    def test_any_workflow_unavailable_is_not_healthy(self) -> None:
        for unavailable_workflow in WORKFLOWS:
            with self.subTest(workflow=unavailable_workflow):
                statuses = {name: "success" for name in WORKFLOWS}
                statuses[unavailable_workflow] = "unavailable"
                self.assertNotEqual(compute_verdict(statuses, mirror_current=True), "HEALTHY")
                self.assertEqual(compute_verdict(statuses, mirror_current=True), "CHECKS FAILING")

    def test_mirror_stale_with_all_checks_green(self) -> None:
        statuses = {name: "success" for name in WORKFLOWS}
        self.assertEqual(compute_verdict(statuses, mirror_current=False), "MIRROR STALE")

    def test_workflows_tuple_is_exactly_four_named_workflows(self) -> None:
        self.assertEqual(
            WORKFLOWS,
            ("Mandatory Governance & Test Suite", "State", "Guard", "Mirror"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
