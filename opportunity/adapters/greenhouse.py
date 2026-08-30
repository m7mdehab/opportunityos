"""Greenhouse ATS Public API Adapter."""
from __future__ import annotations

import json
from typing import Any

from opportunity.adapters.base import BaseAdapter
from opportunity.models import (
    CompensationInterval,
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


class GreenhouseAdapter(BaseAdapter):
    """Parses Greenhouse public jobs endpoint."""

    def __init__(self, company_name: str, board_token: str | None = None) -> None:
        token = board_token or company_name
        feed_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        super().__init__(
            source_id=f"greenhouse:{company_name}",
            track=Track.EMPLOYMENT,
            feed_url=feed_url,
            policy_url="https://www.greenhouse.com/terms-of-use",
        )
        self.company_name = company_name.title() if company_name.islower() else company_name

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> ParseResult:
        data = json.loads(payload)
        if isinstance(data, dict):
            if "jobs" not in data:
                return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)
            jobs = data["jobs"]
        elif isinstance(data, list):
            jobs = data
        else:
            return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)

        raw_count = len(jobs)
        opportunities: list[Opportunity] = []
        for idx, job in enumerate(jobs):
            if not isinstance(job, dict):
                continue
            item_pointer = f"{raw_pointer or 'feed'}:jobs[{idx}]"
            record_checksum = compute_record_checksum(job)

            remote_id = str(job.get("id") or "")
            raw_title = job.get("title")
            title = clean_text(raw_title)
            if not title:
                continue

            raw_content = job.get("content")
            description = clean_text(raw_content) if raw_content else ""
            desc_derivation = DerivationType.RAW_EXTRACTION if description else DerivationType.UNASSERTED_ABSENT

            loc_dict = job.get("location") if isinstance(job.get("location"), dict) else {}
            raw_loc = loc_dict.get("name") or job.get("location")
            location_raw = clean_text(raw_loc)
            url = str(job.get("absolute_url") or "")
            raw_updated = job.get("updated_at")
            updated_at = parse_iso_date(raw_updated)

            responsibilities = extract_list_sections(str(raw_content or ""), r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(str(raw_content or ""), r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            skills = extract_skills_from_text(f"{title} {description}")
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type(str(job.get("employment_type") or ""), title, description)
            track = extract_track(self.track, str(job.get("employment_type") or ""), title, description)
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
                create_field_provenance("track", job.get("employment_type"), track.value, DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_track"),
                create_field_provenance("organization", self.company_name, self.company_name, DerivationType.SOURCE_METADATA_DERIVATION, item_pointer, record_checksum, "greenhouse_board_metadata"),
                create_field_provenance("title", raw_title, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.title", record_checksum, "clean_text"),
                create_field_provenance("description", (raw_content or "")[:100], description[:100], desc_derivation, f"{item_pointer}.content", record_checksum, "clean_text"),
                create_field_provenance("location_raw", raw_loc, location_raw, DerivationType.RAW_EXTRACTION if location_raw else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.location", record_checksum, "clean_text"),
                create_field_provenance("seniority", title, seniority.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.title", record_checksum, "extract_seniority"),
                create_field_provenance("employment_type", job.get("employment_type"), emp_type.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.employment_type", record_checksum, "extract_employment_type"),
                create_field_provenance("remote_policy", raw_loc, remote_policy.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.location", record_checksum, "extract_remote_policy"),
                create_field_provenance("geographic_eligibility", location_raw, geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.location", record_checksum, "classify_geography"),
            ]

            if skills:
                prov_list.append(create_field_provenance("skills", f"{title} {description[:50]}", ", ".join(skills), DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_skills"))
            if responsibilities:
                prov_list.append(create_field_provenance("responsibilities", (raw_content or "")[:50], f"{len(responsibilities)} items", DerivationType.RULE_DERIVATION, f"{item_pointer}.content", record_checksum, "extract_responsibilities"))
            if requirements:
                prov_list.append(create_field_provenance("requirements", (raw_content or "")[:50], f"{len(requirements)} items", DerivationType.RULE_DERIVATION, f"{item_pointer}.content", record_checksum, "extract_requirements"))
            if comp is not None:
                prov_list.append(create_field_provenance("compensation", description[:50], f"{comp.min_amount}-{comp.max_amount} {comp.currency}", DerivationType.RULE_DERIVATION, f"{item_pointer}.content", record_checksum, "extract_compensation"))
                if comp.min_amount is not None:
                    prov_list.append(create_field_provenance("compensation.min_amount", description[:50], str(comp.min_amount), DerivationType.RULE_DERIVATION, f"{item_pointer}.content", record_checksum, "extract_compensation"))
                if comp.max_amount is not None:
                    prov_list.append(create_field_provenance("compensation.max_amount", description[:50], str(comp.max_amount), DerivationType.RULE_DERIVATION, f"{item_pointer}.content", record_checksum, "extract_compensation"))
                if comp.currency is not None:
                    prov_list.append(create_field_provenance("compensation.currency", description[:50], comp.currency, DerivationType.RULE_DERIVATION, f"{item_pointer}.content", record_checksum, "extract_compensation"))
                if comp.interval != CompensationInterval.UNSPECIFIED:
                    prov_list.append(create_field_provenance("compensation.interval", description[:50], comp.interval.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.content", record_checksum, "extract_compensation"))
            if updated_at:
                prov_list.append(create_field_provenance("posted_date", raw_updated, updated_at, DerivationType.RAW_EXTRACTION, f"{item_pointer}.updated_at", record_checksum, "parse_iso_date"))

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
                posted_date=updated_at,
                raw_provenance=provenance,
                record_checksum=record_checksum,
                raw_record_pointer=item_pointer,
                field_provenances=tuple(prov_list),
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return ParseResult(opportunities=tuple(opportunities), records_raw_count=raw_count)
