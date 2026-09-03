import unittest

from matching.models import (
    TailoredArtifact,
    ArtifactType,
    ArtifactSection,
)
from matching.binary_export import BinaryArtifactExporter
from matching.ats_quality import AtsDocumentQualityHarness


def _make_artifact(content: str) -> TailoredArtifact:
    return TailoredArtifact(
        artifact_id="ART-DATE-1",
        artifact_type=ArtifactType.TAILORED_CV,
        opportunity_id="OPP-DATE-1",
        opportunity_content_hash="hashopp-date",
        template_version="1.0",
        policy_version="1.0",
        title="Backend Engineer - Ahmed Ehab",
        sections=(
            ArtifactSection(
                section_id="experience",
                heading="Experience",
                content=content,
                items=(),
                assertion_ids=("as-1",),
                evidence_ids=("ev-1",),
            ),
        ),
        generated_claims=(),
        commitment_checklist=(),
        compiled_at="2026-08-31T20:00:00Z",
    )


class TestAtsParseCheckDates(unittest.TestCase):
    def test_dates_parsed_count_positive_for_real_dates(self):
        artifact = _make_artifact(
            "Employed from 2023-01-01 through Jan 2026 leading backend platform engineering."
        )
        pdf_bytes = BinaryArtifactExporter.export_to_pdf(artifact)

        result = AtsDocumentQualityHarness.ats_parse_check(artifact, pdf_bytes)

        self.assertGreater(result["dates_parsed_count"], 0)
        self.assertEqual(result["tables_detected"], 0)

    def test_dates_parsed_count_zero_for_no_dates(self):
        artifact = _make_artifact(
            "Led backend platform engineering with no temporal references present here."
        )
        pdf_bytes = BinaryArtifactExporter.export_to_pdf(artifact)

        result = AtsDocumentQualityHarness.ats_parse_check(artifact, pdf_bytes)

        self.assertEqual(result["dates_parsed_count"], 0)


if __name__ == "__main__":
    unittest.main()
