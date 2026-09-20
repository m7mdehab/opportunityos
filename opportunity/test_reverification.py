"""Unit tests for StaleOpportunityReverifier.reverify_stale_opportunities.

E4F3.4: this is the first writer ``stale_postings`` has ever had. Every test
here is fully offline: ``reverify_fn`` is always injected, and the shared
``RateLimiter``/``SourceRegistry`` are also injected, so no real network
call or ``docs/SOURCE_REGISTRY.yaml`` read happens.
"""
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from opportunity.registry import SourceRegistry
from opportunity.reverification import StaleOpportunityReverifier
from opportunity.transport import RateLimiter
from storage.engine import get_engine, get_session_factory, init_db
from storage.models import OpportunityRecord

_FIXTURE_REGISTRY_YAML = """
sources:
  - source_id: fixture_allowed
    name: "Fixture Allowed"
    category: employment
    automation:
      read: allowed
    policy_status: reviewed_ok
    observed:
      status: allowed_ok
  - source_id: fixture_disabled
    name: "Fixture Disabled"
    category: employment
    automation:
      read: disabled
    policy_status: manual_only
    observed:
      status: unknown
"""


class TestReverifyStaleOpportunities(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        registry_path = Path(self.temp_dir.name) / "fixture_registry.yaml"
        registry_path.write_text(_FIXTURE_REGISTRY_YAML, encoding="utf-8")
        self.registry = SourceRegistry(registry_path=registry_path)

        db_path = Path(self.temp_dir.name) / "test_reverify.db"
        self.engine = get_engine(f"sqlite:///{db_path}", allow_sqlite=True)
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)
        self.session = self.session_factory()

        self.now = datetime(2026, 9, 3, tzinfo=timezone.utc)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _seed(self, opp_id, *, source_id, age_days, source_url="https://example.test/job"):
        record = OpportunityRecord(
            id=opp_id,
            track="employment",
            title="Fixture Title",
            organization="Fixture Org",
            description="Fixture description.",
            source_id=source_id,
            source_url=source_url,
            content_hash=f"hash-{opp_id}",
            is_stale=False,
            created_at=(self.now - timedelta(days=age_days)).replace(tzinfo=None),
        )
        self.session.add(record)
        self.session.commit()
        return record

    def test_gone_posting_older_than_14_days_is_marked_stale(self):
        self._seed("opp-gone", source_id="fixture_allowed", age_days=20)

        def fake_reverify(url):
            return {"is_stale": True, "status_code": 404, "reason": "HTTP 404"}

        result = StaleOpportunityReverifier.reverify_stale_opportunities(
            self.session,
            registry=self.registry,
            rate_limiter=RateLimiter(default_min_interval_s=0),
            now=self.now,
            reverify_fn=fake_reverify,
        )

        row = self.session.query(OpportunityRecord).filter_by(id="opp-gone").one()
        self.assertTrue(row.is_stale)
        self.assertIsNotNone(row.reverified_at)
        self.assertEqual(result["marked_stale"], 1)
        self.assertEqual(result["checked"], 1)

    def test_still_present_posting_is_not_marked_stale(self):
        self._seed("opp-present", source_id="fixture_allowed", age_days=20)

        def fake_reverify(url):
            return {"is_stale": False, "status_code": 200, "reason": "URL is active and reachable"}

        result = StaleOpportunityReverifier.reverify_stale_opportunities(
            self.session,
            registry=self.registry,
            rate_limiter=RateLimiter(default_min_interval_s=0),
            now=self.now,
            reverify_fn=fake_reverify,
        )

        row = self.session.query(OpportunityRecord).filter_by(id="opp-present").one()
        self.assertFalse(row.is_stale)
        self.assertIsNotNone(row.reverified_at)
        self.assertEqual(result["marked_stale"], 0)
        self.assertEqual(result["checked"], 1)

    def test_posting_younger_than_14_days_is_not_a_candidate(self):
        self._seed("opp-fresh", source_id="fixture_allowed", age_days=3)
        calls = []

        def fake_reverify(url):
            calls.append(url)
            return {"is_stale": True, "status_code": 404, "reason": "HTTP 404"}

        result = StaleOpportunityReverifier.reverify_stale_opportunities(
            self.session,
            registry=self.registry,
            rate_limiter=RateLimiter(default_min_interval_s=0),
            now=self.now,
            reverify_fn=fake_reverify,
        )

        self.assertEqual(calls, [])
        row = self.session.query(OpportunityRecord).filter_by(id="opp-fresh").one()
        self.assertFalse(row.is_stale)
        self.assertIsNone(row.reverified_at)
        self.assertEqual(result["candidates"], 0)

    def test_read_forbidden_source_is_never_reverified(self):
        self._seed("opp-forbidden", source_id="fixture_disabled", age_days=30)
        calls = []

        def fake_reverify(url):
            calls.append(url)
            return {"is_stale": True, "status_code": 404, "reason": "HTTP 404"}

        result = StaleOpportunityReverifier.reverify_stale_opportunities(
            self.session,
            registry=self.registry,
            rate_limiter=RateLimiter(default_min_interval_s=0),
            now=self.now,
            reverify_fn=fake_reverify,
        )

        self.assertEqual(calls, [], "a read-forbidden source must never be re-verified (no request at all)")
        row = self.session.query(OpportunityRecord).filter_by(id="opp-forbidden").one()
        self.assertFalse(row.is_stale)
        self.assertIsNone(row.reverified_at, "left alone: untouched, not just 'not stale'")
        self.assertEqual(result["skipped_policy"], 1)
        self.assertEqual(result["checked"], 0)

    def test_rate_limiter_is_consulted_per_candidate(self):
        self._seed("opp-a", source_id="fixture_allowed", age_days=20)
        self._seed("opp-b", source_id="fixture_allowed", age_days=25)

        acquired = []
        limiter = RateLimiter(default_min_interval_s=0)
        original_acquire = limiter.acquire

        def spy_acquire(source_id, min_interval_s=None):
            acquired.append(source_id)
            return original_acquire(source_id, min_interval_s)

        limiter.acquire = spy_acquire

        StaleOpportunityReverifier.reverify_stale_opportunities(
            self.session,
            registry=self.registry,
            rate_limiter=limiter,
            now=self.now,
            reverify_fn=lambda url: {"is_stale": False, "status_code": 200, "reason": "ok"},
        )

        self.assertEqual(acquired, ["fixture_allowed", "fixture_allowed"])


