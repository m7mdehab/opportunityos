import unittest
from matching.models import (
    TailoredArtifact,
    ArtifactType,
    ArtifactSection,
    GeneratedClaim,
    CommitmentStatus,
)
from matching.binary_export import BinaryArtifactExporter
from matching.ats_quality import AtsDocumentQualityHarness

class TestBinaryArtifactExport(unittest.TestCase):
    def setUp(self):
        self.artifact = TailoredArtifact(
            artifact_id="ART-100",
            artifact_type=ArtifactType.TAILORED_CV,
            opportunity_id="OPP-100",
            opportunity_content_hash="hashopp123",
            template_version="1.0",
            policy_version="1.0",
            title="Senior Distributed Systems Architect - Ahmed Ehab",
            sections=(
                ArtifactSection(
                    section_id="summary",
                    heading="Professional Summary",
                    content="10+ years engineering high-scale distributed backend systems and real-time messaging architectures.",
                    items=(),
                    assertion_ids=("as-1",),
                    evidence_ids=("ev-1",),
                ),
                ArtifactSection(
                    section_id="experience",
                    heading="Key Achievements",
                    content="",
                    items=(
                        "Scaled real-time streaming pipeline from 10k to 500k RPS with zero downtime.",
                        "Designed multi-region PostgreSQL disaster recovery topology with 99.999% uptime.",
                    ),
                    assertion_ids=("as-2", "as-3"),
                    evidence_ids=("ev-2", "ev-3"),
                ),
                ArtifactSection(
                    section_id="skills",
                    heading="Technical Skills",
                    content="",
                    items=("Python, PostgreSQL, Distributed Consensus, Docker, Linux Internals",),
                    assertion_ids=("as-4",),
                    evidence_ids=("ev-4",),
                ),
            ),
            generated_claims=(
                GeneratedClaim(
                    claim_id="cl-1",
                    text="10+ years engineering high-scale distributed backend systems and real-time messaging architectures.",
                    section_id="summary",
                    assertion_ids=("as-1",),
                    evidence_ids=("ev-1",),
                    predicate="summary",
                    authorized_value="10+ years",
                ),
            ),
            commitment_checklist=(),
            compiled_at="2026-08-31T20:00:00Z",
        )

    def test_docx_export_and_inspection(self):
        docx_bytes = BinaryArtifactExporter.export_to_docx(self.artifact)
        self.assertGreater(len(docx_bytes), 0)
        
        info = AtsDocumentQualityHarness.inspect_docx(docx_bytes)
        self.assertTrue(info["has_content"])
        self.assertIn("Senior Distributed Systems Architect", info["full_text"])
        self.assertIn("Key Achievements", info["full_text"])
        self.assertIn("Scaled real-time streaming pipeline", info["full_text"])

    def test_pdf_export_and_inspection(self):
        pdf_bytes = BinaryArtifactExporter.export_to_pdf(self.artifact)
        self.assertGreater(len(pdf_bytes), 0)
        
        info = AtsDocumentQualityHarness.inspect_pdf(pdf_bytes)
        self.assertTrue(info["has_content"])
        self.assertEqual(info["page_count"], 1)
        self.assertIn("Senior Distributed Systems Architect", info["full_text"])
        self.assertIn("Key Achievements", info["full_text"])

    def test_claim_parity_verification(self):
        docx_bytes = BinaryArtifactExporter.export_to_docx(self.artifact)
        pdf_bytes = BinaryArtifactExporter.export_to_pdf(self.artifact)
        
        parity_ok = AtsDocumentQualityHarness.verify_claim_parity(self.artifact, docx_bytes, pdf_bytes)
        self.assertTrue(parity_ok)


if __name__ == "__main__":
    unittest.main()
