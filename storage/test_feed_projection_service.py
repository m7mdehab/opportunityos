from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.filters import FilterSettingsRow
from storage.feed_projection import FeedProjectionRecord
from storage.feed_projection_service import rebuild_feed_projection
from storage.feed_query import FeedQuerySpec, feed_page
from storage.models import Base, MatchEvaluationRecord, OpportunityRecord


class FeedProjectionMaterializationTest(unittest.TestCase):
    def setUp(self) -> None:
        handle, self.db_path = tempfile.mkstemp(prefix="opos-feed-", suffix=".db")
        os.close(handle)
        self.db_url = f"sqlite:///{self.db_path}"
        self.engine = create_engine(self.db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def _opportunity(self, opportunity_id: str, *, title: str = "Data Engineer") -> OpportunityRecord:
        return OpportunityRecord(
            id=opportunity_id,
            track="employment",
            title=title,
            organization="Example Co",
            description="Build durable data pipelines for a remote team.",
            source_id="fixture",
            source_url=f"https://example.invalid/{opportunity_id}",
            content_hash=(opportunity_id[-1] * 64)[:64],
            posted_date="2026-09-17",
            work_mode="remote",
            location_country="EG",
            location_city="Cairo",
            remote_scope="worldwide",
            employment_type="full_time",
            seniority_level="mid",
            title_family="data_engineering",
        )

    def _evaluation(
        self,
        opportunity_id: str,
        *,
        truth_hash: str = "truth-a",
        fit: float = 82.0,
        decision: str = "qualified",
    ) -> MatchEvaluationRecord:
        now = datetime(2026, 9, 17, tzinfo=timezone.utc)
        return MatchEvaluationRecord(
            id=f"eval-{opportunity_id}-{truth_hash}",
            opportunity_id=opportunity_id,
            truth_pack_hash=truth_hash,
            qualification_decision=decision,
            fit_score=fit,
            dimension_scores_json="[]",
            reasons_json='[{"reason":"fixture"}]',
            evaluation_detail_json=None,
            policy_version="test-v1",
            evaluated_at=now,
        )

    def test_rebuild_is_truth_scoped_and_idempotent(self) -> None:
        session = self.Session()
        try:
            session.add_all([self._opportunity("opp-1"), self._opportunity("opp-2")])
            session.flush()
            session.add(self._evaluation("opp-1", truth_hash="truth-a", fit=91.0))
            session.add(self._evaluation("opp-2", truth_hash="truth-b", fit=99.0))
            session.commit()

            first = rebuild_feed_projection(
                session,
                truth_graph=None,
                truth_pack_hash="truth-a",
                batch_size=1,
            )
            session.commit()
            self.assertEqual(first.inserted, 1)
            self.assertEqual(first.updated, 0)
            self.assertEqual(session.query(FeedProjectionRecord).count(), 1)

            second = rebuild_feed_projection(
                session,
                truth_graph=None,
                truth_pack_hash="truth-a",
                batch_size=1,
            )
            session.commit()
            self.assertEqual(second.inserted, 0)
            self.assertEqual(second.updated, 1)
            self.assertEqual(session.query(FeedProjectionRecord).count(), 1)
        finally:
            session.close()

    def test_visibility_and_rank_penalty_are_materialized_without_changing_fit(self) -> None:
        session = self.Session()
        try:
            session.add(self._opportunity("opp-1"))
            session.flush()
            session.add(self._evaluation("opp-1", fit=72.0))
            session.commit()

            hide_settings = {
                "min_fit_score": FilterSettingsRow(
                    enabled=True,
                    mode="hide",
                    params={"min_score": 80.0},
                )
            }
            rebuild_feed_projection(
                session,
                truth_graph=None,
                truth_pack_hash="truth-a",
                filter_settings=hide_settings,
                facet_settings={},
            )
            session.commit()
            row = session.query(FeedProjectionRecord).one()
            self.assertFalse(row.visible)
            self.assertIn("min_fit_score", row.visibility_reason or "")
            self.assertEqual(row.fit_score, 72.0)

            rank_settings = {
                "min_fit_score": FilterSettingsRow(
                    enabled=True,
                    mode="rank_only",
                    params={"min_score": 80.0},
                )
            }
            rebuild_feed_projection(
                session,
                truth_graph=None,
                truth_pack_hash="truth-a",
                filter_settings=rank_settings,
                facet_settings={},
            )
            session.commit()
            row = session.query(FeedProjectionRecord).one()
            self.assertTrue(row.visible)
            self.assertEqual(row.fit_score, 72.0)
            self.assertEqual(row.priority_score, -928.0)
        finally:
            session.close()

    def test_changed_evaluation_updates_existing_projection(self) -> None:
        session = self.Session()
        try:
            session.add(self._opportunity("opp-1"))
            session.flush()
            evaluation = self._evaluation("opp-1", fit=70.0)
            session.add(evaluation)
            session.commit()
            rebuild_feed_projection(session, truth_graph=None, truth_pack_hash="truth-a")
            session.commit()

            evaluation.fit_score = 95.0
            evaluation.reasons_json = '[{"reason":"updated"}]'
            session.commit()
            rebuild_feed_projection(session, truth_graph=None, truth_pack_hash="truth-a")
            session.commit()

            row = session.query(FeedProjectionRecord).one()
            self.assertEqual(row.fit_score, 95.0)
            self.assertEqual(row.priority_score, 95.0)
            self.assertIn("updated", row.reasons_json)
        finally:
            session.close()

    def test_cold_engine_reads_persisted_feed_without_source_hydration(self) -> None:
        session = self.Session()
        try:
            session.add(self._opportunity("opp-1"))
            session.flush()
            session.add(self._evaluation("opp-1", fit=88.0))
            session.commit()
            rebuild_feed_projection(session, truth_graph=None, truth_pack_hash="truth-a")
            session.commit()
        finally:
            session.close()
            self.engine.dispose()

        cold_engine = create_engine(self.db_url)
        ColdSession = sessionmaker(bind=cold_engine)
        cold = ColdSession()
        try:
            page = feed_page(cold, FeedQuerySpec(truth_pack_hash="truth-a"))
            self.assertEqual(page.total, 1)
            self.assertEqual(page.rows[0].opportunity_id, "opp-1")
            self.assertEqual(page.rows[0].fit_score, 88.0)
        finally:
            cold.close()
            cold_engine.dispose()

    def test_restart_cursor_can_resume_after_completed_batch(self) -> None:
        session = self.Session()
        try:
            session.add_all([self._opportunity("opp-1"), self._opportunity("opp-2")])
            session.flush()
            session.add_all([self._evaluation("opp-1"), self._evaluation("opp-2")])
            session.commit()

            first = rebuild_feed_projection(
                session,
                truth_graph=None,
                truth_pack_hash="truth-a",
                batch_size=1,
                start_after="opp-1",
            )
            session.commit()
            self.assertEqual(first.projected, 1)
            self.assertEqual(first.last_opportunity_id, "opp-2")
            self.assertEqual(
                [row.opportunity_id for row in session.query(FeedProjectionRecord).all()],
                ["opp-2"],
            )
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
