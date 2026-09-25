"""FR-007 Owner Lane regression proof for persisted-feed cutover.

Proves:
1. Cold process memory gives identical logical feed output.
2. page_size=25 hydrates a bounded page, not all rows.
3. Decision/min-score/track predicates remain SQL-side.
4. Repeated feed requests do no opportunity evaluation.
5. Persisted hidden/visible state is authoritative for the feed.
6. PostgreSQL search remains SQL/GIN-oriented.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from api.filters import FilterSettingsRow
from matching.scorer import OpportunityScorer
from storage.feed_projection import FeedProjectionRecord, projection_identity
from storage.feed_projection_service import rebuild_feed_projection
from storage.feed_query import FeedQuerySpec, build_feed_query, feed_page
from storage.models import Base, MatchEvaluationRecord, OpportunityRecord


class FeedRegressionContractTest(unittest.TestCase):
    def setUp(self) -> None:
        handle, self.db_path = tempfile.mkstemp(prefix="opos-regression-", suffix=".db")
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

    def _seed_opportunity(
        self,
        opp_id: str,
        *,
        track: str = "employment",
        title: str = "Data Engineer",
        posted_date: str = "2026-09-17",
    ) -> OpportunityRecord:
        return OpportunityRecord(
            id=opp_id,
            track=track,
            title=title,
            organization="Example Corp",
            description=f"Description for {opp_id}",
            source_id="himalayas",
            source_url=f"https://himalayas.app/jobs/{opp_id}",
            content_hash=(opp_id[-1] * 64)[:64],
            posted_date=posted_date,
            work_mode="remote",
            location_country="EG",
            location_city="Cairo",
            remote_scope="worldwide",
            employment_type="full_time",
            seniority_level="mid",
            title_family="data_engineering",
        )

    def _seed_evaluation(
        self,
        opp_id: str,
        *,
        truth_hash: str = "truth-test",
        decision: str = "qualified",
        fit_score: float = 85.0,
    ) -> MatchEvaluationRecord:
        now = datetime(2026, 9, 17, tzinfo=timezone.utc)
        return MatchEvaluationRecord(
            id=f"eval-{opp_id}-{truth_hash}",
            opportunity_id=opp_id,
            truth_pack_hash=truth_hash,
            qualification_decision=decision,
            fit_score=fit_score,
            dimension_scores_json="[]",
            reasons_json='[{"reason":"fit"}]',
            evaluation_detail_json=None,
            policy_version="v1",
            evaluated_at=now,
        )

    def test_cold_process_memory_gives_identical_logical_feed_output(self) -> None:
        session = self.Session()
        try:
            for idx in range(1, 6):
                opp = self._seed_opportunity(f"opp-{idx}", posted_date=f"2026-09-1{idx}")
                eval_rec = self._seed_evaluation(f"opp-{idx}", fit_score=70.0 + idx)
                session.add_all([opp, eval_rec])
            session.commit()
            rebuild_feed_projection(session, truth_graph=None, truth_pack_hash="truth-test")
            session.commit()

            warm_page = feed_page(session, FeedQuerySpec(truth_pack_hash="truth-test", page=1, page_size=10))
            warm_ids = [row.opportunity_id for row in warm_page.rows]
            warm_scores = [row.fit_score for row in warm_page.rows]
            warm_total = warm_page.total
        finally:
            session.close()
            self.engine.dispose()

        # Simulate cold engine/process restart: new engine instance, no memory cache
        cold_engine = create_engine(self.db_url)
        ColdSession = sessionmaker(bind=cold_engine)
        cold_session = ColdSession()
        try:
            cold_page = feed_page(cold_session, FeedQuerySpec(truth_pack_hash="truth-test", page=1, page_size=10))
            self.assertEqual(cold_page.total, warm_total)
            self.assertEqual([row.opportunity_id for row in cold_page.rows], warm_ids)
            self.assertEqual([row.fit_score for row in cold_page.rows], warm_scores)
        finally:
            cold_session.close()
            cold_engine.dispose()

    def test_page_size_hydrates_bounded_page_not_all_rows(self) -> None:
        session = self.Session()
        try:
            opps = [self._seed_opportunity(f"opp-{idx:03d}") for idx in range(1, 51)]
            evals = [self._seed_evaluation(f"opp-{idx:03d}", fit_score=50.0 + (idx % 40)) for idx in range(1, 51)]
            session.add_all(opps + evals)
            session.commit()
            rebuild_feed_projection(session, truth_graph=None, truth_pack_hash="truth-test", batch_size=50)
            session.commit()

            page = feed_page(session, FeedQuerySpec(truth_pack_hash="truth-test", page=1, page_size=25))
            self.assertEqual(page.total, 50)
            self.assertEqual(len(page.rows), 25)
            self.assertEqual(page.page_size, 25)
            self.assertEqual(page.page, 1)
        finally:
            session.close()

    def test_decision_and_min_score_predicates_remain_sql_side(self) -> None:
        session = self.Session()
        try:
            spec = FeedQuerySpec(
                truth_pack_hash="truth-test",
                decision="qualified",
                min_score=80.0,
                track="employment",
                work_mode="remote",
                location_country="EG",
            )
            query = build_feed_query(session, spec)
            sql = str(query.statement.compile(compile_kwargs={"literal_binds": True}))

            self.assertIn("FROM feed_projection", sql)
            self.assertIn("lower(feed_projection.qualification_decision) = 'qualified'", sql)
            self.assertIn("feed_projection.fit_score >= 80", sql)
            self.assertIn("feed_projection.track = 'employment'", sql)
            self.assertIn("lower(feed_projection.work_mode) IN ('remote')", sql)
            self.assertIn("lower(feed_projection.location_country) IN ('eg')", sql)
            self.assertNotIn("opportunities.description", sql)
            self.assertNotIn("JOIN opportunities", sql)
        finally:
            session.close()

    def test_repeated_feed_requests_do_no_opportunity_evaluation(self) -> None:
        session = self.Session()
        try:
            opp = self._seed_opportunity("opp-cached")
            ev = self._seed_evaluation("opp-cached", fit_score=88.0)
            session.add_all([opp, ev])
            session.commit()
            rebuild_feed_projection(session, truth_graph=None, truth_pack_hash="truth-test")
            session.commit()

            with patch.object(OpportunityScorer, "evaluate") as mock_scorer:
                for _ in range(5):
                    page = feed_page(session, FeedQuerySpec(truth_pack_hash="truth-test"))
                    self.assertEqual(page.total, 1)
                    self.assertEqual(page.rows[0].opportunity_id, "opp-cached")
                mock_scorer.assert_not_called()
        finally:
            session.close()

    def test_persisted_hidden_state_is_authoritative(self) -> None:
        session = self.Session()
        try:
            opp1 = self._seed_opportunity("opp-vis")
            ev1 = self._seed_evaluation("opp-vis", fit_score=90.0)
            opp2 = self._seed_opportunity("opp-hid")
            ev2 = self._seed_evaluation("opp-hid", fit_score=70.0)
            session.add_all([opp1, ev1, opp2, ev2])
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
                truth_pack_hash="truth-test",
                filter_settings=hide_settings,
                facet_settings={},
            )
            session.commit()

            # Default: hidden rows excluded
            default_page = feed_page(session, FeedQuerySpec(truth_pack_hash="truth-test", include_hidden=False))
            self.assertEqual([row.opportunity_id for row in default_page.rows], ["opp-vis"])
            self.assertEqual(default_page.total, 1)

            # include_hidden=True: both included, with visible=False on the hidden item
            all_page = feed_page(session, FeedQuerySpec(truth_pack_hash="truth-test", include_hidden=True))
            self.assertEqual(all_page.total, 2)
            row_map = {r.opportunity_id: r for r in all_page.rows}
            self.assertTrue(row_map["opp-vis"].visible)
            self.assertFalse(row_map["opp-hid"].visible)
            self.assertIn("min_fit_score", row_map["opp-hid"].visibility_reason or "")
        finally:
            session.close()

    def test_search_remains_sql_gin_oriented(self) -> None:
        session = self.Session()
        try:
            spec = FeedQuerySpec(truth_pack_hash="truth-test", q='"data engineer" -junior')
            query = build_feed_query(session, spec)
            sql = str(
                query.statement.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
            self.assertIn("feed_projection.search_tsv @@ websearch_to_tsquery", sql)
            self.assertIn("data engineer", sql)
            self.assertIn("-junior", sql)

            # Validate GIN index is explicitly declared on table
            gin_indexes = [
                idx for idx in FeedProjectionRecord.__table__.indexes
                if idx.name == "ix_feed_projection_search_tsv"
            ]
            self.assertEqual(len(gin_indexes), 1)
            self.assertEqual(gin_indexes[0].dialect_options.get("postgresql", {}).get("using"), "gin")
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
