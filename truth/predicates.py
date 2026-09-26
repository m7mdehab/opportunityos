"""Single committed predicate contract for the matching engine (ADR-0015).

`truth/graph.py` projects `AtomicAssertion.predicate` strings from two, and only two,
sources:

1. **PROJECTED** — a profile field walked by `truth/graph.py` per the
   `CANONICAL_MATERIAL_MANIFEST` declared in `truth/models.py`. These names are derived
   programmatically from that manifest below, so this module can never drift from what
   the graph actually emits.
2. **ASSERTION_ONLY** — supplied by a truth pack's top-level `assertions:` section
   (`truth/ingest.py::parse_assertion`, invoked from `graph_from_dict`). Nothing in
   `truth/graph.py` projects these; they exist only if a pack author writes them
   directly into `assertions:`. They are not defects — `career.target_role`,
   `preference.track`, `career.goal`, residence/location, capacity.team_size, and the
   premium full-time/on-site compensation threshold are all legitimately supplied this
   way — but code that reads them must know they carry no profile-projection guarantee.

`matching/scorer.py` and `matching/qualification.py` import predicate names from this
module exclusively; neither spells a predicate string literal itself. See
`docs/adr/ADR-0015-predicate-contract.md`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from truth.models import CANONICAL_MATERIAL_MANIFEST


class PredicateKind(str, Enum):
    """How a predicate string reaches the truth graph."""

    PROJECTED = "projected"
    ASSERTION_ONLY = "assertion_only"


@dataclass(frozen=True, slots=True)
class PredicateSpec:
    """One entry in the predicate registry."""

    name: str
    kind: PredicateKind
    source: str
    description: str = ""


def _projected_specs() -> dict[str, PredicateSpec]:
    """Derive the PROJECTED half of the registry from `truth/models.py`'s own manifest.

    This is not a hand-maintained duplicate: if `CANONICAL_MATERIAL_MANIFEST` changes,
    this dictionary changes with it automatically.
    """
    specs: dict[str, PredicateSpec] = {}
    for field_spec in CANONICAL_MATERIAL_MANIFEST:
        source = f"{field_spec.model_cls.__name__}.{field_spec.field_name}"
        specs[field_spec.predicate] = PredicateSpec(
            name=field_spec.predicate,
            kind=PredicateKind.PROJECTED,
            source=source,
            description=f"Projected by truth/graph.py from {source} (CANONICAL_MATERIAL_MANIFEST).",
        )
    return specs


# ---------------------------------------------------------------------------
# ASSERTION_ONLY predicates: not projected from any profile field. Each is supplied
# only if the pack author writes it into the top-level `assertions:` section
# (truth/ingest.py:566-576, graph_from_dict -> parse_assertion). The "source" below
# names that owning pack section.
# ---------------------------------------------------------------------------
_ASSERTION_ONLY_SPECS: tuple[PredicateSpec, ...] = (
    PredicateSpec(
        name="career.target_role",
        kind=PredicateKind.ASSERTION_ONLY,
        source="assertions",
        description=(
            "Founder's declared target role. Supplied only via the pack's top-level "
            "`assertions:` section; no profile field projects it."
        ),
    ),
    PredicateSpec(
        name="preference.track",
        kind=PredicateKind.ASSERTION_ONLY,
        source="assertions",
        description=(
            "Founder's declared track preference ordering (employment vs. independent). "
            "Supplied only via the pack's top-level `assertions:` section."
        ),
    ),
    PredicateSpec(
        name="career.goal",
        kind=PredicateKind.ASSERTION_ONLY,
        source="assertions",
        description=(
            "Founder's free-text career goal statement. Supplied only via the pack's "
            "top-level `assertions:` section."
        ),
    ),
    PredicateSpec(
        name="residence.country",
        kind=PredicateKind.ASSERTION_ONLY,
        source="assertions",
        description="Founder's asserted country of residence. Supplied only via `assertions:`.",
    ),
    PredicateSpec(
        name="residence.city",
        kind=PredicateKind.ASSERTION_ONLY,
        source="assertions",
        description="Founder's asserted city of residence. Supplied only via `assertions:`.",
    ),
    PredicateSpec(
        name="residence.jurisdiction",
        kind=PredicateKind.ASSERTION_ONLY,
        source="assertions",
        description="Founder's asserted residence jurisdiction. Supplied only via `assertions:`.",
    ),
    PredicateSpec(
        name="location.city",
        kind=PredicateKind.ASSERTION_ONLY,
        source="assertions",
        description="Founder's asserted physical location (city). Supplied only via `assertions:`.",
    ),
    PredicateSpec(
        name="location.country",
        kind=PredicateKind.ASSERTION_ONLY,
        source="assertions",
        description="Founder's asserted physical location (country). Supplied only via `assertions:`.",
    ),
    PredicateSpec(
        name="capacity.team_size",
        kind=PredicateKind.ASSERTION_ONLY,
        source="assertions",
        description=(
            "Founder's asserted delivery team headcount for independent-track scope "
            "comparisons. No BusinessCapacity field carries this; it exists only if "
            "the pack author asserts it directly."
        ),
    ),
    PredicateSpec(
        name="preference.fulltime_onsite_premium_monthly",
        kind=PredicateKind.ASSERTION_ONLY,
        source="assertions",
        description=(
            "Founder's minimum monthly compensation threshold for full-time, on-site "
            "roles, expressed as '<amount> <ISO currency>' (e.g. '85000 EGP'). Used "
            "only as a ranking signal (compensation_fit), never a hard constraint. "
            "Supplied only via the pack's top-level `assertions:` section."
        ),
    ),
)

_REGISTRY: dict[str, PredicateSpec] = {
    **_projected_specs(),
    **{spec.name: spec for spec in _ASSERTION_ONLY_SPECS},
}


def get(name: str) -> PredicateSpec:
    """Look up a predicate's registry entry, raising if it is not declared."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"predicate {name!r} is not declared in truth/predicates.py; "
            "matching/ must not reference an undeclared predicate"
        ) from None


