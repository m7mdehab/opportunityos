from __future__ import annotations

import ast
import unittest
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.db_capacity_guard import PROVIDER_LIMIT_BYTES
from scripts.db_capacity_maintenance import (
    PROVIDER_REWRITE_SAFETY_MARGIN_BYTES,
    relation_rewrite_fits_provider,
    relation_rewrite_peak_estimate,
)


class RelationRewriteHeadroomTests(unittest.TestCase):
    def test_workflow_relation_rewrite_script_imports_its_capacity_helpers(self):
        root = Path(__file__).resolve().parents[1]
        workflow_path = root / ".github/workflows/fr007-hot-evaluation-capacity-reclaim.yml"
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        steps = workflow["jobs"]["maintain"]["steps"]
        step = next(
            item for item in steps
            if item.get("name") == "Reclaim application and Storage metadata bloat without changing rows"
        )
        script = step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        self.assertIn('"storage.objects"', script)
        tree = ast.parse(script)
        imported = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        )
        loaded = {
            node.id for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        self.assertTrue(
            {"PROVIDER_LIMIT_BYTES", "relation_rewrite_peak_estimate"} <= imported & loaded
        )

    def test_maintenance_cli_imports_when_run_as_a_script(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "scripts/db_capacity_maintenance.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("hot-dimensions-apply", result.stdout)

    def test_estimate_includes_database_relation_and_safety_margin(self):
        self.assertEqual(
            relation_rewrite_peak_estimate(400_000_000, 50_000_000),
            450_000_000 + PROVIDER_REWRITE_SAFETY_MARGIN_BYTES,
        )

    def test_large_relation_rewrite_is_deferred_before_provider_boundary(self):
        database_bytes = 405_294_227
        relation_bytes = 124_149_760
        self.assertGreaterEqual(
            relation_rewrite_peak_estimate(database_bytes, relation_bytes),
            PROVIDER_LIMIT_BYTES,
        )
        self.assertFalse(relation_rewrite_fits_provider(database_bytes, relation_bytes))

    def test_medium_relation_rewrite_retains_transient_provider_headroom(self):
        database_bytes = 405_294_227
        relation_bytes = 76_275_712
        self.assertLess(
            relation_rewrite_peak_estimate(database_bytes, relation_bytes),
            PROVIDER_LIMIT_BYTES,
        )
        self.assertTrue(relation_rewrite_fits_provider(database_bytes, relation_bytes))


if __name__ == "__main__":
    unittest.main()
