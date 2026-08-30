"""Remotive Jobs Public API Adapter."""
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


class RemotiveAdapter(BaseAdapter):
    """Parses Remotive public remote jobs API."""

    def __init__(self) -> None:
        super().__init__(
            source_id="remotive",
            track=Track.EMPLOYMENT,
            feed_url="https://remotive.com/api/remote-jobs?limit=100",
            policy_url="https://remotive.com/terms",
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> list[Opportunity]:
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError(f"expected Remotive payload to be dict, got {type(data)}")

        jobs = data.get("jobs", [])
        opportunities: list[Opportunity] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            remote_id = str(job.get("id") or "")
            title = clean_text(job.get("title"))
            if not title:
                continue

            organization = clean_text(job.get("company_name") or "Remotive Employer")
            raw_desc = str(job.get("description") or "")
            description = clean_text(raw_desc)
            location_raw = clean_text(job.get("candidate_required_location") or "Remote")
            url = str(job.get("url") or "")
            posted_date = parse_iso_date(job.get("publication_date"))

            # Tags & skills
            tags = job.get("tags") if isinstance(job.get("tags"), list) else []
            tags_text = " ".join(str(t) for t in tags)
            skills = extract_skills_from_text(f"{title} {description} {tags_text}")

            responsibilities = extract_list_sections(raw_desc, r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(raw_desc, r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type(str(job.get("job_type") or ""), title, description)
            remote_policy = extract_remote_policy(location_raw, description)
            comp = extract_compensation(str(job.get("salary") or "")) or extract_compensation(description)
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
