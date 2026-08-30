"""OpportunityOS Opportunity Data Models, Field Manifest, and Ingestion Schemas.

Covers dual-track employment and independent consulting / procurement opportunities
with strict typing, immutable records, atomic field-level provenance, deterministic
identifiers, and source-health diagnostics.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator


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


class DerivationType(str, Enum):
    RAW_EXTRACTION = "raw_extraction"
    CANONICAL_NORMALIZATION = "canonical_normalization"
    SOURCE_METADATA_DERIVATION = "source_metadata_derivation"
    RULE_DERIVATION = "rule_derivation"
    UNASSERTED_ABSENT = "unasserted_absent"


class SourceHealthStatus(str, Enum):
    HEALTHY = "healthy"
    EMPTY_RESULTS = "empty_results"
    SCHEMA_DRIFT_SUSPECTED = "schema_drift_suspected"
    POLICY_RESTRICTION = "policy_restriction"
    RATE_LIMITED = "rate_limited"
    TRANSIENT_FAILURE = "transient_failure"
    PERSISTENT_FAILURE = "persistent_failure"


# Canonical manifest of all material fields subject to provenance validation
MATERIAL_OPPORTUNITY_FIELD_MANIFEST: frozenset[str] = frozenset({
    "track",
    "organization",
    "title",
    "description",
    "responsibilities",
    "requirements",
    "skills",
    "seniority",
    "employment_type",
    "location_raw",
    "remote_policy",
    "geographic_eligibility",
    "compensation",
    "compensation.min_amount",
    "compensation.max_amount",
    "compensation.currency",
    "compensation.interval",
    "posted_date",
    "closing_date",
    "procurement_metadata",
    "procurement_metadata.notice_type",
    "procurement_metadata.buyer_name",
    "procurement_metadata.buyer_country",
    "procurement_metadata.procurement_category",
    "procurement_metadata.cpv_codes",
    "procurement_metadata.unspsc_codes",
    "procurement_metadata.deadline",
})


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    """Atomic provenance and lineage for an individual material normalized field."""
    field_name: str
    raw_value: str
    normalized_value: str
    derivation_type: str
    raw_pointer: str
    record_checksum: str
    rule_id: str

    def __post_init__(self) -> None:
        if not self.field_name:
            raise ValueError("field_name cannot be empty")
        if not self.derivation_type:
            raise ValueError("derivation_type cannot be empty")


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
    feed_checksum: str = ""

    def __post_init__(self) -> None:
        if not self.source_id or not self.source_id.strip():
            raise ValueError("source_id cannot be empty")
        if not self.fetched_at or not self.fetched_at.strip():
            raise ValueError("fetched_at cannot be empty")


@dataclass(frozen=True, slots=True)
class GeographicEligibility:
    status: str  # "eligible", "excluded", "ineligible", "unclear"
    reason: str
    individual_eligibility: str = "unclear"  # "individual_ok", "entity_required", "unclear"
    individual_reason: str = ""
    extracted_places: tuple[str, ...] = ()
    restrictions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"eligible", "excluded", "ineligible", "unclear"}:
            raise ValueError(f"invalid geographic eligibility status: '{self.status}'")


def compute_canonical_content_hash(
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


def compute_dedup_key(
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


def compute_deterministic_id(source: str, remote_id: str, title: str, organization: str, raw_pointer: str) -> str:
    if remote_id and remote_id.strip():
        clean_remote = re.sub(r"[^\w\-.]", "_", remote_id.strip())
        return f"{source}:{clean_remote}"
    digest = hashlib.sha256(f"{organization}:{title}:{raw_pointer}".encode("utf-8")).hexdigest()[:16]
    return f"{source}:{digest}"


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
    record_checksum: str = ""
    raw_record_pointer: str = ""
    field_provenances: tuple[FieldProvenance, ...] = ()
    canonical_outbound_url: str = ""
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

        # Ensure content_hash is populated deterministically
        if not self.content_hash:
            computed_hash = compute_canonical_content_hash(
                self.organization, self.title, self.location_raw, self.description
            )
            object.__setattr__(self, "content_hash", computed_hash)

        # Ensure dedup_key is populated deterministically
        if not self.dedup_key:
            computed_dedup = compute_dedup_key(
                self.organization, self.title, self.location_raw
            )
            object.__setattr__(self, "dedup_key", computed_dedup)


def validate_opportunity_provenance(opp: Opportunity) -> tuple[bool, str]:
    """Executable validator driving provenance coverage from MATERIAL_OPPORTUNITY_FIELD_MANIFEST."""
    prov_map = {fp.field_name: fp for fp in opp.field_provenances}

    # Material fields that MUST have lineage when populated
    checks = [
        ("track", opp.track.value if opp.track else None),
        ("title", opp.title),
        ("organization", opp.organization if opp.organization else None),
        ("description", opp.description if opp.description else None),
        ("location_raw", opp.location_raw if opp.location_raw else None),
        ("seniority", opp.seniority.value if opp.seniority != SeniorityLevel.UNSPECIFIED else None),
        ("employment_type", opp.employment_type.value if opp.employment_type != EmploymentType.UNSPECIFIED else None),
        ("remote_policy", opp.remote_policy.value if opp.remote_policy != RemotePolicy.UNSPECIFIED else None),
        ("geographic_eligibility", opp.geographic_eligibility.status if opp.geographic_eligibility else None),
    ]

    for field_name, val in checks:
        if val is not None:
            if field_name not in prov_map:
                return False, f"Missing provenance for populated material field '{field_name}'"
            fp = prov_map[field_name]
            if not fp.record_checksum:
                return False, f"Empty record_checksum in provenance for field '{field_name}'"
            if not fp.raw_pointer:
                return False, f"Empty raw_pointer in provenance for field '{field_name}'"

    return True, "Valid"


@dataclass(frozen=True, slots=True)
class OpportunityCluster:
    canonical_id: str
    primary_opportunity: Opportunity
    duplicate_opportunities: tuple[Opportunity, ...] = ()
    possible_duplicates: tuple[Opportunity, ...] = ()
    dedup_layer: str = "exact"  # "exact", "cross_source", "ambiguous"
    sources: tuple[str, ...] = ()
    cluster_size: int = 1
    is_ambiguous: bool = False

    def __post_init__(self) -> None:
        if not self.canonical_id:
            raise ValueError("canonical_id cannot be empty")
        all_sources = tuple(sorted(set((self.primary_opportunity.source,) + tuple(d.source for d in self.duplicate_opportunities) + tuple(p.source for p in self.possible_duplicates))))
        object.__setattr__(self, "sources", all_sources)
        object.__setattr__(self, "cluster_size", 1 + len(self.duplicate_opportunities))


@dataclass(frozen=True, slots=True)
class SourceHealthReport:
    source_id: str
    status: SourceHealthStatus
    transport_status: str
    parser_status: str
    records_raw_count: int
    records_parsed: int
    records_valid: int
    fetch_latency_ms: int
    last_successful_ingestion: str | None
    error_message: str | None = None
    diagnostics: tuple[tuple[str, str], ...] = ()

    @property
    def is_healthy(self) -> bool:
        return self.status is SourceHealthStatus.HEALTHY


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Explicit structured result of feed adapter parsing with sequence protocol support."""
    opportunities: tuple[Opportunity, ...]
    records_raw_count: int
    has_schema_drift: bool = False
    parser_error: str | None = None

    def __len__(self) -> int:
        return len(self.opportunities)

    def __iter__(self) -> Iterator[Opportunity]:
        return iter(self.opportunities)

    def __getitem__(self, idx: int) -> Opportunity:
        return self.opportunities[idx]
