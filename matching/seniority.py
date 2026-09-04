"""Founder seniority model derived from the truth graph (ADR-0016).

`matching/scorer.py`'s old `seniority_and_experience` dimension decided
"senior" by substring-matching a founder's employment titles against a fixed
keyword list (`"senior"`, `"lead"`, `"staff"`, ...). Any title containing
`"lead"` -- including a "Team Lead" role that carried no people-management
responsibility for one person and a modest individual-contributor scope for
another -- made *every* senior-and-up posting look like a match. That is a
scoring lie about a real person (`AGENTS.md`'s first hard rule).

This module replaces keyword matching with three signals computed only from
verified truth-graph evidence:

- `total_professional_months` -- elapsed tenure since the first non-internship
  role, with overlapping/concurrent roles counted once.
- `months_in_family` -- tenure restricted to roles whose title (or
  market-facing title) matches a caller-supplied family alias list. Until
  BRIEF-FR-006 B3 lands `matching/title_families.yaml`, callers pass a simple
  alias list; the family gate itself is reported for context but does not
  drive the pass/fail decision below (B1 scope; B3 wires it in).
- `has_people_leadership` -- derived only from employment responsibility text
  and achievement statements, **never** from title tokens. A "Team Lead"
  title with no responsibility text describing leadership does not count;
  a role titled plainly with a responsibility describing leading a team does.

See `docs/adr/ADR-0016-seniority-model.md` for the committed threshold table
and its rationale, and what this model explicitly refuses to infer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from truth import predicates
from truth.graph import TruthGraph
from truth.models import RelationType, VerificationStatus

# ---------------------------------------------------------------------------
# Employment span reconstruction
# ---------------------------------------------------------------------------

_INTERNSHIP_TITLE_RE = re.compile(r"\bintern(?:ship)?\b", re.IGNORECASE)

# Leadership signal: phrases that describe *doing* people leadership in a
# responsibility or achievement statement. Deliberately does not match a bare
# title token ("Team Lead", "Lead Engineer") -- this pattern is only ever
# applied to responsibility/achievement text, never to `employment.title` or
# `employment.market_facing_title` values. See ADR-0016 "what this refuses to
# infer".
_LEADERSHIP_TEXT_RE = re.compile(
    r"\b("
    r"led\s+(?:a|the|an)?\s*\w*\s*team|leading\s+(?:a|the)?\s*team|"
    r"managed\s+(?:a|the)?\s*team|managing\s+(?:a|the)?\s*team|"
    r"line[\s-]management|direct\s+reports?|"
    r"mentored|mentoring|supervised|supervising|"
    r"hired\s+and\s+(?:led|managed)|grew\s+and\s+led|built\s+and\s+led|"
    r"led\s+the\s+\w+(?:\s+\w+){0,4}\s+(?:team|platform|group|department|org|organization)|"
    r"people\s+management|managed\s+\d+\s+(?:engineers?|people|reports?)|"
    r"led\s+\d+\s+(?:engineers?|people|reports?)"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class EmploymentSpan:
    """One reconstructed employment record, grouped by `AtomicAssertion.subject_id`."""

    subject_id: str
    title: str
    market_facing_title: str | None
    organization: str | None
    start_date: date
    end_date: date | None
    is_internship: bool
    responsibility_texts: tuple[str, ...]
    achievement_texts: tuple[str, ...]
    evidence_refs: tuple[str, ...]


def _is_internship(title: str) -> bool:
    return bool(_INTERNSHIP_TITLE_RE.search(title))


def extract_employment_spans(truth_graph: TruthGraph) -> tuple[EmploymentSpan, ...]:
    """Reconstruct employment spans from verified truth-graph assertions.

    Groups every verified `employment.*` assertion by `subject_id` (the join
    key `truth/graph.py` uses for both profile-projected employment records,
    keyed by `EmploymentRecord.id`, and directly-asserted, flat test/pack
    fixtures keyed by an arbitrary subject like `"founder"`). A subject only
    becomes a span once it has both a title and a start date; a title without
    a verified start date carries no computable tenure and is not fabricated
    into one.

    Achievement statements are attached to a span only when a verified
    `RelationType.ACHIEVED_DURING` relation links the achievement's subject
    back to the employment's subject -- the same relation
    `truth/graph.py::_wire_employment_achievement_relation` establishes for
    profile-projected employment. Flat fixtures with no such relation simply
    carry no achievement text, which is the honest answer.
    """
    titles: dict[str, str] = {}
    market_titles: dict[str, str] = {}
    organizations: dict[str, str] = {}
    starts: dict[str, date] = {}
    ends: dict[str, date] = {}
    responsibilities: dict[str, list[str]] = {}
    evidence: dict[str, set[str]] = {}

    for assertion in truth_graph.assertions.values():
        if assertion.verification_status != VerificationStatus.VERIFIED:
            continue
        subject = assertion.subject_id
        if assertion.predicate == predicates.EMPLOYMENT_TITLE:
            titles[subject] = str(assertion.value)
            evidence.setdefault(subject, set()).update(assertion.evidence_ids)
        elif assertion.predicate == predicates.EMPLOYMENT_MARKET_FACING_TITLE:
            market_titles[subject] = str(assertion.value)
            evidence.setdefault(subject, set()).update(assertion.evidence_ids)
        elif assertion.predicate == predicates.EMPLOYMENT_ORGANIZATION:
            organizations[subject] = str(assertion.value)
            evidence.setdefault(subject, set()).update(assertion.evidence_ids)
        elif assertion.predicate == predicates.EMPLOYMENT_START_DATE and isinstance(assertion.value, date):
            starts[subject] = assertion.value
            evidence.setdefault(subject, set()).update(assertion.evidence_ids)
        elif assertion.predicate == predicates.EMPLOYMENT_END_DATE and isinstance(assertion.value, date):
            ends[subject] = assertion.value
            evidence.setdefault(subject, set()).update(assertion.evidence_ids)
        elif assertion.predicate == predicates.EMPLOYMENT_RESPONSIBILITY:
            responsibilities.setdefault(subject, []).append(str(assertion.value))
            evidence.setdefault(subject, set()).update(assertion.evidence_ids)

    # Achievement statements, grouped by achievement subject_id.
    achievement_texts: dict[str, list[str]] = {}
    achievement_evidence: dict[str, set[str]] = {}
    for assertion in truth_graph.assertions.values():
        if assertion.verification_status != VerificationStatus.VERIFIED:
            continue
        if assertion.predicate == predicates.ACHIEVEMENT_STATEMENT:
            achievement_texts.setdefault(assertion.subject_id, []).append(str(assertion.value))
            achievement_evidence.setdefault(assertion.subject_id, set()).update(assertion.evidence_ids)

    # Link achievements to employment spans only via a verified ACHIEVED_DURING relation.
    linked_achievements: dict[str, list[str]] = {}
    linked_achievement_evidence: dict[str, set[str]] = {}
    for relation in truth_graph.relations.values():
        if relation.relation_type != RelationType.ACHIEVED_DURING:
            continue
        if relation.verification_status != VerificationStatus.VERIFIED:
            continue
        emp_subject, ach_subject = relation.source_id, relation.target_id
        if ach_subject in achievement_texts:
            linked_achievements.setdefault(emp_subject, []).extend(achievement_texts[ach_subject])
            linked_achievement_evidence.setdefault(emp_subject, set()).update(
                achievement_evidence.get(ach_subject, set())
            )

    spans: list[EmploymentSpan] = []
    for subject, title in titles.items():
        start = starts.get(subject)
        if start is None:
            # No verified tenure to compute; not fabricated as "since forever".
            continue
        ev_refs = set(evidence.get(subject, set())) | set(linked_achievement_evidence.get(subject, set()))
        spans.append(EmploymentSpan(
            subject_id=subject,
            title=title,
            market_facing_title=market_titles.get(subject),
            organization=organizations.get(subject),
            start_date=start,
            end_date=ends.get(subject),
            is_internship=_is_internship(title) or _is_internship(market_titles.get(subject, "")),
            responsibility_texts=tuple(responsibilities.get(subject, ())),
            achievement_texts=tuple(linked_achievements.get(subject, ())),
            evidence_refs=tuple(sorted(ev_refs)),
        ))

    return tuple(sorted(spans, key=lambda s: s.start_date))


# ---------------------------------------------------------------------------
# Tenure arithmetic
# ---------------------------------------------------------------------------

def _month_index(d: date) -> int:
    return d.year * 12 + (d.month - 1)


def _months_in_range_inclusive(start: date, end: date) -> int:
    """Whole calendar months spanned by [start, end], inclusive of both ends'
    months. E.g. 2020-04-01 to 2020-04-30 is 1 month; 2020-01-01 to
    2020-12-31 is 12 months."""
    return max(_month_index(end) - _month_index(start) + 1, 0)


def _merge_month_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge inclusive month-index ranges, treating adjacent (no-gap) ranges
    as continuous so back-to-back employers without a gap are not
    double-counted and are not artificially split either."""
    if not ranges:
        return []
    ranges = sorted(ranges)
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _total_months(spans: list[EmploymentSpan], *, as_of: date) -> int:
    ranges: list[tuple[int, int]] = []
    for span in spans:
        if span.is_internship:
            continue
        end = span.end_date or as_of
        if end < span.start_date:
            continue
        ranges.append((_month_index(span.start_date), _month_index(end)))
    merged = _merge_month_ranges(ranges)
    return sum(end - start + 1 for start, end in merged)