def all_predicates() -> dict[str, PredicateSpec]:
    """Return a copy of the full predicate registry."""
    return dict(_REGISTRY)


def is_declared(name: str) -> bool:
    return name in _REGISTRY


# ---------------------------------------------------------------------------
# Named constants. matching/scorer.py and matching/qualification.py import these
# instead of spelling predicate strings themselves.
# ---------------------------------------------------------------------------

# PROJECTED (truth/graph.py, from CANONICAL_MATERIAL_MANIFEST)
SKILL_NAME = "skill.name"
# BRIEF-FR-006 B2: already projected today -- truth/models.py's
# CANONICAL_MATERIAL_MANIFEST declares `MaterialFieldSpec(SkillRecord,
# "proficiency", "skill.proficiency", optional=True)`, and truth/graph.py's
# manifest-driven `_project_entity_manifest` walks every declared field, so
# this predicate was already reachable via `_projected_specs()` before this
# named constant existed. Registering the constant here (not adding a new
# graph projection) is what "read what the graph emits" means per the work
# order.
SKILL_PROFICIENCY = "skill.proficiency"
# BRIEF-FR-006 D1F: newly projected -- truth/models.py's CANONICAL_MATERIAL_MANIFEST
# now declares `MaterialFieldSpec(SkillRecord, "category", "skill.category",
# optional=True)`, so truth/graph.py's manifest-driven projection walks it the
# same generic way it already walked `proficiency`; no new code in graph.py
# was needed.
SKILL_CATEGORY = "skill.category"
EDUCATION_QUALIFICATION = "education.qualification"
EMPLOYMENT_TITLE = "employment.title"
EMPLOYMENT_ORGANIZATION = "employment.organization"
EMPLOYMENT_MARKET_FACING_TITLE = "employment.market_facing_title"
EMPLOYMENT_START_DATE = "employment.start_date"
EMPLOYMENT_END_DATE = "employment.end_date"
EMPLOYMENT_RESPONSIBILITY = "employment.responsibility"
ACHIEVEMENT_STATEMENT = "achievement.statement"
SERVICE_NAME = "service.name"
PORTFOLIO_TITLE = "portfolio.title"
WORK_AUTHORIZATION_JURISDICTION = "work_authorization.jurisdiction"
WORK_AUTHORIZATION_STATUS = "work_authorization.status"
LANGUAGE_LANGUAGE = "language.language"
LANGUAGE_PROFICIENCY = "language.proficiency"
CAPACITY_ANNUAL_TURNOVER_USD = "capacity.annual_turnover_usd"

