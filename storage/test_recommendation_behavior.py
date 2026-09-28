from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.feed_projection_service import load_founder_behavior_profile
from storage.models import (
    Base,
    FounderActivityEventRecord,
    FounderFeedbackRecord,
    OpportunityRecord,
)


class FounderBehaviorProfileStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        for opportunity_id, family, source in (
            ("positive", "data_engineering", "greenhouse:one"),
            ("eligibility", "data_science", "lever:one"),
            ("applied", "analytics_bi", "ashby:one"),
        ):
            self.session.add(OpportunityRecord(
                id=opportunity_id, track="employment", title="Role", organization="Employer",
                description="", source_id=source, source_url="https://example.invalid/role",
                content_hash=(opportunity_id[:1] * 64), title_family=family,
            ))
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    @staticmethod
    def feedback(opportunity_id: str, label: str, event_id: str, at: str) -> FounderFeedbackRecord:
        from datetime import datetime
        return FounderFeedbackRecord(
            id=event_id, opportunity_id=opportunity_id, feedback_label=label,
            structured_reason=None, notes="must not be loaded into profile",
            dedup_hash=event_id, created_at=datetime.fromisoformat(at),
        )

    def test_profile_uses_latest_categorical_feedback_and_ignores_notes(self):
        self.session.add_all([
            self.feedback("positive", "bad_match", "old", "2026-09-01T00:00:00"),
            self.feedback("positive", "good_match", "new", "2026-09-02T00:00:00"),
            self.feedback("eligibility", "eligibility_wrong", "elig", "2026-09-02T00:00:00"),
            FounderActivityEventRecord(
                id="applied-event", opportunity_id="applied", action_type="mark_applied",
                resulting_state="submitted", snoozed_until=None,
                created_at=__import__("datetime").datetime(2026, 9, 2),
            ),
        ])
        self.session.commit()
        profile = load_founder_behavior_profile(self.session)
        self.assertGreater(profile.score(role_family="data_engineering", source_family="greenhouse"), 50)
        self.assertEqual(profile.score(role_family="data_science", source_family="lever"), 50)
        self.assertGreater(profile.score(role_family="analytics_bi", source_family="ashby"), 50)
        without_self = load_founder_behavior_profile(self.session, exclude_opportunity_id="positive")
        self.assertEqual(without_self.score(role_family="data_engineering", source_family="greenhouse"), 50)


if __name__ == "__main__":
    unittest.main()
