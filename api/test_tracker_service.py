from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.routes_api import (
    ActionRequest,
    RestoreTrackerRequest,
    restore_action,
    submit_action,
)
from api.tracker_service import (
    TrackerTransitionError,
    list_tracker_items,
    transition_tracker_state,
)
from outbound.models import ActionStatus
from storage.models import (
    Base,
    FounderActivityEventRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
    OutboundActionRecordModel,
)


class TrackerServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        session = self.Session()
        try:
            for index in range(1, 6):
                session.add(OpportunityRecord(
                    id=f"synthetic-{index}",
                    track="employment",
                    title=f"Synthetic role {index}",
                    organization="Example employer",
                    description="Synthetic description",
                    source_id="example-source",
                    source_url=f"https://example.invalid/jobs/{index}",
                    content_hash=f"{index:064x}",
                    posted_date="2026-09-25",
                ))
            session.commit()
        finally:
            session.close()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_save_then_apply_is_idempotent_on_w23_activity_schema(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            saved = transition_tracker_state(
                session, "synthetic-1", "save", now, request_key="save-once",
            )
            session.commit()
            self.assertEqual((saved.previous_state, saved.state), ("to_review", "saved"))

            applied = transition_tracker_state(
                session, "synthetic-1", "mark_applied",
                now + timedelta(hours=1), request_key="apply-once",
            )
            session.commit()
            self.assertEqual((applied.previous_state, applied.state), ("saved", "applied"))

            replay = transition_tracker_state(
                session, "synthetic-1", "mark_applied",
                now + timedelta(hours=2), request_key="apply-once",
            )
            session.commit()
            self.assertFalse(replay.changed)
            self.assertEqual(session.get(FounderTriageStateRecord, "synthetic-1").state, "applied")
            events = (
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-1")
                .order_by(FounderActivityEventRecord.created_at.asc())
                .all()
            )
            self.assertEqual(
                [(event.action_type, event.resulting_state) for event in events],
                [("save", "saved"), ("mark_applied", "applied")],
            )
        finally:
            session.close()

    def test_reject_and_legacy_dismiss_are_distinct_tracker_states(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            transition_tracker_state(session, "synthetic-2", "reject", now, request_key="reject")
            transition_tracker_state(session, "synthetic-3", "dismiss", now + timedelta(minutes=1))
            session.commit()

            result = list_tracker_items(session, "rejected", truth_pack_hash=None)
            self.assertEqual(result["total"], 2)
            self.assertEqual(
                {item["tracker_state"] for item in result["items"]},
                {"rejected_by_founder", "dismissed"},
            )
        finally:
            session.close()

    def test_batch_action_route_contract_keeps_legacy_applied_response(self) -> None:
        session = self.Session()
        try:
            result = submit_action(
                "synthetic-4",
                ActionRequest(type="mark_applied", idempotency_key="manual-apply"),
                Response(),
                session,
            )
            self.assertEqual(result["action_state"], "submitted")
            self.assertEqual(result["tracker_state"], "applied")
            self.assertTrue(result["undo_event_id"])
            self.assertEqual(
                session.query(OutboundActionRecordModel)
                .filter_by(
                    opportunity_id="synthetic-4",
                    adapter_name="founder_attested",
                    action_status=ActionStatus.SUBMITTED.value,
                )
                .count(),
                1,
            )
        finally:
            session.close()

    def test_apply_undo_restores_to_review_and_is_idempotent(self) -> None:
        session = self.Session()
        try:
            applied = submit_action(
                "synthetic-5",
                ActionRequest(type="mark_applied", idempotency_key="undo-apply"),
                Response(),
                session,
            )
            restored = restore_action(
                "synthetic-5",
                RestoreTrackerRequest(
                    event_id=applied["undo_event_id"],
                    idempotency_key="restore-once",
                ),
                session,
            )
            self.assertEqual(restored["tracker_state"], "to_review")
            self.assertIsNone(session.get(FounderTriageStateRecord, "synthetic-5"))
            attestation = (
                session.query(OutboundActionRecordModel)
                .filter_by(opportunity_id="synthetic-5", adapter_name="founder_attested")
                .one()
            )
            self.assertEqual(attestation.action_status, ActionStatus.UNDONE.value)

            replay = restore_action(
                "synthetic-5",
                RestoreTrackerRequest(
                    event_id=applied["undo_event_id"],
                    idempotency_key="restore-once",
                ),
                session,
            )
            self.assertEqual(replay["tracker_state"], "to_review")
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-5")
                .count(),
                2,
            )
        finally:
            session.close()

    def test_undo_saved_from_snooze_restores_snooze_and_expiry(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        until = now + timedelta(days=2)
        session = self.Session()
        try:
            transition_tracker_state(
                session, "synthetic-1", "snooze", now, snoozed_until=until,
            )
            session.commit()
            saved = submit_action(
                "synthetic-1",
                ActionRequest(type="save", idempotency_key="save-from-snooze"),
                Response(),
                session,
            )
            restored = restore_action(
                "synthetic-1",
                RestoreTrackerRequest(
                    event_id=saved["undo_event_id"],
                    idempotency_key="restore-snooze",
                ),
                session,
            )
            state = session.get(FounderTriageStateRecord, "synthetic-1")
            self.assertEqual(restored["tracker_state"], "snoozed")
            self.assertEqual(state.state, "snoozed")
            self.assertEqual(state.snoozed_until.replace(tzinfo=timezone.utc), until)
        finally:
            session.close()

    def test_newer_activity_makes_undo_conflict(self) -> None:
        session = self.Session()
        try:
            saved = submit_action(
                "synthetic-2",
                ActionRequest(type="save", idempotency_key="stale-save"),
                Response(),
                session,
            )
            transition_tracker_state(
                session, "synthetic-2", "reject",
                datetime.now(timezone.utc) + timedelta(minutes=1),
            )
            session.commit()

            with self.assertRaises(HTTPException) as raised:
                restore_action(
                    "synthetic-2",
                    RestoreTrackerRequest(
                        event_id=saved["undo_event_id"],
                        idempotency_key="stale-restore",
                    ),
                    session,
                )
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(
                session.get(FounderTriageStateRecord, "synthetic-2").state,
                "rejected_by_founder",
            )
        finally:
            session.close()

    def test_pipeline_stage_mutation_is_explicitly_deferred(self) -> None:
        session = self.Session()
        try:
            with self.assertRaises(HTTPException) as raised:
                submit_action(
                    "synthetic-3",
                    ActionRequest(
                        type="set_stage",
                        stage="assessment",
                        idempotency_key="stage-deferred",
                    ),
                    Response(),
                    session,
                )
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIn("deferred", str(raised.exception.detail))
        finally:
            session.close()

    def test_tracker_buckets_exclude_untracked_jobs(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            transition_tracker_state(session, "synthetic-1", "save", now)
            transition_tracker_state(session, "synthetic-2", "mark_applied", now)
            transition_tracker_state(session, "synthetic-3", "reject", now)
            session.commit()
            result = list_tracker_items(session, "all", truth_pack_hash=None)
            self.assertEqual(result["total"], 3)
            self.assertNotIn("synthetic-4", {item["id"] for item in result["items"]})
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