# ASSERTION_ONLY (pack's top-level `assertions:` section)
CAREER_TARGET_ROLE = "career.target_role"
PREFERENCE_TRACK = "preference.track"
CAREER_GOAL = "career.goal"
RESIDENCE_COUNTRY = "residence.country"
RESIDENCE_CITY = "residence.city"
RESIDENCE_JURISDICTION = "residence.jurisdiction"
LOCATION_CITY = "location.city"
LOCATION_COUNTRY = "location.country"
CAPACITY_TEAM_SIZE = "capacity.team_size"
PREFERENCE_FULLTIME_ONSITE_PREMIUM_MONTHLY = "preference.fulltime_onsite_premium_monthly"

# Grouped tuples for `matching/` call sites that scan for founder location facts.
RESIDENCE_LOCATION_PREDICATES: tuple[str, ...] = (
    RESIDENCE_COUNTRY,
    RESIDENCE_CITY,
    LOCATION_CITY,
    LOCATION_COUNTRY,
    RESIDENCE_JURISDICTION,
)

CAREER_TRAJECTORY_PREDICATES: tuple[str, ...] = (
    CAREER_TARGET_ROLE,
    PREFERENCE_TRACK,
    CAREER_GOAL,
)

LANGUAGE_PREDICATES: tuple[str, ...] = (
    LANGUAGE_LANGUAGE,
    LANGUAGE_PROFICIENCY,
)

RESPONSIBILITY_SCOPE_PREDICATES: tuple[str, ...] = (
    EMPLOYMENT_RESPONSIBILITY,
    ACHIEVEMENT_STATEMENT,
)

# `matching/seniority.py` call sites that reconstruct employment spans (title,
# organization, dates, responsibilities) and their linked achievements from
# the truth graph's flat assertion list, grouped by `subject_id`.
EMPLOYMENT_TENURE_PREDICATES: tuple[str, ...] = (
    EMPLOYMENT_TITLE,
    EMPLOYMENT_ORGANIZATION,
    EMPLOYMENT_MARKET_FACING_TITLE,
    EMPLOYMENT_START_DATE,
    EMPLOYMENT_END_DATE,
    EMPLOYMENT_RESPONSIBILITY,
)

DOMAIN_FIT_PREDICATES: tuple[str, ...] = (
    SKILL_NAME,
    SERVICE_NAME,
    EMPLOYMENT_TITLE,
    ACHIEVEMENT_STATEMENT,
)

_NAMED_CONSTANTS: tuple[str, ...] = (
    SKILL_NAME,
    SKILL_PROFICIENCY,
    SKILL_CATEGORY,
    EDUCATION_QUALIFICATION,
    EMPLOYMENT_TITLE,
    EMPLOYMENT_ORGANIZATION,
    EMPLOYMENT_MARKET_FACING_TITLE,
    EMPLOYMENT_START_DATE,
    EMPLOYMENT_END_DATE,
    EMPLOYMENT_RESPONSIBILITY,
    ACHIEVEMENT_STATEMENT,
    SERVICE_NAME,
    PORTFOLIO_TITLE,
    WORK_AUTHORIZATION_JURISDICTION,
    WORK_AUTHORIZATION_STATUS,
    LANGUAGE_LANGUAGE,
    LANGUAGE_PROFICIENCY,
    CAPACITY_ANNUAL_TURNOVER_USD,
    CAREER_TARGET_ROLE,
    PREFERENCE_TRACK,
    CAREER_GOAL,
    RESIDENCE_COUNTRY,
    RESIDENCE_CITY,
    RESIDENCE_JURISDICTION,
    LOCATION_CITY,
    LOCATION_COUNTRY,
    CAPACITY_TEAM_SIZE,
    PREFERENCE_FULLTIME_ONSITE_PREMIUM_MONTHLY,
)

# Fail fast at import time if a named constant above ever drifts from the registry.
for _name in _NAMED_CONSTANTS:
    if _name not in _REGISTRY:
        raise AssertionError(f"truth/predicates.py: named constant {_name!r} has no registry entry")
