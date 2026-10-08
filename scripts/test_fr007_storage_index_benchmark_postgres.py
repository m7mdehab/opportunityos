"""Disposable-Postgres benchmark for *exact* checksum index compression.

The test never connects to hosted Supabase. It uses only synthetic temporary
records in a database explicitly named opportunityos_test.
"""
from __future__ import annotations

import os
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from scripts.fr007_storage_reclamation import audit


@unittest.skipUnless(
    os.environ.get("OPPORTUNITYOS_DB_URL", "").startswith("postgresql"),
    "requires disposable PostgreSQL service",
)
class CompactProvenanceIndexBenchmark(unittest.TestCase):
    def test_production_audit_queries_run_on_disposable_postgres(self):
        engine = create_engine(os.environ["OPPORTUNITYOS_DB_URL"], pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT current_database()")).scalar_one(), "opportunityos_test")
                report = audit(connection)
                self.assertGreater(report["database_bytes"], 0)
                self.assertIn("compression_baseline", report)
                self.assertEqual(len(report["index_targets"]), 4)
                self.assertTrue(all("bytes" in target for target in report["index_targets"]))
                self.assertNotIn("description", str(report["index_targets"]))
        finally:
            engine.dispose()

    def test_canonical_hex_decoding_preserves_uniqueness_and_saves_space(self):
        engine = create_engine(os.environ["OPPORTUNITYOS_DB_URL"], pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                db = connection.execute(text("SELECT current_database()")).scalar_one()
                if db != "opportunityos_test":
                    self.fail("refusing index benchmark outside disposable opportunityos_test")
                with connection.begin_nested():
                    # ON COMMIT DROP ensures no persistent test data survives.
                    connection.exec_driver_sql("""
                        CREATE TEMP TABLE fp_compact_benchmark (
                            opportunity_id varchar(64) NOT NULL,
                            field_name varchar(64) NOT NULL,
                            record_checksum varchar(64) NOT NULL
                        ) ON COMMIT DROP
                    """)
                    connection.exec_driver_sql("""
                        INSERT INTO fp_compact_benchmark
                        SELECT 'source:' || md5((n / 12)::text),
                               'field_' || (n % 12),
                               md5((n / 12)::text) || md5('checksum-' || (n / 12)::text)
                        FROM generate_series(1, 30000) AS n
                    """)
                    connection.exec_driver_sql("""
                        CREATE UNIQUE INDEX fp_benchmark_text_key
                        ON fp_compact_benchmark
                        (opportunity_id, field_name, record_checksum)
                    """)
                    connection.exec_driver_sql("""
                        CREATE UNIQUE INDEX fp_benchmark_binary_key
                        ON fp_compact_benchmark
                        (opportunity_id, field_name, decode(record_checksum, 'hex'))
                    """)
                    text_size = int(connection.execute(text(
                        "SELECT pg_relation_size('pg_temp.fp_benchmark_text_key'::regclass)"
                    )).scalar_one())
                    binary_size = int(connection.execute(text(
                        "SELECT pg_relation_size('pg_temp.fp_benchmark_binary_key'::regclass)"
                    )).scalar_one())
                    self.assertGreater(text_size, binary_size)
                    self.assertGreater(binary_size, 0)
                    self.assertEqual(
                        connection.execute(text(
                            "SELECT count(*) FROM fp_compact_benchmark"
                        )).scalar_one(), 30000,
                    )
                    # Two keys differing only by the checksum must remain
                    # distinct; decoding lowercase canonical hex is bijective.
                    variants = connection.execute(text("""
                        SELECT count(DISTINCT decode(record_checksum, 'hex'))
                        FROM fp_compact_benchmark
                    """)).scalar_one()
                    self.assertGreater(variants, 2000)
                    with self.assertRaises(IntegrityError):
                        with connection.begin_nested():
                            connection.exec_driver_sql("""
                                INSERT INTO fp_compact_benchmark
                                SELECT opportunity_id, field_name, record_checksum
                                FROM fp_compact_benchmark LIMIT 1
                            """)
                connection.rollback()
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
