"""World Bank Procurement Opportunities Adapter."""
from __future__ import annotations

import json
import re
from typing import Any

from opportunity.adapters.base import BaseAdapter
from opportunity.models import (
    DerivationType,
    FieldProvenance,
    Opportunity,
    ProcurementMetadata,
    Track,
    compute_deterministic_id,
)
from opportunity.normalization import (
    clean_text,
    compute_record_checksum,
    create_field_provenance,
    derive_geographic_eligibility,
    extract_skills_from_text,
    parse_iso_date,
)


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
                for idx, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    item_pointer = f"{raw_pointer or 'feed'}:notices[{idx}]"
                    record_checksum = compute_record_checksum(item)

                    remote_id = str(item.get("id") or item.get("notice_id") or item.get("procurement_id") or "")
                    raw_title = item.get("notice_title") or item.get("title") or item.get("project_name")
                    title = clean_text(raw_title)
                    if not title:
                        continue

                    raw_buyer = item.get("borrower") or item.get("organization") or item.get("country_name")
                    buyer = clean_text(raw_buyer)
                    raw_country = item.get("country_name") or item.get("country")
                    country = clean_text(raw_country)
                    deadline = parse_iso_date(item.get("submission_date") or item.get("deadline") or item.get("closing_date"))
                    posted_date = parse_iso_date(item.get("published_date") or item.get("publication_date") or item.get("date"))
                    raw_desc = str(item.get("description") or item.get("notice_text") or title)
                    description = clean_text(raw_desc)
                    url = str(item.get("url") or (f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{remote_id}" if remote_id else ""))
                    raw_type = item.get("notice_type") or item.get("type")
                    notice_type = clean_text(raw_type)
                    raw_cat = item.get("sector") or item.get("category")
                    category = clean_text(raw_cat)

                    proc_meta = ProcurementMetadata(
                        notice_type=notice_type,
                        buyer_name=buyer,
                        buyer_country=country,
                        procurement_category=category,
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
                        raw_pointer=item_pointer,
                        fetched_at=fetched_at,
                        payload=payload,
                    )

                    field_provenances = (
                        create_field_provenance("organization", raw_buyer, buyer, DerivationType.RAW_EXTRACTION if buyer else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.borrower", record_checksum, "clean_text"),
                        create_field_provenance("title", raw_title, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.title", record_checksum, "clean_text"),
                        create_field_provenance("description", raw_desc[:100], description[:100], DerivationType.RAW_EXTRACTION, f"{item_pointer}.description", record_checksum, "clean_text"),
                        create_field_provenance("location_raw", raw_country, country, DerivationType.RAW_EXTRACTION if country else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.country", record_checksum, "clean_text"),
                        create_field_provenance("notice_type", raw_type, notice_type, DerivationType.RAW_EXTRACTION if notice_type else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.notice_type", record_checksum, "clean_text"),
                        create_field_provenance("geographic_eligibility", country, geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.country", record_checksum, "classify_geography"),
                    )

                    opp_id = compute_deterministic_id(self.source_id, remote_id, title, buyer, item_pointer)

                    opp = Opportunity(
                        id=opp_id,
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
                        record_checksum=record_checksum,
                        raw_record_pointer=item_pointer,
                        field_provenances=field_provenances,
                        canonical_outbound_url=url,
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
        for idx, (href, inner) in enumerate(links):
            title = clean_text(inner)
            if len(title) < 10 or title in seen:
                continue
            seen.add(title)
            item_pointer = f"{raw_pointer or 'feed'}:html_link[{idx}]"
            record_checksum = compute_record_checksum(f"{href}:{inner}")
            url = href if href.startswith("http") else f"https://projects.worldbank.org{href}"
            proc_meta = ProcurementMetadata(
                notice_type="",
                buyer_name="",
                buyer_country="",
                procurement_category="",
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
                raw_pointer=item_pointer,
                fetched_at=fetched_at,
                payload=payload,
            )
            field_provenances = (
                create_field_provenance("organization", "", "", DerivationType.UNASSERTED_ABSENT, item_pointer, record_checksum, "unasserted"),
                create_field_provenance("title", inner, title, DerivationType.RAW_EXTRACTION, item_pointer, record_checksum, "clean_text"),
                create_field_provenance("geographic_eligibility", "", geo.status, DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "classify_geography"),
            )
            opp_id = compute_deterministic_id(self.source_id, "", title, "", item_pointer)
            opp = Opportunity(
                id=opp_id,
                track=Track.PROCUREMENT,
                source=self.source_id,
                source_url=url,
                source_id="",
                organization="",
                title=title,
                description=title,
                skills=extract_skills_from_text(title),
                geographic_eligibility=geo,
                procurement_metadata=proc_meta,
                raw_provenance=provenance,
                record_checksum=record_checksum,
                raw_record_pointer=item_pointer,
                field_provenances=field_provenances,
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return opportunities
