import json
import re
import hashlib
from typing import Dict, Any, Optional
from opportunity.models import (
    Opportunity,
    Track,
    FieldProvenance,
    DerivationType,
    SourceProvenance,
    compute_canonical_content_hash,
    compute_dedup_key,
)

class SchemaOrgJobPostingExtractor:
    @staticmethod
    def extract_from_json_ld(json_ld_data: Dict[str, Any], source_url: str, fetched_at: str) -> Optional[Opportunity]:
        type_field = json_ld_data.get("@type", "")
        if type_field != "JobPosting" and type_field != ["JobPosting"]:
            return None

        title = str(json_ld_data.get("title", "")).strip()
        desc = str(json_ld_data.get("description", "")).strip()
        
        org_data = json_ld_data.get("hiringOrganization", {})
        organization = "Confidential"
        if isinstance(org_data, dict):
            organization = org_data.get("name", "Confidential")
        elif isinstance(org_data, str):
            organization = org_data

        content_hash = compute_canonical_content_hash(organization, title, "", desc)
        dedup_key = compute_dedup_key(organization, title, "")
        opp_id = f"schema-org:{content_hash[:12]}"

        provenances = [
            FieldProvenance(
                field_name="title",
                raw_value=title,
                normalized_value=title,
                derivation_type=DerivationType.RAW_EXTRACTION.value,
                raw_pointer="jsonld.title",
                record_checksum=hashlib.sha256(title.encode("utf-8")).hexdigest(),
                rule_id="SCHEMA_ORG_TITLE",
            ),
            FieldProvenance(
                field_name="organization",
                raw_value=organization,
                normalized_value=organization,
                derivation_type=DerivationType.RAW_EXTRACTION.value,
                raw_pointer="jsonld.hiringOrganization.name",
                record_checksum=hashlib.sha256(organization.encode("utf-8")).hexdigest(),
                rule_id="SCHEMA_ORG_ORG",
            ),
            FieldProvenance(
                field_name="description",
                raw_value=desc[:500],
                normalized_value=desc[:500],
                derivation_type=DerivationType.RAW_EXTRACTION.value,
                raw_pointer="jsonld.description",
                record_checksum=hashlib.sha256(desc[:500].encode("utf-8")).hexdigest(),
                rule_id="SCHEMA_ORG_DESC",
            ),
        ]

        raw_prov = SourceProvenance(
            source_id="schema_org:jsonld",
            source_url=source_url,
            feed_url=source_url,
            fetched_at=fetched_at,
            payload_checksum=hashlib.sha256(json.dumps(json_ld_data, sort_keys=True).encode("utf-8")).hexdigest(),
        )

        return Opportunity(
            id=opp_id,
            track=Track.EMPLOYMENT,
            source="schema_org:jsonld",
            source_url=source_url,
            source_id="schema_org:jsonld",
            organization=organization,
            title=title,
            description=desc,
            raw_provenance=raw_prov,
            field_provenances=tuple(provenances),
            canonical_outbound_url=source_url,
            content_hash=content_hash,
            dedup_key=dedup_key,
        )
