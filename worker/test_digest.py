"""Unit tests for worker.digest.generate_digest / latest_digest (E4F3.6).

``test_digest_generation_makes_zero_network_requests`` is the assertion this
work order's acceptance row requires: it monkeypatches ``socket.socket.connect``
to raise if called at all during ``generate_digest`` -- catching any network
attempt regardless of which HTTP client made it -- and asserts it is never
called.
"""
import os
import socket
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from storage.engine import get_engine, get_session_factory, init_db
from storage.models import MatchEvaluationRecord, OpportunityRecord
from worker.digest import generate_digest, latest_digest


class TestGenerateDigest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "test_digest.db")
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)
        self.session = self.session_factory()
        self.out_dir = Path(self.temp_dir.name) / "out" / "digest"
        self.now = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _seed(self, opp_id, *, fit_score, created_at, decision="qualified"):
        self.session.add(
            OpportunityRecord(
                id=opp_id,
                track="employment",
                title=f"Title {opp_id}",
                organization=f"Org {opp_id}",
                description="Fixture description.",
                source_id="himalayas",
                source_url=f"https://himalayas.app/jobs/{opp_id}",
                content_hash=f"hash-{opp_id}",
                created_at=created_at.replace(tzinfo=None) if created_at.tzinfo else created_at,
            )
        )
        if fit_score is not None:
            self.session.add(
                MatchEvaluationRecord(
                    id=f"eval-{opp_id}",
                    opportunity_id=opp_id,
                    truth_pack_hash="hash-fixture",
                    content_hash=f"hash-{opp_id}",
                    qualification_decision=decision,
                    fit_score=fit_score,
                    dimension_scores_json="[]",
                    reasons_json="[]",
                    policy_version="fixture-policy-v1",
                    evaluated_at=created_at.replace(tzinfo=None) if created_at.tzinfo else created_at,
                )
            )
        self.session.commit()

    def test_digest_includes_new_high_fit_items_and_writes_md_and_html(self):
        self._seed("opp-high-fit", fit_score=85.0, created_at=self.now - timedelta(hours=2))
        self._seed("opp-low-fit", fit_score=40.0, created_at=self.now - timedelta(hours=2))
        self._seed("opp-old", fit_score=90.0, created_at=self.now - timedelta(days=5))
        self._seed("opp-unscored", fit_score=None, created_at=self.now - timedelta(hours=1))

        summary = generate_digest(
            self.session, out_dir=self.out_dir, now=self.now, high_fit_threshold=70.0
        )

        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["date"], "2026-09-03")
        md_path = Path(summary["markdown_path"])
        html_path = Path(summary["html_path"])
        self.assertTrue(md_path.exists())
        self.assertTrue(html_path.exists())
        self.assertIn("opp-high-fit".split("-")[0], md_path.read_text(encoding="utf-8")) or True
        md_text = md_path.read_text(encoding="utf-8")
        html_text = html_path.read_text(encoding="utf-8")
        self.assertIn("Title opp-high-fit", md_text)
        self.assertNotIn("Title opp-low-fit", md_text)
        self.assertNotIn("Title opp-old", md_text)
        self.assertNotIn("Title opp-unscored", md_text)
        self.assertIn("Title opp-high-fit", html_text)
        self.assertTrue(html_text.startswith("<!DOCTYPE html>"))

    def test_latest_digest_reads_back_the_most_recently_written_file(self):
        generate_digest(self.session, out_dir=self.out_dir, now=self.now)
        result = latest_digest(out_dir=self.out_dir)
        self.assertIsNotNone(result)
        self.assertEqual(result["date"], "2026-09-03")
        self.assertIn("OpportunityOS Daily Digest", result["markdown"])
        self.assertIn("OpportunityOS Daily Digest", result["html"])

    def test_latest_digest_returns_none_when_none_written_yet(self):
        self.assertIsNone(latest_digest(out_dir=self.out_dir))

    def test_digest_generation_makes_zero_network_requests(self):
        self._seed("opp-high-fit", fit_score=85.0, created_at=self.now - timedelta(hours=2))

        def _forbidden_connect(self, *args, **kwargs):
            raise AssertionError("worker.digest.generate_digest must make zero network requests")

        with mock.patch.object(socket.socket, "connect", _forbidden_connect):
            summary = generate_digest(self.session, out_dir=self.out_dir, now=self.now)

        self.assertEqual(summary["count"], 1)


if __name__ == "__main__":
    unittest.main()
