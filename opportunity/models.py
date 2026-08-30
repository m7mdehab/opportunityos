"""OpportunityOS Opportunity Data Models and Ingestion Schemas.

Covers dual-track employment and independent consulting / procurement opportunities
with strict typing, immutable records, provenance tracking, and geographic eligibility.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Track(str, Enum):
    EMPLOYMENT = "employment"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    PROCUREMENT = "procurement"


class SeniorityLevel(str, Enum):
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    EXECUTIVE = "executive"
    UNSPECIFIED = "unspecified"


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    UNSPECIFIED = "unspecified"


class RemotePolicy(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ON_SITE = "on_site"
    UNSPECIFIED = "unspecified"


class CompensationInterval(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    PROJECT = "project"
    UNSPECIFIED = "unspecified"


class SourceHealthStatus(str, Enum):
    HEALTHY = "healthy"
    EMPTY_RESULTS = "empty_results"
    SCHEMA_DRIFT_SUSPECTED = "schema_drift_suspected"
    POLICY_RESTRICTION = "policy_restriction"
    RATE_LIMITED = "rate_limited"
    TRANSIENT_FAILURE = "transient_failure"
    PERSISTENT_FAILURE = "persistent_failure"


@dataclass(frozen=True, slots=True)
class Compensation:
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str | None = None
    interval: CompensationInterval = CompensationInterval.UNSPECIFIED

    def __post_init__(self) -> None:
        if self.min_amount is not None and self.max_amount is not None:
            if self.min_amount > self.max_amount:
                raise ValueError(
                    f"min_amount ({self.min_amount}) cannot exceed max_amount ({self.max_amount})"
                )
        if self.currency is not None:
            if not isinstance(self.currency, str) or not self.currency.strip():
                raise ValueError("currency must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class ProcurementMetadata:
    notice_type: str = ""
    buyer_name: str = ""
    buyer_country: str = ""
    procurement_category: str = ""
    cpv_codes: tuple[str, ...] = ()
    unspsc_codes: tuple[str, ...] = ()
    bid_bonding_required: bool | None = None
    turnover_required: float | None = None
    languages: tuple[str, ...] = ()
    deadline: str | None = None


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    source_id: str
    source_url: str
    feed_url: str
    fetched_at: str
    fetch_latency_ms: int = 0
    raw_pointer: str = ""
    payload_checksum: str = ""

    def __post_init__(self) -> None:
        if not self.source_id or not self.source_id.strip():
            raise ValueError("source_id cannot be empty")
        if not self.fetched_at or not self.fetched_at.strip():
            raise ValueError("fetched_at cannot be empty")


@dataclass(frozen=True, slots=True)
class GeographicEligibility:
    status: str  # "eligible", "ineligible", "unclear"
    reason: str
    individual_eligibility: str = "unclear"  # "individual_ok", "entity_required", "unclear"
    individual_reason: str = ""
    extracted_places: tuple[str, ...] = ()
    restrictions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"eligible", "excluded", "ineligible", "unclear"}:
            raise ValueError(f"invalid geographic eligibility status: '{self.status}'")


def _compute_canonical_content_hash(
    organization: str,
    title: str,
    location_raw: str,
    description: str,
) -> str:
    norm_org = organization.strip().casefold()
    norm_title = re.sub(r"\s+", " ", title.strip().casefold())
    norm_loc = re.sub(r"\s+", " ", location_raw.strip().casefold())
    norm_desc = re.sub(r"\s+", " ", description.strip().casefold())
    payload = f"{norm_org}|{norm_title}|{norm_loc}|{norm_desc}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _compute_dedup_key(
    organization: str,
    title: str,
    location_raw: str,
) -> str:
    norm_org = re.sub(r"[^\w\s]", "", organization.strip().casefold())
    norm_org = re.sub(r"\s+", " ", norm_org).strip()
    norm_title = re.sub(r"[^\w\s]", "", title.strip().casefold())
    norm_title = re.sub(r"\s+", " ", norm_title).strip()
    norm_loc = re.sub(r"[^\w\s]", "", location_raw.strip().casefold())
    norm_loc = re.sub(r"\s+", " ", norm_loc).strip()
    payload = f"{norm_org}:{norm_title}:{norm_loc}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class Opportunity:
    id: str
    track: Track
    source: str
    source_url: str
    source_id: str
    organization: str
    title: str
    description: str
    responsibilities: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    seniority: SeniorityLevel = SeniorityLevel.UNSPECIFIED
    employment_type: EmploymentType = EmploymentType.UNSPECIFIED
    location_raw: str = ""
    remote_policy: RemotePolicy = RemotePolicy.UNSPECIFIED
    geographic_eligibility: GeographicEligibility | None = None
    compensation: Compensation | None = None
    posted_date: str | None = None
    closing_date: str | None = None
    procurement_metadata: ProcurementMetadata | None = None
    raw_provenance: SourceProvenance | None = None
    content_hash: str = ""
    dedup_key: str = ""
    extra_attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("opportunity id cannot be empty")
        if not self.source or not self.source.strip():
            raise ValueError("source cannot be empty")
        if not self.title or not self.title.strip():
            raise ValueError("title cannot be empty")
        if not isinstance(self.track, Track):
            raise ValueError(f"track must be an instance of Track enum, got {type(self.track)}")
        if not isinstance(self.seniority, SeniorityLevel):
            raise ValueError(f"seniority must be an instance of SeniorityLevel enum, got {type(self.seniority)}")
        if not isinstance(self.employment_type, EmploymentType):
            raise ValueError(f"employment_type must be an instance of EmploymentType enum, got {type(self.employment_type)}")
        if not isinstance(self.remote_policy, RemotePolicy):
            raise ValueError(f"remote_policy must be an instance of RemotePolicy enum, got {type(self.remote_policy)}")

        # Ensure content_hash is populated
        if not self.content_hash:
            computed_hash = _compute_canonical_content_hash(
                self.organization, self.title, self.location_raw, self.description
            )
            object.__setattr__(self, "content_hash", computed_hash)

        # Ensure dedup_key is populated
        if not self.dedup_key:
            computed_dedup = _compute_dedup_key(
                self.organization, self.title, self.location_raw
            )
            object.__setattr__(self, "dedup_key", computed_dedup)


@dataclass(frozen=True, slots=True)
class OpportunityCluster:
    canonical_id: str
    primary_opportunity: Opportunity
    duplicate_opportunities: tuple[Opportunity, ...] = ()
    dedup_layer: str = "exact"  # "exact" or "cross_source"
    sources: tuple[str, ...] = ()
    cluster_size: int = 1

    def __post_init__(self) -> None:
        if not self.canonical_id:
            raise ValueError("canonical_id cannot be empty")
        all_sources = tuple(sorted(set((self.primary_opportunity.source,) + tuple(d.source for d in self.duplicate_opportunities))))
        object.__setattr__(self, "sources", all_sources)
        object.__setattr__(self, "cluster_size", 1 + len(self.duplicate_opportunities))


@dataclass(frozen=True, slots=True)
class SourceHealthReport:
    source_id: str
    status: SourceHealthStatus
    records_fetched: int
    records_parsed: int
    records_valid: int
    fetch_latency_ms: int
    last_successful_ingestion: str | None
    error_message: str | None = None
    diagnostics: tuple[tuple[str, str], ...] = ()

    @property
    def is_healthy(self) -> bool:
        return self.status is SourceHealthStatus.HEALTHY
