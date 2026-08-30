"""Himalayas Jobs Public API Adapter."""
from __future__ import annotations

import json
from typing import Any

from opportunity.models import Compensation, CompensationInterval, Opportunity, Track
from opportunity.normalization import (
    clean_text,
    derive_geographic_eligibility,
    extract_employment_type,
    extract_list_sections,
    extract_remote_policy,
    extract_seniority,
    extract_skills_from_text,
    parse_iso_date,
)
from opportunity.adapters.base import BaseAdapter


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
        for job in jobs:
            if not isinstance(job, dict):
                continue
            remote_id = str(job.get("id") or job.get("slug") or "")
            title = clean_text(job.get("title"))
            if not title:
                continue

            organization = clean_text(job.get("companyName") or job.get("company_name") or "Himalayas Employer")
            raw_desc = str(job.get("description") or "")
            description = clean_text(raw_desc)
            
            # Location & restrictions
            loc_parts = []
            if job.get("location"):
                loc_parts.append(str(job.get("location")))
            if job.get("locationRestrictions"):
                loc_parts.extend(job.get("locationRestrictions") if isinstance(job.get("locationRestrictions"), list) else [str(job.get("locationRestrictions"))])
            location_raw = clean_text(", ".join(loc_parts) or "Remote")

            url = str(job.get("applicationLink") or job.get("url") or "")
            posted_date = parse_iso_date(job.get("pubDate") or job.get("createdAt") or job.get("publishedAt"))

            # Compensation
            min_sal = job.get("minSalary") or job.get("min_salary")
            max_sal = job.get("maxSalary") or job.get("max_salary")
            currency = str(job.get("currency") or "USD") if (min_sal or max_sal) else None
            comp = None
            if min_sal is not None or max_sal is not None:
                try:
                    c_min = float(min_sal) if min_sal is not None else None
                    c_max = float(max_sal) if max_sal is not None else None
                    comp = Compensation(
                        min_amount=c_min,
                        max_amount=c_max,
                        currency=currency,
                        interval=CompensationInterval.YEARLY,
                    )
                except ValueError:
                    comp = None

            responsibilities = extract_list_sections(raw_desc, r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(raw_desc, r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            skills = extract_skills_from_text(f"{title} {description}")
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type(str(job.get("employmentType") or ""), title, description)
            remote_policy = extract_remote_policy(location_raw, description)
            geo = derive_geographic_eligibility(
                title=title,
                location_raw=location_raw,
                description=description,
                track=Track.EMPLOYMENT,
                source=self.source_id,
                url=url,
            )

            provenance = self.create_provenance(
                source_url=url,
                raw_pointer=raw_pointer,
                fetched_at=fetched_at,
                payload=payload,
            )

            opp = Opportunity(
                id=f"{self.source_id}:{remote_id}" if remote_id else f"{self.source_id}:{abs(hash(title + organization))}",
                track=Track.EMPLOYMENT,
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
            )
            opportunities.append(opp)

        return opportunities
