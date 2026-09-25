from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.tracker_documents_service import (
    CV_VARIANT_IDS,
    TrackerDocumentError,
    link_tracker_document,
    list_tracker_document_candidates,
    list_tracker_documents,
    unlink_tracker_document,
)
from storage.models import (
    ArtifactCacheRecord,
    Base,
    FounderActivityEventRecord,
    FounderApplicationDetailRecord,
    FounderCVSelectionRecord,
    FounderTrackerDocumentRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
)


class TrackerDocumentsServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.now = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
        session = self.Session()
        try:
            for index, state in enumerate(("applied", "saved", "rejected_by_employer"), start=1):
                opportunity_id = f"synthetic-document-{index}"
                session.add(OpportunityRecord(
                    id=opportunity_id,
                    track="employment",
                    title=f"Synthetic role {index}",
                    organization="Example employer",
                    description="Synthetic description",
                    source_id="example-source",
                    source_url=f"https://example.invalid/jobs/{index}",
                    content_hash=f"{index + 400:064x}",
                    posted_date="2026-09-25",
                ))
                session.add(FounderTriageStateRecord(
                    opportunity_id=opportunity_id,
                    state=state,
                    created_at=self.now,
                    updated_at=self.now,
                ))
            self.recommended_variant = sorted(CV_VARIANT_IDS)[0]
            session.add(FounderCVSelectionRecord(
                opportunity_id="synthetic-document-1",
                variant=self.recommended_variant,
                object_path="synthetic-private-location-not-returned.pdf",
                sha256="b" * 64,
                selected_at=self.now,
                truth_pack_hash="synthetic-truth-hash",
            ))
            session.add(ArtifactCacheRecord(
                cache_key="synthetic-cover-letter-docx-cache-key",
                opportunity_id="synthetic-document-1",
                truth_pack_hash="synthetic-truth-hash",
                template_id="classic",
                artifact_kind="cover-letter",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                payload=b"synthetic cached document bytes",
                storage_backend="postgres_payload",
                payload_sha256="c" * 64,
                size_bytes=32,
                generation_version="synthetic-test",
                created_at=self.now,
            ))
            session.add(ArtifactCacheRecord(
                cache_key="synthetic-cover-letter-pdf-cache-key",
                opportunity_id="synthetic-document-1",
                truth_pack_hash="synthetic-truth-hash",
                template_id="compact",
                artifact_kind="cover-letter-pdf",
                content_type="application/pdf",
                payload=b"synthetic PDF bytes",
                storage_backend="postgres_payload",
                payload_sha256="d" * 64,
                size_bytes=20,
                generation_version="synthetic-test",
                created_at=self.now + timedelta(minutes=1),
            ))
            session.commit()
        finally:
            session.close()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_candidates_are_bounded_and_expose_identity_metadata_only(self) -> None:
        session = self.Session()
        try:
            result = list_tracker_document_candidates(session, "synthetic-document-1", page_size=500)
            self.assertEqual(result["page_size"], 100)
            self.assertEqual(result["total"], len(CV_VARIANT_IDS) + 2)
            cv_candidates = [item for item in result["items"] if item["document_kind"] == "cv"]
            cover_letters = [item for item in result["items"] if item["document_kind"] == "cover_letter"]
            self.assertEqual({item["document_id"] for item in cv_candidates}, CV_VARIANT_IDS)
            recommended = [item for item in cv_candidates if item["recommended"]]
            self.assertEqual([item["document_id"] for item in recommended], [self.recommended_variant])
            self.assertEqual({item["format"] for item in cover_letters}, {"docx", "pdf"})
            serialized = json.dumps(result)
            for key in ("payload", "content", "object_path", "sha256", "storage_backend", "payload_sha256"):
                self.assertNotIn(key, serialized)
            self.assertNotIn("synthetic-private-location", serialized)
            self.assertNotIn("synthetic cached document bytes", serialized)

            page = list_tracker_document_candidates(session, "synthetic-document-1", page=2, page_size=2)
            self.assertEqual((page["page"], page["page_size"], len(page["items"])), (2, 2, 2))
        finally:
            session.close()

    def test_link_replay_conflicting_reuse_and_selected_cv_event_metadata(self) -> None:
        session = self.Session()
        try:
            doc_id = sorted(CV_VARIANT_IDS)[1]
            first = link_tracker_document(session, "synthetic-document-1", "cv", doc_id, self.now, request_key="cv-link-1")
            self.assertTrue(first.changed)
            session.commit()
            details = session.get(FounderApplicationDetailRecord, "synthetic-document-1")
            self.assertEqual(details.selected_cv_document_id, doc_id)
            event = session.query(FounderActivityEventRecord).filter_by(opportunity_id="synthetic-document-1").one()
            self.assertEqual(event.action_type, "tracker_document_linked")
            self.assertEqual((event.from_state, event.to_state), ("applied", "applied"))
            self.assertEqual(json.loads(event.metadata_json), {"document_kind": "cv", "document_id": doc_id})
            self.assertNotIn("synthetic-private", event.metadata_json)

            replay = link_tracker_document(session, "synthetic-document-1", "cv", doc_id, self.now + timedelta(minutes=1), request_key="cv-link-1")
            self.assertFalse(replay.changed)
            with self.assertRaisesRegex(TrackerDocumentError, "already used"):
                link_tracker_document(session, "synthetic-document-1", "cv", self.recommended_variant, self.now, request_key="cv-link-1")
            session.commit()
            self.assertEqual(session.query(FounderActivityEventRecord).filter_by(opportunity_id="synthetic-document-1").count(), 1)
        finally:
            session.close()

    def test_replace_noop_unlink_and_application_detail_synchronization(self) -> None:
        session = self.Session()
        try:
            first_id = sorted(CV_VARIANT_IDS)[0]
            second_id = sorted(CV_VARIANT_IDS)[1]
            first = link_tracker_document(session, "synthetic-document-1", "cv", first_id, self.now, request_key="replace-1")
            session.commit()
            second = link_tracker_document(session, "synthetic-document-1", "cv", second_id, self.now + timedelta(minutes=1), request_key="replace-2")
            self.assertTrue(second.changed)
            session.commit()
            links = list_tracker_documents(session, "synthetic-document-1")
            self.assertEqual(links["total"], 1)
            self.assertEqual(links["selected_cv_document_id"], second_id)
            rows = session.query(FounderTrackerDocumentRecord).filter_by(opportunity_id="synthetic-document-1", document_kind="cv").all()
            self.assertEqual(sum(row.unlinked_at is None for row in rows), 1)
            self.assertEqual(next(row for row in rows if row.id == first.link["id"]).unlinked_at, self.now.replace(tzinfo=None) + timedelta(minutes=1))

            no_op = link_tracker_document(session, "synthetic-document-1", "cv", second_id, self.now + timedelta(minutes=2), request_key="replace-noop")
            self.assertFalse(no_op.changed)
            unlinked = unlink_tracker_document(session, "synthetic-document-1", second.link["id"], self.now + timedelta(minutes=3), request_key="unlink-1")
            self.assertTrue(unlinked.changed)
            session.commit()
            self.assertEqual(list_tracker_documents(session, "synthetic-document-1")["total"], 0)
            self.assertIsNone(session.get(FounderApplicationDetailRecord, "synthetic-document-1").selected_cv_document_id)
            events = session.query(FounderActivityEventRecord).filter_by(opportunity_id="synthetic-document-1").order_by(FounderActivityEventRecord.event_at.asc()).all()
            self.assertEqual([event.action_type for event in events], ["tracker_document_linked", "tracker_document_linked", "tracker_document_unlinked"])
            self.assertTrue(all(set(json.loads(event.metadata_json)) == {"document_kind", "document_id"} for event in events))
        finally:
            session.close()

    def test_cached_cover_letter_link_is_same_opportunity_and_metadata_only(self) -> None:
        session = self.Session()
        try:
            candidates = list_tracker_document_candidates(session, "synthetic-document-1")
            letter = next(item for item in candidates["items"] if item["document_kind"] == "cover_letter" and item["format"] == "pdf")
            linked = link_tracker_document(
                session,
                "synthetic-document-1",
                "cover_letter",
                letter["document_id"],
                self.now,
                request_key="letter-link-1",
            )
            self.assertTrue(linked.changed)
            session.commit()
            details = session.get(FounderApplicationDetailRecord, "synthetic-document-1")
            self.assertEqual(details.selected_cover_letter_document_id, letter["document_id"])
            event = session.query(FounderActivityEventRecord).filter_by(opportunity_id="synthetic-document-1").one()
            self.assertEqual(json.loads(event.metadata_json), {"document_kind": "cover_letter", "document_id": letter["document_id"]})
            with self.assertRaisesRegex(TrackerDocumentError, "unavailable for this opportunity"):
                link_tracker_document(session, "synthetic-document-3", "cover_letter", letter["document_id"], self.now, request_key="other-job-letter")
        finally:
            session.close()

    def test_validation_eligibility_missing_rows_and_rollback(self) -> None:
        session = self.Session()
        try:
            with self.assertRaisesRegex(TrackerDocumentError, "only for application-tracked"):
                list_tracker_documents(session, "synthetic-document-2")
            with self.assertRaisesRegex(TrackerDocumentError, "opportunity not found"):
                list_tracker_documents(session, "missing")
            for kind, doc_id, error in (
                ("other", "id", "unknown document_kind"),
                ("cv", "unknown", "unknown CV document identity"),
                ("cover_letter", "nonexistent-cache-id", "unavailable for this opportunity"),
            ):
                with self.subTest(kind=kind, doc_id=doc_id), self.assertRaisesRegex(TrackerDocumentError, error):
                    link_tracker_document(session, "synthetic-document-1", kind, doc_id, self.now, request_key=f"bad-{kind}-{doc_id}")
            with self.assertRaisesRegex(TrackerDocumentError, "idempotency_key is required"):
                link_tracker_document(session, "synthetic-document-1", "cv", self.recommended_variant, self.now, request_key=" ")

            before_events = session.query(FounderActivityEventRecord).count()
            result = link_tracker_document(session, "synthetic-document-3", "cv", self.recommended_variant, self.now, request_key="rollback-link")
            self.assertTrue(result.changed)
            session.rollback()
            self.assertEqual(session.query(FounderTrackerDocumentRecord).filter_by(opportunity_id="synthetic-document-3").count(), 0)
            self.assertEqual(session.query(FounderActivityEventRecord).count(), before_events)
            self.assertIsNone(session.get(FounderApplicationDetailRecord, "synthetic-document-3"))
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