class TestGreenhouseTombstone(unittest.TestCase):
    class _Response:
        def __init__(self, body: bytes, status: int = 200):
            self.body = body
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getcode(self):
            return self.status

        def read(self, _limit=-1):
            return self.body

    def _result(self, body: str, url: str = "https://boards.greenhouse.io/acme/jobs/1"):
        with patch(
            "opportunity.reverification.urllib.request.urlopen",
            return_value=self._Response(body.encode("utf-8")),
        ):
            return StaleOpportunityReverifier.reverify_url(url)

    def test_exact_greenhouse_marker_marks_stale(self):
        result = self._result(
            "<html>Page not found. The job board you were viewing is no longer active.</html>"
        )
        self.assertTrue(result["is_stale"])

    def test_normalized_marker_marks_stale(self):
        result = self._result("PAGE NOT FOUND.  The job board you were viewing is no longer active.")
        self.assertTrue(result["is_stale"])

    def test_near_miss_and_non_greenhouse_are_not_stale(self):
        self.assertFalse(self._result("Page not found. This job is no longer active.")["is_stale"])
        self.assertFalse(
            self._result(
                "Page not found. The job board you were viewing is no longer active.",
                "https://jobs.example.test/jobs/1",
            )["is_stale"]
        )

    def test_ambiguous_200_is_not_stale(self):
        self.assertFalse(self._result("temporary error page")["is_stale"])


if __name__ == "__main__":
    unittest.main()
