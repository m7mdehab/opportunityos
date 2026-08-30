"""We Work Remotely Public RSS Feed Adapter."""
from __future__ import annotations

import re
import xml.etree.ElementTree as element_tree
from typing import Any

from opportunity.adapters.base import BaseAdapter
from opportunity.models import (
    CompensationInterval,
    DerivationType,
    FieldProvenance,
    Opportunity,
    ParseResult,
    Track,
    compute_deterministic_id,
)
from opportunity.normalization import (
    clean_text,
    compute_record_checksum,
    create_field_provenance,
    derive_geographic_eligibility,
    extract_compensation,
    extract_employment_type,
    extract_list_sections,
    extract_remote_policy,
    extract_seniority,
    extract_skills_from_text,
    extract_track,
    parse_iso_date,
)


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
    ) -> ParseResult:
        try:
            root = element_tree.fromstring(payload)
        except element_tree.ParseError as e:
            return ParseResult(opportunities=(), records_raw_count=0, parser_error=f"Invalid XML: {e}")

        if root.tag != "rss" and root.find("channel") is None:
            return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)

        items = root.findall(".//item")
        raw_count = len(items)
        opportunities: list[Opportunity] = []
        for idx, item in enumerate(items):
            item_pointer = f"{raw_pointer or 'feed'}:item[{idx}]"
            raw_item_str = element_tree.tostring(item, encoding="unicode")
            record_checksum = compute_record_checksum(raw_item_str)

            raw_title = clean_text(item.findtext("title"))
            if not raw_title:
                continue

            # WWR format is typically: "Company Name: Job Title"
            if ":" in raw_title:
                org_part, _, title_part = raw_title.partition(":")
                organization = clean_text(org_part)
                title = clean_text(title_part)
                org_derivation = DerivationType.RAW_EXTRACTION
            else:
                organization = ""
                title = raw_title
                org_derivation = DerivationType.UNASSERTED_ABSENT

            url = clean_text(item.findtext("link") or item.findtext("guid"))
            raw_pub = item.findtext("pubDate")
            posted_date = parse_iso_date(raw_pub)
            raw_desc = item.findtext("description")
            description = clean_text(raw_desc) if raw_desc else ""
            desc_derivation = DerivationType.RAW_EXTRACTION if description else DerivationType.UNASSERTED_ABSENT

            raw_region = item.findtext("region") or item.findtext("category")
            location_raw = clean_text(raw_region)

            id_match = re.search(r"/remote-jobs/(\d+-[^/?#]+)", url)
            remote_id = id_match.group(1) if id_match else clean_text(item.findtext("guid"))

            responsibilities = extract_list_sections(str(raw_desc or ""), r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(str(raw_desc or ""), r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            skills = extract_skills_from_text(f"{title} {description}")
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type(location_raw, title, description)
            track = extract_track(self.track, location_raw, title, description)
            remote_policy = extract_remote_policy(location_raw, description)
            comp = extract_compensation(description)
            geo = derive_geographic_eligibility(
                title=title,
                location_raw=location_raw,
                description=description,
                track=track,
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
                create_field_provenance("track", location_raw, track.value, DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_track"),
                create_field_provenance("organization", organization, organization, org_derivation, f"{item_pointer}.title", record_checksum, "title_partition"),
                create_field_provenance("title", raw_title, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.title", record_checksum, "title_partition"),
                create_field_provenance("description", (raw_desc or "")[:100], description[:100], desc_derivation, f"{item_pointer}.description", record_checksum, "clean_text"),
                create_field_provenance("location_raw", raw_region, location_raw, DerivationType.RAW_EXTRACTION if location_raw else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.region", record_checksum, "clean_text"),
                create_field_provenance("seniority", title, seniority.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.title", record_checksum, "extract_seniority"),
                create_field_provenance("employment_type", location_raw, emp_type.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.region", record_checksum, "extract_employment_type"),
                create_field_provenance("remote_policy", raw_region, remote_policy.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.region", record_checksum, "extract_remote_policy"),
                create_field_provenance("geographic_eligibility", location_raw, geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.region", record_checksum, "classify_geography"),
            ]

            if skills:
                prov_list.append(create_field_provenance("skills", f"{title} {description[:50]}", ", ".join(skills), DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_skills"))
            if responsibilities:
                prov_list.append(create_field_provenance("responsibilities", (raw_desc or "")[:50], f"{len(responsibilities)} items", DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_responsibilities"))
            if requirements:
                prov_list.append(create_field_provenance("requirements", (raw_desc or "")[:50], f"{len(requirements)} items", DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_requirements"))
            if comp is not None:
                prov_list.append(create_field_provenance("compensation", description[:50], f"{comp.min_amount}-{comp.max_amount} {comp.currency}", DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_compensation"))
                if comp.min_amount is not None:
                    prov_list.append(create_field_provenance("compensation.min_amount", description[:50], str(comp.min_amount), DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_compensation"))
                if comp.max_amount is not None:
                    prov_list.append(create_field_provenance("compensation.max_amount", description[:50], str(comp.max_amount), DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_compensation"))
                if comp.currency is not None:
                    prov_list.append(create_field_provenance("compensation.currency", description[:50], comp.currency, DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_compensation"))
                if comp.interval != CompensationInterval.UNSPECIFIED:
                    prov_list.append(create_field_provenance("compensation.interval", description[:50], comp.interval.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_compensation"))
            if posted_date:
                prov_list.append(create_field_provenance("posted_date", raw_pub, posted_date, DerivationType.RAW_EXTRACTION, f"{item_pointer}.pubDate", record_checksum, "parse_iso_date"))

            opp_id = compute_deterministic_id(self.source_id, remote_id, title, organization, item_pointer)

            opp = Opportunity(
                id=opp_id,
                track=track,
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
                record_checksum=record_checksum,
                raw_record_pointer=item_pointer,
                field_provenances=tuple(prov_list),
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return ParseResult(opportunities=tuple(opportunities), records_raw_count=raw_count)
