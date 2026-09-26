from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.tracker_interviews_service import (
    TrackerInterviewError,
    create_tracker_interview,
    list_opportunity_interviews,
    list_tracker_interviews,
    update_tracker_interview,
)
from storage.models import (
    Base,
    FounderActivityEventRecord,
    FounderInterviewRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
)


class TrackerInterviewsServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            for index, state in enumerate(("saved", "applied", "offer", "rejected_by_employer", "to_review"), start=1):
                opportunity_id = f"synthetic-interview-{index}"
                session.add(OpportunityRecord(
                    id=opportunity_id,
                    track="employment",
                    title=f"Synthetic role {index}",
                    organization="Example employer",
                    description="Synthetic description",
                    source_id="example-source",
                    source_url=f"https://example.invalid/jobs/{index}",
                    content_hash=f"{index + 300:064x}",
                    posted_date="2026-09-25",
                ))
                if state != "to_review":
                    session.add(FounderTriageStateRecord(
                        opportunity_id=opportunity_id,
                        state=state,
                        created_at=self.now,
                        updated_at=self.now,
                    ))
            session.commit()
        finally:
            session.close()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_create_normalizes_datetime_and_records_private_id_only_event(self) -> None:
        session = self.Session()
        try:
            created = create_tracker_interview(
                session,
                "synthetic-interview-2",
                {
                    "scheduled_at": "2026-10-01T12:30:00+03:00",
                    "round_label": "  Round 2  ",
                    "interview_type": "technical",
                    "interview_format": "video",
                    "interviewer_name": "  Example interviewer  ",
                    "preparation_notes": "Private prep context",
                    "post_interview_notes": "Private debrief",
                },
                self.now,
                request_key="add-1",
            )
            self.assertTrue(created.changed)
            self.assertEqual(created.interview["scheduled_at"], "2026-10-01T09:30:00Z")
            self.assertEqual(created.interview["round_label"], "Round 2")
            self.assertEqual(created.interview["interviewer_name"], "Example interviewer")
            session.commit()
            event = session.query(FounderActivityEventRecord).filter_by(opportunity_id="synthetic-interview-2").one()
            self.assertEqual(event.action_type, "interview_added")
            self.assertEqual((event.from_state, event.to_state), ("applied", "applied"))
            self.assertEqual(json.loads(event.metadata_json), {"interview_id": created.interview["id"]})
            self.assertNotIn("Private", event.metadata_json)
            replay = create_tracker_interview(
                session,
                "synthetic-interview-2",
                {"round_label": "Different replay payload"},
                self.now + timedelta(minutes=2),
                request_key="add-1",
            )
            self.assertFalse(replay.changed)
            self.assertEqual(replay.interview["id"], created.interview["id"])
            session.commit()
            self.assertEqual(session.query(FounderActivityEventRecord).filter_by(opportunity_id="synthetic-interview-2").count(), 1)
        finally:
            session.close()

    def test_eligibility_validation_and_pagination(self) -> None:
        session = self.Session()
        try:
            for opportunity_id in ("synthetic-interview-1", "synthetic-interview-4", "synthetic-interview-5"):
                with self.subTest(opportunity_id=opportunity_id), self.assertRaisesRegex(TrackerInterviewError, "only for Applied"):
                    list_opportunity_interviews(session, opportunity_id)
            with self.assertRaisesRegex(TrackerInterviewError, "opportunity not found"):
                list_opportunity_interviews(session, "missing")
            for scheduled_at in ("2026-10-01T12:00:00", "bad-date", 123):
                with self.subTest(scheduled_at=scheduled_at), self.assertRaisesRegex(TrackerInterviewError, "scheduled_at"):
                    create_tracker_interview(session, "synthetic-interview-2", {"scheduled_at": scheduled_at}, self.now, request_key=f"bad-date-{scheduled_at}")
            for fields, expected in (
                ({"interview_type": "coffee"}, "unknown interview_type"),
                ({"interview_format": "office"}, "unknown interview_format"),
                ({"outcome": "maybe"}, "unknown outcome"),
                ({"round_label": "x" * 65}, "round_label cannot exceed"),
                ({"preparation_notes": "x" * 4001}, "preparation_notes cannot exceed"),
            ):
                with self.subTest(fields=tuple(fields)), self.assertRaisesRegex(TrackerInterviewError, expected):
                    create_tracker_interview(session, "synthetic-interview-2", fields, self.now, request_key=f"invalid-{len(fields)}-{expected}")
            with self.assertRaisesRegex(TrackerInterviewError, "idempotency_key is required"):
                create_tracker_interview(session, "synthetic-interview-2", {}, self.now, request_key=" ")

            for index in range(3):
                create_tracker_interview(session, "synthetic-interview-2", {"round_label": f"Round {index}"}, self.now, request_key=f"page-{index}")
            session.commit()
            page = list_opportunity_interviews(session, "synthetic-interview-2", page=2, page_size=1)
            capped = list_opportunity_interviews(session, "synthetic-interview-2", page_size=500)
            self.assertEqual((page["total"], len(page["items"]), page["page_size"]), (3, 1, 1))
            self.assertEqual(capped["page_size"], 100)
        finally:
            session.close()

    def test_update_clear_complete_noop_replay_conflict_and_rollback(self) -> None:
        session = self.Session()
        try:
            created = create_tracker_interview(session, "synthetic-interview-2", {"outcome": "pending", "interviewer_name": "Name"}, self.now, request_key="update-create")
            session.commit()
            interview_id = created.interview["id"]
            updated = update_tracker_interview(
                session,
                "synthetic-interview-2",
                interview_id,
                {"interviewer_name": None, "scheduled_at": "2026-10-03T09:00:00Z"},
                self.now + timedelta(minutes=1),
                request_key="update-1",
            )
            self.assertTrue(updated.changed)
            self.assertIsNone(updated.interview["interviewer_name"])
            self.assertEqual(updated.interview["scheduled_at"], "2026-10-03T09:00:00Z")
            session.commit()
            no_op = update_tracker_interview(session, "synthetic-interview-2", interview_id, {"interviewer_name": None}, self.now, request_key="ignored-noop-key")
            self.assertFalse(no_op.changed)
            completed = update_tracker_interview(session, "synthetic-interview-2", interview_id, {"outcome": "passed"}, self.now + timedelta(minutes=2), request_key="complete-1")
            self.assertTrue(completed.changed)
            session.commit()
            events = session.query(FounderActivityEventRecord).filter_by(opportunity_id="synthetic-interview-2").order_by(FounderActivityEventRecord.event_at.asc()).all()
            self.assertEqual([event.action_type for event in events], ["interview_added", "interview_updated", "interview_completed"])
            self.assertTrue(all(json.loads(event.metadata_json) == {"interview_id": interview_id} for event in events))
            replay = update_tracker_interview(session, "synthetic-interview-2", interview_id, {"outcome": "passed"}, self.now, request_key="complete-1")
            self.assertFalse(replay.changed)
            with self.assertRaisesRegex(TrackerInterviewError, "already used"):
                update_tracker_interview(session, "synthetic-interview-2", interview_id, {"round_label": "Other"}, self.now, request_key="complete-1")
            other = create_tracker_interview(session, "synthetic-interview-3", {}, self.now, request_key="other-opportunity-key")
            session.commit()
            with self.assertRaisesRegex(TrackerInterviewError, "already used"):
                create_tracker_interview(session, "synthetic-interview-2", {}, self.now, request_key="other-opportunity-key")

            before = session.query(FounderActivityEventRecord).count()
            rolled_back = create_tracker_interview(session, "synthetic-interview-3", {"round_label": "Rollback"}, self.now, request_key="rollback-interview")
            self.assertTrue(rolled_back.changed)
            session.rollback()
            self.assertEqual(session.query(FounderInterviewRecord).filter_by(round_label="Rollback").count(), 0)
            self.assertEqual(session.query(FounderActivityEventRecord).count(), before)
        finally:
            session.close()

    def test_upcoming_summary_excludes_notes_closed_and_non_applied_items(self) -> None:
        session = self.Session()
        try:
            upcoming = create_tracker_interview(
                session, "synthetic-interview-2",
                {"scheduled_at": "2026-10-01T10:00:00Z", "preparation_notes": "DO NOT LEAK PREP", "post_interview_notes": "DO NOT LEAK DEBRIEF"},
                self.now, request_key="upcoming-1",
            )
            create_tracker_interview(session, "synthetic-interview-2", {"scheduled_at": "2026-09-24T10:00:00Z"}, self.now, request_key="past-1")
            create_tracker_interview(session, "synthetic-interview-2", {"scheduled_at": "2026-10-02T10:00:00Z", "outcome": "cancelled"}, self.now, request_key="cancelled-1")
            session.add(FounderInterviewRecord(
                id="closed-job-interview",
                opportunity_id="synthetic-interview-4",
                scheduled_at=datetime(2026, 10, 3, 10),
                outcome="pending",
                created_at=datetime(2026, 9, 25, 9),
                updated_at=datetime(2026, 9, 25, 9),
            ))
            session.commit()
            result = list_tracker_interviews(session, "upcoming", now=self.now, page_size=500)
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["page_size"], 100)
            item = result["items"][0]
            self.assertEqual(item["id"], upcoming.interview["id"])
            self.assertNotIn("preparation_notes", item)
            self.assertNotIn("post_interview_notes", item)
            self.assertNotIn("DO NOT LEAK", json.dumps(result))
            with self.assertRaisesRegex(TrackerInterviewError, "unknown interview bucket"):
                list_tracker_interviews(session, "past", now=self.now)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
