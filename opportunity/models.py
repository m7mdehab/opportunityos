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
from typing import Any, Callable, Iterator


class Track(str, Enum):
    EMPLOYMENT = "employment"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    PROCUREMENT = "procurement"
    TUTORING = "tutoring"  # BRIEF-FR-006 E23: platform-application tutoring track, not a postings track.


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
    PLATFORM_APPLICATION = "platform_application"  # BRIEF-FR-006 E23: tutoring platforms; not a posting.
    UNSPECIFIED = "unspecified"


class RemotePolicy(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ON_SITE = "on_site"
    UNSPECIFIED = "unspecified"


class WorkMode(str, Enum):
    """BRIEF-FR-006 A1 canonical work-mode field (values per the brief: remote |
    hybrid | onsite | unspecified -- distinct spelling from ``RemotePolicy.ON_SITE``,
    which predates this field and stays for backward compatibility; see
    ``_WORK_MODE_TO_REMOTE_POLICY`` below for the mapping)."""
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNSPECIFIED = "unspecified"


class RemoteScope(str, Enum):
    """Only meaningful when ``work_mode`` is ``REMOTE`` (or, loosely, ``HYBRID``)."""
    WORLDWIDE = "worldwide"
    REGION_RESTRICTED = "region_restricted"
    UNSPECIFIED = "unspecified"


WORK_MODE_SOURCE_VALUES: frozenset[str] = frozenset({"adapter", "inference", "none"})


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


@dataclass(frozen=True, slots=True)
class MaterialFieldRule:
    """Executable rule definition for a material opportunity field."""
    field_name: str
    is_populated: Callable[[Opportunity], bool]
    provenance_field_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.provenance_field_names:
            object.__setattr__(self, "provenance_field_names", (self.field_name,))


# Authoritative executable rules driving material opportunity provenance validation
MATERIAL_OPPORTUNITY_FIELD_RULES: tuple[MaterialFieldRule, ...] = (
    MaterialFieldRule("track", lambda opp: bool(opp.track)),
    MaterialFieldRule("organization", lambda opp: bool(opp.organization)),
    MaterialFieldRule("title", lambda opp: bool(opp.title)),
    MaterialFieldRule("description", lambda opp: bool(opp.description)),
    MaterialFieldRule("responsibilities", lambda opp: bool(opp.responsibilities)),
    MaterialFieldRule("requirements", lambda opp: bool(opp.requirements)),
    MaterialFieldRule("skills", lambda opp: bool(opp.skills)),
    MaterialFieldRule("seniority", lambda opp: opp.seniority != SeniorityLevel.UNSPECIFIED),
    MaterialFieldRule("employment_type", lambda opp: opp.employment_type != EmploymentType.UNSPECIFIED),
    MaterialFieldRule("location_raw", lambda opp: bool(opp.location_raw)),
    # BRIEF-FR-006 A1: ``work_mode`` (not ``remote_policy``) is now the canonical
    # populated-field signal and the field every adapter attaches a FieldProvenance
    # entry to. ``remote_policy`` stays as a constructor-compatible, always-synced
    # alias (see Opportunity.__post_init__) but is deliberately not re-checked here
    # to avoid requiring two separate provenance entries for one underlying fact.
    MaterialFieldRule("work_mode", lambda opp: opp.work_mode != WorkMode.UNSPECIFIED),
    MaterialFieldRule("geographic_eligibility", lambda opp: bool(opp.geographic_eligibility)),
    MaterialFieldRule("compensation", lambda opp: opp.compensation is not None, ("compensation",)),
    MaterialFieldRule("compensation.min_amount", lambda opp: opp.compensation is not None and opp.compensation.min_amount is not None, ("compensation.min_amount",)),
    MaterialFieldRule("compensation.max_amount", lambda opp: opp.compensation is not None and opp.compensation.max_amount is not None, ("compensation.max_amount",)),
    MaterialFieldRule("compensation.currency", lambda opp: opp.compensation is not None and opp.compensation.currency is not None, ("compensation.currency",)),
    MaterialFieldRule("compensation.interval", lambda opp: opp.compensation is not None and opp.compensation.interval != CompensationInterval.UNSPECIFIED, ("compensation.interval",)),
    MaterialFieldRule("posted_date", lambda opp: bool(opp.posted_date)),
    MaterialFieldRule("closing_date", lambda opp: bool(opp.closing_date)),
    MaterialFieldRule("procurement_metadata", lambda opp: opp.procurement_metadata is not None, ("procurement_metadata", "notice_type", "buyer_name", "cpv_codes")),
    MaterialFieldRule("procurement_metadata.notice_type", lambda opp: opp.procurement_metadata is not None and bool(opp.procurement_metadata.notice_type), ("notice_type", "procurement_metadata.notice_type")),
    MaterialFieldRule("procurement_metadata.buyer_name", lambda opp: opp.procurement_metadata is not None and bool(opp.procurement_metadata.buyer_name), ("buyer_name", "organization", "procurement_metadata.buyer_name")),
    MaterialFieldRule("procurement_metadata.buyer_country", lambda opp: opp.procurement_metadata is not None and bool(opp.procurement_metadata.buyer_country), ("buyer_country", "location_raw", "procurement_metadata.buyer_country")),
    MaterialFieldRule("procurement_metadata.procurement_category", lambda opp: opp.procurement_metadata is not None and bool(opp.procurement_metadata.procurement_category), ("procurement_category", "procurement_metadata.procurement_category")),
    MaterialFieldRule("procurement_metadata.cpv_codes", lambda opp: opp.procurement_metadata is not None and bool(opp.procurement_metadata.cpv_codes), ("cpv_codes", "procurement_metadata.cpv_codes")),
    MaterialFieldRule("procurement_metadata.unspsc_codes", lambda opp: opp.procurement_metadata is not None and bool(opp.procurement_metadata.unspsc_codes), ("unspsc_codes", "procurement_metadata.unspsc_codes")),
    MaterialFieldRule("procurement_metadata.deadline", lambda opp: opp.procurement_metadata is not None and bool(opp.procurement_metadata.deadline), ("deadline", "closing_date", "procurement_metadata.deadline")),
)

# Canonical manifest of all material fields
MATERIAL_OPPORTUNITY_FIELD_MANIFEST: frozenset[str] = frozenset(r.field_name for r in MATERIAL_OPPORTUNITY_FIELD_RULES)


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


# BRIEF-FR-006 A1 Master decision: ``work_mode`` is the new canonical field.
# ``Opportunity.remote_policy`` stays reachable (not deleted -- BRIEF-003 and
# every frozen matching/api/truth call site keep constructing and reading it)
# but its value is always derived to agree with ``work_mode`` -- see
# ``Opportunity.__post_init__``. Literal `on_site` (RemotePolicy) vs. `onsite`
# (WorkMode) is intentional: the brief specifies `onsite` for the new field and
# `on_site` already shipped in RemotePolicy before this deliverable.
_WORK_MODE_TO_REMOTE_POLICY: dict[WorkMode, RemotePolicy] = {
    WorkMode.REMOTE: RemotePolicy.REMOTE,
    WorkMode.HYBRID: RemotePolicy.HYBRID,
    WorkMode.ONSITE: RemotePolicy.ON_SITE,
    WorkMode.UNSPECIFIED: RemotePolicy.UNSPECIFIED,
}
_REMOTE_POLICY_TO_WORK_MODE: dict[RemotePolicy, WorkMode] = {
    remote_policy: work_mode for work_mode, remote_policy in _WORK_MODE_TO_REMOTE_POLICY.items()
}


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
        candidate = f"{source}:{clean_remote}"
        if len(candidate) <= 64:
            return candidate
        # Composed id exceeds storage.models.Opportunity.id's 64-char primary key
        # bound (e.g. We Work Remotely slugs). Fall back to the same bounded,
        # deterministic hash form already used below for the empty-remote_id case,
        # so long remote_ids never overflow the column or collide via truncation.
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
    # BRIEF-FR-006 A1 fields. ``work_mode`` is the new canonical, writable field;
    # ``remote_policy`` below is a read-only derived @property (Master decision #1)
    # -- NOT a constructor parameter any more. See the FR-006 A1 report: this is a
    # breaking change for any `Opportunity(remote_policy=...)` call site outside
    # this deliverable's allowed file set (six frozen files identified and named
    # in that report; they must be repointed at `work_mode=` in a follow-up).
    work_mode: WorkMode = WorkMode.UNSPECIFIED
    work_mode_source: str = "none"  # "adapter" | "inference" | "none"
    location_country: str = ""  # ISO-2
    location_city: str = ""
    location_region: str = ""
    remote_scope: RemoteScope = RemoteScope.UNSPECIFIED
    remote_scope_regions: tuple[str, ...] = ()
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
        if not isinstance(self.work_mode, WorkMode):
            raise ValueError(f"work_mode must be an instance of WorkMode enum, got {type(self.work_mode)}")
        if not isinstance(self.remote_scope, RemoteScope):
            raise ValueError(f"remote_scope must be an instance of RemoteScope enum, got {type(self.remote_scope)}")
        if self.work_mode_source not in WORK_MODE_SOURCE_VALUES:
            raise ValueError(
                f"work_mode_source must be one of {sorted(WORK_MODE_SOURCE_VALUES)}, got {self.work_mode_source!r}"
            )

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

    @property
    def remote_policy(self) -> RemotePolicy:
        """Read-only derived alias of ``work_mode`` (BRIEF-FR-006 A1 Master decision
        #1). Kept so BRIEF-003 call sites that only *read* ``opp.remote_policy``
        keep working; it is deliberately not a constructor parameter -- ``work_mode``
        is the single writable source of truth."""
        return _WORK_MODE_TO_REMOTE_POLICY[self.work_mode]


def validate_opportunity_provenance(opp: Opportunity) -> tuple[bool, str]:
    """Mechanically authoritative validation driven by MATERIAL_OPPORTUNITY_FIELD_RULES."""
    prov_map = {fp.field_name: fp for fp in opp.field_provenances}

    for rule in MATERIAL_OPPORTUNITY_FIELD_RULES:
        if rule.is_populated(opp):
            matching_names = [pname for pname in rule.provenance_field_names if pname in prov_map]
            if not matching_names:
                return False, f"Missing provenance for populated material field '{rule.field_name}'"
            for pname in matching_names:
                fp = prov_map[pname]
                if not fp.record_checksum:
                    return False, f"Empty record_checksum in provenance for field '{pname}'"
                if not fp.raw_pointer:
                    return False, f"Empty raw_pointer in provenance for field '{pname}'"

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
