"""Lever ATS Public Postings API Adapter."""
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
        self.company_name = company_name

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> list[Opportunity]:
        data = json.loads(payload)
        if not isinstance(data, list):
            raise ValueError(f"expected Lever payload to be a list, got {type(data)}")

        opportunities: list[Opportunity] = []
        for posting in data:
            if not isinstance(posting, dict):
                continue
            remote_id = str(posting.get("id") or "")
            title = clean_text(posting.get("text") or posting.get("title"))
            if not title:
                continue

            raw_desc = str(posting.get("description") or posting.get("descriptionPlain") or "")
            description = clean_text(raw_desc)
            categories = posting.get("categories") if isinstance(posting.get("categories"), dict) else {}
            location_raw = clean_text(categories.get("location") or categories.get("allLocations") or "")
            commitment = clean_text(categories.get("commitment"))
            url = str(posting.get("hostedUrl") or posting.get("applyUrl") or "")
            created_at = parse_iso_date(posting.get("createdAt"))

            responsibilities = extract_list_sections(raw_desc, r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(raw_desc, r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            skills = extract_skills_from_text(f"{title} {description}")
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type(commitment, title, description)
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
                posted_date=created_at,
                raw_provenance=provenance,
            )
            opportunities.append(opp)

        return opportunities
