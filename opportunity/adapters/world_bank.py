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
    ParseResult,
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
    extract_work_location,
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
    ) -> ParseResult:
        opportunities: list[Opportunity] = []

        # Structured JSON format
        if payload.strip().startswith("{") or payload.strip().startswith("["):
            try:
                data = json.loads(payload)
                if isinstance(data, dict):
                    if "notices" not in data and "rows" not in data and "results" not in data:
                        return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)
                    items = data.get("notices") or data.get("rows") or data.get("results") or []
                elif isinstance(data, list):
                    items = data
                else:
                    return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)

                raw_count = len(items)
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
                    raw_deadline = item.get("submission_date") or item.get("deadline") or item.get("closing_date")
                    deadline = parse_iso_date(raw_deadline)
                    raw_posted = item.get("published_date") or item.get("publication_date") or item.get("date")
                    posted_date = parse_iso_date(raw_posted)
                    
                    raw_desc = item.get("description") or item.get("notice_text")
                    description = clean_text(raw_desc) if raw_desc else ""
                    desc_derivation = DerivationType.RAW_EXTRACTION if description else DerivationType.UNASSERTED_ABSENT

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
                    # Native mapping first (brief: World Bank duty station / buyer
                    # country). See ungm.py's identical comment for the rationale.
                    work_loc = extract_work_location(country, description, native_country=country)
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

                    prov_list: list[FieldProvenance] = [
                        create_field_provenance("track", "", Track.PROCUREMENT.value, DerivationType.SOURCE_METADATA_DERIVATION, item_pointer, record_checksum, "world_bank_track"),
                        create_field_provenance("organization", raw_buyer, buyer, DerivationType.RAW_EXTRACTION if buyer else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.borrower", record_checksum, "clean_text"),
                        create_field_provenance("title", raw_title, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.title", record_checksum, "clean_text"),
                        create_field_provenance("description", (raw_desc or "")[:100], description[:100], desc_derivation, f"{item_pointer}.description", record_checksum, "clean_text"),
                        create_field_provenance("location_raw", raw_country, country, DerivationType.RAW_EXTRACTION if country else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.country", record_checksum, "clean_text"),
                        create_field_provenance("notice_type", raw_type, notice_type, DerivationType.RAW_EXTRACTION if notice_type else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.notice_type", record_checksum, "clean_text"),
                        create_field_provenance("geographic_eligibility", country, geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.country", record_checksum, "classify_geography"),
                    ]

                    if skills:
                        prov_list.append(create_field_provenance("skills", f"{title} {description[:50]}", ", ".join(skills), DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_skills"))
                    if buyer:
                        prov_list.append(create_field_provenance("buyer_name", raw_buyer, buyer, DerivationType.RAW_EXTRACTION, f"{item_pointer}.borrower", record_checksum, "clean_text"))
                    if country:
                        prov_list.append(create_field_provenance("buyer_country", raw_country, country, DerivationType.RAW_EXTRACTION, f"{item_pointer}.country", record_checksum, "clean_text"))
                    if category:
                        prov_list.append(create_field_provenance("procurement_category", raw_cat, category, DerivationType.RAW_EXTRACTION, f"{item_pointer}.category", record_checksum, "clean_text"))
                    if posted_date:
                        prov_list.append(create_field_provenance("posted_date", raw_posted, posted_date, DerivationType.RAW_EXTRACTION, f"{item_pointer}.published_date", record_checksum, "parse_iso_date"))
                    if deadline:
                        prov_list.append(create_field_provenance("closing_date", raw_deadline, deadline, DerivationType.RAW_EXTRACTION, f"{item_pointer}.submission_date", record_checksum, "parse_iso_date"))
                        prov_list.append(create_field_provenance("deadline", raw_deadline, deadline, DerivationType.RAW_EXTRACTION, f"{item_pointer}.submission_date", record_checksum, "parse_iso_date"))

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
                        work_mode=work_loc.work_mode,
                        work_mode_source=work_loc.work_mode_source,
                        location_country=work_loc.location_country,
                        location_city=work_loc.location_city,
                        location_region=work_loc.location_region,
                        remote_scope=work_loc.remote_scope,
                        remote_scope_regions=work_loc.remote_scope_regions,
                        geographic_eligibility=geo,
                        posted_date=posted_date,
                        closing_date=deadline,
                        procurement_metadata=proc_meta,
                        raw_provenance=provenance,
                        record_checksum=record_checksum,
                        raw_record_pointer=item_pointer,
                        field_provenances=tuple(prov_list),
                        canonical_outbound_url=url,
                    )
                    opportunities.append(opp)
                return ParseResult(opportunities=tuple(opportunities), records_raw_count=raw_count)
            except json.JSONDecodeError:
                pass

        # HTML parsing fallback
        links = re.findall(
            r'<a[^>]+href=["\']([^"\']*(?:procurement-detail|opportunities)[^"\']*)["\'][^>]*>(.*?)</a>',
            payload,
            re.IGNORECASE | re.DOTALL,
        )
        seen: set[str] = set()
        raw_count = len(links)
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
                description="",
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
            skills = extract_skills_from_text(title)
            prov_list = [
                create_field_provenance("track", "", Track.PROCUREMENT.value, DerivationType.SOURCE_METADATA_DERIVATION, item_pointer, record_checksum, "world_bank_track"),
                create_field_provenance("organization", "", "", DerivationType.UNASSERTED_ABSENT, item_pointer, record_checksum, "unasserted"),
                create_field_provenance("title", inner, title, DerivationType.RAW_EXTRACTION, item_pointer, record_checksum, "clean_text"),
                create_field_provenance("description", "", "", DerivationType.UNASSERTED_ABSENT, item_pointer, record_checksum, "unasserted"),
                create_field_provenance("geographic_eligibility", "", geo.status, DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "classify_geography"),
            ]
            if skills:
                prov_list.append(create_field_provenance("skills", title, ", ".join(skills), DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_skills"))

            opp_id = compute_deterministic_id(self.source_id, "", title, "", item_pointer)
            opp = Opportunity(
                id=opp_id,
                track=Track.PROCUREMENT,
                source=self.source_id,
                source_url=url,
                source_id="",
                organization="",
                title=title,
                description="",
                skills=skills,
                geographic_eligibility=geo,
                procurement_metadata=proc_meta,
                raw_provenance=provenance,
                record_checksum=record_checksum,
                raw_record_pointer=item_pointer,
                field_provenances=tuple(prov_list),
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return ParseResult(opportunities=tuple(opportunities), records_raw_count=raw_count)
