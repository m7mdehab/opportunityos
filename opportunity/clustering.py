"""A2 (BRIEF-FR-006) -- near-duplicate clustering of postings into families.

The founder's first real run showed twenty near-identical "Senior Customer
Engineer" cards at fit 73, differing only by location. Twenty cards for one
job is one opportunity and nineteen units of noise. This module groups
postings from the same employer, for the same normalized title, that differ
only by location/team suffix, into one *family*; the family card carries the
best-fit member's score (never an average) and a location list, and never
hides a member's real ``decision``/``fit_score`` behind a sibling's.

This is a layer *above* ``opportunity.dedupe`` (frozen, not touched here):
dedupe removes the same posting seen twice (proven identity); clustering
groups genuinely different postings for the same role. Neither weakens nor
duplicates the other -- ``family_key`` is computed only from
``organization``/``title`` and is orthogonal to dedupe's identity/content
hashing.

Deterministic and pure: no I/O, no reliance on dict/set iteration order,
same inputs always yield the same outputs.

Title normalizer used
----------------------
``matching.title_family.normalize_title`` (work order B3) if importable on
this branch; otherwise a same-signature fallback defined here (see
``_fallback_normalize_title``) so the Master can swap it at integration
without touching call sites. ``TITLE_NORMALIZER_SOURCE`` records, at import
time, which one is actually in effect -- callers/tests/evidence scripts
should report it.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from opportunity.models import Opportunity

try:
    from matching.title_family import normalize_title as _normalize_title_impl
    TITLE_NORMALIZER_SOURCE = "matching.title_family.normalize_title"
except ImportError:  # pragma: no cover - exercised only when B3 is absent from the base
    _TOKEN_RE = re.compile(r"[a-z0-9]+")
    _NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
    _LEVEL_TOKEN_RANK: dict[str, int] = {
        "intern": 0, "internship": 0, "trainee": 0,
        "junior": 1, "jr": 1, "entry": 1, "graduate": 1, "associate": 1,
        "mid": 2, "ii": 2,
        "senior": 3, "sr": 3, "lead": 3,
        "staff": 4,
        "principal": 5, "distinguished": 5, "chief": 5,
    }
    _LEVEL_BY_RANK: dict[int, str] = {
        0: "intern", 1: "junior", 2: "mid", 3: "senior", 4: "staff", 5: "principal",
    }

    def _fallback_normalize_title(title: str) -> tuple[str, str, str]:
        """Same-signature (family_id, level, matched_rule) stand-in for
        ``matching.title_family.normalize_title``, used only when B3 has not
        landed on this branch. Family granularity here is coarser (there is
        no committed ``title_families.yaml`` alias table to draw on without
        importing that module's private data): it falls back to the
        core-title text itself (see ``_strip_location_team_suffix`` below) as
        the family id, which is safe (never merges two different titles) but
        will not group known synonyms the way B3's alias table does."""
        normalized = _NON_ALNUM_RE.sub(" ", (title or "").casefold()).strip()
        best_rank: int | None = None
        for token in _TOKEN_RE.findall(normalized):
            rank = _LEVEL_TOKEN_RANK.get(token)
            if rank is not None and (best_rank is None or rank > best_rank):
                best_rank = rank
        level = _LEVEL_BY_RANK[best_rank] if best_rank is not None else "unspecified"
        core = _strip_location_team_suffix(title or "")
        return core or "other", level, "fallback#core_title"

    _normalize_title_impl = _fallback_normalize_title
    TITLE_NORMALIZER_SOURCE = "opportunity.clustering._fallback_normalize_title"


_SUFFIX_SPLIT_RE = re.compile(r"\s+[-‐-―]\s+|,|\(|\||/")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_EMPLOYER_RE = re.compile(r"[^a-z0-9]+")


def _strip_location_team_suffix(title: str) -> str:
    """Strip a trailing location/team suffix from a raw title, conservatively.

    Splits only on a hyphen/en-dash/em-dash *surrounded by whitespace* (so
    hyphenated compound words like "Full-Stack Engineer" are untouched), a
    comma, an opening parenthesis, a pipe, or a slash -- the punctuation
    patterns job boards actually use to append "- EMEA", ", Remote",
    "(APAC)", "| Berlin" to an otherwise-identical title. Takes the text
    before the first such delimiter. Named assumption: this heuristic can
    both under-strip (an unusual suffix format) and, in principle, over-strip
    a title that genuinely uses one of these delimiters as part of the role
    name itself; it is used only as extra key material for titles that do
    not match a known title family (the "other" bucket) and never overrides
    a matched family's own id, so an over-strip there only risks two
    genuinely different "other" titles being treated as candidates for the
    same family key less often than the truth, never a false employer/family
    merge.
    """
    core = _SUFFIX_SPLIT_RE.split(title or "", maxsplit=1)[0]
    return _WS_RE.sub(" ", core).strip().casefold()


def normalize_title(title: str) -> tuple[str, str, str]:
    """Re-exported title normalizer actually in effect (see module docstring)."""
    return _normalize_title_impl(title)


def normalized_title_key(title: str) -> str:
    """Combine a title's family id and seniority level into one normalized
    title string for clustering purposes.

    Named assumption: two postings are the "same normalized title" for
    family purposes when they resolve to the same title family AND the same
    seniority level -- "Customer Engineer" and "Senior Customer Engineer"
    are treated as different opportunities (a level word is a real
    distinction the founder should see), not location/team variants of one
    another. Only location and team suffixes collapse.

    For titles that do not match any committed family (``family_id ==
    "other"``), the family id alone is too coarse to trust: two unrelated
    titles that both fail to match any known family would otherwise collide.
    So the "other" bucket additionally folds in the location/team-suffix-
    stripped title text itself, keeping the same collapse behavior (location
    suffixes still stripped) without merging unrelated unmatched titles.
    """
    family_id, level, _rule = normalize_title(title or "")
    if family_id == "other":
        return f"other:{level}:{_strip_location_team_suffix(title or '')}"
    return f"{family_id}:{level}"


def _normalize_employer(organization: str) -> str:
    return _NON_ALNUM_EMPLOYER_RE.sub("", (organization or "").casefold())


def compute_family_key(organization: str, title: str) -> str:
    """Pure, deterministic family key from an employer name and a raw title.

    Exposed separately from :func:`family_key` (which takes a full
    ``Opportunity``) so a caller that only has ``organization``/``title``
    columns -- e.g. a storage-row backfill -- does not need to construct a
    full ``Opportunity`` just to compute this.
    """
    employer_key = _normalize_employer(organization)
    title_key = normalized_title_key(title)
    payload = f"{employer_key}|{title_key}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def family_key(opportunity: Opportunity) -> str:
    """Deterministic, pure family key: employer + normalized title, with
    location and team suffixes stripped. Same inputs always yield the same
    key, independent of dict/set iteration order and independent of the
    order rows were polled in (it is a pure function of two string fields).
    """
    return compute_family_key(opportunity.organization, opportunity.title)


@dataclass(frozen=True, slots=True)
class FamilyMember:
    """One clustered posting plus the match-evaluation facts needed to build
    a family card.

    ``Opportunity`` itself carries no ``fit_score``/``decision`` (those live
    in ``storage.models.MatchEvaluationRecord``, joined in by the caller --
    this module has no database access and must stay pure), so callers
    supply them explicitly. Both default to ``None`` when no evaluation
    exists yet for that member; such a member can still be grouped into a
    family but is never selected as ``best_member_id`` over an evaluated
    sibling (see ``_select_best``).
    """
    opportunity: Opportunity
    fit_score: float | None = None
    decision: str | None = None


@dataclass(frozen=True, slots=True)
class Family:
    """A family card: one row per family, carrying the best-fit member's
    score/decision (never an average), a location list, and the member
    count. ``decisions_differ`` is set whenever two members disagree on
    ``decision`` -- the family card must never hide an ``ineligible``
    member's status behind a ``qualified`` sibling; the UI is expected to
    show that flag alongside the best member's own decision.
    """
    family_key: str
    employer: str
    normalized_title: str
    member_ids: tuple[str, ...]
    best_member_id: str
    best_fit_score: float | None
    best_decision: str | None
    locations: tuple[str, ...]
    member_count: int
    decisions_differ: bool

    @property
    def is_singleton(self) -> bool:
        """A posting with no sibling is a family of one and should behave
        exactly like a plain card."""
        return self.member_count == 1


def _select_best(members: Sequence[FamilyMember]) -> FamilyMember:
    """Deterministic best-fit selection: highest ``fit_score`` wins; members
    with no evaluation yet sort last; ties (including "nobody evaluated yet")
    break on ``opportunity.id`` ascending, so the result never depends on
    input order.
    """
    def sort_key(m: FamilyMember) -> tuple[int, float, str]:
        has_no_score = m.fit_score is None
        score_for_sort = -(m.fit_score if m.fit_score is not None else 0.0)
        return (1 if has_no_score else 0, score_for_sort, m.opportunity.id)

    return sorted(members, key=sort_key)[0]


def cluster_members(members: Iterable[FamilyMember]) -> tuple[Family, ...]:
    """Group members into deterministic families.

    Output is sorted by ``family_key`` (and, within a family, member ids are
    sorted ascending), so the result is fully independent of input iteration
    order. Never mutates any ``FamilyMember``/``Opportunity`` -- no member's
    ``decision`` or ``fit_score`` is read destructively or written at all.
    """
    groups: dict[str, list[FamilyMember]] = {}
    for member in members:
        key = family_key(member.opportunity)
        groups.setdefault(key, []).append(member)

    families: list[Family] = []
    for key in sorted(groups.keys()):
        group = sorted(groups[key], key=lambda m: m.opportunity.id)
        best = _select_best(group)
        decisions = {m.decision for m in group if m.decision is not None}
        locations = tuple(sorted({
            m.opportunity.location_raw for m in group if m.opportunity.location_raw
        }))
        families.append(Family(
            family_key=key,
            employer=group[0].opportunity.organization,
            normalized_title=normalized_title_key(group[0].opportunity.title),
            member_ids=tuple(m.opportunity.id for m in group),
            best_member_id=best.opportunity.id,
            best_fit_score=best.fit_score,
            best_decision=best.decision,
            locations=locations,
            member_count=len(group),
            decisions_differ=len(decisions) > 1,
        ))
    return tuple(families)


def cluster_opportunities(opportunities: Iterable[Opportunity]) -> tuple[Family, ...]:
    """Convenience wrapper over :func:`cluster_members` for callers that have
    plain ``Opportunity`` objects with no evaluation data (every member's
    ``fit_score``/``decision`` will be ``None``)."""
    return cluster_members(FamilyMember(opportunity=opp) for opp in opportunities)


def check_family_invariants(
    members: Iterable[FamilyMember],
) -> tuple[int, int, int]:
    """Whole-corpus invariant check (A2.4), over the *whole* input, not a
    sample: zero families spanning two different employers, zero spanning
    two different normalized titles.

    Recomputes families from ``members`` via :func:`cluster_members`, then
    independently re-derives, for every family, the *set* of distinct raw
    ``organization`` strings and the *set* of distinct
    :func:`normalized_title_key` results across that family's own members
    (looked up from the materialized input, not trusted from the ``Family``
    object's single recorded ``employer``/``normalized_title`` fields) --
    so this is a real check over data, not a tautology about
    ``cluster_members``'s internal grouping key.

    Returns ``(family_count, cross_employer_violations,
    cross_title_violations)``.
    """
    materialized = list(members)
    families = cluster_members(materialized)
    by_id: dict[str, FamilyMember] = {m.opportunity.id: m for m in materialized}

    cross_employer = 0
    cross_title = 0
    for fam in families:
        employers = {by_id[mid].opportunity.organization for mid in fam.member_ids}
        titles = {normalized_title_key(by_id[mid].opportunity.title) for mid in fam.member_ids}
        if len(employers) > 1:
            cross_employer += 1
        if len(titles) > 1:
            cross_title += 1
    return len(families), cross_employer, cross_title
