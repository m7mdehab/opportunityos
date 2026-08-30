"""EU TED (Tenders Electronic Daily) Search API Adapter.

Read-only search POST query permitted under ADR-0005.
"""
from __future__ import annotations

import json
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
    parse_iso_date,
)

DEFAULT_TED_SEARCH_BODY: dict[str, Any] = {
    "query": "ND=2026",
    "fields": [
        "publication-number",
        "notice-title",
        "buyer-name",
        "buyer-country",
        "publication-date",
        "deadline",
        "links",
        "cpv",
        "notice-type",
        "category",
        "description",
    ],
    "limit": 100,
}


class EUTEDAdapter(BaseAdapter):
    """Parses EU TED procurement notices search responses."""

    def __init__(self) -> None:
        super().__init__(
            source_id="eu_ted",
            track=Track.PROCUREMENT,
            feed_url="https://api.ted.europa.eu/v3/notices/search",
            policy_url="https://docs.ted.europa.eu/legal-notice.html",
            method="POST",
            default_body=DEFAULT_TED_SEARCH_BODY,
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> ParseResult:
        data = json.loads(payload)
        if not isinstance(data, dict):
            return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)

        if "notices" not in data and "results" not in data:
            return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)

        notices = data.get("notices") or data.get("results") or []
        if isinstance(notices, dict):
            notices = notices.get("notice", [])
        if not isinstance(notices, list):
            return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)

        raw_count = len(notices)
        opportunities: list[Opportunity] = []
        for idx, notice in enumerate(notices):
            if not isinstance(notice, dict):
                continue
            item_pointer = f"{raw_pointer or 'feed'}:notices[{idx}]"
            record_checksum = compute_record_checksum(notice)

            pub_num = str(notice.get("publication-number") or notice.get("id") or "")
            raw_title = notice.get("notice-title") or notice.get("title")
            title = clean_text(raw_title)
            if not title:
                continue

            raw_buyer = notice.get("buyer-name")
            buyer = clean_text(raw_buyer)
            raw_country = notice.get("buyer-country") or notice.get("country")
            buyer_country = clean_text(raw_country)
            raw_pub = notice.get("publication-date")
            posted_date = parse_iso_date(raw_pub)
            raw_deadline = notice.get("deadline") or notice.get("closing-date")
            deadline = parse_iso_date(raw_deadline)
            
            links = notice.get("links") if isinstance(notice.get("links"), dict) else {}
            html_direct = links.get("htmlDirect") if isinstance(links.get("htmlDirect"), dict) else {}
            url = str(html_direct.get("ENG") or notice.get("url") or (f"https://ted.europa.eu/udl?uri=TED:NOTICE:{pub_num}:TEXT:EN:HTML" if pub_num else ""))
            
            cpv = notice.get("cpv") or ()
            cpv_codes = tuple(str(c) for c in cpv) if isinstance(cpv, list) else (str(cpv),) if cpv else ()

            raw_notice_type = notice.get("notice-type")
            notice_type = clean_text(raw_notice_type)
            raw_cat = notice.get("category")
            category = clean_text(raw_cat)

            proc_meta = ProcurementMetadata(
                notice_type=notice_type,
                buyer_name=buyer,
                buyer_country=buyer_country,
                procurement_category=category,
                cpv_codes=cpv_codes,
                deadline=deadline,
            )

            # Concrete bug fix: If description is absent, it MUST NOT become title
            raw_desc = notice.get("description")
            description = clean_text(raw_desc) if raw_desc else ""
            desc_derivation = DerivationType.RAW_EXTRACTION if description else DerivationType.UNASSERTED_ABSENT

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
                raw_pointer=item_pointer,
                fetched_at=fetched_at,
                payload=payload,
            )

            prov_list: list[FieldProvenance] = [
                create_field_provenance("track", "", Track.PROCUREMENT.value, DerivationType.SOURCE_METADATA_DERIVATION, item_pointer, record_checksum, "eu_ted_track"),
                create_field_provenance("organization", raw_buyer, buyer, DerivationType.RAW_EXTRACTION if buyer else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.buyer-name", record_checksum, "clean_text"),
                create_field_provenance("title", raw_title, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.notice-title", record_checksum, "clean_text"),
                create_field_provenance("description", (raw_desc or "")[:100], description[:100], desc_derivation, f"{item_pointer}.description", record_checksum, "clean_text"),
                create_field_provenance("location_raw", raw_country, buyer_country, DerivationType.RAW_EXTRACTION if buyer_country else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.buyer-country", record_checksum, "clean_text"),
                create_field_provenance("notice_type", raw_notice_type, notice_type, DerivationType.RAW_EXTRACTION if notice_type else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.notice-type", record_checksum, "clean_text"),
                create_field_provenance("geographic_eligibility", buyer_country, geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.buyer-country", record_checksum, "classify_geography"),
            ]

            if skills:
                prov_list.append(create_field_provenance("skills", f"{title} {description[:50]}", ", ".join(skills), DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_skills"))
            if buyer:
                prov_list.append(create_field_provenance("buyer_name", raw_buyer, buyer, DerivationType.RAW_EXTRACTION, f"{item_pointer}.buyer-name", record_checksum, "clean_text"))
            if buyer_country:
                prov_list.append(create_field_provenance("buyer_country", raw_country, buyer_country, DerivationType.RAW_EXTRACTION, f"{item_pointer}.buyer-country", record_checksum, "clean_text"))
            if category:
                prov_list.append(create_field_provenance("procurement_category", raw_cat, category, DerivationType.RAW_EXTRACTION, f"{item_pointer}.category", record_checksum, "clean_text"))
            if cpv_codes:
                prov_list.append(create_field_provenance("cpv_codes", str(cpv), ", ".join(cpv_codes), DerivationType.RAW_EXTRACTION, f"{item_pointer}.cpv", record_checksum, "extract_cpv"))
            if posted_date:
                prov_list.append(create_field_provenance("posted_date", raw_pub, posted_date, DerivationType.RAW_EXTRACTION, f"{item_pointer}.publication-date", record_checksum, "parse_iso_date"))
            if deadline:
                prov_list.append(create_field_provenance("closing_date", raw_deadline, deadline, DerivationType.RAW_EXTRACTION, f"{item_pointer}.deadline", record_checksum, "parse_iso_date"))
                prov_list.append(create_field_provenance("deadline", raw_deadline, deadline, DerivationType.RAW_EXTRACTION, f"{item_pointer}.deadline", record_checksum, "parse_iso_date"))

            opp_id = compute_deterministic_id(self.source_id, pub_num, title, buyer, item_pointer)

            opp = Opportunity(
                id=opp_id,
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
                record_checksum=record_checksum,
                raw_record_pointer=item_pointer,
                field_provenances=tuple(prov_list),
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return ParseResult(opportunities=tuple(opportunities), records_raw_count=raw_count)
