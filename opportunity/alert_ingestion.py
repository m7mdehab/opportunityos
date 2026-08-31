import re
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from opportunity.models import (
    Opportunity,
    Track,
    FieldProvenance,
    DerivationType,
    SourceProvenance,
    compute_canonical_content_hash,
    compute_dedup_key,
)

TITLE_PATTERNS = [
    re.compile(r"(?i)new job(?: opening)?:\s*([^\n\r\|–—]+)"),
    re.compile(r"(?i)job alert:\s*([^\n\r\|–—]+)"),
    re.compile(r"(?i)opportunity:\s*([^\n\r\|–—]+)"),
    re.compile(r"(?i)role:\s*([^\n\r\|–—]+)"),
    re.compile(r"(?i)^([A-Za-z0-9\s/,\-\+]+?)\s+at\s+([A-Za-z0-9\s,\-\.\&]+)"),
]

ORG_PATTERNS = [
    re.compile(r"(?i)\bat\s+([A-Za-z0-9\s,\-\.\&]+?)(?:\s+in|\s+-\s+|\s*\n|\s*\r|$)"),
    re.compile(r"(?i)company:\s*([A-Za-z0-9\s,\-\.\&]+)"),
    re.compile(r"(?i)organization:\s*([A-Za-z0-9\s,\-\.\&]+)"),
]

URL_PATTERN = re.compile(r"https?://[^\s<>\"'\)\(]+")


class AlertIngestionEngine:
    @staticmethod
    def parse_alert_message(
        source_provider: str,
        sender: str,
        subject: str,
        body: str,
        received_at: Optional[datetime] = None,
    ) -> Optional[Opportunity]:
        received_time = received_at or datetime.now(timezone.utc)
        
        # 1. Extract Title
        title = None
        for pattern in TITLE_PATTERNS:
            match = pattern.search(subject) or pattern.search(body)
            if match:
                title = match.group(1).strip()
                break
        if not title:
            if len(subject) < 100 and not any(kw in subject.lower() for kw in ("digest", "newsletter")):
                title = subject.strip()
            else:
                title = "Unknown Opportunity"

        # 2. Extract Organization
        organization = None
        for pattern in ORG_PATTERNS:
            match = pattern.search(subject) or pattern.search(body)
            if match:
                organization = match.group(1).strip()
                break
        if not organization:
            organization = "Confidential Employer"

        # 3. Extract Canonical URL
        urls = URL_PATTERN.findall(body) or URL_PATTERN.findall(subject)
        canonical_url = urls[0] if urls else f"https://alerts.opportunityos.internal/alert-{hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]}"

        # 4. Generate Opportunity ID and Content Hash
        content_hash = compute_canonical_content_hash(organization, title, "", body)
        dedup_key = compute_dedup_key(organization, title, "")
        opp_id = f"alert-{source_provider.lower()}:{content_hash[:12]}"

        track = Track.EMPLOYMENT
        if any(kw in (subject + " " + body).lower() for kw in ("tender", "procurement", "rfp", "eoi", "contract")):
            track = Track.PROCUREMENT
        elif any(kw in (subject + " " + body).lower() for kw in ("freelance", "upwork", "mostaql", "bounty")):
            track = Track.FREELANCE

        # 5. Build Provenances
        provenances = [
            FieldProvenance(
                field_name="title",
                raw_value=title,
                normalized_value=title,
                derivation_type=DerivationType.RULE_DERIVATION.value,
                raw_pointer="subject",
                record_checksum=hashlib.sha256(title.encode("utf-8")).hexdigest(),
                rule_id="ALERT_TITLE_RULE_1",
            ),
            FieldProvenance(
                field_name="organization",
                raw_value=organization,
                normalized_value=organization,
                derivation_type=DerivationType.RULE_DERIVATION.value,
                raw_pointer="subject",
                record_checksum=hashlib.sha256(organization.encode("utf-8")).hexdigest(),
                rule_id="ALERT_ORG_RULE_1",
            ),
            FieldProvenance(
                field_name="description",
                raw_value=body[:500],
                normalized_value=body[:500],
                derivation_type=DerivationType.RAW_EXTRACTION.value,
                raw_pointer="body",
                record_checksum=hashlib.sha256(body[:500].encode("utf-8")).hexdigest(),
                rule_id="ALERT_BODY_RULE_1",
            ),
        ]

        raw_prov = SourceProvenance(
            source_id=f"alert:{source_provider.lower()}",
            source_url=canonical_url,
            feed_url="",
            fetched_at=received_time.isoformat(),
            payload_checksum=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        )

        return Opportunity(
            id=opp_id,
            track=track,
            source=f"alert:{source_provider.lower()}",
            source_url=canonical_url,
            source_id=f"alert:{source_provider.lower()}",
            organization=organization,
            title=title,
            description=body,
            raw_provenance=raw_prov,
            field_provenances=tuple(provenances),
            canonical_outbound_url=canonical_url,
            content_hash=content_hash,
            dedup_key=dedup_key,
        )
