"""UNGM (United Nations Global Marketplace) Procurement Adapter."""
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
    ) -> ParseResult:
        opportunities: list[Opportunity] = []

        # Structured JSON format
        if payload.strip().startswith("{") or payload.strip().startswith("["):
            try:
                data = json.loads(payload)
                if isinstance(data, dict):
                    if "notices" not in data and "data" not in data and "results" not in data:
                        return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)
                    items = data.get("notices") or data.get("data") or data.get("results") or []
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

                    remote_id = str(item.get("id") or item.get("notice_id") or item.get("reference") or "")
                    raw_title = item.get("title") or item.get("notice_title")
                    title = clean_text(raw_title)
                    if not title:
                        continue

                    raw_buyer = item.get("agency") or item.get("organization") or item.get("buyer")
                    buyer = clean_text(raw_buyer)
                    raw_country = item.get("country") or item.get("location")
                    country = clean_text(raw_country)
                    raw_deadline = item.get("deadline") or item.get("closing_date")
                    deadline = parse_iso_date(raw_deadline)
                    raw_posted = item.get("posted_date") or item.get("published_date") or item.get("date")
                    posted_date = parse_iso_date(raw_posted)
                    
                    raw_desc = item.get("description") or item.get("content")
                    description = clean_text(raw_desc) if raw_desc else ""
                    desc_derivation = DerivationType.RAW_EXTRACTION if description else DerivationType.UNASSERTED_ABSENT

                    url = str(item.get("url") or (f"https://www.ungm.org/Public/Notice/{remote_id}" if remote_id else ""))
                    raw_type = item.get("type") or item.get("notice_type")
                    notice_type = clean_text(raw_type)
                    raw_cat = item.get("category")
                    category = clean_text(raw_cat)
                    raw_unspsc = item.get("unspsc") or ()
                    unspsc_tuple = tuple(str(u) for u in raw_unspsc) if isinstance(raw_unspsc, (list, tuple)) else (str(raw_unspsc),) if raw_unspsc else ()

                    proc_meta = ProcurementMetadata(
                        notice_type=notice_type,
                        buyer_name=buyer,
                        buyer_country=country,
                        procurement_category=category,
                        unspsc_codes=unspsc_tuple,
                        deadline=deadline,
                    )

                    skills = extract_skills_from_text(f"{title} {description}")
                    # Native mapping first (brief: "UNGM/World Bank/TED duty station /
                    # buyer country"). Procurement notices carry a delivery country, not
                    # a remote/hybrid/onsite work_mode -- so only location_country is
                    # populated natively here; work_mode stays whatever (if anything)
                    # text inference finds in the notice description.
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
                        create_field_provenance("track", "", Track.PROCUREMENT.value, DerivationType.SOURCE_METADATA_DERIVATION, item_pointer, record_checksum, "ungm_track"),
                        create_field_provenance("organization", raw_buyer, buyer, DerivationType.RAW_EXTRACTION if buyer else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.agency", record_checksum, "clean_text"),
                        create_field_provenance("title", raw_title, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.title", record_checksum, "clean_text"),
                        create_field_provenance("description", (raw_desc or "")[:100], description[:100], desc_derivation, f"{item_pointer}.description", record_checksum, "clean_text"),
                        create_field_provenance("location_raw", raw_country, country, DerivationType.RAW_EXTRACTION if country else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.country", record_checksum, "clean_text"),
                        create_field_provenance("notice_type", raw_type, notice_type, DerivationType.RAW_EXTRACTION if notice_type else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.type", record_checksum, "clean_text"),
                        create_field_provenance("geographic_eligibility", country, geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.country", record_checksum, "classify_geography"),
                    ]

                    if skills:
                        prov_list.append(create_field_provenance("skills", f"{title} {description[:50]}", ", ".join(skills), DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_skills"))
                    if buyer:
                        prov_list.append(create_field_provenance("buyer_name", raw_buyer, buyer, DerivationType.RAW_EXTRACTION, f"{item_pointer}.agency", record_checksum, "clean_text"))
                    if country:
                        prov_list.append(create_field_provenance("buyer_country", raw_country, country, DerivationType.RAW_EXTRACTION, f"{item_pointer}.country", record_checksum, "clean_text"))
                    if category:
                        prov_list.append(create_field_provenance("procurement_category", raw_cat, category, DerivationType.RAW_EXTRACTION, f"{item_pointer}.category", record_checksum, "clean_text"))
                    if unspsc_tuple:
                        prov_list.append(create_field_provenance("unspsc_codes", str(raw_unspsc), ", ".join(unspsc_tuple), DerivationType.RAW_EXTRACTION, f"{item_pointer}.unspsc", record_checksum, "extract_unspsc"))
                    if posted_date:
                        prov_list.append(create_field_provenance("posted_date", raw_posted, posted_date, DerivationType.RAW_EXTRACTION, f"{item_pointer}.posted_date", record_checksum, "parse_iso_date"))
                    if deadline:
                        prov_list.append(create_field_provenance("closing_date", raw_deadline, deadline, DerivationType.RAW_EXTRACTION, f"{item_pointer}.deadline", record_checksum, "parse_iso_date"))
                        prov_list.append(create_field_provenance("deadline", raw_deadline, deadline, DerivationType.RAW_EXTRACTION, f"{item_pointer}.deadline", record_checksum, "parse_iso_date"))

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
                        raw_source_record_json=self.serialize_source_record(item),
                        field_provenances=tuple(prov_list),
                        canonical_outbound_url=url,
                    )
                    opportunities.append(opp)
                return ParseResult(opportunities=tuple(opportunities), records_raw_count=raw_count)
            except json.JSONDecodeError:
                pass

        # HTML parsing fallback
        notice_links = re.findall(
            r'<a[^>]+href=["\'](/Public/Notice/(\d+)|https://www\.ungm\.org/Public/Notice/(\d+))["\'][^>]*>(.*?)</a>',
            payload,
            re.IGNORECASE | re.DOTALL,
        )
        seen_ids: set[str] = set()
        raw_count = len(notice_links)
        for idx, match in enumerate(notice_links):
            path, id1, id2, inner = match
            remote_id = id1 or id2 or ""
            if remote_id in seen_ids:
                continue
            seen_ids.add(remote_id)
            item_pointer = f"{raw_pointer or 'feed'}:html_link[{idx}]"
            record_checksum = compute_record_checksum(f"{remote_id}:{inner}")

            title = clean_text(inner)
            if len(title) < 5:
                continue
            url = f"https://www.ungm.org/Public/Notice/{remote_id}" if remote_id else "https://www.ungm.org/Public/Notice"
            buyer = ""
            
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
                create_field_provenance("track", "", Track.PROCUREMENT.value, DerivationType.SOURCE_METADATA_DERIVATION, item_pointer, record_checksum, "ungm_track"),
                create_field_provenance("organization", "", "", DerivationType.UNASSERTED_ABSENT, item_pointer, record_checksum, "unasserted"),
                create_field_provenance("title", inner, title, DerivationType.RAW_EXTRACTION, item_pointer, record_checksum, "clean_text"),
                create_field_provenance("description", "", "", DerivationType.UNASSERTED_ABSENT, item_pointer, record_checksum, "unasserted"),
                create_field_provenance("geographic_eligibility", "", geo.status, DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "classify_geography"),
            ]
            if skills:
                prov_list.append(create_field_provenance("skills", title, ", ".join(skills), DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_skills"))

            opp_id = compute_deterministic_id(self.source_id, remote_id, title, buyer, item_pointer)
            opp = Opportunity(
                id=opp_id,
                track=Track.PROCUREMENT,
                source=self.source_id,
                source_url=url,
                source_id=remote_id,
                organization=buyer,
                title=title,
                description="",
                skills=skills,
                geographic_eligibility=geo,
                procurement_metadata=proc_meta,
                raw_provenance=provenance,
                record_checksum=record_checksum,
                raw_record_pointer=item_pointer,
                raw_source_record_json=self.serialize_source_record(inner),
                field_provenances=tuple(prov_list),
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return ParseResult(opportunities=tuple(opportunities), records_raw_count=raw_count)
