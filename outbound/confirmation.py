"""Confirmation Receipt & Evidence Detector."""
from __future__ import annotations

import re
from .models import ConfirmationEvidence


class ConfirmationDetector:
    """Detects and extracts cryptographic submission confirmation receipts."""

    SUCCESS_PATTERNS = [
        re.compile(r"thank you for (?:your )?applying", re.IGNORECASE),
        re.compile(r"application (?:has been )?submitted", re.IGNORECASE),
        re.compile(r"application (?:has been )?received", re.IGNORECASE),
        re.compile(r"we have received your application", re.IGNORECASE),
        re.compile(r"submission successful", re.IGNORECASE),
        re.compile(r"your application was sent", re.IGNORECASE),
    ]

    RECEIPT_PATTERNS = [
        re.compile(r"(?:confirmation|application|reference|receipt)\s*(?:#|id|number|code)?\s*[:\-]?\s*([a-zA-Z0-9_\-]+)", re.IGNORECASE),
    ]

    @classmethod
    def detect_confirmation(
        cls,
        page_text: str,
        current_url: str = "",
    ) -> ConfirmationEvidence | None:
        """Evaluate page content for deterministic confirmation indicators."""
        if not page_text or not page_text.strip():
            return None

        matched_text = ""
        for pat in cls.SUCCESS_PATTERNS:
            m = pat.search(page_text)
            if m:
                matched_text = m.group(0)
                break

        if not matched_text:
            return None

        receipt_id = ""
        for rpat in cls.RECEIPT_PATTERNS:
            rm = rpat.search(page_text)
            if rm:
                receipt_id = rm.group(1)
                break

        return ConfirmationEvidence(
            confirmed=True,
            confirmation_text=matched_text,
            receipt_reference=receipt_id,
            final_url=current_url,
        )
