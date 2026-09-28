from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from storage.feed_projection import FeedProjectionRecord, projection_identity
from storage.feed_query import FeedQuerySpec, build_feed_query, feed_page
from storage.models import Base, OpportunityRecord


class FeedQueryContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        now = datetime.now(timezone.utc)

        def add(
            opportunity_id: str,
            *,
            truth_hash: str = "truth-a",
            decision: str = "QUALIFIED",
            fit: float = 80.0,
            priority: float | None = None,
            visible: bool = True,
            track: str = "employment",
            work_mode: str = "remote",
            country: str | None = "EG",
            family: str | None = "data_engineering",
            source_id: str = "example",
            posted_date: str = "2026-09-17",
            recommendation_state: str = "for_you",
            recommendation_priority: float | None = None,
        ) -> None:
            self.session.add(OpportunityRecord(
                id=opportunity_id,
                track=track,
                title=f"Role {opportunity_id}",
                organization="Example",
                description="",
                source_id=source_id,
                source_url=f"https://example.invalid/{opportunity_id}",
                content_hash=(opportunity_id[-1] * 64)[:64],
                search_tsv="role example",
            ))
            self.session.add(
                FeedProjectionRecord(
                    id=projection_identity(opportunity_id, truth_hash),
                    opportunity_id=opportunity_id,
                    opportunity_content_hash=(opportunity_id[-1] * 64)[:64],
                    truth_pack_hash=truth_hash,
                    projection_version="v1",
                    title=f"Role {opportunity_id}",
                    organization="Example",
                    source_id=source_id,
                    source_url=f"https://example.invalid/{opportunity_id}",
                    posted_date=posted_date,
                    track=track,
                    opportunity_type="employment",
                    title_family=family,
                    seniority_level="mid",
                    work_mode=work_mode,
                    location_country=country,
                    location_city="Cairo" if country == "EG" else None,
                    location_region=None,
                    remote_scope="worldwide",
                    remote_scope_regions=None,
                    employment_type="full_time",
                    qualification_decision=decision,
                    fit_score=fit,
                    priority_score=fit if priority is None else priority,
                    recommendation_state=recommendation_state,
                    recommendation_reasons_json="[]",
                    recommendation_priority=fit if recommendation_priority is None else recommendation_priority,
                    learned_affinity=50.0,
                    reasons_json="[]",
                    red_line_match=not visible,
                    excluded_industry_match=False,
                    visible=visible,
                    visibility_reason=None if visible else "red_line",
                    evaluated_at=now,
                    projected_at=now,
                )
            )

        add("opp-1", fit=91.0, priority=91.0)
        add("opp-2", decision="UNCERTAIN", fit=72.0, priority=72.0, recommendation_priority=91.0)
        add("opp-3", fit=99.0, priority=99.0, visible=False)
        add("opp-4", truth_hash="truth-b", fit=98.0, priority=98.0)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_default_page_is_profile_scoped_and_excludes_hidden(self) -> None:
        result = feed_page(self.session, FeedQuerySpec(truth_pack_hash="truth-a"))
        self.assertEqual([row.opportunity_id for row in result.rows], ["opp-1", "opp-2"])
        self.assertEqual(result.total, 2)

    def test_decision_and_score_are_applied_before_pagination(self) -> None:
        result = feed_page(
            self.session,
            FeedQuerySpec(
                truth_pack_hash="truth-a",
                decision="QUALIFIED",
                min_score=80.0,
                include_hidden=True,
            ),
        )
        self.assertEqual([row.opportunity_id for row in result.rows], ["opp-3", "opp-1"])
        self.assertEqual(result.total, 2)

    def test_page_size_is_bounded_and_ordering_is_persisted_rank(self) -> None:
        result = feed_page(
            self.session,
            FeedQuerySpec(
                truth_pack_hash="truth-a",
                include_hidden=True,
                page=1,
                page_size=1,
            ),
        )
        self.assertEqual([row.opportunity_id for row in result.rows], ["opp-3"])
        self.assertEqual(result.total, 3)
        self.assertEqual(result.page_size, 1)

    def test_search_compiles_to_postgres_full_text_predicate(self) -> None:
        query = build_feed_query(
            self.session,
            FeedQuerySpec(truth_pack_hash="truth-a", q='"data engineer" -customer'),
        )
        sql = str(
            query.statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("opportunities.search_tsv @@ websearch_to_tsquery", sql)
        self.assertIn("data engineer", sql)
        self.assertNotIn("opportunities.description", sql)

    def test_query_contract_reads_projection_table_only(self) -> None:
        query = build_feed_query(
            self.session,
            FeedQuerySpec(
                truth_pack_hash="truth-a",
                track="employment",
                work_mode="remote",
                location_country="EG",
                title_family="data_engineering",
                source_id="example",
            ),
        )
        sql = str(query.statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("FROM feed_projection", sql)
        self.assertNotIn("FROM opportunities", sql)
        self.assertNotIn("JOIN opportunities", sql)

    def test_for_you_query_uses_recommendation_state_and_persisted_score_with_id_tie_break(self) -> None:
        result = feed_page(self.session, FeedQuerySpec(truth_pack_hash="truth-a", sort_by="for_you"))
        self.assertEqual([row.opportunity_id for row in result.rows], ["opp-1", "opp-2"])
        self.assertEqual(result.total, 2)

    def test_recommendation_state_filters_before_pagination(self) -> None:
        now = datetime.now(timezone.utc)
        self.session.add(OpportunityRecord(
            id="opp-review", track="employment", title="Role review", organization="Example",
            description="", source_id="example", source_url="https://example.invalid/review",
            content_hash="r" * 64, search_tsv="role example",
        ))
        self.session.add(FeedProjectionRecord(
            id="opp-review", opportunity_id="opp-review", opportunity_content_hash="r" * 64,
            truth_pack_hash="truth-a", projection_version="v1", title="Role review",
            organization="Example", source_id="example", source_url="https://example.invalid/review",
            posted_date="2026-09-17", track="employment", opportunity_type="employment",
            title_family="data_engineering", seniority_level="mid", work_mode="remote",
            location_country="EG", location_city="Cairo", location_region=None,
            remote_scope="worldwide", remote_scope_regions=None, employment_type="full_time",
            qualification_decision="QUALIFIED", fit_score=97.0, priority_score=97.0,
            recommendation_state="review", recommendation_reasons_json="[]",
            recommendation_priority=999999.0, learned_affinity=50.0,
            reasons_json="[]", red_line_match=False, excluded_industry_match=False,
            visible=True, visibility_reason=None, evaluated_at=now, projected_at=now,
        ))
        self.session.commit()
        result = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a", recommendation_states=("review",),
        ))
        self.assertEqual([row.opportunity_id for row in result.rows], ["opp-review"])


if __name__ == "__main__":
    unittest.main()
