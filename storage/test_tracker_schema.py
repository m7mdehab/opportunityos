from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from storage.models import (
    Base,
    FounderActivityEventRecord,
    FounderApplicationDetailRecord,
    FounderFollowUpRecord,
    FounderInterviewRecord,
    FounderTrackerDocumentRecord,
    FounderTrackerNoteRecord,
    FounderTrackerSnapshotRecord,
    FounderTriageStateRecord,
)


class FounderTrackerSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_tracker_tables_and_transition_timestamp_columns_exist(self) -> None:
        inspector = inspect(self.engine)
        tables = set(inspector.get_table_names())
        self.assertTrue({
            "founder_triage_states",
            "founder_activity_events",
            "founder_application_details",
            "founder_tracker_notes",
            "founder_follow_ups",
            "founder_interviews",
            "founder_tracker_documents",
            "founder_tracker_snapshots",
        }.issubset(tables))

        triage_columns = {column["name"] for column in inspector.get_columns("founder_triage_states")}
        self.assertTrue({"state", "saved_at", "applied_at", "closed_at", "updated_at"}.issubset(triage_columns))
        self.assertEqual(inspector.get_check_constraints("founder_triage_states"), [])

    def test_timeline_idempotency_and_query_indexes_exist(self) -> None:
        inspector = inspect(self.engine)
        self.assertIn(
            "ix_founder_activity_events_opportunity_event_at",
            {item["name"] for item in inspector.get_indexes("founder_activity_events")},
        )
        self.assertIn(
            "ix_founder_triage_states_state_updated_at",
            {item["name"] for item in inspector.get_indexes("founder_triage_states")},
        )
        self.assertIn(
            "ix_founder_follow_ups_opportunity_due_completed",
            {item["name"] for item in inspector.get_indexes("founder_follow_ups")},
        )

        session = self.Session()
        try:
            event_time = datetime(2026, 9, 25, tzinfo=timezone.utc)
            session.add_all([
                FounderActivityEventRecord(
                    id="event-one", opportunity_id="opp-one", action_type="saved",
                    event_at=event_time, idempotency_key="save-once",
                ),
                FounderActivityEventRecord(
                    id="event-two", opportunity_id="opp-two", action_type="saved",
                    event_at=event_time, idempotency_key="save-once",
                ),
            ])
            with self.assertRaises(IntegrityError):
                session.commit()
        finally:
            session.rollback()
            session.close()

    def test_tracker_metadata_and_cold_snapshot_use_small_fields_and_restrict_deletes(self) -> None:
        inspector = inspect(self.engine)
        self.assertEqual(
            [column["name"] for column in inspector.get_columns("founder_application_details")],
            [
                "opportunity_id", "application_method", "application_reference",
                "selected_cv_document_id", "selected_cover_letter_document_id", "updated_at",
            ],
        )
        self.assertIn("note_text", {column["name"] for column in inspector.get_columns("founder_tracker_notes")})
        self.assertIn("completed_at", {column["name"] for column in inspector.get_columns("founder_follow_ups")})
        self.assertIn("preparation_notes", {column["name"] for column in inspector.get_columns("founder_interviews")})
        self.assertIn("document_id", {column["name"] for column in inspector.get_columns("founder_tracker_documents")})

        snapshot_columns = {column["name"] for column in inspector.get_columns("founder_tracker_snapshots")}
        self.assertIn("artifact_cache_key", snapshot_columns)
        self.assertIn("content_hash", snapshot_columns)
        self.assertIn("priority_score", snapshot_columns)
        self.assertNotIn("description", snapshot_columns)
        foreign_keys = inspector.get_foreign_keys("founder_tracker_snapshots")
        self.assertEqual(
            {tuple(fk["constrained_columns"]): fk["options"].get("ondelete") for fk in foreign_keys},
            {("opportunity_id",): "RESTRICT", ("artifact_cache_key",): "RESTRICT"},
        )

    def test_legacy_triage_values_remain_valid_during_additive_transition(self) -> None:
        session = self.Session()
        try:
            session.add(
                FounderTriageStateRecord(
                    opportunity_id="legacy-opportunity",
                    state="dismissed",
                    snoozed_until=None,
                    updated_at=datetime(2026, 9, 25),
                )
            )
            session.commit()
            row = session.get(FounderTriageStateRecord, "legacy-opportunity")
            self.assertEqual(row.state, "dismissed")
            self.assertIsNone(row.saved_at)
            self.assertIsNone(row.applied_at)
            self.assertIsNone(row.closed_at)
        finally:
            session.close()

    def test_tracker_model_constructors_accept_minimal_rows(self) -> None:
        now = datetime(2026, 9, 25, tzinfo=timezone.utc)
        self.assertIsNotNone(FounderActivityEventRecord(
            id="event", opportunity_id="opp", action_type="note_added", event_at=now,
        ))
        self.assertIsNotNone(FounderApplicationDetailRecord(opportunity_id="opp", updated_at=now))
        self.assertIsNotNone(FounderTrackerNoteRecord(
            id="note", opportunity_id="opp", note_text="private synthetic note", updated_at=now,
        ))
        self.assertIsNotNone(FounderFollowUpRecord(
            id="follow-up", opportunity_id="opp", due_at=now, updated_at=now,
        ))
        self.assertIsNotNone(FounderInterviewRecord(
            id="interview", opportunity_id="opp", updated_at=now,
        ))
        self.assertIsNotNone(FounderTrackerDocumentRecord(
            id="document-link", opportunity_id="opp", document_kind="cv",
            document_id="synthetic-doc", linked_at=now,
        ))
        self.assertIsNotNone(FounderTrackerSnapshotRecord(
            id="snapshot", opportunity_id="opp", content_hash="a" * 64,
            artifact_cache_key="artifact-key", title="Synthetic job", organization="Example",
            track="employment", source_id="fixture", source_url="https://example.invalid/job",
            work_mode="remote", captured_at=now,
        ))


if __name__ == "__main__":
    unittest.main()
