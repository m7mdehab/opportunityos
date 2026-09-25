from __future__ import annotations

import os
import json
import tempfile
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.filters import FilterSettingsRow
from storage.feed_projection import FeedProjectionRecord
from storage.feed_projection_service import (
    rebuild_feed_projection,
    refresh_existing_feed_projections,
    refresh_opportunity_projection,
)
from storage.feed_query import FeedQuerySpec, feed_page
from storage.ranking import recommended_priority_score
from storage.models import Base, FounderFilterSettingRecord, MatchEvaluationRecord, OpportunityRecord


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

    def _opportunity(
        self,
        opportunity_id: str,
        *,
        title: str = "Data Engineer",
        posted_date: str = "2026-09-17",
        is_stale: bool = False,
    ) -> OpportunityRecord:
        return OpportunityRecord(
            id=opportunity_id,
            track="employment",
            title=title,
            organization="Example Co",
            description="Build durable data pipelines for a remote team.",
            source_id="fixture",
            source_url=f"https://example.invalid/{opportunity_id}",
            content_hash=(opportunity_id[-1] * 64)[:64],
            posted_date=posted_date,
            is_stale=is_stale,
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
        detail: dict | None = None,
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
            evaluation_detail_json=json.dumps(detail) if detail is not None else None,
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
            self.assertLess(row.priority_score, 0.0)
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
            initial_priority = session.query(FeedProjectionRecord).one().priority_score

            evaluation.fit_score = 95.0
            evaluation.reasons_json = '[{"reason":"updated"}]'
            session.commit()
            rebuild_feed_projection(session, truth_graph=None, truth_pack_hash="truth-a")
            session.commit()

            row = session.query(FeedProjectionRecord).one()
            self.assertEqual(row.fit_score, 95.0)
            self.assertGreater(row.priority_score, initial_priority)
            self.assertIn("updated", row.reasons_json)
        finally:
            session.close()

    def test_recommended_priority_uses_existing_evaluation_detail_and_posting_freshness(self) -> None:
        session = self.Session()
        try:
            opportunity = self._opportunity("opp-ranked", posted_date="2026-09-24")
            evaluation = self._evaluation(
                "opp-ranked",
                fit=82.25,
                decision="uncertain",
                detail={
                    "preference_score": 77.5,
                    "confidence_score": 84.25,
                    "confidence_factors": [
                        {"name": "source_freshness_and_strength", "score": 68.0},
                    ],
                },
            )
            session.add(opportunity)
            session.flush()
            session.add(evaluation)
            session.commit()

            projected_at = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
            record = refresh_opportunity_projection(
                session,
                opportunity_id="opp-ranked",
                truth_pack_hash="truth-a",
                projected_at=projected_at,
            )
            session.commit()

            expected = recommended_priority_score(
                decision="uncertain",
                fit_score=82.25,
                preference_score=77.5,
                confidence_score=84.25,
                freshness_score=100.0,
                source_confidence=68.0,
                rank_penalty=0,
            )
            self.assertEqual(record.fit_score, 82.25)
            self.assertEqual(record.priority_score, expected)
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

    def test_refresh_opportunity_projection_updates_single_opportunity(self) -> None:
        from storage.feed_projection_service import refresh_opportunity_projection

        session = self.Session()
        try:
            session.add(self._opportunity("opp-refresh"))
            session.flush()
            eval_record = self._evaluation("opp-refresh", fit=77.0)
            session.add(eval_record)
            session.commit()

            # Refresh creates the projection
            rec = refresh_opportunity_projection(
                session,
                opportunity_id="opp-refresh",
                truth_pack_hash="truth-a",
            )
            session.commit()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.opportunity_id, "opp-refresh")
            self.assertEqual(rec.fit_score, 77.0)

            # Update evaluation and refresh incrementally
            eval_record.fit_score = 93.0
            session.commit()
            updated_rec = refresh_opportunity_projection(
                session,
                opportunity_id="opp-refresh",
                truth_pack_hash="truth-a",
            )
            session.commit()
            self.assertEqual(updated_rec.fit_score, 93.0)
            self.assertEqual(session.query(FeedProjectionRecord).count(), 1)
        finally:
            session.close()

    def test_settings_refresh_preserves_other_truth_hashes_and_synthetic_projection(self) -> None:
        session = self.Session()
        try:
            session.add(self._opportunity("opp-scoped"))
            session.flush()
            session.add_all([
                self._evaluation("opp-scoped", truth_hash="truth-a", fit=82.0),
                self._evaluation("opp-scoped", truth_hash="truth-b", fit=82.0),
            ])
            session.commit()
            for truth_hash in ("truth-a", "truth-b", "active"):
                refresh_opportunity_projection(
                    session, opportunity_id="opp-scoped", truth_pack_hash=truth_hash,
                    allow_unevaluated=True,
                )
            session.commit()

            def stored_row(truth_hash):
                row = session.query(FeedProjectionRecord).filter_by(
                    opportunity_id="opp-scoped", truth_pack_hash=truth_hash
                ).one()
                return {column.name: getattr(row, column.name)
                        for column in FeedProjectionRecord.__table__.columns}

            before_b = stored_row("truth-b")
            before_active = stored_row("active")
            session.add(FounderFilterSettingRecord(
                filter_id="min_fit_score", enabled=True, mode="hide",
                params_json='{"min_score": 90}',
                updated_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
            ))
            session.commit()

            refreshed = refresh_existing_feed_projections(
                session, truth_graph=None, truth_pack_hash="truth-a", batch_size=1
            )
            session.commit()
            self.assertEqual(refreshed, 1)
            self.assertFalse(stored_row("truth-a")["visible"])
            self.assertEqual(stored_row("truth-b"), before_b)
            self.assertEqual(stored_row("active"), before_active)
            with self.assertRaises(ValueError):
                refresh_existing_feed_projections(
                    session, truth_graph=None, truth_pack_hash="active"
                )
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
