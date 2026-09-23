from __future__ import annotations

import dataclasses
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from matching.scorer import OpportunityScorer
from matching.test_qualification import create_test_graph, create_test_opportunity
from opportunity.models import DerivationType, FieldProvenance
from opportunity.persistence import persist_evaluated_batch
from opportunity.pipeline import IngestionBatch
from storage.cold_storage import unpack
from storage.engine import get_engine, get_session_factory, init_db
from storage.feed_projection import FeedProjectionRecord
from storage.models import (
    FieldProvenanceRecord,
    FounderFeedbackRecord,
    MatchEvaluationRecord,
    OpportunityColdArchiveRecord,
    OpportunityRecord,
)
from storage.repository import StorageRepository
from truth.pack import LoadedPack, PackValidationReport
from worker.handlers import make_evaluate_new_handler


class MemoryPrivateStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload(self, key: str, body: bytes) -> None:
        self.objects[key] = bytes(body)

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def _cold_opportunity(description: str = "Build an unrelated on-site role"):
    base = create_test_opportunity(
        opp_id="source:job-1",
        geo_status="excluded",
        description=description,
        skills=("Kubernetes",),
        responsibilities=("Operate an on-site datacenter",),
    )
    return dataclasses.replace(
        base,
        record_checksum="source-record-checksum",
        field_provenances=(FieldProvenance(
            field_name="source_reason",
            raw_value=description,
            normalized_value=description,
            derivation_type=DerivationType.RAW_EXTRACTION.value,
            raw_pointer="description",
            record_checksum="source-record-checksum",
            rule_id="fixture",
        ),),
        raw_source_record_json=json.dumps(
            {"id": "job-1", "description": description}, separators=(",", ":")
        ),
        content_hash="",
    )


def _batch(opportunity) -> IngestionBatch:
    return IngestionBatch(
        batch_id="storage-v2-fixture",
        run_id="storage-v2-test",
        ingested_at="2026-09-23",
        opportunities=(opportunity,),
        clusters=(),
        health_reports=(),
        total_raw_ingested=1,
        total_unique_opportunities=1,
        exact_duplicates_removed=0,
        cross_source_duplicates_clustered=0,
        ambiguous_duplicates_count=0,
        track_counts=(("employment", 1),),
        eligibility_counts=(("excluded", 1),),
    )


def _pack(graph, truth_pack_hash: str) -> LoadedPack:
    return LoadedPack(
        graph=graph,
        truth_pack_hash=truth_pack_hash,
        report=PackValidationReport(valid=True, section_counts=(), findings=()),
    )


