from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from storage.feed_projection import FeedProjectionRecord, projection_identity
from storage.feed_projection_invariants import verify_feed_projection_page
from storage.feed_projection_service import rebuild_feed_projection
from storage.models import Base, MatchEvaluationRecord, OpportunityRecord


class FeedProjectionInvariantTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def _opportunity(self, opportunity_id: str, *, title: str = "Data Engineer") -> OpportunityRecord:
        return OpportunityRecord(
            id=opportunity_id,
            track="employment",
            title=title,
            organization="Synthetic Example Co",
            description="Synthetic test description, never selected by verifier.",
            source_id="synthetic-test",
            source_url=f"https://example.invalid/{opportunity_id}",
            content_hash=("a" if opportunity_id.endswith("1") else "b") * 64,
            posted_date="2026-09-24",
            work_mode="remote",
            location_country="EG",
            location_city="Cairo",
            remote_scope="worldwide",
            employment_type="full_time",
            seniority_level="mid",
            title_family="data_engineering",
        )

    def _evaluation(self, opportunity_id: str) -> MatchEvaluationRecord:
        return MatchEvaluationRecord(
            id=f"eval-{opportunity_id}",
            opportunity_id=opportunity_id,
            truth_pack_hash="synthetic-truth",
            qualification_decision="qualified",
            fit_score=84.0,
            dimension_scores_json="[]",
            reasons_json='[{"reason":"synthetic fixture"}]',
            evaluation_detail_json=json.dumps({
                "preference_score": 72.5,
                "confidence_score": 88,
                "explanation": "Synthetic rationale must not be selected by verifier.",
            }),
            policy_version="synthetic-v1",
            evaluated_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
        )

    def _target_graph(self):
        from truth.graph import TruthGraph
        from truth.models import CareerProfile, EvidenceRecord, TargetRoleRecord, TargetRoleTier

        graph = TruthGraph()
        graph.add_evidence(EvidenceRecord(
            id="synthetic-tier-evidence",
            content="Synthetic reviewed primary target role: Data Engineer",
            source="synthetic-test",
            locator="test.target_roles.0",
        ))
        graph.add_career_profile(CareerProfile(
            id="synthetic-career-profile",
            target_roles=(TargetRoleRecord(
                id="synthetic-target-role",
                title="Data Engineer",
                evidence_ids=("synthetic-tier-evidence",),
                tier=TargetRoleTier("primary"),
            ),),
        ))
        return graph

    def _rebuild(self, session) -> None:
        session.add_all((self._opportunity("synthetic-opp-1"), self._opportunity("synthetic-opp-2")))
        session.flush()
        session.add_all((self._evaluation("synthetic-opp-1"), self._evaluation("synthetic-opp-2")))
        session.commit()
        stats = rebuild_feed_projection(
            session,
            truth_graph=None,
            truth_pack_hash="synthetic-truth",
            batch_size=2,
        )
        session.commit()
        self.assertEqual(stats.projected, 2)

    def test_synthetic_rebuild_is_clean_and_pages_resume_by_exclusive_cursor(self) -> None:
        session = self.Session()
        try:
            self._rebuild(session)

            first = verify_feed_projection_page(
                session, truth_pack_hash="synthetic-truth", page_size=1
            )
            self.assertEqual(first.scanned, 1)
            self.assertEqual(first.issue_counts, ())
            self.assertTrue(first.has_more)
            self.assertEqual(first.next_cursor, projection_identity("synthetic-opp-1", "synthetic-truth"))

            second = verify_feed_projection_page(
                session,
                truth_pack_hash="synthetic-truth",
                page_size=1,
                start_after=first.next_cursor,
            )
            self.assertEqual(second.scanned, 1)
            self.assertEqual(second.issue_counts, ())
            self.assertFalse(second.has_more)
        finally:
            session.close()

    def test_legacy_v1_null_w4_2_fields_are_accepted(self) -> None:
        session = self.Session()
        try:
            opportunity = self._opportunity("synthetic-legacy-1")
            session.add(opportunity)
            session.flush()
            session.add(FeedProjectionRecord(
                id=projection_identity(opportunity.id, "synthetic-truth"),
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                truth_pack_hash="synthetic-truth",
                projection_version="v1",
                title=opportunity.title,
                organization=opportunity.organization,
                source_id=opportunity.source_id,
                source_url=opportunity.source_url,
                track=opportunity.track,
                seniority_level=opportunity.seniority_level,
                work_mode=opportunity.work_mode,
                remote_scope=opportunity.remote_scope,
                employment_type=opportunity.employment_type,
                qualification_decision=None,
                fit_score=None,
                preference_score=None,
                confidence_score=None,
                priority_score=None,
                reasons_json="[]",
                search_text="Synthetic legacy projection",
                evaluated_at=datetime(2026, 9, 24),
                projected_at=datetime(2026, 9, 24),
            ))
            session.commit()

            result = verify_feed_projection_page(
                session, truth_pack_hash="synthetic-truth", page_size=1
            )
            self.assertEqual(result.scanned, 1)
            self.assertEqual(result.issue_counts, ())
        finally:
            session.close()

    def test_synthetic_target_tier_is_checked_against_supplied_truth_graph(self) -> None:
        session = self.Session()
        try:
            graph = self._target_graph()
            opportunity = self._opportunity("synthetic-tier-1")
            session.add(opportunity)
            session.flush()
            session.add(self._evaluation(opportunity.id))
            session.commit()
            rebuild_feed_projection(
                session,
                truth_graph=graph,
                truth_pack_hash="synthetic-truth",
                batch_size=1,
            )
            session.commit()

            result = verify_feed_projection_page(
                session,
                truth_pack_hash="synthetic-truth",
                page_size=1,
                truth_graph=graph,
            )
            self.assertEqual(result.issue_counts, ())

            row = session.get(FeedProjectionRecord, projection_identity(
                opportunity.id, "synthetic-truth"
            ))
            row.target_tier = "adjacent"
            session.commit()
            corrupted = verify_feed_projection_page(
                session,
                truth_pack_hash="synthetic-truth",
                page_size=1,
                truth_graph=graph,
            )
            self.assertEqual(dict(corrupted.issue_counts).get("target_tier_mismatch"), 1)
        finally:
            session.close()

    def test_corruption_is_counted_with_one_way_tokens_only(self) -> None:
        session = self.Session()
        try:
            self._rebuild(session)
            record = session.get(FeedProjectionRecord, projection_identity(
                "synthetic-opp-1", "synthetic-truth"
            ))
            record.opportunity_content_hash = "f" * 64
            record.title_level = "invented-level"
            record.preference_score = 101
            session.commit()

            result = verify_feed_projection_page(
                session, truth_pack_hash="synthetic-truth", page_size=1
            )
            codes = dict(result.issue_counts)
            self.assertIn("content_hash_mismatch", codes)
            self.assertIn("title_level_mismatch", codes)
            self.assertIn("invalid_preference_score", codes)
            self.assertIn("preference_score_mismatch", codes)
            self.assertTrue(result.issue_tokens)
            self.assertNotIn("synthetic-opp-1", repr(result))
            self.assertNotIn("synthetic-opp-1", json.dumps(result.to_safe_dict()))
            self.assertNotIn("synthetic-opp-1:synthetic-truth", json.dumps(result.to_safe_dict()))
        finally:
            session.close()

    def test_query_is_scalar_limited_bounded_and_read_only(self) -> None:
        session = self.Session()
        statements: list[str] = []
        try:
            self._rebuild(session)

            def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
                if "FROM feed_projection" in statement:
                    statements.append(statement.lower())

            event.listen(self.engine, "before_cursor_execute", capture)
            before = (len(session.new), len(session.dirty), len(session.deleted))
            result = verify_feed_projection_page(
                session, truth_pack_hash="synthetic-truth", page_size=1
            )
            after = (len(session.new), len(session.dirty), len(session.deleted))
            event.remove(self.engine, "before_cursor_execute", capture)

            self.assertEqual(before, after)
            self.assertEqual(result.scanned, 1)
            self.assertEqual(len(statements), 1)
            sql = statements[0]
            self.assertIn("limit", sql)
            self.assertNotIn("description", sql)
            self.assertNotIn("raw_payload_json", sql)
            self.assertNotIn("search_text", sql)
            self.assertNotIn("reasons_json", sql)
            self.assertNotIn("evaluation_detail_json as", sql)
            self.assertIn("json_extract", sql)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
