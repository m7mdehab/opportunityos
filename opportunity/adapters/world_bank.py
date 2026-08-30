"""World Bank Procurement Opportunities Adapter."""
from __future__ import annotations

import json
import re
from typing import Any

from opportunity.models import Opportunity, ProcurementMetadata, Track
from opportunity.normalization import (
    clean_text,
    derive_geographic_eligibility,
    extract_skills_from_text,
    parse_iso_date,
)
from opportunity.adapters.base import BaseAdapter


class WorldBankAdapter(BaseAdapter):
    """Parses World Bank procurement notices and consulting opportunities."""

    def __init__(self) -> None:
        super().__init__(
            source_id="world_bank",
            track=Track.PROCUREMENT,
            feed_url="https://projects.worldbank.org/en/projects-operations/opportunities",
            policy_url="https://www.worldbank.org/en/about/legal/terms-of-use",
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> list[Opportunity]:
        opportunities: list[Opportunity] = []

        # Structured JSON format
        if payload.strip().startswith("{") or payload.strip().startswith("["):
            try:
                data = json.loads(payload)
                items = data if isinstance(data, list) else data.get("notices") or data.get("rows") or data.get("results") or []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    remote_id = str(item.get("id") or item.get("notice_id") or item.get("procurement_id") or "")
                    title = clean_text(item.get("notice_title") or item.get("title") or item.get("project_name"))
                    if not title:
                        continue

                    buyer = clean_text(item.get("borrower") or item.get("country_name") or "World Bank")
                    country = clean_text(item.get("country_name") or item.get("country") or "")
                    deadline = parse_iso_date(item.get("submission_date") or item.get("deadline") or item.get("closing_date"))
                    posted_date = parse_iso_date(item.get("published_date") or item.get("publication_date") or item.get("date"))
                    description = clean_text(item.get("description") or item.get("notice_text") or title)
                    url = str(item.get("url") or f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{remote_id}" if remote_id else "")
                    notice_type = clean_text(item.get("notice_type") or item.get("type") or "Request for Proposals")

                    proc_meta = ProcurementMetadata(
                        notice_type=notice_type,
                        buyer_name=buyer,
                        buyer_country=country,
                        procurement_category=clean_text(item.get("sector") or item.get("category") or "Consulting Services"),
                        deadline=deadline,
                    )

                    skills = extract_skills_from_text(f"{title} {description}")
                    geo = derive_geographic_eligibility(
                        title=title,
                        location_raw=country,
                        description=description,
                        track=Track.PROCUREMENT,
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
                        id=f"{self.source_id}:{remote_id}" if remote_id else f"{self.source_id}:{abs(hash(title + buyer))}",
                        track=Track.PROCUREMENT,
                        source=self.source_id,
                        source_url=url,
                        source_id=remote_id,
                        organization="World Bank",
                        title=title,
                        description=description,
                        skills=skills,
                        location_raw=country,
                        geographic_eligibility=geo,
                        posted_date=posted_date,
                        closing_date=deadline,
                        procurement_metadata=proc_meta,
                        raw_provenance=provenance,
                    )
                    opportunities.append(opp)
                return opportunities
            except json.JSONDecodeError:
                pass

        # HTML parsing fallback
        links = re.findall(
            r'<a[^>]+href=["\']([^"\']*(?:procurement-detail|opportunities)[^"\']*)["\'][^>]*>(.*?)</a>',
            payload,
            re.IGNORECASE | re.DOTALL,
        )
        seen: set[str] = set()
        for href, inner in links:
            title = clean_text(inner)
            if len(title) < 10 or title in seen:
                continue
            seen.add(title)
            url = href if href.startswith("http") else f"https://projects.worldbank.org{href}"
            proc_meta = ProcurementMetadata(
                notice_type="Procurement Notice",
                buyer_name="World Bank",
                buyer_country="",
                procurement_category="Consulting Services",
            )
            geo = derive_geographic_eligibility(
                title=title,
                location_raw="",
                description=title,
                track=Track.PROCUREMENT,
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
                id=f"{self.source_id}:{abs(hash(title))}",
                track=Track.PROCUREMENT,
                source=self.source_id,
                source_url=url,
                source_id="",
                organization="World Bank",
                title=title,
                description=title,
                skills=extract_skills_from_text(title),
                geographic_eligibility=geo,
                procurement_metadata=proc_meta,
                raw_provenance=provenance,
            )
            opportunities.append(opp)

        return opportunities
