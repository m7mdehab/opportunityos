"""Himalayas Jobs Public API Adapter."""
from __future__ import annotations

import json
from typing import Any

from opportunity.adapters.base import BaseAdapter
from opportunity.models import (
    Compensation,
    CompensationInterval,
    DerivationType,
    FieldProvenance,
    Opportunity,
    Track,
    compute_deterministic_id,
)
from opportunity.normalization import (
    clean_text,
    compute_record_checksum,
    create_field_provenance,
    derive_geographic_eligibility,
    extract_employment_type,
    extract_list_sections,
    extract_remote_policy,
    extract_seniority,
    extract_skills_from_text,
    extract_track,
    parse_iso_date,
)


class HimalayasAdapter(BaseAdapter):
    """Parses Himalayas public remote jobs API."""

    def __init__(self) -> None:
        super().__init__(
            source_id="himalayas",
            track=Track.EMPLOYMENT,
            feed_url="https://himalayas.app/jobs/api?limit=100",
            policy_url="https://himalayas.app/terms",
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> list[Opportunity]:
        data = json.loads(payload)
        if isinstance(data, dict):
            jobs = data.get("jobs", [])
        elif isinstance(data, list):
            jobs = data
        else:
            raise ValueError(f"expected Himalayas payload to be dict or list, got {type(data)}")

        opportunities: list[Opportunity] = []
        for idx, job in enumerate(jobs):
            if not isinstance(job, dict):
                continue
            item_pointer = f"{raw_pointer or 'feed'}:jobs[{idx}]"
            record_checksum = compute_record_checksum(job)

            remote_id = str(job.get("id") or job.get("slug") or "")
            raw_title = job.get("title")
            title = clean_text(raw_title)
            if not title:
                continue

            raw_org = job.get("companyName") or job.get("company_name")
            organization = clean_text(raw_org)
            raw_desc = str(job.get("description") or "")
            description = clean_text(raw_desc)
            
            # Location & restrictions without default strings
            loc_parts = []
            if job.get("location"):
                loc_parts.append(str(job.get("location")))
            if job.get("locationRestrictions"):
                loc_parts.extend(job.get("locationRestrictions") if isinstance(job.get("locationRestrictions"), list) else [str(job.get("locationRestrictions"))])
            raw_loc = ", ".join(loc_parts)
            location_raw = clean_text(raw_loc)

            url = str(job.get("applicationLink") or job.get("url") or "")
            posted_date = parse_iso_date(job.get("pubDate") or job.get("createdAt") or job.get("publishedAt"))

            # Compensation without default currency or interval
            min_sal = job.get("minSalary") or job.get("min_salary")
            max_sal = job.get("maxSalary") or job.get("max_salary")
            currency = str(job.get("currency")) if job.get("currency") else None
            comp = None
            if min_sal is not None or max_sal is not None:
                try:
                    c_min = float(min_sal) if min_sal is not None else None
                    c_max = float(max_sal) if max_sal is not None else None
                    interval = CompensationInterval.YEARLY if (c_min or 0) > 10000 else CompensationInterval.UNSPECIFIED
                    comp = Compensation(
                        min_amount=c_min,
                        max_amount=c_max,
                        currency=currency,
                        interval=interval,
                    )
                except ValueError:
                    comp = None

            responsibilities = extract_list_sections(raw_desc, r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(raw_desc, r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            skills = extract_skills_from_text(f"{title} {description}")
            seniority = extract_seniority(title, description)
            raw_emp = str(job.get("employmentType") or "")
            emp_type = extract_employment_type(raw_emp, title, description)
            track = extract_track(self.track, raw_emp, title, description)
            remote_policy = extract_remote_policy(location_raw, description)
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

            field_provenances = (
                create_field_provenance("organization", raw_org, organization, DerivationType.RAW_EXTRACTION if organization else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.companyName", record_checksum, "clean_text"),
                create_field_provenance("title", raw_title, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.title", record_checksum, "clean_text"),
                create_field_provenance("description", raw_desc[:100], description[:100], DerivationType.RAW_EXTRACTION, f"{item_pointer}.description", record_checksum, "clean_text"),
                create_field_provenance("location_raw", raw_loc, location_raw, DerivationType.RAW_EXTRACTION if location_raw else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.location", record_checksum, "clean_text"),
                create_field_provenance("seniority", title, seniority.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.title", record_checksum, "extract_seniority"),
                create_field_provenance("employment_type", raw_emp, emp_type.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.employmentType", record_checksum, "extract_employment_type"),
                create_field_provenance("remote_policy", raw_loc, remote_policy.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.location", record_checksum, "extract_remote_policy"),
                create_field_provenance("geographic_eligibility", location_raw, geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.location", record_checksum, "classify_geography"),
            )

            opp_id = compute_deterministic_id(self.source_id, remote_id, title, organization, item_pointer)

            opp = Opportunity(
                id=opp_id,
                track=track,
                source=self.source_id,
                source_url=url,
                source_id=remote_id,
                organization=organization,
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
                posted_date=posted_date,
                raw_provenance=provenance,
                record_checksum=record_checksum,
                raw_record_pointer=item_pointer,
                field_provenances=field_provenances,
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return opportunities
