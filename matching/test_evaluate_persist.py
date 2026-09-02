"""Unit tests for matching.evaluate_persist.evaluate_and_store.

Follows the existing unit convention in this repo (see
opportunity/test_persistence.py): storage.engine.get_engine(...,
allow_sqlite=True) against a temp-file SQLite DB, never the real production
database. No network access.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from matching.evaluate_persist import evaluate_and_store
from matching.models import QualificationDecision
from matching.test_qualification import create_test_graph, create_test_opportunity
from storage.engine import get_engine, get_session_factory, init_db
from storage.models import MatchEvaluationRecord
from storage.repository import StorageRepository


class EvaluateAndStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_evaluate_persist.db")
        self.engine = get_engine(f"sqlite:///{self.db_path}", allow_sqlite=True)
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)
        self.session = self.session_factory()
        self.repository = StorageRepository(self.session)
        self.truth_graph = create_test_graph()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_insert_creates_one_row_with_expected_fields(self) -> None:
        opp = create_test_opportunity(opp_id="opp-insert-1", skills=("Python", "Go"))
        evaluated_at = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)

        record = evaluate_and_store(
            opp,
            self.truth_graph,
            self.repository,
            truth_pack_hash="hash-a",
            evaluated_at=evaluated_at,
        )

        self.assertEqual(record.opportunity_id, "opp-insert-1")
        self.assertEqual(record.truth_pack_hash, "hash-a")
        # SQLite (unlike PostgreSQL) round-trips DateTime as naive, so compare
        # on the naive wall-clock value rather than tz-aware equality.
        self.assertEqual(record.evaluated_at.replace(tzinfo=None), evaluated_at.replace(tzinfo=None))
        self.assertIn(record.qualification_decision, {d.value for d in QualificationDecision})
        self.assertGreaterEqual(record.fit_score, 0.0)
        self.assertLessEqual(record.fit_score, 100.0)

        rows = self.session.query(MatchEvaluationRecord).all()
        self.assertEqual(len(rows), 1)

        dims = json.loads(rows[0].dimension_scores_json)
        self.assertIsInstance(dims, list)
        self.assertGreater(len(dims), 0)
        for dim in dims:
            self.assertIn("dimension_name", dim)
            self.assertIn("raw_score", dim)

        reasons = json.loads(rows[0].reasons_json)
        self.assertIsInstance(reasons, list)
        for reason in reasons:
            self.assertIn(reason["kind"], {"strength", "gap", "unknown", "hard_failure"})
            self.assertIn("dimension", reason)
            self.assertIn("text", reason)

    def test_same_hash_reevaluation_upserts_in_place(self) -> None:
        opp = create_test_opportunity(opp_id="opp-upsert-1")
        first = evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-same"
        )
        first_id = first.id

        second = evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-same"
        )

        self.assertEqual(second.id, first_id)
        rows = self.session.query(MatchEvaluationRecord).filter_by(
            opportunity_id="opp-upsert-1", truth_pack_hash="hash-same"
        ).all()
        self.assertEqual(len(rows), 1, "re-evaluating under the same hash must overwrite, not duplicate")

    def test_different_hash_creates_second_row_and_leaves_first_intact(self) -> None:
        opp = create_test_opportunity(opp_id="opp-multi-hash-1")
        first = evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-1"
        )
        second = evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-2"
        )

        self.assertNotEqual(first.id, second.id)
        rows = self.session.query(MatchEvaluationRecord).filter_by(
            opportunity_id="opp-multi-hash-1"
        ).all()
        self.assertEqual(len(rows), 2)

        refetched_first = (
            self.session.query(MatchEvaluationRecord)
            .filter_by(opportunity_id="opp-multi-hash-1", truth_pack_hash="hash-1")
            .first()
        )
        self.assertIsNotNone(refetched_first)
        self.assertEqual(refetched_first.id, first.id)

    def test_uncertain_decision_round_trips_as_literal_string_uncertain(self) -> None:
        """A geo status of 'unclear' drives QualificationEngine to UNCERTAIN
        (no hard failure, but an unresolved hard-constraint check) -- this
        must be stored as the literal string 'uncertain', not coerced to
        'ineligible' or anything else. This test would fail if any branch in
        evaluate_and_store rewrote the decision before persisting it."""
        opp = create_test_opportunity(opp_id="opp-uncertain-1", geo_status="unclear")

        record = evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-uncertain"
        )

        self.assertEqual(
            record.qualification_decision,
            QualificationDecision.UNCERTAIN.value,
        )
        self.assertEqual(record.qualification_decision, "uncertain")

        reloaded = (
            self.session.query(MatchEvaluationRecord)
            .filter_by(opportunity_id="opp-uncertain-1", truth_pack_hash="hash-uncertain")
            .first()
        )
        self.assertEqual(reloaded.qualification_decision, "uncertain")

    def test_missing_truth_pack_hash_raises(self) -> None:
        opp = create_test_opportunity(opp_id="opp-no-hash")
        with self.assertRaises(ValueError):
            evaluate_and_store(opp, self.truth_graph, self.repository, truth_pack_hash="")

    def test_evaluated_at_defaults_to_real_now_not_scorer_hardcoded_default(self) -> None:
        opp = create_test_opportunity(opp_id="opp-default-time")
        before = datetime.now(timezone.utc)

        record = evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-time"
        )

        after = datetime.now(timezone.utc)
        stored = record.evaluated_at
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        self.assertGreaterEqual(stored, before)
        self.assertLessEqual(stored, after)
        # The scorer's own hard-coded default ("2026-08-30") must never be
        # what ends up here unless "now" genuinely is that date.
        self.assertNotEqual(stored.date().isoformat(), "2026-08-30")


if __name__ == "__main__":
    unittest.main()
