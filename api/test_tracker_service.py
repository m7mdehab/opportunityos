from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.tracker_service import (
    TrackerTransitionError,
    list_tracker_items,
    transition_tracker_state,
)
from api.routes_api import ActionRequest, submit_action
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


if __name__ == "__main__":
    unittest.main()
