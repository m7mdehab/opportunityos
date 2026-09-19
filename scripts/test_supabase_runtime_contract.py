import unittest
from storage.supabase_runtime import (SupabaseRuntimeContract, assert_runtime_schema_capabilities,
    render_runtime_sql, runtime_sql_sha256)

class _Rows:
    def __init__(self, rows): self.rows = rows
    def __iter__(self): return iter(self.rows)
class _Connection:
    def __init__(self, rows): self.rows, self.statements = rows, []
    def execute(self, statement): self.statements.append(statement); return _Rows(self.rows)

class SupabaseRuntimeContractTests(unittest.TestCase):
    def test_render_is_deterministic_and_secret_free(self):
        first = render_runtime_sql()
        self.assertEqual(first, render_runtime_sql())
        self.assertEqual(runtime_sql_sha256(), runtime_sql_sha256())
        self.assertNotIn("postgresql://", first)
        self.assertNotIn("postgres://", first)
        self.assertNotIn("service_role", first)
        self.assertNotIn("password", first.lower())
        self.assertNotIn("raw_payload_json", first)
        self.assertIn("selected_cv_sha256", first)
        self.assertIn("s.read_allowed = true", first)
        self.assertIn("LIMIT 16", first)
    def test_browser_surface_and_queue_boundary_are_explicit(self):
        sql = render_runtime_sql()
        self.assertIn("WITH (security_invoker = true)", sql)
        self.assertIn("GRANT SELECT ON public.founder_feed TO authenticated", sql)
        self.assertIn("REVOKE ALL ON public.founder_feed FROM anon", sql)
        self.assertIn("public.opos_is_founder()", sql)
        self.assertIn("GRANT EXECUTE ON FUNCTION public.enqueue_poll_now(text) TO authenticated", sql)
        self.assertIn("REVOKE ALL ON FUNCTION public.enqueue_poll_now(text) FROM PUBLIC", sql)
        self.assertIn("poll_job_status", sql)
    def test_custom_identifiers_are_validated(self):
        with self.assertRaises(ValueError): render_runtime_sql(SupabaseRuntimeContract(feed_view="founder_feed;drop"))
    def test_capability_check_reads_only_and_passes(self):
        connection = _Connection([("feed_projection",), ("worker_jobs",), ("source_schedules",)])
        assert_runtime_schema_capabilities(connection)
        self.assertEqual(len(connection.statements), 1)
        self.assertIn("information_schema.tables", connection.statements[0])
    def test_capability_check_fails_closed_when_table_missing(self):
        with self.assertRaisesRegex(RuntimeError, "worker_jobs"):
            assert_runtime_schema_capabilities(_Connection([("feed_projection",)]))
if __name__ == "__main__": unittest.main()
