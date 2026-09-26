from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.tracker_followups_service import (
    TrackerFollowUpError,
    create_tracker_follow_up,
    list_opportunity_follow_ups,
    list_tracker_follow_ups,
    update_tracker_follow_up,
)
from storage.models import (
    Base,
    FounderActivityEventRecord,
    FounderFollowUpRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
)


class TrackerFollowUpsServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            states = ("saved", "applied", "interviewing", "rejected_by_employer", "to_review")
            for index, state in enumerate(states, start=1):
                opportunity_id = f"synthetic-follow-up-{index}"
                session.add(OpportunityRecord(
                    id=opportunity_id,
                    track="employment",
                    title=f"Synthetic role {index}",
                    organization="Example employer",
                    description="Synthetic description",
                    source_id="example-source",
                    source_url=f"https://example.invalid/jobs/{index}",
                    content_hash=f"{index + 200:064x}",
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

    def test_create_replay_and_private_event_metadata(self) -> None:
        session = self.Session()
        try:
            first = create_tracker_follow_up(
                session,
                "synthetic-follow-up-1",
                "2026-09-25",
                "  Ask recruiter about interview timeline  ",
                self.now,
                request_key="create-follow-up-1",
            )
            self.assertTrue(first.changed)
            self.assertEqual(first.follow_up["note_text"], "Ask recruiter about interview timeline")
            self.assertEqual(first.follow_up["status"], "due_today")
            session.commit()

            replay = create_tracker_follow_up(
                session,
                "synthetic-follow-up-1",
                "2026-09-25",
                "Ask recruiter about interview timeline",
                self.now + timedelta(minutes=1),
                request_key="create-follow-up-1",
            )
            self.assertFalse(replay.changed)
            self.assertEqual(replay.follow_up["id"], first.follow_up["id"])
            session.commit()

            events = session.query(FounderActivityEventRecord).filter_by(
                opportunity_id="synthetic-follow-up-1",
            ).all()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].action_type, "follow_up_created")
            self.assertEqual((events[0].from_state, events[0].to_state), ("saved", "saved"))
            self.assertEqual(json.loads(events[0].metadata_json), {"follow_up_id": first.follow_up["id"]})
            self.assertNotIn("recruiter", events[0].metadata_json)
        finally:
            session.close()

    def test_due_today_overdue_upcoming_groups_are_bounded_and_private(self) -> None:
        session = self.Session()
        try:
            created = {}
            for suffix, due_date, note in (
                ("past", "2026-09-24", "private overdue note"),
                ("today", "2026-09-25", "private due-today note"),
                ("future", "2026-09-26", "private upcoming note"),
            ):
                result = create_tracker_follow_up(
                    session,
                    "synthetic-follow-up-1",
                    due_date,
                    note,
                    self.now,
                    request_key=f"create-{suffix}",
                )
                created[suffix] = result.follow_up["id"]
            closed_item = FounderFollowUpRecord(
                id="closed-follow-up",
                opportunity_id="synthetic-follow-up-4",
                due_at=datetime(2026, 9, 24),
                completed_at=None,
                note_text="closed job private note",
                created_at=datetime(2026, 9, 25, 9),
                updated_at=datetime(2026, 9, 25, 9),
            )
            session.add(closed_item)
            session.commit()

            overdue = list_tracker_follow_ups(session, "overdue", today=date(2026, 9, 25), page_size=1)
            due_today = list_tracker_follow_ups(session, "due_today", today=date(2026, 9, 25))
            upcoming = list_tracker_follow_ups(session, "upcoming", today=date(2026, 9, 25))
            self.assertEqual((overdue["total"], overdue["page_size"]), (1, 1))
            self.assertEqual(overdue["items"][0]["id"], created["past"])
            self.assertEqual(due_today["items"][0]["id"], created["today"])
            self.assertEqual(upcoming["items"][0]["id"], created["future"])
            self.assertNotIn("note_text", overdue["items"][0])
            self.assertNotIn("closed-follow-up", {item["id"] for item in overdue["items"]})
        finally:
            session.close()

    def test_update_completion_reopen_replay_and_noop_event_counts(self) -> None:
        session = self.Session()
        try:
            created = create_tracker_follow_up(
                session, "synthetic-follow-up-2", "2026-09-25", None, self.now,
                request_key="create-for-updates",
            )
            session.commit()
            follow_up_id = created.follow_up["id"]

            edited = update_tracker_follow_up(
                session,
                "synthetic-follow-up-2",
                follow_up_id,
                self.now + timedelta(hours=1),
                request_key="edit-follow-up",
                due_date="2026-09-26",
                note_text=" Prepare documents ",
                note_text_provided=True,
            )
            self.assertTrue(edited.changed)
            self.assertEqual((edited.follow_up["due_date"], edited.follow_up["note_text"]), ("2026-09-26", "Prepare documents"))
            session.commit()

            no_op = update_tracker_follow_up(
                session,
                "synthetic-follow-up-2",
                follow_up_id,
                self.now + timedelta(hours=2),
                request_key="no-op-edit-follow-up",
                due_date="2026-09-26",
                note_text="Prepare documents",
                note_text_provided=True,
            )
            self.assertFalse(no_op.changed)
            session.commit()

            completed = update_tracker_follow_up(
                session, "synthetic-follow-up-2", follow_up_id, self.now + timedelta(hours=3),
                request_key="complete-follow-up", completed=True,
            )
            self.assertTrue(completed.changed)
            self.assertEqual(completed.follow_up["status"], "completed")
            session.commit()
            replay = update_tracker_follow_up(
                session, "synthetic-follow-up-2", follow_up_id, self.now + timedelta(hours=4),
                request_key="complete-follow-up", completed=True,
            )
            self.assertFalse(replay.changed)
            session.commit()

            reopened = update_tracker_follow_up(
                session, "synthetic-follow-up-2", follow_up_id, self.now + timedelta(hours=5),
                request_key="reopen-follow-up", completed=False,
            )
            self.assertTrue(reopened.changed)
            self.assertIsNone(reopened.follow_up["completed_at"])
            session.commit()

            events = session.query(FounderActivityEventRecord).filter_by(
                opportunity_id="synthetic-follow-up-2",
            ).order_by(FounderActivityEventRecord.event_at.asc()).all()
            self.assertEqual(
                [event.action_type for event in events],
                ["follow_up_created", "follow_up_updated", "follow_up_completed", "follow_up_reopened"],
            )
            self.assertEqual(
                [json.loads(event.metadata_json) for event in events],
                [{"follow_up_id": follow_up_id}] * 4,
            )
            self.assertNotIn("Prepare documents", " ".join(event.metadata_json for event in events))
        finally:
            session.close()

    def test_eligibility_validation_pagination_and_idempotency_conflicts(self) -> None:
        session = self.Session()
        try:
            with self.assertRaisesRegex(TrackerFollowUpError, "only for Saved and Applied"):
                list_opportunity_follow_ups(session, "synthetic-follow-up-5", today=date(2026, 9, 25))
            with self.assertRaisesRegex(TrackerFollowUpError, "opportunity not found"):
                list_opportunity_follow_ups(session, "missing", today=date(2026, 9, 25))
            for due_date in ("2026-2-5", "not-a-date", "2026-02-30"):
                with self.subTest(due_date=due_date), self.assertRaisesRegex(TrackerFollowUpError, "due_date"):
                    create_tracker_follow_up(
                        session, "synthetic-follow-up-1", due_date, None, self.now,
                        request_key=f"bad-{due_date}",
                    )
            with self.assertRaisesRegex(TrackerFollowUpError, "note_text cannot exceed"):
                create_tracker_follow_up(
                    session, "synthetic-follow-up-1", "2026-09-25", "x" * 4001, self.now,
                    request_key="too-long-note",
                )
            with self.assertRaisesRegex(TrackerFollowUpError, "idempotency_key is required"):
                create_tracker_follow_up(
                    session, "synthetic-follow-up-1", "2026-09-25", None, self.now,
                    request_key=" ",
                )

            created = []
            for index in range(3):
                result = create_tracker_follow_up(
                    session, "synthetic-follow-up-1", f"2026-09-{25 + index:02d}", None, self.now,
                    request_key=f"page-{index}",
                )
                created.append(result.follow_up["id"])
            session.commit()
            page = list_opportunity_follow_ups(
                session, "synthetic-follow-up-1", today=date(2026, 9, 25), page=2, page_size=1,
            )
            capped = list_opportunity_follow_ups(
                session, "synthetic-follow-up-1", today=date(2026, 9, 25), page_size=1000,
            )
            self.assertEqual((page["total"], len(page["items"]), page["page_size"]), (3, 1, 1))
            self.assertEqual(capped["page_size"], 100)

            other = create_tracker_follow_up(
                session, "synthetic-follow-up-2", "2026-09-25", None, self.now,
                request_key="shared-follow-up-key",
            )
            session.commit()
            with self.assertRaisesRegex(TrackerFollowUpError, "already used"):
                create_tracker_follow_up(
                    session, "synthetic-follow-up-1", "2026-09-25", None, self.now,
                    request_key="shared-follow-up-key",
                )
            with self.assertRaisesRegex(TrackerFollowUpError, "already used"):
                update_tracker_follow_up(
                    session, "synthetic-follow-up-2", other.follow_up["id"], self.now,
                    request_key="shared-follow-up-key", completed=True,
                )
        finally:
            session.close()

    def test_follow_up_row_and_event_rollback_together(self) -> None:
        session = self.Session()
        try:
            created = create_tracker_follow_up(
                session,
                "synthetic-follow-up-3",
                "2026-09-25",
                "Will roll back",
                self.now,
                request_key="rollback-follow-up",
            )
            self.assertTrue(created.changed)
            session.rollback()
            self.assertEqual(session.query(FounderFollowUpRecord).filter_by(
                opportunity_id="synthetic-follow-up-3",
            ).count(), 0)
            self.assertEqual(session.query(FounderActivityEventRecord).filter_by(
                opportunity_id="synthetic-follow-up-3",
            ).count(), 0)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
