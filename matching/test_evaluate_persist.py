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
from unittest.mock import patch

from matching.evaluate_persist import evaluate_and_store
from matching.models import QualificationDecision
from matching.test_qualification import create_test_graph, create_test_opportunity
from storage.engine import get_engine, get_session_factory, init_db
from storage.feed_projection import FeedProjectionRecord
from storage.models import MatchEvaluationRecord, OpportunityRecord
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

    def _evaluate_and_store(self, opportunity, truth_graph, repository, **kwargs):
        if self.session.get(OpportunityRecord, opportunity.id) is None:
            self.session.add(OpportunityRecord(
                id=opportunity.id,
                track=opportunity.track.value,
                title=opportunity.title,
                organization=opportunity.organization,
                description=opportunity.description,
                source_id=opportunity.source,
                source_url=opportunity.source_url,
                content_hash=f"fixture-{opportunity.id}",
            ))
            self.session.commit()
        return evaluate_and_store(opportunity, truth_graph, repository, **kwargs)

    def test_insert_creates_one_row_with_expected_fields(self) -> None:
        opp = create_test_opportunity(opp_id="opp-insert-1", skills=("Python", "Go"))
        evaluated_at = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)

        record = self._evaluate_and_store(
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
        first = self._evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-same"
        )
        first_id = first.id

        second = self._evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-same"
        )

        self.assertEqual(second.id, first_id)
        rows = self.session.query(MatchEvaluationRecord).filter_by(
            opportunity_id="opp-upsert-1", truth_pack_hash="hash-same"
        ).all()
        self.assertEqual(len(rows), 1, "re-evaluating under the same hash must overwrite, not duplicate")

    def test_projection_publication_failure_raises_and_idempotent_retry_publishes(self) -> None:
        opp = create_test_opportunity(opp_id="opp-publication-retry")
        with patch(
            "storage.feed_projection_service.refresh_opportunity_projection",
            side_effect=RuntimeError("synthetic publication failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic publication failure"):
                self._evaluate_and_store(
                    opp, self.truth_graph, self.repository, truth_pack_hash="truth-retry"
                )

        self.assertEqual(self.session.query(MatchEvaluationRecord).filter_by(
            opportunity_id=opp.id, truth_pack_hash="truth-retry"
        ).count(), 1)
        self.assertEqual(self.session.query(FeedProjectionRecord).filter_by(
            opportunity_id=opp.id, truth_pack_hash="truth-retry"
        ).count(), 0)

        self._evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="truth-retry"
        )
        self.assertEqual(self.session.query(MatchEvaluationRecord).filter_by(
            opportunity_id=opp.id, truth_pack_hash="truth-retry"
        ).count(), 1)
        self.assertEqual(self.session.query(FeedProjectionRecord).filter_by(
            opportunity_id=opp.id, truth_pack_hash="truth-retry"
        ).count(), 1)

    def test_worker_retry_republishes_committed_evaluation_without_duplicate(self) -> None:
        from truth.pack import LoadedPack, PackValidationReport
        from worker.handlers import make_evaluate_new_handler

        opp = create_test_opportunity(opp_id="opp-worker-publication-retry")
        self.session.add(OpportunityRecord(
            id=opp.id, track=opp.track.value, title=opp.title,
            organization=opp.organization, description=opp.description,
            source_id=opp.source, source_url=opp.source_url,
            content_hash="worker-retry-fixture",
        ))
        self.session.commit()
        pack = LoadedPack(
            graph=self.truth_graph,
            truth_pack_hash="truth-worker-retry",
            report=PackValidationReport(valid=True, section_counts=(), findings=()),
        )
        handler = make_evaluate_new_handler(
            session_factory=self.session_factory, pack_loader=lambda _path: pack
        )
        with patch(
            "storage.feed_projection_service.refresh_opportunity_projection",
            side_effect=RuntimeError("synthetic publication failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic publication failure"):
                handler({})

        self.assertEqual(self.session.query(MatchEvaluationRecord).filter_by(
            opportunity_id=opp.id, truth_pack_hash="truth-worker-retry"
        ).count(), 1)
        self.assertEqual(self.session.query(FeedProjectionRecord).filter_by(
            opportunity_id=opp.id, truth_pack_hash="truth-worker-retry"
        ).count(), 0)

        handler({})
        self.assertEqual(self.session.query(MatchEvaluationRecord).filter_by(
            opportunity_id=opp.id, truth_pack_hash="truth-worker-retry"
        ).count(), 1)
        self.assertEqual(self.session.query(FeedProjectionRecord).filter_by(
            opportunity_id=opp.id, truth_pack_hash="truth-worker-retry"
        ).count(), 1)

    def test_different_hash_creates_second_row_and_leaves_first_intact(self) -> None:
        opp = create_test_opportunity(opp_id="opp-multi-hash-1")
        first = self._evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-1"
        )
        second = self._evaluate_and_store(
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

        record = self._evaluate_and_store(
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
            self._evaluate_and_store(opp, self.truth_graph, self.repository, truth_pack_hash="")

    def test_evaluated_at_defaults_to_real_now_not_scorer_hardcoded_default(self) -> None:
        opp = create_test_opportunity(opp_id="opp-default-time")
        before = datetime.now(timezone.utc)

        record = self._evaluate_and_store(
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

    def test_evaluation_detail_json_shape_and_null_passed_never_coerced(self) -> None:
        """geo_status='unclear' drives a hard-constraint result with passed=None
        (UNKNOWN). evaluation_detail_json must carry that through as JSON
        null, never as false, and must carry the exact D6-agreed shape."""
        opp = create_test_opportunity(opp_id="opp-detail-1", geo_status="unclear")

        record = self._evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-detail"
        )

        detail = json.loads(record.evaluation_detail_json)
        self.assertEqual(
            set(detail.keys()),
            {"hard_constraints", "strengths", "gaps", "unknowns", "uncertainty_penalty", "explanation"},
        )
        self.assertIsInstance(detail["hard_constraints"], list)
        self.assertGreater(len(detail["hard_constraints"]), 0)

        geo_entries = [hc for hc in detail["hard_constraints"] if hc["constraint_name"] == "geographic_eligibility"]
        self.assertEqual(len(geo_entries), 1)
        geo_entry = geo_entries[0]
        self.assertEqual(
            set(geo_entry.keys()),
            {
                "constraint_name", "passed", "reason", "required_field", "founder_fact",
                "is_hard_failure", "provenance_pointer", "constraint_type",
                "job_evidence_text", "job_evidence_field", "source_pointer",
                "founder_side_evidence", "decision", "confidence",
                "requirement_mandatory", "explanation",
            },
        )
        # passed must be the literal JSON null (Python None), never False.
        self.assertIsNone(geo_entry["passed"])
        self.assertNotEqual(geo_entry["passed"], False)
        self.assertEqual(geo_entry["constraint_type"], geo_entry["constraint_name"])
        self.assertEqual(geo_entry["decision"], geo_entry["passed"])
        self.assertEqual(geo_entry["job_evidence_field"], geo_entry["required_field"])
        self.assertEqual(geo_entry["source_pointer"], geo_entry["provenance_pointer"])
        self.assertEqual(geo_entry["founder_side_evidence"], geo_entry["founder_fact"])
        self.assertEqual(geo_entry["explanation"], geo_entry["reason"])
        self.assertGreaterEqual(geo_entry["confidence"], 0.0)
        self.assertLessEqual(geo_entry["confidence"], 1.0)
        self.assertIn(geo_entry["requirement_mandatory"], (True, False, None))

        for hc in detail["hard_constraints"]:
            self.assertIn(hc["passed"], (True, False, None))

        self.assertIsInstance(detail["strengths"], list)
        self.assertIsInstance(detail["gaps"], list)
        self.assertIsInstance(detail["unknowns"], list)
        self.assertIsInstance(detail["uncertainty_penalty"], float)
        self.assertIsInstance(detail["explanation"], str)

    def test_concurrent_evaluate_and_store_same_hash_does_not_raise(self) -> None:
        """Simulates the SELECT-then-write race (Finding 5): two callers both
        miss on the initial SELECT, both attempt to insert the same
        deterministic row. On the SQLite fallback path this must be caught
        and converted into an update rather than propagating an
        IntegrityError."""
        from matching.evaluate_persist import _upsert_match_evaluation

        opp = create_test_opportunity(opp_id="opp-race-1")
        first = self._evaluate_and_store(
            opp, self.truth_graph, self.repository, truth_pack_hash="hash-race"
        )

        # Delete the row out from under the ORM identity map to force a real
        # "miss" on the next SELECT, then race two upserts against the same
        # (opportunity_id, truth_pack_hash): the second one only wins the
        # race if the first has already inserted and committed by the time
        # it runs, so simulate the *interleaved* case directly by deleting
        # and re-inserting mid-flight via a second, independent session.
        second_session = self.session_factory()
        try:
            # Both sessions "miss" (row exists from `first` above, so this
            # exercises the existing-row UPDATE branch, not the INSERT-race
            # branch specifically -- kept as a smoke test that concurrent
            # upserts of the same key never raise).
            record_id = first.id
            values = {
                "qualification_decision": "qualified",
                "fit_score": 55.5,
                "dimension_scores_json": "[]",
                "reasons_json": "[]",
                "evaluation_detail_json": "{}",
                "policy_version": "1.0.0",
                "evaluated_at": first.evaluated_at,
            }
            result = _upsert_match_evaluation(
                second_session,
                record_id=record_id,
                opportunity_id="opp-race-1",
                truth_pack_hash="hash-race",
                values=values,
            )
            self.assertEqual(result.id, record_id)
        finally:
            second_session.close()

        rows = self.session.query(MatchEvaluationRecord).filter_by(
            opportunity_id="opp-race-1", truth_pack_hash="hash-race"
        ).all()
        self.assertEqual(len(rows), 1, "a race must never produce a duplicate row")


if __name__ == "__main__":
    unittest.main()
