"""Synthetic inspection and parity tests; no database or private data required."""

import copy
import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from scripts import migration_baseline as mb


class Cursor:
    def __init__(self):
        self.sql = []
        self.rows = []
        self.position = 0

    def execute(self, sql):
        self.sql.append(sql)
        self.position = 0
        if "information_schema.columns" in sql:
            self.rows = [("opportunities", "id"), ("opportunities", "content_hash"),
                         ("match_evaluations", "opportunity_id"),
                         ("match_evaluations", "truth_pack_hash"),
                         ("match_evaluations", "qualification_decision"),
                         ("alembic_version", "version_num")]
        elif "information_schema.table_constraints" in sql:
            self.rows = [("match_evaluations", "uq_match_evaluations_opportunity_truth_pack")]
        elif "FROM public.alembic_version" in sql:
            self.rows = [("0006_feed_projection",)]
        elif "GROUP BY truth_pack_hash" in sql:
            self.rows = [("a" * 64, 1, 1)]
        elif "ORDER BY id LIMIT" in sql:
            self.rows = [("greenhouse:acme:123", "b" * 64)]
        elif "SELECT id, content_hash FROM public.opportunities ORDER BY id" in sql:
            self.rows = [("greenhouse:acme:123", "b" * 64)]
        elif "SELECT opportunity_id, truth_pack_hash, qualification_decision" in sql:
            self.rows = [("greenhouse:acme:123", "a" * 64, "qualified")]
        elif "GROUP BY 1 ORDER BY 1" in sql:
            self.rows = [("qualified", 1)]
        elif "count(*)" in sql:
            self.rows = [(0 if "AS duplicates" in sql or "LEFT JOIN" in sql else
                          1 if 'FROM public."opportunities"' in sql or 'FROM public."match_evaluations"' in sql else 0,)]
        else:
            self.rows = []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]

    def fetchmany(self, size):
        chunk = self.rows[self.position:self.position + size]
        self.position += len(chunk)
        return chunk

    def close(self):
        pass


class Connection:
    def __init__(self):
        self.query = Cursor()
        self.rollbacks = 0

    def cursor(self):
        return self.query

    def rollback(self):
        self.rollbacks += 1


class MigrationBaselineTests(unittest.TestCase):
    def test_snapshot_is_allowlisted_and_read_only(self):
        db = Connection()
        data = mb.inspect(db)
        self.assertEqual(data["alembic_revision"], "0006_feed_projection")
        self.assertEqual(data["tables"]["opportunities"], 1)
        self.assertIsNone(data["tables"]["artifact_cache"])
        self.assertEqual(data["evaluation_coverage"][0]["truth_pack_hash"], "a" * 64)
        self.assertEqual(data["opportunity_sample"], [{"id": "greenhouse:acme:123", "content_hash": "b" * 64}])
        self.assertEqual(db.rollbacks, 0)
        self.assertEqual(db.query.sql[-1], "ROLLBACK")
        self.assertTrue(db.query.sql[0].endswith("READ ONLY"))
        self.assertTrue(all(sql.lstrip().upper().startswith(("SET TRANSACTION", "SET LOCAL", "SELECT", "ROLLBACK"))
                            for sql in db.query.sql))
        output = str(data).lower()
        for forbidden in ("description", "raw_payload", "password", "notes", "payload_json"):
            self.assertNotIn(forbidden, output)

    def test_compare_exact_and_deterministic(self):
        data = mb.inspect(Connection())
        self.assertEqual(mb.compare(data, copy.deepcopy(data)), [])
        changed = copy.deepcopy(data)
        changed["tables"]["opportunities"] = 0
        changed["opportunity_sample"][0]["content_hash"] = "c" * 64
        self.assertEqual(mb.compare(data, changed),
                         ["tables.opportunities: mismatch", "opportunity_sample: mismatch"])

    def test_missing_optional_table_is_explicit_and_mismatch_fails(self):
        data = mb.inspect(Connection())
        other = copy.deepcopy(data)
        other["tables"]["artifact_cache"] = 0
        self.assertEqual(mb.compare(data, other), ["tables.artifact_cache: mismatch"])

    def test_equal_snapshots_with_integrity_defect_do_not_pass(self):
        data = mb.inspect(Connection())
        data["invariants"]["duplicate_evaluations"] = 2
        self.assertEqual(mb.compare(data, copy.deepcopy(data)), [
            "baseline.invariants.duplicate_evaluations: nonzero",
            "candidate.invariants.duplicate_evaluations: nonzero",
        ])

    def test_unsupported_is_distinct_from_pass(self):
        data = mb.inspect(Connection())
        self.assertIn("tables.artifact_cache", mb.unsupported(data))
        self.assertIn("null_counts.artifact_cache.payload", mb.unsupported(data))

    def test_driver_error_is_redacted(self):
        class BadDriver:
            def connect(self, url):
                raise RuntimeError(url)

        with patch.dict("sys.modules", {"psycopg2": BadDriver()}), \
             patch.dict("os.environ", {"OPPORTUNITYOS_DB_URL": "postgresql://" + "secret:password" + "@host/db"}):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(mb.main(["snapshot"]), 2)
            self.assertNotIn("secret", stderr.getvalue())
        self.assertNotIn("password", stderr.getvalue())

    def test_full_identity_digest_and_unknown_sensitive_counts_are_compared(self):
        data = mb.inspect(Connection())
        self.assertEqual(len(data["identity_digests"]["opportunities"]), 64)
        self.assertEqual(data["decision_distributions"]["match_evaluations"], {"qualified": 1})
        self.assertIsNone(data["null_counts"]["artifact_cache.payload"])
        changed = copy.deepcopy(data)
        changed["identity_digests"]["evaluation_bindings"] = "0" * 64
        changed["null_counts"]["opportunities.content_hash"] = 2
        self.assertEqual(mb.compare(data, changed), [
            "identity_digests.evaluation_bindings: mismatch",
            "null_counts.opportunities.content_hash: mismatch",
        ])


if __name__ == "__main__":
    unittest.main()