def total_professional_months(spans: tuple[EmploymentSpan, ...], *, as_of: date | None = None) -> int:
    """Total months of professional (non-internship) experience, counting
    overlapping/concurrent roles once."""
    as_of = as_of or date.today()
    return _total_months(list(spans), as_of=as_of)


def _title_matches_family(span: EmploymentSpan, family_aliases: tuple[str, ...]) -> bool:
    haystacks = [span.title.casefold()]
    if span.market_facing_title:
        haystacks.append(span.market_facing_title.casefold())
    return any(alias.casefold() in haystack for alias in family_aliases for haystack in haystacks)


def months_in_family(
    spans: tuple[EmploymentSpan, ...],
    family_aliases: tuple[str, ...],
    *,
    as_of: date | None = None,
) -> int:
    """Months of (non-internship) tenure in roles whose title matches any of
    `family_aliases` (case-insensitive substring match against
    `employment.title` / `employment.market_facing_title`). Overlapping roles
    within the family are counted once."""
    if not family_aliases:
        return 0
    as_of = as_of or date.today()
    family_spans = [s for s in spans if not s.is_internship and _title_matches_family(s, family_aliases)]
    return _total_months(family_spans, as_of=as_of)


def has_people_leadership(spans: tuple[EmploymentSpan, ...]) -> tuple[bool, tuple[str, ...]]:
    """Whether any (non-internship) role's responsibility or achievement text
    describes people leadership. Title text is never consulted -- see the
    module docstring and ADR-0016."""
    evidence_refs: list[str] = []
    found = False
    for span in spans:
        if span.is_internship:
            continue
        texts = span.responsibility_texts + span.achievement_texts
        if any(_LEADERSHIP_TEXT_RE.search(text) for text in texts):
            found = True
            evidence_refs.extend(span.evidence_refs)
    return found, tuple(sorted(set(evidence_refs)))


