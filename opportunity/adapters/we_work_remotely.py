"""We Work Remotely Public RSS Feed Adapter."""
from __future__ import annotations

import re
import xml.etree.ElementTree as element_tree
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


class WeWorkRemotelyAdapter(BaseAdapter):
    """Parses We Work Remotely RSS feed."""

    def __init__(self) -> None:
        super().__init__(
            source_id="we_work_remotely",
            track=Track.EMPLOYMENT,
            feed_url="https://weworkremotely.com/remote-jobs.rss",
            policy_url="https://weworkremotely.com/terms-and-conditions",
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> list[Opportunity]:
        try:
            root = element_tree.fromstring(payload)
        except element_tree.ParseError as e:
            raise ValueError(f"invalid XML in We Work Remotely RSS payload: {e}")

        items = root.findall(".//item")
        opportunities: list[Opportunity] = []
        for item in items:
            raw_title = clean_text(item.findtext("title"))
            if not raw_title:
                continue

            # WWR format is typically: "Company Name: Job Title"
            if ":" in raw_title:
                org_part, _, title_part = raw_title.partition(":")
                organization = clean_text(org_part)
                title = clean_text(title_part)
            else:
                organization = "We Work Remotely Employer"
                title = raw_title

            url = clean_text(item.findtext("link") or item.findtext("guid"))
            posted_date = parse_iso_date(item.findtext("pubDate"))
            raw_desc = str(item.findtext("description") or "")
            description = clean_text(raw_desc)
            
            # Region tag or custom tag
            region = clean_text(item.findtext("region") or item.findtext("category") or "Anywhere in the World")
            location_raw = region

            # Extract remote ID from URL guid or link
            id_match = re.search(r"/remote-jobs/(\d+-[^/?#]+)", url)
            remote_id = id_match.group(1) if id_match else clean_text(item.findtext("guid"))

            responsibilities = extract_list_sections(raw_desc, r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(raw_desc, r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            skills = extract_skills_from_text(f"{title} {description}")
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type(region, title, description)
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
