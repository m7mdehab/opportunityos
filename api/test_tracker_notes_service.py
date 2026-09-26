from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.tracker_notes_service import (
    TrackerNoteError,
    create_tracker_note,
    list_tracker_notes,
    update_tracker_note,
)
from storage.models import (
    Base,
    FounderActivityEventRecord,
    FounderTrackerNoteRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
)


class TrackerNotesServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            for index in range(1, 4):
                session.add(OpportunityRecord(
                    id=f"synthetic-note-{index}",
                    track="employment",
                    title=f"Synthetic role {index}",
                    organization="Example employer",
                    description="Synthetic description",
                    source_id="example-source",
                    source_url=f"https://example.invalid/jobs/{index}",
                    content_hash=f"{index + 100:064x}",
                    posted_date="2026-09-25",
                ))
            session.flush()
            session.add(FounderTriageStateRecord(
                opportunity_id="synthetic-note-1",
                state="applied",
                created_at=self.now,
                updated_at=self.now,
            ))
            session.add(FounderTriageStateRecord(
                opportunity_id="synthetic-note-2",
                state="interviewing",
                created_at=self.now,
                updated_at=self.now,
            ))
            session.add(FounderTriageStateRecord(
                opportunity_id="synthetic-note-3",
                state="saved",
                created_at=self.now,
                updated_at=self.now,
            ))
            session.commit()
        finally:
            session.close()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_create_replay_and_atomic_note_event_metadata_is_private(self) -> None:
        session = self.Session()
        try:
            first = create_tracker_note(
                session,
                "synthetic-note-1",
                "  Call recruiter after the screen  ",
                self.now,
                request_key="create-note-1",
            )
            self.assertTrue(first.changed)
            self.assertEqual(first.note["note_text"], "Call recruiter after the screen")
            session.commit()

            replay = create_tracker_note(
                session,
                "synthetic-note-1",
                "Call recruiter after the screen",
                self.now + timedelta(minutes=1),
                request_key="create-note-1",
            )
            self.assertFalse(replay.changed)
            self.assertEqual(replay.note["id"], first.note["id"])
            session.commit()

            events = session.query(FounderActivityEventRecord).filter_by(
                opportunity_id="synthetic-note-1",
            ).all()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].action_type, "tracker_note_created")
            self.assertEqual((events[0].from_state, events[0].to_state), ("applied", "applied"))
            metadata = json.loads(events[0].metadata_json)
            self.assertEqual(metadata, {"note_id": first.note["id"]})
            self.assertNotIn("Call recruiter", events[0].metadata_json)
            self.assertEqual(
                session.query(FounderTrackerNoteRecord).filter_by(opportunity_id="synthetic-note-1").count(),
                1,
            )
        finally:
            session.close()

    def test_edit_archive_and_noop_mutations_emit_one_event_per_real_change(self) -> None:
        session = self.Session()
        try:
            created = create_tracker_note(
                session, "synthetic-note-2", "Prepare portfolio examples", self.now,
                request_key="create-2",
            )
            session.commit()
            note_id = created.note["id"]

            edited = update_tracker_note(
                session, "synthetic-note-2", note_id, self.now + timedelta(minutes=2),
                request_key="edit-2", note_text="Prepare two portfolio examples",
            )
            self.assertTrue(edited.changed)
            session.commit()

            no_op_edit = update_tracker_note(
                session, "synthetic-note-2", note_id, self.now + timedelta(minutes=3),
                request_key="edit-no-op", note_text="Prepare two portfolio examples",
            )
            self.assertFalse(no_op_edit.changed)
            session.commit()

            archived = update_tracker_note(
                session, "synthetic-note-2", note_id, self.now + timedelta(minutes=4),
                request_key="archive-2", archive=True,
            )
            self.assertTrue(archived.changed)
            self.assertIsNotNone(archived.note["archived_at"])
            session.commit()

            archive_replay = update_tracker_note(
                session, "synthetic-note-2", note_id, self.now + timedelta(minutes=5),
                request_key="archive-2", archive=True,
            )
            self.assertFalse(archive_replay.changed)
            session.commit()

            active = list_tracker_notes(session, "synthetic-note-2")
            self.assertEqual((active["total"], active["items"]), (0, []))
            events = session.query(FounderActivityEventRecord).filter_by(
                opportunity_id="synthetic-note-2",
            ).order_by(FounderActivityEventRecord.event_at.asc()).all()
            self.assertEqual(
                [event.action_type for event in events],
                ["tracker_note_created", "tracker_note_updated", "tracker_note_archived"],
            )
            self.assertTrue(all(event.from_state == event.to_state == "interviewing" for event in events))
            self.assertTrue(all("Prepare" not in event.metadata_json for event in events))
            with self.assertRaisesRegex(TrackerNoteError, "archived notes cannot be edited"):
                update_tracker_note(
                    session, "synthetic-note-2", note_id, self.now + timedelta(minutes=6),
                    request_key="edit-archived", note_text="Edit an archived note",
                )
            session.rollback()
            self.assertEqual(
                session.query(FounderActivityEventRecord).filter_by(
                    opportunity_id="synthetic-note-2",
                ).count(),
                3,
            )
        finally:
            session.close()

    def test_listing_is_bounded_paginated_and_scoped_to_opportunity(self) -> None:
        session = self.Session()
        try:
            for index in range(3):
                create_tracker_note(
                    session,
                    "synthetic-note-1",
                    f"Synthetic note {index}",
                    self.now + timedelta(minutes=index),
                    request_key=f"page-{index}",
                )
            create_tracker_note(
                session, "synthetic-note-2", "Another application's note", self.now,
                request_key="other-app",
            )
            session.commit()

            first = list_tracker_notes(session, "synthetic-note-1", page=1, page_size=2)
            second = list_tracker_notes(session, "synthetic-note-1", page=2, page_size=2)
            capped = list_tracker_notes(session, "synthetic-note-1", page_size=1000)
            self.assertEqual((first["total"], first["page_size"], len(first["items"])), (3, 2, 2))
            self.assertEqual((second["total"], len(second["items"])), (3, 1))
            self.assertEqual(capped["page_size"], 100)
            self.assertTrue(all(item["opportunity_id"] == "synthetic-note-1" for item in first["items"]))
        finally:
            session.close()

    def test_untracked_rows_and_wrong_note_ownership_are_rejected(self) -> None:
        session = self.Session()
        try:
            with self.assertRaisesRegex(TrackerNoteError, "not an application-tracked"):
                list_tracker_notes(session, "synthetic-note-3")
            with self.assertRaisesRegex(TrackerNoteError, "not an application-tracked"):
                create_tracker_note(
                    session, "synthetic-note-3", "No saved-job note", self.now,
                    request_key="saved-note",
                )
            note = create_tracker_note(
                session, "synthetic-note-1", "Owned by first role", self.now,
                request_key="ownership-create",
            )
            session.commit()
            with self.assertRaisesRegex(TrackerNoteError, "note not found"):
                update_tracker_note(
                    session, "synthetic-note-2", note.note["id"], self.now,
                    request_key="wrong-owner", note_text="Cannot access another role note",
                )
            session.rollback()
        finally:
            session.close()

    def test_invalid_text_payload_and_idempotency_reuse_fail_without_events(self) -> None:
        session = self.Session()
        try:
            for invalid in ("", "  ", "x" * 4001):
                with self.assertRaises(TrackerNoteError):
                    create_tracker_note(
                        session, "synthetic-note-1", invalid, self.now,
                        request_key=f"invalid-{len(invalid)}",
                    )
                session.rollback()

            with self.assertRaisesRegex(TrackerNoteError, "idempotency_key is required"):
                create_tracker_note(
                    session, "synthetic-note-1", "Missing key", self.now,
                    request_key=" ",
                )
            session.rollback()
            with self.assertRaisesRegex(TrackerNoteError, "idempotency_key is too long"):
                create_tracker_note(
                    session, "synthetic-note-1", "Long key", self.now,
                    request_key="k" * 129,
                )
            session.rollback()

            created = create_tracker_note(
                session, "synthetic-note-1", "Original note", self.now,
                request_key="same-key",
            )
            session.commit()
            with self.assertRaisesRegex(TrackerNoteError, "already used"):
                update_tracker_note(
                    session,
                    "synthetic-note-1",
                    created.note["id"],
                    self.now + timedelta(minutes=1),
                    request_key="same-key",
                    note_text="Different operation using same key",
                )
            session.rollback()
            self.assertEqual(
                session.query(FounderActivityEventRecord).filter_by(
                    opportunity_id="synthetic-note-1",
                ).count(),
                1,
            )
        finally:
            session.close()

    def test_note_and_event_share_the_callers_transaction(self) -> None:
        session = self.Session()
        try:
            create_tracker_note(
                session, "synthetic-note-1", "Rolled-back note", self.now,
                request_key="rolled-back",
            )
            session.rollback()
        finally:
            session.close()

        verify = self.Session()
        try:
            self.assertEqual(
                verify.query(FounderTrackerNoteRecord).filter_by(
                    opportunity_id="synthetic-note-1",
                ).count(),
                0,
            )
            self.assertEqual(
                verify.query(FounderActivityEventRecord).filter_by(
                    opportunity_id="synthetic-note-1",
                ).count(),
                0,
            )
        finally:
            verify.close()


if __name__ == "__main__":
    unittest.main()
