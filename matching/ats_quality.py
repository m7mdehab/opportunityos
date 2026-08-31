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
