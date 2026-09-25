import json
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from api.tracker_activity_service import MAX_PAGE_SIZE, TrackerActivityError, list_tracker_activity
from storage.models import Base, FounderActivityEventRecord, OpportunityRecord


class TrackerActivityServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        session = self.Session()
        session.add(OpportunityRecord(
            id="synthetic-timeline-job",
            track="employment",
            title="Synthetic activity role",
            organization="Example employer",
            description="Synthetic description that must not enter the event projection",
            source_id="example-source",
            source_url="https://example.invalid/jobs/timeline",
            content_hash="e" * 64,
            posted_date="2026-09-25",
        ))
        session.commit()
        session.close()

    def tearDown(self) -> None:
        self.engine.dispose()

    def add_event(self, event_id: str, event_at: datetime, *, metadata: str = "{}", idempotency: str | None = None) -> None:
        session = self.Session()
        session.add(FounderActivityEventRecord(
            id=event_id,
            opportunity_id="synthetic-timeline-job",
            action_type="application_stage_updated",
            from_state="applied",
            to_state="interviewing",
            event_at=event_at,
            metadata_json=metadata,
            idempotency_key=idempotency,
            created_at=event_at,
        ))
        session.commit()
        session.close()

    def test_bounded_newest_first_pages_ties_and_utc_projection(self) -> None:
        for index in range(103):
            self.add_event(f"timeline-{index:03d}", self.now + timedelta(seconds=index))
        self.add_event("timeline-tie-a", self.now + timedelta(days=1))
        self.add_event("timeline-tie-b", self.now + timedelta(days=1))
        session = self.Session()
        try:
            first = list_tracker_activity(session, "synthetic-timeline-job", page_size=500)
            self.assertEqual(first["page_size"], MAX_PAGE_SIZE)
            self.assertEqual(first["total"], 105)
            self.assertEqual(len(first["items"]), 100)
            self.assertEqual([item["id"] for item in first["items"][:2]], ["timeline-tie-b", "timeline-tie-a"])
            self.assertEqual(first["items"][2]["id"], "timeline-102")
            self.assertEqual(first["items"][0]["event_at"], "2026-09-26T12:00:00Z")
            second = list_tracker_activity(session, "synthetic-timeline-job", page=2, page_size=100)
            self.assertEqual(len(second["items"]), 5)
            self.assertEqual(second["items"][-1]["id"], "timeline-000")
        finally:
            session.close()

    def test_response_omits_metadata_keys_and_content(self) -> None:
        self.add_event(
            "timeline-private-sentinel",
            self.now,
            metadata=json.dumps({"note_id": "synthetic-note-id", "note_text": "PRIVATE NOTE BODY"}),
            idempotency="synthetic-idempotency-secret",
        )
        statements: list[str] = []

        def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
            if "founder_activity_events" in statement.lower():
                statements.append(statement.lower())

        event.listen(self.engine, "before_cursor_execute", capture)
        session = self.Session()
        try:
            result = list_tracker_activity(session, "synthetic-timeline-job")
            self.assertEqual(set(result["items"][0]), {"id", "action_type", "from_state", "to_state", "event_at"})
            serialized = json.dumps(result)
            self.assertNotIn("metadata_json", serialized)
            self.assertNotIn("idempotency_key", serialized)
            self.assertNotIn("PRIVATE NOTE BODY", serialized)
            self.assertNotIn("synthetic-note-id", serialized)
            self.assertNotIn("synthetic-idempotency-secret", serialized)
            event_selects = [statement for statement in statements if "count(" not in statement]
            self.assertTrue(event_selects)
            self.assertNotIn("metadata_json", event_selects[-1])
            self.assertNotIn("idempotency_key", event_selects[-1])
        finally:
            session.close()
            event.remove(self.engine, "before_cursor_execute", capture)

    def test_empty_existing_opportunity_returns_empty_page_without_writes(self) -> None:
        session = self.Session()
        try:
            before = session.query(FounderActivityEventRecord).count()
            result = list_tracker_activity(session, "synthetic-timeline-job")
            self.assertEqual((result["total"], result["items"]), (0, []))
            self.assertEqual(session.query(FounderActivityEventRecord).count(), before)
            self.assertFalse(session.new)
            self.assertFalse(session.dirty)
        finally:
            session.close()

    def test_missing_opportunity_is_rejected(self) -> None:
        session = self.Session()
        try:
            with self.assertRaisesRegex(TrackerActivityError, "opportunity not found"):
                list_tracker_activity(session, "missing-synthetic-opportunity")
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
