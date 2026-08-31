import io
import docx
import pdfplumber
from typing import Dict, Any, List
from matching.models import TailoredArtifact

class AtsDocumentQualityHarness:
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

        docx_text = docx_info["full_text"]
        pdf_text = pdf_info["full_text"]

        # Verify all sections and items appear in both outputs
        for sec in artifact.sections:
            if sec.heading:
                if sec.heading not in docx_text or sec.heading not in pdf_text:
                    return False
            if sec.content:
                # Basic check for key fragments
                words = sec.content.split()
                if words and words[0] not in docx_text:
                    return False
            for item in sec.items:
                if item not in docx_text or item not in pdf_text:
                    return False

        return True