# ---------------------------------------------------------------------------
# Committed threshold table (ADR-0016)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LevelRequirement:
    level: str
    months_floor: int
    requires_leadership: bool


#: Committed thresholds mapping a required level to a total-professional-months
#: floor and whether verified people-leadership evidence is also required.
#: Rationale and the industry bands behind these numbers are recorded in
#: `docs/adr/ADR-0016-seniority-model.md`; this table is the single source of
#: truth for both the scorer and this module's tests.
SENIORITY_THRESHOLDS: tuple[LevelRequirement, ...] = (
    LevelRequirement("junior", 0, False),
    LevelRequirement("mid", 24, False),
    LevelRequirement("senior", 60, False),
    LevelRequirement("staff", 120, True),
    LevelRequirement("principal", 180, True),
)

THRESHOLDS_BY_LEVEL: dict[str, LevelRequirement] = {t.level: t for t in SENIORITY_THRESHOLDS}


@dataclass(frozen=True, slots=True)
class SeniorityAssessment:
    """Everything the scorer needs to explain a seniority decision without
    fabricating a claim: the computed numbers, the evidence backing them, and
    whether the founder meets the requested level's committed bar."""

    total_months: int
    family_months: int
    family_aliases: tuple[str, ...]
    has_leadership: bool
    leadership_evidence_refs: tuple[str, ...]
    tenure_evidence_refs: tuple[str, ...]
    requirement: LevelRequirement | None
    meets_requirement: bool
    months_gap: int  # 0 if requirement is met or unknown


