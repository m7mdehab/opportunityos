"""Remote OK Public API Adapter."""
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


class RemoteOKAdapter(BaseAdapter):
    """Parses Remote OK public API."""

    def __init__(self) -> None:
        super().__init__(
            source_id="remote_ok",
            track=Track.EMPLOYMENT,
            feed_url="https://remoteok.com/api",
            policy_url="https://remoteok.com/terms",
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> list[Opportunity]:
        data = json.loads(payload)
        if not isinstance(data, list):
            raise ValueError(f"expected Remote OK payload to be list, got {type(data)}")

        # Remote OK API often includes legal / metadata item at index 0 without "position" or "id"
        jobs = [item for item in data if isinstance(item, dict) and ("position" in item or "title" in item)]
        opportunities: list[Opportunity] = []
        for job in jobs:
            remote_id = str(job.get("id") or "")
            title = clean_text(job.get("position") or job.get("title"))
            if not title:
                continue

            organization = clean_text(job.get("company") or "Remote OK Employer")
            raw_desc = str(job.get("description") or "")
            description = clean_text(raw_desc)
            location_raw = clean_text(job.get("location") or "Remote")
            url = str(job.get("url") or f"https://remoteok.com/l/{remote_id}" if remote_id else "")
            posted_date = parse_iso_date(job.get("date"))

            # Tags & skills
            tags = job.get("tags") if isinstance(job.get("tags"), list) else []
            tags_text = " ".join(str(t) for t in tags)
            skills = extract_skills_from_text(f"{title} {description} {tags_text}")

            # Salary
            min_sal = job.get("salary_min")
            max_sal = job.get("salary_max")
            comp = None
            if min_sal is not None or max_sal is not None:
                try:
                    c_min = float(min_sal) if min_sal is not None else None
                    c_max = float(max_sal) if max_sal is not None else None
                    comp = Compensation(
                        min_amount=c_min,
                        max_amount=c_max,
                        currency="USD",
                        interval=CompensationInterval.YEARLY,
                    )
                except ValueError:
                    comp = None

            responsibilities = extract_list_sections(raw_desc, r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(raw_desc, r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type(tags_text, title, description)
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
