from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import Response
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.tracker_service import (
    TrackerTransitionError,
    list_tracker_items,
    transition_tracker_state,
)
from api.routes_api import ActionRequest, submit_action
from api.routes_api import RestoreTrackerRequest, restore_action
from outbound.models import ActionStatus
from storage.models import (
    Base,
    FounderActivityEventRecord,
    FounderTriageStateRecord,
    IdempotencyReservationRecord,
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

    def test_save_then_explicit_apply_keeps_one_event_per_transition(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            saved = transition_tracker_state(
                session, "synthetic-1", "save", now, request_key="save-once",
            )
            self.assertTrue(saved.changed)
            self.assertEqual((saved.previous_state, saved.state), ("to_review", "saved"))
            session.commit()

            applied = transition_tracker_state(
                session,
                "synthetic-1",
                "mark_applied",
                now + timedelta(hours=1),
                request_key="apply-once",
            )
            self.assertTrue(applied.changed)
            self.assertEqual((applied.previous_state, applied.state), ("saved", "applied"))
            session.commit()

            repeated = transition_tracker_state(
                session,
                "synthetic-1",
                "mark_applied",
                now + timedelta(hours=2),
                request_key="apply-once",
            )
            self.assertFalse(repeated.changed)
            session.commit()

            state = session.get(FounderTriageStateRecord, "synthetic-1")
            events = (
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-1")
                .order_by(FounderActivityEventRecord.event_at.asc())
                .all()
            )
            self.assertEqual(state.state, "applied")
            self.assertEqual(state.saved_at.replace(tzinfo=timezone.utc), now)
            self.assertEqual(state.applied_at.replace(tzinfo=timezone.utc), now + timedelta(hours=1))
            self.assertEqual(len(events), 2)
            self.assertEqual(
                [(event.action_type, event.from_state, event.to_state) for event in events],
                [("saved", "to_review", "saved"), ("applied", "saved", "applied")],
            )
        finally:
            session.close()

    def test_repeat_action_is_a_noop_and_reject_after_apply_is_invalid(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            transition_tracker_state(session, "synthetic-2", "save", now)
            session.commit()
            repeated = transition_tracker_state(
                session, "synthetic-2", "save", now + timedelta(minutes=1),
            )
            self.assertFalse(repeated.changed)
            session.commit()

            transition_tracker_state(
                session, "synthetic-2", "mark_applied", now + timedelta(minutes=2),
            )
            session.commit()
            with self.assertRaises(TrackerTransitionError):
                transition_tracker_state(
                    session, "synthetic-2", "save", now + timedelta(minutes=3),
                )
            session.rollback()
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-2")
                .count(),
                2,
            )
        finally:
            session.close()

    def test_failed_action_commit_leaves_no_triage_state_or_activity_event(self) -> None:
        session = self.Session()
        try:
            with patch.object(session, "commit", side_effect=RuntimeError("synthetic commit failure")):
                with self.assertRaisesRegex(RuntimeError, "synthetic commit failure"):
                    submit_action(
                        "synthetic-1",
                        ActionRequest(type="save", idempotency_key="failed-save"),
                        Response(),
                        session,
                    )
            session.rollback()

            self.assertIsNone(session.get(FounderTriageStateRecord, "synthetic-1"))
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-1")
                .count(),
                0,
            )
        finally:
            session.close()

    def test_reject_is_distinct_from_legacy_dismiss_and_is_idempotent(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            first = transition_tracker_state(
                session, "synthetic-3", "reject", now, request_key="reject-once",
            )
            self.assertEqual(first.state, "rejected_by_founder")
            session.commit()
            again = transition_tracker_state(
                session, "synthetic-3", "reject", now + timedelta(minutes=1),
                request_key="reject-once",
            )
            self.assertFalse(again.changed)
            session.commit()

            legacy = transition_tracker_state(
                session, "synthetic-4", "dismiss", now,
            )
            self.assertEqual(legacy.state, "dismissed")
            session.commit()

            rejected = list_tracker_items(
                session, "rejected", truth_pack_hash=None,
            )
            self.assertEqual(rejected["total"], 2)
            self.assertEqual(
                {item["tracker_state"] for item in rejected["items"]},
                {"rejected_by_founder", "dismissed"},
            )
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-3")
                .count(),
                1,
            )
        finally:
            session.close()

    def test_tracker_buckets_are_paginated_by_state_and_exclude_to_review(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            actions = [
                ("synthetic-1", "save"),
                ("synthetic-2", "save"),
                ("synthetic-3", "mark_applied"),
                ("synthetic-4", "reject"),
            ]
            for index, (opportunity_id, action) in enumerate(actions):
                transition_tracker_state(
                    session, opportunity_id, action, now + timedelta(minutes=index),
                )
            session.commit()

            first = list_tracker_items(
                session, "saved", truth_pack_hash=None, page=1, page_size=1,
            )
            second = list_tracker_items(
                session, "saved", truth_pack_hash=None, page=2, page_size=1,
            )
            applied = list_tracker_items(
                session, "applied", truth_pack_hash=None,
            )
            all_tracked = list_tracker_items(
                session, "all", truth_pack_hash=None,
            )

            self.assertEqual((first["total"], len(first["items"])), (2, 1))
            self.assertEqual((second["total"], len(second["items"])), (2, 1))
            self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
            self.assertEqual(applied["items"][0]["tracker_state"], "applied")
            self.assertEqual(all_tracked["total"], 4)
            self.assertNotIn("synthetic-5", {item["id"] for item in all_tracked["items"]})
        finally:
            session.close()

    def test_legacy_snooze_remains_a_state_transition(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            until = now + timedelta(days=1)
            result = transition_tracker_state(
                session, "synthetic-5", "snooze", now, snoozed_until=until,
            )
            session.commit()
            self.assertEqual(result.state, "snoozed")
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-5", action_type="snoozed")
                .count(),
                1,
            )
        finally:
            session.close()

    def test_application_stages_move_forward_with_append_only_events(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            applied = transition_tracker_state(
                session, "synthetic-1", "mark_applied", now,
            )
            session.commit()
            self.assertEqual(applied.state, "applied")

            screen = transition_tracker_state(
                session, "synthetic-1", "set_stage", now + timedelta(minutes=1),
                target_stage="recruiter_screen", request_key="stage-screen",
            )
            session.commit()
            self.assertEqual((screen.previous_state, screen.state), ("applied", "recruiter_screen"))
            self.assertTrue(screen.changed)

            assessment = transition_tracker_state(
                session, "synthetic-1", "set_stage", now + timedelta(minutes=2),
                target_stage="assessment", request_key="stage-assessment",
            )
            session.commit()
            self.assertEqual((assessment.previous_state, assessment.state), ("recruiter_screen", "assessment"))

            repeated = transition_tracker_state(
                session, "synthetic-1", "set_stage", now + timedelta(minutes=3),
                target_stage="assessment", request_key="stage-assessment",
            )
            session.commit()
            self.assertFalse(repeated.changed)

            current = "assessment"
            for index, target in enumerate(("interviewing", "final_interview", "offer", "accepted"), 4):
                result = transition_tracker_state(
                    session,
                    "synthetic-1",
                    "set_stage",
                    now + timedelta(minutes=index),
                    target_stage=target,
                    request_key=f"stage-{target}",
                )
                session.commit()
                self.assertEqual((result.previous_state, result.state), (current, target))
                current = target

            replay = transition_tracker_state(
                session, "synthetic-1", "set_stage", now + timedelta(minutes=10),
                target_stage="assessment", request_key="stage-assessment",
            )
            session.commit()
            self.assertFalse(replay.changed)
            self.assertEqual(replay.state, "accepted")
            with self.assertRaises(TrackerTransitionError):
                transition_tracker_state(
                    session, "synthetic-1", "set_stage", now + timedelta(minutes=11),
                    target_stage="rejected_by_employer",
                )

            events = (
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-1")
                .order_by(FounderActivityEventRecord.event_at.asc())
                .all()
            )
            self.assertEqual(len(events), 7)
            self.assertEqual(
                [(event.action_type, event.from_state, event.to_state) for event in events],
                [
                    ("applied", "to_review", "applied"),
                    ("application_stage_updated", "applied", "recruiter_screen"),
                    ("application_stage_updated", "recruiter_screen", "assessment"),
                    ("application_stage_updated", "assessment", "interviewing"),
                    ("application_stage_updated", "interviewing", "final_interview"),
                    ("application_stage_updated", "final_interview", "offer"),
                    ("application_stage_updated", "offer", "accepted"),
                ],
            )
            state = session.get(FounderTriageStateRecord, "synthetic-1")
            self.assertEqual(state.state, "accepted")
            self.assertIsNotNone(state.closed_at)
        finally:
            session.close()

    def test_employer_terminal_outcomes_are_listed_as_rejected(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            for index, outcome in enumerate(
                ("rejected_by_employer", "withdrawn", "no_response"), start=2,
            ):
                opportunity_id = f"synthetic-{index}"
                transition_tracker_state(
                    session, opportunity_id, "mark_applied", now,
                )
                transition_tracker_state(
                    session,
                    opportunity_id,
                    "set_stage",
                    now + timedelta(minutes=index),
                    target_stage=outcome,
                )
            session.commit()

            rejected = list_tracker_items(session, "rejected", truth_pack_hash=None)
            self.assertEqual(rejected["total"], 3)
            self.assertEqual(
                {item["tracker_state"] for item in rejected["items"]},
                {"rejected_by_employer", "withdrawn", "no_response"},
            )
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter(FounderActivityEventRecord.to_state.in_(
                    ("rejected_by_employer", "withdrawn", "no_response")
                ))
                .count(),
                3,
            )
        finally:
            session.close()

    def test_pipeline_rejects_backwards_and_post_terminal_transitions(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            with self.assertRaises(TrackerTransitionError):
                transition_tracker_state(
                    session, "synthetic-5", "set_stage", now,
                    target_stage="assessment",
                )
            session.rollback()

            transition_tracker_state(session, "synthetic-5", "mark_applied", now)
            session.commit()
            transition_tracker_state(
                session, "synthetic-5", "set_stage", now + timedelta(minutes=1),
                target_stage="interviewing",
            )
            session.commit()
            with self.assertRaises(TrackerTransitionError):
                transition_tracker_state(
                    session, "synthetic-5", "set_stage", now + timedelta(minutes=2),
                    target_stage="assessment",
                )
            session.rollback()

            transition_tracker_state(
                session, "synthetic-5", "set_stage", now + timedelta(minutes=3),
                target_stage="withdrawn",
            )
            session.commit()
            with self.assertRaises(TrackerTransitionError):
                transition_tracker_state(
                    session, "synthetic-5", "set_stage", now + timedelta(minutes=4),
                    target_stage="offer",
                )
            session.rollback()
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-5")
                .count(),
                3,
            )
        finally:
            session.close()

    def test_explicit_applied_route_keeps_legacy_response_and_does_not_reserve_submit_key(self) -> None:
        session = self.Session()
        try:
            reservation_count = session.query(IdempotencyReservationRecord).count()
            first = submit_action(
                "synthetic-5",
                ActionRequest(type="mark_applied", idempotency_key="manual-apply-once"),
                Response(),
                session,
            )
            second = submit_action(
                "synthetic-5",
                ActionRequest(type="mark_applied", idempotency_key="manual-apply-once"),
                Response(),
                session,
            )
            self.assertEqual(first["action_state"], "submitted")
            self.assertEqual(first["tracker_state"], "applied")
            self.assertEqual(second["action_id"], first["action_id"])
            self.assertEqual(
                session.query(OutboundActionRecordModel)
                .filter_by(opportunity_id="synthetic-5", adapter_name="founder_attested")
                .count(),
                1,
            )
            self.assertEqual(session.query(IdempotencyReservationRecord).count(), reservation_count)
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-5", to_state="applied")
                .count(),
                1,
            )
        finally:
            session.close()

    def test_stage_route_accepts_explicit_stage_without_new_outbound_action(self) -> None:
        session = self.Session()
        try:
            applied = submit_action(
                "synthetic-1",
                ActionRequest(type="mark_applied", idempotency_key="route-apply"),
                Response(),
                session,
            )
            self.assertEqual(applied["tracker_state"], "applied")
            before = session.query(OutboundActionRecordModel).filter_by(
                opportunity_id="synthetic-1", adapter_name="founder_attested",
            ).count()

            first = submit_action(
                "synthetic-1",
                ActionRequest(
                    type="set_stage",
                    stage="assessment",
                    idempotency_key="route-assessment",
                ),
                Response(),
                session,
            )
            again = submit_action(
                "synthetic-1",
                ActionRequest(
                    type="set_stage",
                    stage="assessment",
                    idempotency_key="route-assessment",
                ),
                Response(),
                session,
            )
            self.assertEqual(first["tracker_state"], "assessment")
            self.assertEqual(again["tracker_state"], "assessment")
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-1", action_type="application_stage_updated")
                .count(),
                1,
            )
            self.assertEqual(
                session.query(OutboundActionRecordModel).filter_by(
                    opportunity_id="synthetic-1", adapter_name="founder_attested",
                ).count(),
                before,
            )
        finally:
            session.close()

    def test_apply_undo_restores_to_review_and_keeps_attestation_as_undone(self) -> None:
        session = self.Session()
        try:
            applied = submit_action(
                "synthetic-5",
                ActionRequest(type="mark_applied", idempotency_key="undo-apply"),
                Response(),
                session,
            )
            self.assertTrue(applied["undo_event_id"])

            restored = restore_action(
                "synthetic-5",
                RestoreTrackerRequest(
                    event_id=applied["undo_event_id"],
                    idempotency_key="restore-apply-once",
                ),
                session,
            )
            self.assertEqual(restored["tracker_state"], "to_review")
            self.assertEqual(session.get(FounderTriageStateRecord, "synthetic-5").state, "to_review")
            attestation = session.query(OutboundActionRecordModel).filter_by(
                opportunity_id="synthetic-5", adapter_name="founder_attested",
            ).one()
            self.assertEqual(attestation.action_status, ActionStatus.UNDONE.value)
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-5")
                .count(),
                2,
            )

            retried = restore_action(
                "synthetic-5",
                RestoreTrackerRequest(
                    event_id=applied["undo_event_id"],
                    idempotency_key="restore-apply-once",
                ),
                session,
            )
            self.assertEqual(retried["tracker_state"], "to_review")
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-5")
                .count(),
                2,
            )
        finally:
            session.close()

    def test_undo_from_saved_restores_the_previous_snooze_and_expiry(self) -> None:
        now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        snoozed_until = now + timedelta(days=2)
        session = self.Session()
        try:
            transition_tracker_state(
                session, "synthetic-4", "snooze", now, snoozed_until=snoozed_until,
            )
            session.commit()
            saved = submit_action(
                "synthetic-4",
                ActionRequest(type="save", idempotency_key="save-from-snooze"),
                Response(),
                session,
            )
            restored = restore_action(
                "synthetic-4",
                RestoreTrackerRequest(
                    event_id=saved["undo_event_id"],
                    idempotency_key="restore-saved-once",
                ),
                session,
            )
            state = session.get(FounderTriageStateRecord, "synthetic-4")
            self.assertEqual(restored["tracker_state"], "snoozed")
            self.assertEqual(state.state, "snoozed")
            self.assertEqual(state.snoozed_until.replace(tzinfo=timezone.utc), snoozed_until)
        finally:
            session.close()

    def test_undo_mark_applied_returns_to_saved_and_restores_saved_timestamp(self) -> None:
        session = self.Session()
        try:
            saved = submit_action(
                "synthetic-1",
                ActionRequest(type="save", idempotency_key="save-before-apply"),
                Response(),
                session,
            )
            saved_at = session.get(FounderTriageStateRecord, "synthetic-1").saved_at
            applied = submit_action(
                "synthetic-1",
                ActionRequest(type="mark_applied", idempotency_key="apply-after-save"),
                Response(),
                session,
            )
            self.assertTrue(saved["undo_event_id"])
            self.assertTrue(applied["undo_event_id"])

            restored = restore_action(
                "synthetic-1",
                RestoreTrackerRequest(
                    event_id=applied["undo_event_id"],
                    idempotency_key="undo-apply-to-saved",
                ),
                session,
            )
            state = session.get(FounderTriageStateRecord, "synthetic-1")
            self.assertEqual(restored["tracker_state"], "saved")
            self.assertEqual(state.state, "saved")
            self.assertEqual(state.saved_at, saved_at)
            self.assertIsNone(state.applied_at)
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-1")
                .count(),
                3,
            )
        finally:
            session.close()

    def test_unrelated_newer_activity_makes_undo_conflict_without_state_change(self) -> None:
        now = datetime.now(timezone.utc)
        session = self.Session()
        try:
            saved = submit_action(
                "synthetic-4",
                ActionRequest(type="save", idempotency_key="save-before-note"),
                Response(),
                session,
            )
            session.add(FounderActivityEventRecord(
                id="tracker-event-unrelated-newer",
                opportunity_id="synthetic-4",
                action_type="tracker_note_created",
                from_state="saved",
                to_state="saved",
                event_at=now + timedelta(minutes=1),
                metadata_json="{}",
                created_at=now + timedelta(minutes=1),
            ))
            session.commit()

            with self.assertRaises(HTTPException) as raised:
                restore_action(
                    "synthetic-4",
                    RestoreTrackerRequest(
                        event_id=saved["undo_event_id"],
                        idempotency_key="undo-before-note",
                    ),
                    session,
                )
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(session.get(FounderTriageStateRecord, "synthetic-4").state, "saved")
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-4", action_type="tracker_restored")
                .count(),
                0,
            )
        finally:
            session.close()

    def test_stale_undo_is_conflict_and_does_not_write_a_restore_event(self) -> None:
        session = self.Session()
        try:
            saved = submit_action(
                "synthetic-3",
                ActionRequest(type="save", idempotency_key="stale-save"),
                Response(),
                session,
            )
            transition_tracker_state(
                session,
                "synthetic-3",
                "reject",
                datetime.now(timezone.utc) + timedelta(minutes=1),
            )
            session.commit()

            with self.assertRaises(HTTPException) as raised:
                restore_action(
                    "synthetic-3",
                    RestoreTrackerRequest(
                        event_id=saved["undo_event_id"],
                        idempotency_key="stale-restore",
                    ),
                    session,
                )
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(session.get(FounderTriageStateRecord, "synthetic-3").state, "rejected_by_founder")
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-3", action_type="tracker_restored")
                .count(),
                0,
            )
        finally:
            session.close()

    def test_restore_commit_failure_rolls_back_tracker_event_and_attestation(self) -> None:
        session = self.Session()
        try:
            applied = submit_action(
                "synthetic-2",
                ActionRequest(type="mark_applied", idempotency_key="failed-undo-apply"),
                Response(),
                session,
            )
            with patch.object(session, "commit", side_effect=RuntimeError("synthetic restore commit failure")):
                with self.assertRaisesRegex(RuntimeError, "synthetic restore commit failure"):
                    restore_action(
                        "synthetic-2",
                        RestoreTrackerRequest(
                            event_id=applied["undo_event_id"],
                            idempotency_key="failed-restore",
                        ),
                        session,
                    )
            session.rollback()
            self.assertEqual(session.get(FounderTriageStateRecord, "synthetic-2").state, "applied")
            self.assertEqual(
                session.query(OutboundActionRecordModel)
                .filter_by(opportunity_id="synthetic-2", action_status=ActionStatus.SUBMITTED.value)
                .count(),
                1,
            )
            self.assertEqual(
                session.query(FounderActivityEventRecord)
                .filter_by(opportunity_id="synthetic-2", action_type="tracker_restored")
                .count(),
                0,
            )
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