class StorageV2DirectTierTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = get_engine(
            f"sqlite:///{os.path.join(self.temp_dir.name, 'storage_v2.sqlite')}",
            allow_sqlite=True,
        )
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)
        self.session = self.session_factory()
        self.private_storage = MemoryPrivateStorage()
        self.graph = create_test_graph()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _ingest_cold(self, opportunity=None):
        opportunity = opportunity or _cold_opportunity()
        result = persist_evaluated_batch(
            _batch(opportunity),
            StorageRepository(self.session, cold_storage_client=self.private_storage),
            truth_graph=self.graph,
            truth_pack_hash="truth-a",
        )
        return opportunity, result

    def test_hard_ineligible_source_goes_directly_to_private_cold_tier(self):
        opportunity, result = self._ingest_cold()
        self.assertEqual(result.inserted_ids, (opportunity.id,))

        row = self.session.get(OpportunityRecord, opportunity.id)
        self.assertEqual(row.lifecycle_tier, "cold")
        self.assertIsNone(row.description)
        self.assertIsNone(row.raw_payload_json)
        self.assertEqual(
            self.session.query(FieldProvenanceRecord)
            .filter_by(opportunity_id=opportunity.id)
            .count(),
            0,
        )
        self.assertEqual(self.session.query(MatchEvaluationRecord).count(), 1)
        evaluation = self.session.query(MatchEvaluationRecord).one()
        self.assertEqual(evaluation.qualification_decision, "ineligible")
        self.assertIsNone(evaluation.dimension_scores_json)
        self.assertIsNone(evaluation.evaluation_detail_json)
        self.assertEqual(evaluation.hard_failure_code, "geographic_eligibility")
        cold_reasons = json.loads(evaluation.reasons_json)
        self.assertEqual(cold_reasons, [{
            "kind": "hard_failure",
            "dimension": "geographic_eligibility",
            "text": "geographic_eligibility",
        }])
        self.assertLessEqual(len(evaluation.reasons_json.encode("utf-8")), 512)
        self.assertEqual(self.session.query(OpportunityColdArchiveRecord).count(), 1)
        self.assertEqual(self.session.query(FeedProjectionRecord).count(), 0)

        archive = self.session.get(OpportunityColdArchiveRecord, opportunity.id)
        compressed = self.private_storage.get(archive.object_key)
        payload = unpack(
            compressed,
            archive.payload_sha256,
            opportunity_id=opportunity.id,
            content_hash=opportunity.content_hash,
        )
        self.assertEqual(payload["canonical_description"], opportunity.description)
        self.assertEqual(payload["original_source_payload"], opportunity.raw_source_record_json)
        self.assertTrue(payload["provenance"])
        self.assertEqual(payload["normalized_opportunity"]["geographic_eligibility"]["status"], "excluded")
        self.assertEqual(payload["normalized_opportunity"]["responsibilities"], list(opportunity.responsibilities))

    def test_archived_placeholder_is_rejected_before_scoring_or_any_persistence(self):
        opportunity = _cold_opportunity(" [ARCHIVED] ")

        class RecordingScorer:
            calls = 0

            def evaluate(inner_self, *args, **kwargs):
                inner_self.calls += 1
                raise AssertionError("placeholder must be rejected before matching")

        scorer = RecordingScorer()
        repository = StorageRepository(self.session, cold_storage_client=self.private_storage)
        with self.assertRaisesRegex(ValueError, "refusing to score archived placeholder"):
            persist_evaluated_batch(
                _batch(opportunity),
                repository,
                truth_graph=self.graph,
                truth_pack_hash="truth-a",
                scorer=scorer,
            )

        self.assertEqual(scorer.calls, 0)
        self.assertEqual(self.session.query(OpportunityRecord).count(), 0)
        self.assertEqual(self.session.query(MatchEvaluationRecord).count(), 0)
        self.assertEqual(self.session.query(OpportunityColdArchiveRecord).count(), 0)
        self.assertEqual(self.private_storage.objects, {})

    def test_changed_content_replaces_archive_and_reclaims_old_object(self):
        first, _ = self._ingest_cold()
        first_archive = self.session.get(OpportunityColdArchiveRecord, first.id)
        old_key = first_archive.object_key

        changed = _cold_opportunity("Changed authoritative source document")
        self.assertNotEqual(changed.content_hash, first.content_hash)
        result = persist_evaluated_batch(
            _batch(changed),
            StorageRepository(self.session, cold_storage_client=self.private_storage),
            truth_graph=self.graph,
            truth_pack_hash="truth-a",
        )

        self.assertEqual(result.updated_ids, (changed.id,))
        current = self.session.get(OpportunityColdArchiveRecord, changed.id)
        self.assertNotEqual(current.object_key, old_key)
        self.assertNotIn(old_key, self.private_storage.objects)
        self.assertEqual(set(self.private_storage.objects), {current.object_key})
        self.assertEqual(self.session.query(OpportunityRecord).count(), 1)

    def test_truth_pack_change_rechecks_exact_archive_and_keeps_terminal_row_cold(self):
        opportunity, _ = self._ingest_cold()
        new_pack = _pack(self.graph, "truth-b")
        handler = make_evaluate_new_handler(
            session_factory=self.session_factory,
            pack_loader=lambda _path: new_pack,
            cold_storage_client=self.private_storage,
        )

        handler({})

        row = self.session.get(OpportunityRecord, opportunity.id)
        self.assertEqual(row.lifecycle_tier, "cold")
        self.assertIsNone(row.description)
        self.assertEqual(self.session.query(MatchEvaluationRecord).count(), 1)
        evaluation = self.session.query(MatchEvaluationRecord).one()
        self.assertEqual(evaluation.truth_pack_hash, "truth-b")
        self.assertEqual(evaluation.content_hash, opportunity.content_hash)
        self.assertEqual(self.session.query(FeedProjectionRecord).count(), 0)

    def test_re_evaluation_promotes_eligible_archive_without_persisting_placeholder(self):
        opportunity, _ = self._ingest_cold()
        eligible_result = OpportunityScorer().evaluate(
            create_test_opportunity(opp_id=opportunity.id, geo_status="eligible"),
            self.graph,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

        class PromotionScorer:
            seen = None

            def evaluate(inner_self, reconstructed, truth_graph, evaluated_at=""):
                inner_self.seen = reconstructed
                return dataclasses.replace(eligible_result, opportunity_id=reconstructed.id)

        promotion_scorer = PromotionScorer()
        handler = make_evaluate_new_handler(
            session_factory=self.session_factory,
            pack_loader=lambda _path: _pack(self.graph, "truth-b"),
            scorer=promotion_scorer,
            cold_storage_client=self.private_storage,
        )

        handler({})

        row = self.session.get(OpportunityRecord, opportunity.id)
        self.assertEqual(promotion_scorer.seen.description, opportunity.description)
        self.assertEqual(promotion_scorer.seen.raw_source_record_json, opportunity.raw_source_record_json)
        self.assertEqual(row.lifecycle_tier, "hot")
        self.assertEqual(row.description, opportunity.description)
        self.assertNotEqual(row.description, "[archived]")
        self.assertIsNone(self.session.get(OpportunityColdArchiveRecord, opportunity.id))
        self.assertFalse(self.private_storage.objects)
        self.assertEqual(
            self.session.query(FeedProjectionRecord)
            .filter_by(opportunity_id=opportunity.id, truth_pack_hash="truth-b")
            .count(),
            1,
        )

    def test_founder_history_protects_a_cold_record_during_pack_change(self):
        opportunity, _ = self._ingest_cold()
        self.session.add(
            FounderFeedbackRecord(
                id="feedback-cold-1",
                opportunity_id=opportunity.id,
                feedback_label="reviewed",
                dedup_hash="a" * 64,
            )
        )
        self.session.commit()
        handler = make_evaluate_new_handler(
            session_factory=self.session_factory,
            pack_loader=lambda _path: _pack(self.graph, "truth-b"),
            cold_storage_client=self.private_storage,
        )

        handler({})

        row = self.session.get(OpportunityRecord, opportunity.id)
        self.assertEqual(row.lifecycle_tier, "protected")
        self.assertEqual(row.description, opportunity.description)
        self.assertEqual(self.session.query(FounderFeedbackRecord).count(), 1)
        self.assertIsNone(self.session.get(OpportunityColdArchiveRecord, opportunity.id))
        self.assertFalse(self.private_storage.objects)


if __name__ == "__main__":
    unittest.main()
