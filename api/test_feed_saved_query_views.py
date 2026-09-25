from __future__ import annotations

import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.saved_views import create_saved_view, list_saved_views, update_saved_view
from storage.models import Base


class FeedSavedQueryViewsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_full_feed_query_round_trips_and_facet_update_preserves_it(self) -> None:
        query = {
            "track": "employment",
            "decision": "qualified",
            "q": '"data engineer" -agency',
            "multi": {"work_mode": ["remote", "hybrid"], "source_id": ["alpha"]},
            "scoreRanges": {
                "fit_score": {"min": "80", "max": ""},
                "preference_score": {"min": "", "max": ""},
                "confidence_score": {"min": "70", "max": "95"},
                "priority_score": {"min": "", "max": ""},
            },
            "postedFrom": "2026-09-01",
            "postedTo": "2026-09-25",
            "sortBy": "fit_desc",
            "includeHidden": False,
        }
        session = self.Session()
        try:
            created = create_saved_view(
                session,
                name="Remote data engineering",
                facets={},
                search_query=query["q"],
                feed_query=query,
                is_default=False,
                now=datetime(2026, 9, 25),
                view_id="query-view-1",
            )
            self.assertEqual(created["feed_query"], query)
        finally:
            session.close()

        fresh_session = self.Session()
        try:
            views = list_saved_views(fresh_session)
            self.assertEqual(len(views), 1)
            self.assertEqual(views[0]["feed_query"], query)
            self.assertEqual(views[0]["facets"], {})
            updated = update_saved_view(
                fresh_session,
                "query-view-1",
                facets={"legacy_facet": {"include": ["remote"], "exclude": []}},
                now=datetime(2026, 9, 26),
            )
            self.assertIsNotNone(updated)
            self.assertEqual(updated["feed_query"], query)
            self.assertEqual(updated["facets"]["legacy_facet"]["include"], ["remote"])
        finally:
            fresh_session.close()

    def test_legacy_facet_only_view_keeps_its_old_shape(self) -> None:
        facets = {"work_mode": {"include": ["remote"], "exclude": ["onsite"]}}
        session = self.Session()
        try:
            created = create_saved_view(
                session,
                name="Legacy remote only",
                facets=facets,
                search_query="remote role",
                is_default=True,
                now=datetime(2026, 9, 25),
                view_id="facet-view-1",
            )
            self.assertIsNone(created["feed_query"])
        finally:
            session.close()

        fresh_session = self.Session()
        try:
            view = list_saved_views(fresh_session)[0]
            self.assertEqual(view["facets"], facets)
            self.assertEqual(view["search_query"], "remote role")
            self.assertTrue(view["is_default"])
            self.assertIsNone(view["feed_query"])
        finally:
            fresh_session.close()


if __name__ == "__main__":
    unittest.main()
