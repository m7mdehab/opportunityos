from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from storage.feed_projection import FeedProjectionRecord, projection_identity
from storage.feed_query import FeedQuerySpec, build_feed_query, feed_page
from storage.models import (
    Base,
    FounderTriageStateRecord,
    OutboundActionRecordModel,
)


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
        ) -> None:
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
                    reasons_json="[]",
                    red_line_match=not visible,
                    excluded_industry_match=False,
                    visible=visible,
                    visibility_reason=None if visible else "red_line",
                    search_text=f"Role {opportunity_id} Example",
                    search_tsv=None,
                    evaluated_at=now,
                    projected_at=now,
                )
            )

        self.add_projection = add
        add("opp-1", fit=91.0, priority=91.0)
        add("opp-2", decision="UNCERTAIN", fit=72.0, priority=72.0)
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

    def test_default_excludes_proven_ineligible_but_explicit_decision_includes_it(self) -> None:
        self.add_projection("opp-5", decision="INELIGIBLE", fit=100.0, priority=100.0)
        self.session.commit()
        default = feed_page(
            self.session,
            FeedQuerySpec(truth_pack_hash="truth-a", include_hidden=True),
        )
        default_ids = {row.opportunity_id for row in default.rows}
        self.assertNotIn("opp-5", default_ids)

        explicitly_ineligible = feed_page(
            self.session,
            FeedQuerySpec(
                truth_pack_hash="truth-a",
                decision="ineligible",
                include_hidden=True,
            ),
        )
        self.assertEqual([row.opportunity_id for row in explicitly_ineligible.rows], ["opp-5"])

    def test_default_excludes_active_tracked_rows_and_submitted_jobs_but_resurfaces_expired_snooze(self) -> None:
        as_of = datetime(2026, 9, 25, 12, 0, 0)
        self.add_projection("opp-6", fit=80.0, priority=80.0)
        self.add_projection("opp-7", fit=78.0, priority=78.0)
        self.add_projection("opp-8", fit=76.0, priority=76.0)
        self.add_projection("opp-9", fit=74.0, priority=74.0)
        self.session.add_all([
            FounderTriageStateRecord(
                opportunity_id="opp-6", state="saved", snoozed_until=None,
                created_at=as_of, updated_at=as_of,
            ),
            FounderTriageStateRecord(
                opportunity_id="opp-7", state="snoozed", snoozed_until=datetime(2026, 9, 26),
                created_at=as_of, updated_at=as_of,
            ),
            FounderTriageStateRecord(
                opportunity_id="opp-8", state="snoozed", snoozed_until=datetime(2026, 9, 25, 11, 0),
                created_at=as_of, updated_at=as_of,
            ),
            OutboundActionRecordModel(
                id="action-opp-9",
                opportunity_id="opp-9",
                opportunity_content_hash="a" * 64,
                workspace="default",
                candidate_id="founder",
                track="employment",
                source="fixture",
                adapter_name="founder_attested",
                adapter_version="1.0",
                execution_mode="dry_run",
                qualification_decision="qualified",
                match_score_snapshot=74.0,
                artifact_ids_json="[]",
                artifact_hashes_json="[]",
                manifest_hash="b" * 64,
                action_status="submitted",
                idempotency_key="fixture-action-opp-9",
                created_at=as_of,
                updated_at=as_of,
            ),
        ])
        self.session.commit()

        default = feed_page(
            self.session,
            FeedQuerySpec(truth_pack_hash="truth-a", include_hidden=True, as_of=as_of),
        )
        default_ids = {row.opportunity_id for row in default.rows}
        self.assertNotIn("opp-6", default_ids)
        self.assertNotIn("opp-7", default_ids)
        self.assertIn("opp-8", default_ids)
        self.assertNotIn("opp-9", default_ids)

        explicitly_including_tracked = feed_page(
            self.session,
            FeedQuerySpec(
                truth_pack_hash="truth-a",
                include_hidden=True,
                include_tracked=True,
                as_of=as_of,
            ),
        )
        tracked_ids = {row.opportunity_id for row in explicitly_including_tracked.rows}
        self.assertTrue({"opp-6", "opp-7", "opp-9"}.issubset(tracked_ids))
        self.assertIn("opp-8", tracked_ids)

    def test_composite_score_tie_break_is_opportunity_id(self) -> None:
        self.add_projection("opp-6", fit=80.0, priority=80.0)
        self.add_projection("opp-z", fit=80.0, priority=80.0)
        self.session.commit()
        result = feed_page(
            self.session,
            FeedQuerySpec(truth_pack_hash="truth-a", include_hidden=True),
        )
        tied_ids = [row.opportunity_id for row in result.rows if row.priority_score == 80.0]
        self.assertEqual(tied_ids, ["opp-6", "opp-z"])

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
        self.assertIn("feed_projection.search_tsv @@ websearch_to_tsquery", sql)
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


if __name__ == "__main__":
    unittest.main()
