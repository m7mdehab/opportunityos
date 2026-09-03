import io
import re
import docx
import pdfplumber
from typing import Dict, Any, List
from matching.models import TailoredArtifact

class AtsDocumentQualityHarness:
    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def inspect_docx(docx_bytes: bytes) -> Dict[str, Any]:
        doc = docx.Document(io.BytesIO(docx_bytes))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        full_text = "\n".join(paragraphs)
        return {
            "paragraph_count": len(paragraphs),
            "full_text": full_text,
            "has_content": len(full_text) > 0,
        }

    @staticmethod
    def inspect_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for idx, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append({"page_number": idx + 1, "text": text})
            full_text = "\n".join(p["text"] for p in pages)
            return {
                "page_count": len(pages),
                "pages": pages,
                "full_text": full_text,
                "has_content": len(full_text) > 0,
            }

    @staticmethod
    def verify_claim_parity(artifact: TailoredArtifact, docx_bytes: bytes, pdf_bytes: bytes) -> bool:
        docx_info = AtsDocumentQualityHarness.inspect_docx(docx_bytes)
        pdf_info = AtsDocumentQualityHarness.inspect_pdf(pdf_bytes)

        docx_norm = AtsDocumentQualityHarness._normalize_whitespace(docx_info["full_text"])
        pdf_norm = AtsDocumentQualityHarness._normalize_whitespace(pdf_info["full_text"])

        # 1. Document Title Verification
        title_norm = AtsDocumentQualityHarness._normalize_whitespace(artifact.title)
        if title_norm not in docx_norm or title_norm not in pdf_norm:
            return False

        # 2. Section Heading & Content Full Parity Verification
        for sec in artifact.sections:
            if sec.heading:
                h_norm = AtsDocumentQualityHarness._normalize_whitespace(sec.heading)
                if h_norm not in docx_norm or h_norm not in pdf_norm:
                    return False
            if sec.content:
                c_norm = AtsDocumentQualityHarness._normalize_whitespace(sec.content)
                if c_norm not in docx_norm or c_norm not in pdf_norm:
                    return False
            for item in sec.items:
                i_norm = AtsDocumentQualityHarness._normalize_whitespace(item)
                if i_norm not in docx_norm or i_norm not in pdf_norm:
                    return False

        # 3. Generated Claims Parity
        for claim in artifact.generated_claims:
            cl_norm = AtsDocumentQualityHarness._normalize_whitespace(claim.text)
            if cl_norm not in docx_norm or cl_norm not in pdf_norm:
                return False

        return True

    @staticmethod
    def ats_parse_check(artifact: "TailoredArtifact", pdf_bytes: bytes) -> Dict[str, Any]:
        """A committed ATS-parse check over the extracted PDF text (work
        order D1 requirement 7): which of the artifact's own section
        headings are detected verbatim, how many employment/education/
        certification dates parse, and that no table is present in the PDF
        (`pdfplumber`'s own table detector -- this module never builds a
        `reportlab.platypus.Table`, so this is expected to always be empty,
        and asserting it is what proves that, not just that we didn't call
        the API)."""
        pdf_info = AtsDocumentQualityHarness.inspect_pdf(pdf_bytes)
        full_text = pdf_info["full_text"]
        norm_text = AtsDocumentQualityHarness._normalize_whitespace(full_text)

        sections_detected = [
            sec.heading for sec in artifact.sections
            if sec.heading and AtsDocumentQualityHarness._normalize_whitespace(sec.heading) in norm_text
        ]

        date_pattern = re.compile(
            r"(?:\d{4}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})"
        )
        dates_parsed = date_pattern.findall(full_text)

        tables_detected = 0
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables_detected += len(page.extract_tables())

        return {
            "sections_detected": sections_detected,
            "dates_parsed_count": len(dates_parsed),
            "dates_parsed": dates_parsed,
            "tables_detected": tables_detected,
        }

