from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.feed_projection import FeedProjectionRecord, projection_identity
from storage.models import Base


class FeedProjectionContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_projection_identity_is_stable_and_profile_scoped(self) -> None:
        self.assertEqual(
            projection_identity("opp-1", "truth-a"),
            "opp-1:truth-a",
        )
        self.assertNotEqual(
            projection_identity("opp-1", "truth-a"),
            projection_identity("opp-1", "truth-b"),
        )

    def test_projection_contract_exposes_query_path_indexes(self) -> None:
        index_names = {index.name for index in FeedProjectionRecord.__table__.indexes}
        self.assertTrue(
            {
                "ix_feed_projection_truth_visible_rank",
                "ix_feed_projection_truth_decision_score",
                "ix_feed_projection_truth_posted",
                "ix_feed_projection_search_tsv",
                "ix_feed_projection_source_id",
                "ix_feed_projection_title_family",
                "ix_feed_projection_work_mode",
                "ix_feed_projection_location_country",
            }.issubset(index_names)
        )

    def test_cold_process_correctness_is_persisted_not_cache_backed(self) -> None:
        session = self.Session()
        try:
            record = FeedProjectionRecord(
                id=projection_identity("opp-1", "truth-a"),
                opportunity_id="opp-1",
                opportunity_content_hash="h" * 64,
                truth_pack_hash="truth-a",
                projection_version="v1",
                title="Data Engineer",
                organization="Example",
                source_id="example",
                source_url="https://example.invalid/job/1",
                posted_date="2026-09-17",
                track="employment",
                opportunity_type="employment",
                title_family="data_engineering",
                seniority_level="mid",
                work_mode="remote",
                location_country="EG",
                location_city="Cairo",
                location_region=None,
                remote_scope="worldwide",
                remote_scope_regions=None,
                employment_type="full_time",
                qualification_decision="QUALIFIED",
                fit_score=82.0,
                priority_score=82.0,
                reasons_json="[]",
                red_line_match=False,
                excluded_industry_match=False,
                visible=True,
                visibility_reason=None,
                search_text="Data Engineer Example Cairo remote",
                search_tsv=None,
                evaluated_at="2026-09-17 00:00:00+00:00",
                projected_at="2026-09-17 00:00:00+00:00",
            )
            session.add(record)
            session.commit()
            session.expunge_all()

            reloaded = (
                session.query(FeedProjectionRecord)
                .filter_by(truth_pack_hash="truth-a", visible=True)
                .one()
            )
            self.assertEqual(reloaded.opportunity_id, "opp-1")
            self.assertEqual(reloaded.qualification_decision, "QUALIFIED")
            self.assertEqual(reloaded.fit_score, 82.0)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
