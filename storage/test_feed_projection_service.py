from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.filters import FilterSettingsRow
from storage.feed_projection import FeedProjectionRecord
from storage.feed_projection_service import (
    rebuild_feed_projection,
    refresh_feed_projection_candidates,
    refresh_existing_feed_projections,
    refresh_opportunity_projection,
)
from storage.feed_query import FeedQuerySpec, feed_page
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
            content_hash=(opportunity_id[-1] * 64)[:64],
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

    def test_targeted_refresh_reclassifies_roles_and_allows_uncertain_low_evidence_discovery(self) -> None:
        session = self.Session()
        try:
            target = self._opportunity("opp-targeted", title="Senior Data Engineer")
            target.lifecycle_tier = "hot"
            target.role_relevance_class = "unknown"
            target.founder_geo_state = "likely_eligible"
            target.application_access = "direct_free"
            target.application_url = "https://boards.greenhouse.io/example/jobs/123"
            session.add(target)
            session.flush()
            evaluation = self._evaluation(
                "opp-targeted", decision="uncertain", fit=42.0,
            )
            evaluation.evaluation_detail_json = (
                '{"confidence_score":72,"confidence_factors":'
                '[{"name":"founder_evidence_completeness","score":50}]}'
            )
            session.add(evaluation)
            session.commit()

            rebuild_feed_projection(session, truth_graph=None, truth_pack_hash="truth-a")
            session.commit()
            before = session.query(FeedProjectionRecord).one()
            self.assertEqual(before.recommendation_state, "review")

            stats = refresh_feed_projection_candidates(
                session, ["opp-targeted"], truth_graph=None, truth_pack_hash="truth-a",
            )
            session.commit()

            self.assertEqual(stats.updated, 1)
            row = session.query(FeedProjectionRecord).one()
            opportunity = session.query(OpportunityRecord).one()
            self.assertEqual(opportunity.role_relevance_class, "core")
            self.assertEqual(row.recommendation_state, "for_you")
            self.assertIn("check_eligibility", row.recommendation_reasons_json)
            self.assertIn("founder_evidence_limited", row.recommendation_reasons_json)
        finally:
            session.close()

    def test_targeted_refresh_excludes_us_onsite_even_when_description_has_global_boilerplate(self) -> None:
        session = self.Session()
        try:
            target = self._opportunity("opp-us-onsite")
            target.lifecycle_tier = "hot"
            target.founder_geo_state = "likely_eligible"
            target.application_access = "direct_free"
            target.application_url = "https://boards.greenhouse.io/example/jobs/124"
            target.location_country = "US"
            target.location_city = None
            target.location_region = "Arlington, VA"
            target.work_mode = "onsite"
            target.remote_scope = "unspecified"
            target.description = "We are a global company with teams worldwide. This job is onsite in Arlington."
            session.add(target)
            session.flush()
            session.add(self._evaluation("opp-us-onsite", decision="uncertain"))
            session.commit()

            rebuild_feed_projection(session, truth_graph=None, truth_pack_hash="truth-a")
            session.commit()
            refresh_feed_projection_candidates(
                session, ["opp-us-onsite"], truth_graph=None, truth_pack_hash="truth-a",
            )
            session.commit()

            row = session.query(FeedProjectionRecord).one()
            self.assertEqual(row.founder_geo_state, "ineligible")
            self.assertEqual(row.recommendation_state, "excluded")
            self.assertIn("onsite/hybrid workplace", row.founder_geo_reason)
        finally:
            session.close()

    def test_targeted_refresh_reviews_unverified_required_clearance(self) -> None:
        session = self.Session()
        try:
            target = self._opportunity("opp-clearance")
            target.lifecycle_tier = "hot"
            target.application_access = "direct_free"
            target.application_url = "https://boards.greenhouse.io/example/jobs/125"
            target.description = (
                "Remote from Egypt. Required qualifications: Active Secret security clearance required."
            )
            session.add(target)
            session.flush()
            session.add(self._evaluation("opp-clearance", decision="uncertain"))
            session.commit()

            rebuild_feed_projection(session, truth_graph=None, truth_pack_hash="truth-a")
            session.commit()
            refresh_feed_projection_candidates(
                session, ["opp-clearance"], truth_graph=None, truth_pack_hash="truth-a",
            )
            session.commit()

            row = session.query(FeedProjectionRecord).one()
            self.assertEqual(row.founder_geo_state, "eligible")
            self.assertEqual(row.recommendation_state, "review")
            self.assertIn("required_clearance_unverified", row.recommendation_reasons_json)
        finally:
            session.close()

    def test_targeted_refresh_rejects_more_than_the_safe_candidate_limit(self) -> None:
        session = self.Session()
        try:
            with self.assertRaisesRegex(ValueError, "limited to 100"):
                refresh_feed_projection_candidates(
                    session,
                    [f"opp-{index}" for index in range(101)],
                    truth_graph=None,
                    truth_pack_hash="truth-a",
                )
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

    def test_bounded_refresh_recovers_verified_public_greenhouse_application_route(self) -> None:
        session = self.Session()
        try:
            opportunity = self._opportunity("opp-legacy-greenhouse", title="Lead Data Engineer")
            opportunity.source_id = "greenhouse:canonical"
            opportunity.source_url = "https://job-boards.greenhouse.io/canonical/jobs/123"
            opportunity.application_url = None
            opportunity.application_route = "unknown"
            opportunity.application_access = "unknown"
            opportunity.location_country = None
            opportunity.location_city = None
            opportunity.location_region = "EMEA Remote"
            opportunity.description = (
                "Lead Data Engineer. Location: this role is remote in the EMEA region. "
                "Build durable data pipelines with Python and SQL."
            )
            opportunity.work_mode = "remote"
            opportunity.remote_scope = "unspecified"
            opportunity.lifecycle_tier = "hot"
            session.add(opportunity)
            session.flush()
            session.add(self._evaluation("opp-legacy-greenhouse", decision="uncertain", fit=71.0))
            session.commit()

            projected = refresh_opportunity_projection(
                session,
                opportunity_id="opp-legacy-greenhouse",
                truth_pack_hash="truth-a",
            )
            session.commit()

            refreshed = session.query(OpportunityRecord).filter_by(
                id="opp-legacy-greenhouse"
            ).one()
            self.assertEqual(refreshed.application_url, opportunity.source_url)
            self.assertEqual(refreshed.application_route, "ats")
            self.assertEqual(refreshed.application_access, "direct_free")
            self.assertIsNotNone(projected)
            self.assertEqual(projected.application_access, "direct_free")
            self.assertEqual(
                projected.recommendation_state,
                "for_you",
                projected.recommendation_reasons_json,
            )
        finally:
            session.close()

    def test_settings_refresh_updates_only_one_authoritative_projection(self) -> None:
        session = self.Session()
        try:
            session.add(self._opportunity("opp-scoped"))
            session.flush()
            session.add(self._evaluation("opp-scoped", truth_hash="truth-a", fit=82.0))
            session.commit()
            refresh_opportunity_projection(
                session, opportunity_id="opp-scoped", truth_pack_hash="truth-a",
                allow_unevaluated=True,
            )
            session.commit()

            self.assertEqual(session.query(FeedProjectionRecord).count(), 1)
            with self.assertRaises(ValueError):
                refresh_opportunity_projection(
                    session, opportunity_id="opp-scoped", truth_pack_hash="active",
                    allow_unevaluated=True,
                )
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
            row = session.query(FeedProjectionRecord).filter_by(
                opportunity_id="opp-scoped"
            ).one()
            self.assertEqual(row.truth_pack_hash, "truth-a")
            self.assertFalse(row.visible)
            self.assertEqual(session.query(FeedProjectionRecord).count(), 1)
            with self.assertRaises(ValueError):
                refresh_existing_feed_projections(
                    session, truth_graph=None, truth_pack_hash="active"
                )
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()

