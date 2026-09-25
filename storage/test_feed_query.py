from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Literal, get_args, get_origin, get_type_hints

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
            decision: str | None = "QUALIFIED",
            fit: float | None = 80.0,
            priority: float | None = None,
            visible: bool = True,
            track: str = "employment",
            work_mode: str = "remote",
            remote_scope: str = "worldwide",
            country: str | None = "EG",
            family: str | None = "data_engineering",
            target_tier: str | None = "primary",
            preference: float | None = None,
            confidence: float | None = None,
            employment_type: str = "full_time",
            seniority_level: str = "mid",
            posted_date: str | None = "2026-09-17",
            source_id: str = "example",
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
                    target_tier=target_tier,
                    preference_score=preference,
                    confidence_score=confidence,
                    seniority_level=seniority_level,
                    work_mode=work_mode,
                    location_country=country,
                    location_city="Cairo" if country == "EG" else None,
                    location_region=None,
                    remote_scope=remote_scope,
                    remote_scope_regions=None,
                    employment_type=employment_type,
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

        attestation = self.session.query(OutboundActionRecordModel).filter_by(id="action-opp-9").one()
        attestation.action_status = "undone"
        self.session.commit()
        after_undo = feed_page(
            self.session,
            FeedQuerySpec(truth_pack_hash="truth-a", include_hidden=True, as_of=as_of),
        )
        self.assertIn("opp-9", {row.opportunity_id for row in after_undo.rows})

    def test_default_inbox_excludes_every_saved_pipeline_and_closed_tracker_state(self) -> None:
        as_of = datetime(2026, 9, 25, 12, 0, 0)
        states = [
            "saved", "applied", "recruiter_screen", "assessment", "interviewing",
            "final_interview", "offer", "accepted", "rejected_by_founder",
            "rejected_by_employer", "withdrawn", "no_response", "position_closed",
            "archived", "dismissed", "snoozed",
        ]
        for index, state in enumerate(states):
            opportunity_id = f"tracked-{index:02d}"
            self.add_projection(opportunity_id, fit=90.0 - index, priority=90.0 - index)
            self.session.add(FounderTriageStateRecord(
                opportunity_id=opportunity_id,
                state=state,
                snoozed_until=(as_of + timedelta(days=1)) if state == "snoozed" else None,
                created_at=as_of,
                updated_at=as_of,
            ))
        self.session.commit()

        default = feed_page(
            self.session,
            FeedQuerySpec(truth_pack_hash="truth-a", include_hidden=True, as_of=as_of),
        )
        default_ids = {row.opportunity_id for row in default.rows}
        self.assertTrue(all(f"tracked-{index:02d}" not in default_ids for index in range(len(states))))

        explicitly_including_tracked = feed_page(
            self.session,
            FeedQuerySpec(
                truth_pack_hash="truth-a",
                include_hidden=True,
                include_tracked=True,
                as_of=as_of,
            ),
        )
        included_ids = {row.opportunity_id for row in explicitly_including_tracked.rows}
        self.assertTrue(all(f"tracked-{index:02d}" in included_ids for index in range(len(states))))

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

    def test_multiselect_values_are_or_within_facets_and_and_between_facets(self) -> None:
        self.add_projection(
            "opp-5", work_mode="hybrid", country="US", employment_type="contract"
        )
        self.add_projection(
            "opp-6", work_mode="onsite", country="EG", employment_type="full_time"
        )
        self.add_projection(
            "opp-7", work_mode="hybrid", country="CA", employment_type="contract"
        )
        self.session.commit()

        result = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a",
            work_modes=("remote", "hybrid"),
            location_countries=("EG", "US"),
            employment_types=("full_time", "contract"),
            target_tiers=("primary",),
            title_families=("data_engineering",),
            include_hidden=True,
        ))
        self.assertEqual(
            {row.opportunity_id for row in result.rows},
            {"opp-1", "opp-2", "opp-3", "opp-5"},
        )
        self.assertEqual(result.total, 4)

    def test_unknown_nulls_and_stored_unspecified_values_are_explicitly_filterable(self) -> None:
        self.add_projection(
            "opp-5", country=None, family=None, target_tier=None,
            work_mode="unspecified", employment_type="unspecified",
        )
        self.add_projection("opp-6", country="EG", family="other", target_tier="stretch")
        self.session.commit()

        null_selection = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a",
            location_countries=("unknown",),
            target_tiers=("unknown",),
            title_families=("unknown",),
            include_hidden=True,
        ))
        self.assertEqual([row.opportunity_id for row in null_selection.rows], ["opp-5"])

        unmapped_families = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a", title_families=("unknown",), include_hidden=True
        ))
        self.assertEqual(
            {row.opportunity_id for row in unmapped_families.rows}, {"opp-5", "opp-6"}
        )

        unspecified = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a",
            work_modes=("unknown",),
            employment_types=("unknown",),
            include_hidden=True,
        ))
        self.assertEqual([row.opportunity_id for row in unspecified.rows], ["opp-5"])

    def test_unknown_filters_match_blank_and_literal_unknown_values(self) -> None:
        self.add_projection(
            "opp-5", decision=None, track="", work_mode="", remote_scope="",
            country="unknown", family=None, target_tier="unknown", source_id="",
            employment_type="", seniority_level="",
        )
        self.add_projection(
            "opp-6", decision=" UNKNOWN ", track="unknown", work_mode="unspecified",
            remote_scope="unknown", country=None, family="other", target_tier=None,
            source_id="unknown", employment_type="unknown", seniority_level="unknown",
        )
        self.add_projection("opp-7", work_mode="unknown")
        self.session.commit()

        result = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a",
            track="unknown",
            decision="unknown",
            work_modes=("unknown",),
            remote_scopes=("unknown",),
            employment_types=("unknown",),
            seniority_levels=("unknown",),
            location_countries=("unknown",),
            target_tiers=("unknown",),
            title_families=("unknown",),
            source_ids=("unknown",),
            include_hidden=True,
        ))
        self.assertEqual(
            {row.opportunity_id for row in result.rows},
            {"opp-5", "opp-6"},
        )
        work_mode_unknown = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a", work_modes=("unknown",), include_hidden=True
        ))
        self.assertEqual(
            {row.opportunity_id for row in work_mode_unknown.rows},
            {"opp-5", "opp-6", "opp-7"},
        )

    def test_independent_score_ranges_and_posting_dates_filter_before_count_and_page(self) -> None:
        self.add_projection(
            "opp-5", fit=86.0, preference=78.0, confidence=82.0,
            priority=75.0, posted_date="2026-09-20",
        )
        self.add_projection(
            "opp-6", fit=88.0, preference=77.0, confidence=95.0,
            priority=74.0, posted_date="2026-09-22",
        )
        self.add_projection(
            "opp-7", fit=86.0, preference=55.0, confidence=82.0,
            priority=73.0, posted_date="2026-09-21",
        )
        self.session.commit()

        result = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a",
            min_fit_score=80.0,
            max_fit_score=90.0,
            min_preference_score=70.0,
            max_confidence_score=90.0,
            min_priority_score=70.0,
            posted_from="2026-09-19",
            posted_to="2026-09-21",
            include_hidden=True,
            page=1,
            page_size=1,
        ))
        self.assertEqual(result.total, 1)
        self.assertEqual([row.opportunity_id for row in result.rows], ["opp-5"])
        self.assertEqual(result.page_size, 1)

    def test_supported_sorts_are_deterministic_null_last_and_remote_is_only_ordering(self) -> None:
        self.add_projection("opp-5", fit=85.0, priority=100.0, work_mode="onsite", posted_date="2026-09-24")
        self.add_projection("opp-6", fit=90.0, priority=20.0, work_mode="remote", posted_date=None)
        self.add_projection("opp-7", fit=None, priority=None, work_mode="hybrid", posted_date="2026-09-25")
        self.add_projection("opp-8", decision="INELIGIBLE", fit=100.0, priority=100.0, work_mode="remote")
        self.session.commit()

        fit_sorted = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a", sort_by="fit_desc", include_hidden=True
        ))
        self.assertEqual(
            [row.opportunity_id for row in fit_sorted.rows[:3]], ["opp-3", "opp-1", "opp-6"]
        )
        self.assertEqual(fit_sorted.rows[-1].opportunity_id, "opp-7")
        fit_ascending = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a", sort_by="fit_asc", include_hidden=True
        ))
        self.assertEqual(fit_ascending.rows[0].opportunity_id, "opp-2")
        self.assertEqual(fit_ascending.rows[-1].opportunity_id, "opp-7")

        newest = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a", sort_by="newest_posted", include_hidden=True
        ))
        self.assertEqual(newest.rows[0].opportunity_id, "opp-7")
        self.assertEqual(newest.rows[-1].opportunity_id, "opp-6")
        oldest = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a", sort_by="oldest_posted", include_hidden=True
        ))
        self.assertEqual(oldest.rows[0].opportunity_id, "opp-1")
        self.assertEqual(oldest.rows[-1].opportunity_id, "opp-6")

        recommended = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a", include_hidden=True
        ))
        remote_first = feed_page(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a", sort_by="remote_first", include_hidden=True
        ))
        self.assertEqual(
            {row.opportunity_id for row in remote_first.rows},
            {row.opportunity_id for row in recommended.rows},
        )
        self.assertNotIn("opp-8", {row.opportunity_id for row in remote_first.rows})
        self.assertEqual(remote_first.rows[0].opportunity_id, "opp-3")
        self.assertEqual(remote_first.rows[0].fit_score, 99.0)

        with self.assertRaises(ValueError):
            feed_page(self.session, FeedQuerySpec(
                truth_pack_hash="truth-a", sort_by="random", include_hidden=True
            ))

    def test_new_filters_compile_to_projection_only_postgresql_sql(self) -> None:
        query = build_feed_query(self.session, FeedQuerySpec(
            truth_pack_hash="truth-a",
            work_modes=("remote", "hybrid"),
            location_countries=("EG", "unknown"),
            employment_types=("full_time",),
            target_tiers=("primary", "unknown"),
            min_fit_score=70.0,
            min_preference_score=60.0,
            min_confidence_score=50.0,
            posted_from="2026-09-01",
            posted_to="2026-09-30",
        ))
        sql = str(query.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ))
        self.assertIn("feed_projection.work_mode", sql)
        self.assertIn("feed_projection.location_country", sql)
        self.assertIn("feed_projection.employment_type", sql)
        self.assertIn("feed_projection.target_tier", sql)
        self.assertIn("feed_projection.preference_score", sql)
        self.assertIn("feed_projection.confidence_score", sql)
        self.assertIn("feed_projection.posted_date", sql)
        self.assertNotIn("FROM opportunities", sql)
        self.assertNotIn("JOIN opportunities", sql)

    def test_opportunities_route_exposes_repeatable_facets_and_constrained_sort(self) -> None:
        from api.routes_api import router

        route = next(
            route for route in router.routes
            if getattr(route, "path", None) == "/api/opportunities"
        )
        query_names = {parameter.name for parameter in route.dependant.query_params}
        self.assertTrue({
            "work_mode", "location_country", "employment_type", "target_tier",
            "title_family", "min_fit_score", "posted_from", "posted_to", "sort_by",
        }.issubset(query_names))

        hints = get_type_hints(route.endpoint)
        self.assertIn(list[str], get_args(hints["work_mode"]))
        self.assertIs(get_origin(hints["sort_by"]), Literal)
        self.assertEqual(
            set(get_args(hints["sort_by"])),
            {"recommended", "fit_desc", "fit_asc", "newest_posted", "oldest_posted", "remote_first"},
        )


if __name__ == "__main__":
    unittest.main()