def assess(
    truth_graph: TruthGraph,
    *,
    required_level: str | None,
    family_aliases: tuple[str, ...] = (),
    as_of: date | None = None,
) -> SeniorityAssessment | None:
    """Compute the full seniority assessment for `truth_graph` against
    `required_level` (one of `THRESHOLDS_BY_LEVEL`'s keys, or `None`/unknown
    for an unspecified requirement). Returns `None` if the truth graph has no
    reconstructable employment span at all (no verified title+start_date
    pair) -- the caller must not invent a score from nothing."""
    spans = extract_employment_spans(truth_graph)
    if not spans:
        return None

    as_of = as_of or date.today()
    total = total_professional_months(spans, as_of=as_of)
    family = months_in_family(spans, family_aliases, as_of=as_of) if family_aliases else 0
    leadership, leadership_refs = has_people_leadership(spans)
    tenure_refs = tuple(sorted({ref for span in spans for ref in span.evidence_refs}))

    requirement = THRESHOLDS_BY_LEVEL.get(required_level) if required_level else None
    if requirement is None:
        meets = False
        gap = 0
    else:
        months_short = max(requirement.months_floor - total, 0)
        leadership_ok = (not requirement.requires_leadership) or leadership
        meets = months_short == 0 and leadership_ok
        gap = months_short

    return SeniorityAssessment(
        total_months=total,
        family_months=family,
        family_aliases=family_aliases,
        has_leadership=leadership,
        leadership_evidence_refs=leadership_refs,
        tenure_evidence_refs=tenure_refs,
        requirement=requirement,
        meets_requirement=meets,
        months_gap=gap,
    )


def _format_years_months(months: int) -> str:
    years, rem = divmod(months, 12)
    if years and rem:
        return f"{years}y {rem}m"
    if years:
        return f"{years}y"
    return f"{rem}m"


def explain(assessment: SeniorityAssessment, *, family_label: str = "target role family") -> str:
    """Render the assessment as the explanation shape the brief specifies:
    months professional, months in family, what the role asks, and the gap --
    generated from the computed numbers, never a fixed string."""
    parts = [
        f"Founder: {_format_years_months(assessment.total_months)} professional",
        f"{_format_years_months(assessment.family_months)} in {family_label}",
    ]
    if assessment.requirement is None:
        parts.append("role's required level is unspecified")
    else:
        req = assessment.requirement
        floor_desc = f"{req.level.title()} ({_format_years_months(req.months_floor)}+)"
        if req.requires_leadership:
            floor_desc += ", people leadership"
        parts.append(f"role asks {floor_desc}")
        if assessment.meets_requirement:
            parts.append("meets the bar")
        else:
            if assessment.months_gap > 0:
                parts.append(f"gap: {_format_years_months(assessment.months_gap)}")
            elif req.requires_leadership and not assessment.has_leadership:
                parts.append("gap: no verified people-leadership evidence")
    return "; ".join(parts) + "."
