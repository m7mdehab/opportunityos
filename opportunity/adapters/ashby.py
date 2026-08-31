import json
import hashlib
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

class AshbyAdapter:
    @staticmethod
    def parse_job_posting(organization: str, job_dict: Dict[str, Any], fetched_at: str) -> Opportunity:
        job_id = str(job_dict.get("id", ""))
        title = str(job_dict.get("title", "")).strip()
        desc = str(job_dict.get("descriptionHtml", "") or job_dict.get("descriptionPlain", "")).strip()
        location_name = str(job_dict.get("locationName", "")).strip()
        source_url = str(job_dict.get("jobUrl", "") or f"https://jobs.ashbyhq.com/{organization}/{job_id}")

        content_hash = compute_canonical_content_hash(organization, title, location_name, desc)
        dedup_key = compute_dedup_key(organization, title, location_name)
        opp_id = f"ashby:{organization}:{job_id}"

        provenances = [
            FieldProvenance(
                field_name="title",
                raw_value=title,
                normalized_value=title,
                derivation_type=DerivationType.RAW_EXTRACTION.value,
                raw_pointer="title",
                record_checksum=hashlib.sha256(title.encode("utf-8")).hexdigest(),
                rule_id="ASHBY_TITLE_1",
            ),
            FieldProvenance(
                field_name="organization",
                raw_value=organization,
                normalized_value=organization,
                derivation_type=DerivationType.SOURCE_METADATA_DERIVATION.value,
                raw_pointer="org",
                record_checksum=hashlib.sha256(organization.encode("utf-8")).hexdigest(),
                rule_id="ASHBY_ORG_1",
            ),
            FieldProvenance(
                field_name="description",
                raw_value=desc[:500],
                normalized_value=desc[:500],
                derivation_type=DerivationType.RAW_EXTRACTION.value,
                raw_pointer="descriptionPlain",
                record_checksum=hashlib.sha256(desc[:500].encode("utf-8")).hexdigest(),
                rule_id="ASHBY_DESC_1",
            ),
        ]

        raw_prov = SourceProvenance(
            source_id=f"ashby:{organization}",
            source_url=source_url,
            feed_url=f"https://api.ashbyhq.com/posting-api/job-board/{organization}",
            fetched_at=fetched_at,
            payload_checksum=hashlib.sha256(json.dumps(job_dict, sort_keys=True).encode("utf-8")).hexdigest(),
        )

        return Opportunity(
            id=opp_id,
            track=Track.EMPLOYMENT,
            source=f"ashby:{organization}",
            source_url=source_url,
            source_id=f"ashby:{organization}",
            organization=organization,
            title=title,
            description=desc,
            location_raw=location_name,
            raw_provenance=raw_prov,
            field_provenances=tuple(provenances),
            canonical_outbound_url=source_url,
            content_hash=content_hash,
            dedup_key=dedup_key,
        )
