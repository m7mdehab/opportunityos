"""EU TED (Tenders Electronic Daily) Search API Adapter.

Read-only search POST query permitted under ADR-0005.
"""
from __future__ import annotations

import json
from typing import Any

from opportunity.models import Opportunity, ProcurementMetadata, Track
from opportunity.normalization import (
    clean_text,
    derive_geographic_eligibility,
    extract_skills_from_text,
    parse_iso_date,
)
from opportunity.adapters.base import BaseAdapter


class EUTEDAdapter(BaseAdapter):
    """Parses EU TED procurement notices search responses."""

    def __init__(self) -> None:
        super().__init__(
            source_id="eu_ted",
            track=Track.PROCUREMENT,
            feed_url="https://api.ted.europa.eu/v3/notices/search",
            policy_url="https://docs.ted.europa.eu/legal-notice.html",
            method="POST",
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> list[Opportunity]:
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError(f"expected EU TED payload to be dict, got {type(data)}")

        notices = data.get("notices") or data.get("results") or []
        if isinstance(notices, dict):
            notices = notices.get("notice", [])
        if not isinstance(notices, list):
            raise ValueError(f"expected EU TED notices list, got {type(notices)}")

        opportunities: list[Opportunity] = []
        for notice in notices:
            if not isinstance(notice, dict):
                continue
            pub_num = str(notice.get("publication-number") or notice.get("id") or "")
            title = clean_text(notice.get("notice-title") or notice.get("title"))
            if not title:
                continue

            buyer = clean_text(notice.get("buyer-name") or "EU Contracting Authority")
            buyer_country = clean_text(notice.get("buyer-country") or notice.get("country") or "EU")
            posted_date = parse_iso_date(notice.get("publication-date"))
            deadline = parse_iso_date(notice.get("deadline") or notice.get("closing-date"))
            
            links = notice.get("links") if isinstance(notice.get("links"), dict) else {}
            html_direct = links.get("htmlDirect") if isinstance(links.get("htmlDirect"), dict) else {}
            url = str(html_direct.get("ENG") or notice.get("url") or f"https://ted.europa.eu/udl?uri=TED:NOTICE:{pub_num}:TEXT:EN:HTML" if pub_num else "")
            
            cpv = notice.get("cpv") or ()
            cpv_codes = tuple(str(c) for c in cpv) if isinstance(cpv, list) else (str(cpv),) if cpv else ()

            proc_meta = ProcurementMetadata(
                notice_type=clean_text(notice.get("notice-type") or "Tender Notice"),
                buyer_name=buyer,
                buyer_country=buyer_country,
                procurement_category=clean_text(notice.get("category") or "Services"),
                cpv_codes=cpv_codes,
                deadline=deadline,
            )

            description = clean_text(notice.get("description") or title)
            skills = extract_skills_from_text(f"{title} {description}")
            geo = derive_geographic_eligibility(
                title=title,
                location_raw=buyer_country,
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
                id=f"{self.source_id}:{pub_num}" if pub_num else f"{self.source_id}:{abs(hash(title + buyer))}",
                track=Track.PROCUREMENT,
                source=self.source_id,
                source_url=url,
                source_id=pub_num,
                organization=buyer,
                title=title,
                description=description,
                skills=skills,
                location_raw=buyer_country,
                geographic_eligibility=geo,
                posted_date=posted_date,
                closing_date=deadline,
                procurement_metadata=proc_meta,
                raw_provenance=provenance,
            )
            opportunities.append(opp)

        return opportunities
