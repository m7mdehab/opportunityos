"""Greenhouse ATS Public API Adapter."""
from __future__ import annotations

import json
from typing import Any

from opportunity.models import Opportunity, Track
from opportunity.normalization import (
    clean_text,
    derive_geographic_eligibility,
    extract_compensation,
    extract_employment_type,
    extract_list_sections,
    extract_remote_policy,
    extract_seniority,
    extract_skills_from_text,
    parse_iso_date,
)
from opportunity.adapters.base import BaseAdapter


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
    ) -> list[Opportunity]:
        data = json.loads(payload)
        if isinstance(data, dict):
            jobs = data.get("jobs", [])
        elif isinstance(data, list):
            jobs = data
        else:
            raise ValueError(f"unexpected Greenhouse payload type: {type(data)}")

        opportunities: list[Opportunity] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            remote_id = str(job.get("id") or "")
            title = clean_text(job.get("title"))
            if not title:
                continue

            raw_content = str(job.get("content") or "")
            description = clean_text(raw_content)
            loc_dict = job.get("location") if isinstance(job.get("location"), dict) else {}
            location_raw = clean_text(loc_dict.get("name") or job.get("location"))
            url = str(job.get("absolute_url") or "")
            updated_at = parse_iso_date(job.get("updated_at"))

            responsibilities = extract_list_sections(raw_content, r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(raw_content, r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            skills = extract_skills_from_text(f"{title} {description}")
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type(str(job.get("employment_type") or ""), title, description)
            remote_policy = extract_remote_policy(location_raw, description)
            comp = extract_compensation(description)
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
                id=f"{self.source_id}:{remote_id}" if remote_id else f"{self.source_id}:{abs(hash(title))}",
                track=Track.EMPLOYMENT,
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
            )
            opportunities.append(opp)

        return opportunities
