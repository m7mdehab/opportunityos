"""Remote OK Public API Adapter."""
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
    Track,
    compute_deterministic_id,
)
from opportunity.normalization import (
    clean_text,
    compute_record_checksum,
    create_field_provenance,
    derive_geographic_eligibility,
    extract_employment_type,
    extract_list_sections,
    extract_remote_policy,
    extract_seniority,
    extract_skills_from_text,
    extract_track,
    parse_iso_date,
)


class RemoteOKAdapter(BaseAdapter):
    """Parses Remote OK public API."""

    def __init__(self) -> None:
        super().__init__(
            source_id="remote_ok",
            track=Track.EMPLOYMENT,
            feed_url="https://remoteok.com/api",
            policy_url="https://remoteok.com/terms",
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> list[Opportunity]:
        data = json.loads(payload)
        if not isinstance(data, list):
            raise ValueError(f"expected Remote OK payload to be list, got {type(data)}")

        # Skip non-job metadata/legal dictionaries
        jobs = [item for item in data if isinstance(item, dict) and ("position" in item or "title" in item)]
        opportunities: list[Opportunity] = []
        for idx, job in enumerate(jobs):
            item_pointer = f"{raw_pointer or 'feed'}:items[{idx}]"
            record_checksum = compute_record_checksum(job)

            remote_id = str(job.get("id") or "")
            raw_title = job.get("position") or job.get("title")
            title = clean_text(raw_title)
            if not title:
                continue

            raw_org = job.get("company")
            organization = clean_text(raw_org)
            raw_desc = str(job.get("description") or "")
            description = clean_text(raw_desc)
            raw_loc = job.get("location")
            location_raw = clean_text(raw_loc)
            url = str(job.get("url") or (f"https://remoteok.com/l/{remote_id}" if remote_id else ""))
            posted_date = parse_iso_date(job.get("date"))

            # Tags & skills
            tags = job.get("tags") if isinstance(job.get("tags"), list) else []
            tags_text = " ".join(str(t) for t in tags)
            skills = extract_skills_from_text(f"{title} {description} {tags_text}")

            # Salary without defaulting currency
            min_sal = job.get("salary_min")
            max_sal = job.get("salary_max")
            comp = None
            if min_sal is not None or max_sal is not None:
                try:
                    c_min = float(min_sal) if min_sal is not None else None
                    c_max = float(max_sal) if max_sal is not None else None
                    interval = CompensationInterval.YEARLY if (c_min or 0) > 10000 else CompensationInterval.UNSPECIFIED
                    comp = Compensation(
                        min_amount=c_min,
                        max_amount=c_max,
                        currency="USD" if "$" in f"{raw_desc} {job.get('salary', '')}" else None,
                        interval=interval,
                    )
                except ValueError:
                    comp = None

            responsibilities = extract_list_sections(raw_desc, r"(?:responsibilit|what\s+you'?ll\s+do|the\s+role|duties)")
            requirements = extract_list_sections(raw_desc, r"(?:requirement|qualificat|what\s+we'?re\s+looking\s+for|what\s+you\s+bring)")
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type(tags_text, title, description)
            track = extract_track(self.track, tags_text, title, description)
            remote_policy = extract_remote_policy(location_raw, description)
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

            field_provenances = (
                create_field_provenance("organization", raw_org, organization, DerivationType.RAW_EXTRACTION if organization else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.company", record_checksum, "clean_text"),
                create_field_provenance("title", raw_title, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.position", record_checksum, "clean_text"),
                create_field_provenance("description", raw_desc[:100], description[:100], DerivationType.RAW_EXTRACTION, f"{item_pointer}.description", record_checksum, "clean_text"),
                create_field_provenance("location_raw", raw_loc, location_raw, DerivationType.RAW_EXTRACTION if location_raw else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.location", record_checksum, "clean_text"),
                create_field_provenance("seniority", title, seniority.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.position", record_checksum, "extract_seniority"),
                create_field_provenance("employment_type", tags_text, emp_type.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.tags", record_checksum, "extract_employment_type"),
                create_field_provenance("remote_policy", raw_loc, remote_policy.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.location", record_checksum, "extract_remote_policy"),
                create_field_provenance("geographic_eligibility", location_raw, geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.location", record_checksum, "classify_geography"),
            )

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
                field_provenances=field_provenances,
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return opportunities
