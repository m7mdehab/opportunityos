from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from api.deps import require_session
from api.feed_filter_metadata import (
    CATEGORY_FACETS,
    MAX_FACET_VALUES,
    UNAVAILABLE_FILTERS,
    _category_query,
    _date_query,
    _score_query,
    feed_filter_metadata,
)
from api.routes_api import router
from storage.feed_projection import FeedProjectionRecord, projection_identity
from storage.models import Base


class FeedFilterMetadataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        now = datetime(2026, 9, 25, tzinfo=timezone.utc)
        self.now = now

        self.add_projection(
            "opp-a", truth_hash="truth-x", decision="QUALIFIED", fit=95.0,
            preference=85.0, confidence=65.0, priority=70.0, posted="2026-09-20",
            country=None, city="", family="other", tier=None, source="source-a",
        )
        self.add_projection(
            "opp-b", truth_hash="truth-x", decision="REVIEW_REQUIRED", fit=75.0,
            preference=None, confidence=91.0, priority=45.0, posted=None,
            country="EG", city="Cairo", family="data_engineering", tier="primary",
            source="source-b",
        )
        self.add_projection(
            "opp-hidden", truth_hash="truth-x", fit=100.0, visible=False,
            source="hidden-source", title="PRIVATE CONTENT MUST NOT LEAK",
        )
        self.add_projection(
            "opp-other-pack", truth_hash="truth-y", fit=100.0,
            source="other-pack-source",
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def add_projection(
        self,
        opportunity_id: str,
        *,
        truth_hash: str = "truth-x",
        decision: str | None = "QUALIFIED",
        fit: float | None = 80.0,
        preference: float | None = 60.0,
        confidence: float | None = 70.0,
        priority: float | None = 50.0,
        posted: str | None = "2026-09-25",
        country: str | None = "EG",
        city: str | None = "Cairo",
        family: str | None = "data_engineering",
        tier: str | None = "primary",
        source: str = "example",
        visible: bool = True,
        title: str | None = None,
    ) -> None:
        self.session.add(FeedProjectionRecord(
            id=projection_identity(opportunity_id, truth_hash),
            opportunity_id=opportunity_id,
            opportunity_content_hash=(opportunity_id[-1] * 64)[:64],
            truth_pack_hash=truth_hash,
            projection_version="v2",
            title=title or f"Synthetic role {opportunity_id}",
            organization="Synthetic Employer",
            source_id=source,
            source_url=f"https://example.invalid/{opportunity_id}",
            posted_date=posted,
            track="employment",
            opportunity_type="employment",
            title_family=family,
            title_level="mid",
            target_tier=tier,
            seniority_level="mid",
            work_mode="remote",
            location_country=country,
            location_city=city,
            location_region=None,
            remote_scope="worldwide",
            remote_scope_regions=None,
            employment_type="full_time",
            qualification_decision=decision,
            fit_score=fit,
            preference_score=preference,
            confidence_score=confidence,
            priority_score=priority,
            reasons_json="[\"NO CONTENT SHOULD BE READ\"]",
            red_line_match=not visible,
            excluded_industry_match=False,
            visible=visible,
            visibility_reason=None if visible else "red_line",
            search_text="synthetic searchable text",
            search_tsv=None,
            evaluated_at=self.now,
            projected_at=self.now,
        ))

    def test_category_counts_are_truth_and_visible_scoped_with_unknown_normalization(self) -> None:
        result = feed_filter_metadata(self.session, "truth-x")
        facets = result["facets"]

        self.assertEqual(result["truth_pack_hash"], "truth-x")
        self.assertEqual(result["count_scope"], {
            "visible_only": True,
            "independent_of_selected_filters": True,
            "includes_tracked_and_ineligible": True,
        })
        self.assertEqual(facets["decision"]["option_count"], 2)
        self.assertEqual(
            {item["value"]: item["count"] for item in facets["decision"]["values"]},
            {"qualified": 1, "review_required": 1},
        )
        self.assertEqual(
            {item["value"]: item["count"] for item in facets["location_country"]["values"]},
            {"unknown": 1, "eg": 1},
        )
        self.assertEqual(
            {item["value"]: item["count"] for item in facets["title_family"]["values"]},
            {"unknown": 1, "data_engineering": 1},
        )
        self.assertEqual(facets["track"]["values"], [{"value": "employment", "count": 2}])
        self.assertNotIn("hidden-source", json.dumps(result))
        self.assertNotIn("other-pack-source", json.dumps(result))
        self.assertNotIn("PRIVATE CONTENT MUST NOT LEAK", json.dumps(result))
        self.assertNotIn("opp-a", json.dumps(result))

    def test_score_and_posted_date_aggregates_are_scalar_counts(self) -> None:
        result = feed_filter_metadata(self.session, "truth-x")["ranges"]
        self.assertEqual(result["fit_score"], {
            "min": 75.0,
            "max": 95.0,
            "unknown_count": 0,
            "threshold_counts": {"90+": 1, "80+": 1, "70+": 2, "60+": 2, "50+": 2},
        })
        self.assertEqual(result["preference_score"]["unknown_count"], 1)
        self.assertEqual(result["preference_score"]["threshold_counts"]["80+"], 1)
        self.assertEqual(result["confidence_score"]["threshold_counts"]["90+"], 1)
        self.assertEqual(result["priority_score"]["threshold_counts"]["70+"], 1)
        self.assertEqual(result["posted_date"], {
            "min": "2026-09-20",
            "max": "2026-09-20",
            "unknown_count": 1,
        })

    def test_category_values_are_bounded_and_truncation_is_explicit(self) -> None:
        for index in range(MAX_FACET_VALUES + 5):
            self.add_projection(
                f"many-{index}", truth_hash="truth-many", source=f"source-{index:03}"
            )
        self.session.commit()

        result = feed_filter_metadata(self.session, "truth-many")["facets"]["source_id"]
        self.assertEqual(result["option_count"], MAX_FACET_VALUES + 5)
        self.assertEqual(len(result["values"]), MAX_FACET_VALUES)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["values"][0]["value"], "source-000")

    def test_supported_sorts_and_unsupported_filter_reasons_are_explicit(self) -> None:
        result = feed_filter_metadata(self.session, "truth-x")
        self.assertEqual(
            [item["value"] for item in result["sorts"]],
            ["recommended", "fit_desc", "fit_asc", "newest_posted", "oldest_posted", "remote_first"],
        )
        unavailable = result["unavailable_filters"]
        ids = [item["id"] for item in unavailable]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(unavailable), len(UNAVAILABLE_FILTERS))
        self.assertTrue(all(item["reason"].strip() for item in unavailable))
        self.assertTrue({
            "tracking_state", "eligibility_evidence", "skill_match_and_gaps",
            "compensation", "company_attributes", "posting_health",
            "cv_application_readiness", "tracked_user_metadata",
        }.issubset(ids))

    def test_metadata_uses_only_grouped_or_scalar_projection_queries(self) -> None:
        statements: list[str] = []

        def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement.lower())

        event.listen(self.engine, "before_cursor_execute", record_sql)
        try:
            result = feed_filter_metadata(self.session, "truth-x")
        finally:
            event.remove(self.engine, "before_cursor_execute", record_sql)

        self.assertTrue(result["facets"])
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().startswith("select") for sql in statements))
        self.assertTrue(all("from feed_projection" in sql for sql in statements))
        self.assertTrue(all("opportunities" not in sql for sql in statements))
        self.assertTrue(all("reasons_json" not in sql and "source_url" not in sql for sql in statements))
        self.assertTrue(any("group by" in sql for sql in statements))
        self.assertTrue(any(" over (" in sql or "over (" in sql for sql in statements))

    def test_representative_queries_compile_for_postgresql_without_connection(self) -> None:
        for facet in CATEGORY_FACETS:
            query = _category_query(self.session, facet, "truth-x")
            sql = str(query.statement.compile(dialect=postgresql.dialect()))
            self.assertIn("feed_projection", sql)
            self.assertNotIn("opportunities", sql)
        for query in (
            _score_query(self.session, "truth-x"),
            _date_query(self.session, "truth-x"),
        ):
            sql = str(query.statement.compile(dialect=postgresql.dialect()))
            self.assertIn("feed_projection", sql)
            self.assertNotIn("opportunities", sql)

    def test_route_is_additive_and_inherits_session_guard(self) -> None:
        route_map = {route.path: route for route in router.routes}
        self.assertIn("/api/feed/filter-metadata", route_map)
        self.assertEqual(route_map["/api/feed/filter-metadata"].methods, {"GET"})
        self.assertIn("/api/facets", route_map)
        self.assertEqual(route_map["/api/facets"].endpoint.__name__, "list_facets")
        self.assertTrue(any(dependency.dependency is require_session for dependency in router.dependencies))


if __name__ == "__main__":
    unittest.main()
