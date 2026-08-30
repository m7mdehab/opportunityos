"""UNGM (United Nations Global Marketplace) Procurement Adapter."""
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


class UNGMAdapter(BaseAdapter):
    """Parses UNGM procurement notices and tender opportunities."""

    def __init__(self) -> None:
        super().__init__(
            source_id="ungm",
            track=Track.PROCUREMENT,
            feed_url="https://www.ungm.org/Public/Notice",
            policy_url="https://www.ungm.org/Public/Terms",
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> list[Opportunity]:
        opportunities: list[Opportunity] = []

        # Payload may be structured JSON or HTML
        if payload.strip().startswith("{") or payload.strip().startswith("["):
            try:
                data = json.loads(payload)
                items = data if isinstance(data, list) else data.get("notices") or data.get("data") or data.get("results") or []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    remote_id = str(item.get("id") or item.get("notice_id") or item.get("reference") or "")
                    title = clean_text(item.get("title") or item.get("notice_title") or item.get("description"))
                    if not title:
                        continue

                    buyer = clean_text(item.get("agency") or item.get("organization") or item.get("buyer") or "United Nations")
                    country = clean_text(item.get("country") or item.get("location") or "")
                    deadline = parse_iso_date(item.get("deadline") or item.get("closing_date"))
                    posted_date = parse_iso_date(item.get("posted_date") or item.get("published_date") or item.get("date"))
                    raw_desc = str(item.get("description") or item.get("content") or title)
                    description = clean_text(raw_desc)
                    url = str(item.get("url") or f"https://www.ungm.org/Public/Notice/{remote_id}" if remote_id else "")
                    notice_type = clean_text(item.get("type") or item.get("notice_type") or "RFP")

                    proc_meta = ProcurementMetadata(
                        notice_type=notice_type,
                        buyer_name=buyer,
                        buyer_country=country,
                        procurement_category=clean_text(item.get("category") or "Consulting Services"),
                        unspsc_codes=tuple(item.get("unspsc") or ()) if isinstance(item.get("unspsc"), list) else (),
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
                        organization=buyer,
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
        notice_links = re.findall(
            r'<a[^>]+href=["\'](/Public/Notice/(\d+)|https://www\.ungm\.org/Public/Notice/(\d+))["\'][^>]*>(.*?)</a>',
            payload,
            re.IGNORECASE | re.DOTALL,
        )
        seen_ids: set[str] = set()
        for match in notice_links:
            path, id1, id2, inner = match
            remote_id = id1 or id2 or ""
            if remote_id in seen_ids:
                continue
            seen_ids.add(remote_id)
            title = clean_text(inner)
            if len(title) < 5:
                continue
            url = f"https://www.ungm.org/Public/Notice/{remote_id}" if remote_id else "https://www.ungm.org/Public/Notice"
            buyer = "United Nations"
            
            proc_meta = ProcurementMetadata(
                notice_type="RFP",
                buyer_name=buyer,
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
                id=f"{self.source_id}:{remote_id}" if remote_id else f"{self.source_id}:{abs(hash(title))}",
                track=Track.PROCUREMENT,
                source=self.source_id,
                source_url=url,
                source_id=remote_id,
                organization=buyer,
                title=title,
                description=title,
                skills=extract_skills_from_text(title),
                geographic_eligibility=geo,
                procurement_metadata=proc_meta,
                raw_provenance=provenance,
            )
            opportunities.append(opp)

        return opportunities
