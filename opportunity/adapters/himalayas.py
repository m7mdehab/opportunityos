"""Himalayas Jobs Public API Adapter."""
from __future__ import annotations

import json
from typing import Any

from opportunity.adapters.base import BaseAdapter
from opportunity.models import (
    Compensation,
    CompensationInterval,
    DerivationType,
    FieldProvenance,
    Opportunity,
    ParseResult,
    Track,
    WorkMode,
    compute_deterministic_id,
)
from opportunity.normalization import (
    clean_text,
    compute_record_checksum,
    create_field_provenance,
    derive_geographic_eligibility,
    extract_employment_type,
    extract_list_sections,
    extract_seniority,
    extract_skills_from_text,
    extract_track,
    extract_work_location,
    parse_iso_date,
)


class HimalayasAdapter(BaseAdapter):
    """Parses Himalayas public remote jobs API."""

    def __init__(self) -> None:
        super().__init__(
            source_id="himalayas",
            track=Track.EMPLOYMENT,
            feed_url="https://himalayas.app/jobs/api?limit=100",
            policy_url="https://himalayas.app/terms",
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> ParseResult:
        data = json.loads(payload)
        if isinstance(data, dict):
            if "jobs" not in data:
                return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)
            jobs = data["jobs"]
        elif isinstance(data, list):
            jobs = data
        else:
            return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)

        raw_count = len(jobs)
        opportunities: list[Opportunity] = []
        for idx, job in enumerate(jobs):
            if not isinstance(job, dict):
                continue
            item_pointer = f"{raw_pointer or 'feed'}:jobs[{idx}]"
            record_checksum = compute_record_checksum(job)

            remote_id = str(job.get("id") or job.get("slug") or "")
            raw_title = job.get("title")
            title = clean_text(raw_title)
            if not title:
                continue

            raw_org = job.get("companyName") or job.get("company_name")
            organization = clean_text(raw_org)
            raw_desc = job.get("description")
            description = clean_text(raw_desc) if raw_desc else ""
            desc_derivation = DerivationType.RAW_EXTRACTION if description else DerivationType.UNASSERTED_ABSENT

            # Location & restrictions without default strings
            loc_parts = []
            if job.get("location"):
                loc_parts.append(str(job.get("location")))
            if job.get("locationRestrictions"):
                loc_parts.extend(job.get("locationRestrictions") if isinstance(job.get("locationRestrictions"), list) else [str(job.get("locationRestrictions"))])
            raw_loc = ", ".join(loc_parts)
            location_raw = clean_text(raw_loc)
            raw_restrictions = job.get("locationRestrictions")
            native_region = clean_text(
                ", ".join(raw_restrictions) if isinstance(raw_restrictions, list) else (raw_restrictions or "")
            )

            url = str(job.get("applicationLink") or job.get("url") or "")
            # Some live Himalayas rows omit both ``id`` and ``slug`` while
            # still providing a stable, posting-specific application URL.
            # Treat that URL as the source-native identity instead of falling
            # through to the positional raw_pointer hash, which changes when
            # the API reorders its jobs array.
            if not remote_id:
                remote_id = url
            raw_pub = job.get("pubDate") or job.get("createdAt") or job.get("publishedAt")
            posted_date = parse_iso_date(raw_pub)

            # Compensation without default currency or interval
            min_sal = job.get("minSalary") or job.get("min_salary")
            max_sal = job.get("maxSalary") or job.get("max_salary")
            currency = str(job.get("currency")) if job.get("currency") else None
            comp = None
            if min_sal is not None or max_sal is not None:
                try:
                    c_min = float(min_sal) if min_sal is not None else None
                    c_max = float(max_sal) if max_sal is not None else None
                    comp = Compensation(
                        min_amount=c_min,
                        max_amount=c_max,
                        currency=currency,
                        interval=CompensationInterval.UNSPECIFIED,
                    )
                except ValueError:
                    comp = None

            responsibilities = extract_list_sections(str(raw_desc or ""), r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(str(raw_desc or ""), r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            skills = extract_skills_from_text(f"{title} {description}")
            seniority = extract_seniority(title, description)
            raw_emp = str(job.get("employmentType") or "")
            emp_type = extract_employment_type(raw_emp, title, description)
            track = extract_track(self.track, raw_emp, title, description)
            # Native mapping first (brief: Himalayas `locationRestrictions`). The
            # Himalayas board is remote-only by construction (every listing is a
            # remote job), so `work_mode` itself is an adapter-native fact; the
            # restriction list is the native region hint.
            work_loc = extract_work_location(
                location_raw, description,
                native_work_mode=WorkMode.REMOTE,
                native_region=native_region,
            )
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
                create_field_provenance("track", raw_emp, track.value, DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_track"),
                create_field_provenance("organization", raw_org, organization, DerivationType.RAW_EXTRACTION if organization else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.companyName", record_checksum, "clean_text"),
                create_field_provenance("title", raw_title, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.title", record_checksum, "clean_text"),
                create_field_provenance("description", (raw_desc or "")[:100], description[:100], desc_derivation, f"{item_pointer}.description", record_checksum, "clean_text"),
                create_field_provenance("location_raw", raw_loc, location_raw, DerivationType.RAW_EXTRACTION if location_raw else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.location", record_checksum, "clean_text"),
                create_field_provenance("seniority", title, seniority.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.title", record_checksum, "extract_seniority"),
                create_field_provenance("employment_type", raw_emp, emp_type.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.employmentType", record_checksum, "extract_employment_type"),
                create_field_provenance(
                    "work_mode", raw_restrictions or "himalayas_remote_board", work_loc.work_mode.value,
                    DerivationType.SOURCE_METADATA_DERIVATION, f"{item_pointer}.locationRestrictions",
                    record_checksum, "himalayas_remote_board",
                ),
                create_field_provenance("geographic_eligibility", location_raw, geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.location", record_checksum, "classify_geography"),
            ]

            if skills:
                prov_list.append(create_field_provenance("skills", f"{title} {description[:50]}", ", ".join(skills), DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_skills"))
            if responsibilities:
                prov_list.append(create_field_provenance("responsibilities", (raw_desc or "")[:50], f"{len(responsibilities)} items", DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_responsibilities"))
            if requirements:
                prov_list.append(create_field_provenance("requirements", (raw_desc or "")[:50], f"{len(requirements)} items", DerivationType.RULE_DERIVATION, f"{item_pointer}.description", record_checksum, "extract_requirements"))
            if comp is not None:
                prov_list.append(create_field_provenance("compensation", f"{min_sal}-{max_sal} {currency}", f"{comp.min_amount}-{comp.max_amount} {comp.currency}", DerivationType.RULE_DERIVATION, f"{item_pointer}.salary", record_checksum, "extract_compensation"))
                if comp.min_amount is not None:
                    prov_list.append(create_field_provenance("compensation.min_amount", str(min_sal), str(comp.min_amount), DerivationType.RULE_DERIVATION, f"{item_pointer}.minSalary", record_checksum, "extract_compensation"))
                if comp.max_amount is not None:
                    prov_list.append(create_field_provenance("compensation.max_amount", str(max_sal), str(comp.max_amount), DerivationType.RULE_DERIVATION, f"{item_pointer}.maxSalary", record_checksum, "extract_compensation"))
                if comp.currency is not None:
                    prov_list.append(create_field_provenance("compensation.currency", str(currency), comp.currency, DerivationType.RULE_DERIVATION, f"{item_pointer}.currency", record_checksum, "extract_compensation"))
                if comp.interval != CompensationInterval.UNSPECIFIED:
                    prov_list.append(create_field_provenance("compensation.interval", "salary_range", comp.interval.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.salary", record_checksum, "extract_compensation"))
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
                work_mode=work_loc.work_mode,
                work_mode_source=work_loc.work_mode_source,
                location_country=work_loc.location_country,
                location_city=work_loc.location_city,
                location_region=work_loc.location_region,
                remote_scope=work_loc.remote_scope,
                remote_scope_regions=work_loc.remote_scope_regions,
                geographic_eligibility=geo,
                compensation=comp,
                posted_date=posted_date,
                raw_provenance=provenance,
                record_checksum=record_checksum,
                raw_record_pointer=item_pointer,
                raw_source_record_json=self.serialize_source_record(job),
                field_provenances=tuple(prov_list),
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return ParseResult(opportunities=tuple(opportunities), records_raw_count=raw_count)
