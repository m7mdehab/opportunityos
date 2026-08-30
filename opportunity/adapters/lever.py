"""Lever ATS Public Postings API Adapter."""
from __future__ import annotations

import json
from typing import Any

from opportunity.adapters.base import BaseAdapter
from opportunity.models import (
    DerivationType,
    FieldProvenance,
    Opportunity,
    ParseResult,
    Track,
    compute_deterministic_id,
)
from opportunity.normalization import (
    clean_text,
    compute_record_checksum,
    create_field_provenance,
    derive_geographic_eligibility,
    extract_compensation,
    extract_employment_type,
    extract_list_sections,
    extract_remote_policy,
    extract_seniority,
    extract_skills_from_text,
    extract_track,
    parse_iso_date,
)


class LeverAdapter(BaseAdapter):
    """Parses Lever public postings endpoint."""

    def __init__(self, company_name: str, site_token: str | None = None) -> None:
        token = site_token or company_name
        feed_url = f"https://api.lever.co/v0/postings/{token}?mode=json"
        super().__init__(
            source_id=f"lever:{company_name}",
            track=Track.EMPLOYMENT,
            feed_url=feed_url,
            policy_url="https://www.lever.co/terms",
        )
        self.company_name = company_name.title() if company_name.islower() else company_name

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> ParseResult:
        data = json.loads(payload)
        if isinstance(data, list):
            postings = data
        elif isinstance(data, dict):
            if "postings" not in data:
                return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)
            postings = data["postings"]
        else:
            return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)

        raw_count = len(postings)
        opportunities: list[Opportunity] = []
        for idx, posting in enumerate(postings):
            if not isinstance(posting, dict):
                continue
            item_pointer = f"{raw_pointer or 'feed'}:postings[{idx}]"
            record_checksum = compute_record_checksum(posting)

            remote_id = str(posting.get("id") or "")
            raw_title = posting.get("text") or posting.get("title")
            title = clean_text(raw_title)
            if not title:
                continue

            raw_desc = posting.get("description") or posting.get("descriptionPlain")
            description = clean_text(raw_desc) if raw_desc else ""
            desc_derivation = DerivationType.RAW_EXTRACTION if description else DerivationType.UNASSERTED_ABSENT

            categories = posting.get("categories") if isinstance(posting.get("categories"), dict) else {}
            raw_loc = categories.get("location") or categories.get("allLocations") or ""
            location_raw = clean_text(raw_loc)
            commitment = clean_text(categories.get("commitment"))
            url = str(posting.get("hostedUrl") or posting.get("applyUrl") or "")
            raw_created = posting.get("createdAt")
            created_at = parse_iso_date(raw_created)

            responsibilities = extract_list_sections(str(raw_desc or ""), r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(str(raw_desc or ""), r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            skills = extract_skills_from_text(f"{title} {description}")
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type(commitment, title, description)
            track = extract_track(self.track, commitment, title, description)
            remote_policy = extract_remote_policy(location_raw, description)
            comp = extract_compensation(description)
            geo = derive_geographic_eligibility(
                title=title,
                location_raw=location_raw,
                description=description,
                track=track,
                source=self.source_id,
                url=url,
            )

            provenance = self.create_provenance(
                source_url=url,
                raw_pointer=item_pointer,
                fetched_at=fetched_at,
                payload=payload,
            )

            prov_list: list[FieldProvenance] = [
                create_field_provenance("track", commitment, track.value, DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_track"),
                create_field_provenance("organization", self.company_name, self.company_name, DerivationType.SOURCE_METADATA_DERIVATION, item_pointer, record_checksum, "lever_site_metadata"),
                create_field_provenance("title", raw_title, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.text", record_checksum, "clean_text"),
                create_field_provenance("description", (raw_desc or "")[:100], description[:100], desc_derivation, f"{item_pointer}.description", record_checksum, "clean_text"),
                create_field_provenance("location_raw", raw_loc, location_raw, DerivationType.RAW_EXTRACTION if location_raw else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.categories.location", record_checksum, "clean_text"),
                create_field_provenance("seniority", title, seniority.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.text", record_checksum, "extract_seniority"),
                create_field_provenance("employment_type", commitment, emp_type.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.categories.commitment", record_checksum, "extract_employment_type"),
                create_field_provenance("remote_policy", raw_loc, remote_policy.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.categories.location", record_checksum, "extract_remote_policy"),
                create_field_provenance("geographic_eligibility", location_raw, geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.categories.location", record_checksum, "classify_geography"),
            ]

            if skills:
                prov_list.append(create_field_provenance("skills", f"{title} {description[:50]}", ", ".join(skills), DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_skills"))
            if responsibilities:
                prov_list.append(create_field_provenance("responsibilities", (raw_desc or "")[:50], f"{len(responsibilities)} items", DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_responsibilities"))
            if requirements:
                prov_list.append(create_field_provenance("requirements", (raw_desc or "")[:50], f"{len(requirements)} items", DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_requirements"))
            if comp is not None:
                prov_list.append(create_field_provenance("compensation", description[:50], f"{comp.min_amount}-{comp.max_amount} {comp.currency}", DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_compensation"))
            if created_at:
                prov_list.append(create_field_provenance("posted_date", raw_created, created_at, DerivationType.RAW_EXTRACTION, f"{item_pointer}.createdAt", record_checksum, "parse_iso_date"))

            opp_id = compute_deterministic_id(self.source_id, remote_id, title, self.company_name, item_pointer)

            opp = Opportunity(
                id=opp_id,
                track=track,
                source=self.source_id,
                source_url=url,
                source_id=remote_id,
                organization=self.company_name,
                title=title,
                description=description,
                responsibilities=responsibilities,
                requirements=requirements,
                skills=skills,
                seniority=seniority,
                employment_type=emp_type,
                location_raw=location_raw,
                remote_policy=remote_policy,
                geographic_eligibility=geo,
                compensation=comp,
                posted_date=created_at,
                raw_provenance=provenance,
                record_checksum=record_checksum,
                raw_record_pointer=item_pointer,
                field_provenances=tuple(prov_list),
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return ParseResult(opportunities=tuple(opportunities), records_raw_count=raw_count)
