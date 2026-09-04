"""C1 (BRIEF-FR-006) -- the generic facet engine, plus C4's hidden-reasons
audit and the B4-adjacent 10%-of-a-poll warning signal.

Governing instruction (verbatim in spirit from the founder, repeated here
because every design choice below answers to it): *"I can exclude something
close that isn't right for me; I can't get back something suitable that was
excluded before I saw it."* Nothing here hides a row by default. A facet only
narrows the feed when the founder has set an explicit include or exclude
value for it (`FounderFacetRecord.values_json`, migration 0004); the default
for every facet, on a fresh database, is an absent row -- equivalent to
`include=[] exclude=[]` -- which `facet_hides` below treats as "does not
narrow anything at all".

This module deliberately does not replace `api/filters.py`'s ten
founder-controlled policy filters (Master's decision, `orders/C1-facets.md`
section "Master's decisions"): `founder_filter_settings` and its
hide/rank_only/label_only vocabulary is untouched. A facet only ever
contributes an entry to an opportunity's `hidden_by` list; it never writes a
`decision` or a `fit_score` (contract invariant, asserted by
`api/test_api.py::FacetsTest.test_no_re_judgement_under_any_facet_exclusion`).

Every facet reads data api/filters.py's `OpportunityFilterContext` already
carries (opp columns, `decision`, `fit_score`, persisted compensation) --
adding a facet is a declaration in `FACET_DEFINITIONS`, never a new branch in
a query builder (order requirement).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .filters import (
    FILTER_DEFINITIONS,
    OpportunityFilterContext,
    affected_count as filter_affected_count,
    apply_filters,
    matched_excluded_industry,
    matched_red_line_rule,
)

# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FacetDefinition:
    facet_id: str
    value_type: str  # "enum" | "string" | "boolean" | "range" | "date-window"
    description: str
    #: Reads whatever this facet buckets an opportunity into. `now` is
    #: injected (not read from `datetime.now()` inside the lambda) so
    #: date-window/range buckets are deterministic under test.
    value_of: Callable[[OpportunityFilterContext, datetime], str]
    available: bool = True
    #: Set only when `available` is False -- the reason this facet has no
    #: data source yet (mirrors `api/filters.py`'s `unavailable_reason`
    #: council pattern: never silently filter on a signal that does not
    #: exist).
    unavailable_reason: str | None = None


def _bucket_or_unspecified(raw: Any) -> str:
    if raw is None:
        return "unspecified"
    text = str(raw).strip()
    return text if text else "unspecified"


def _posted_within_bucket(ctx: OpportunityFilterContext, now: datetime) -> str:
    raw = ctx.opp.posted_date
    if not raw:
        return "unspecified"
    try:
        posted = datetime.fromisoformat(str(raw)[:10])
    except ValueError:
        return "unspecified"
    posted = posted.replace(tzinfo=timezone.utc)
    age_days = (now - posted).total_seconds() / 86400.0
    if age_days < 1:
        return "last_24h"
    if age_days < 7:
        return "last_7d"
    if age_days < 30:
        return "last_30d"
    if age_days < 90:
        return "last_90d"
    return "older"


def _fit_score_bucket(ctx: OpportunityFilterContext, now: datetime) -> str:
    score = ctx.fit_score
    if score is None:
        return "unscored"
    if score < 25:
        return "0-25"
    if score < 50:
        return "25-50"
    if score < 75:
        return "50-75"
    return "75-100"


def _compensation_stated_bucket(ctx: OpportunityFilterContext, now: datetime) -> str:
    return "yes" if (ctx.compensation_min is not None or ctx.compensation_max is not None) else "no"


_LANGUAGE_UNAVAILABLE_REASON = (
    "No language is ever persisted for an opportunity: `opportunity/models.py`'s "
    "`Opportunity.languages` tuple exists on the in-memory model, but nothing in "
    "`opportunity/persistence.py`, `storage/models.py::OpportunityRecord`, or "
    "`field_provenances` writes it to storage. This facet is declared (the brief "
    "requires it in the list) but has no data source to bucket by until a future "
    "brief persists it -- exactly the council `availability` pattern "
    "`api/filters.py::stale_postings` already established for a no-op filter."
)


FACET_DEFINITIONS: tuple[FacetDefinition, ...] = (
    FacetDefinition("work_mode", "enum", "How the role is performed (remote/hybrid/onsite/unspecified).",
                     lambda ctx, now: _bucket_or_unspecified(ctx.opp.work_mode)),
    FacetDefinition("location_country", "enum", "Opportunity's location country (ISO-2).",
                     lambda ctx, now: _bucket_or_unspecified(ctx.opp.location_country)),
    FacetDefinition("location_city", "string", "Opportunity's location city.",
                     lambda ctx, now: _bucket_or_unspecified(ctx.opp.location_city)),
    FacetDefinition("remote_scope", "enum", "Geographic scope a remote posting is open to.",
                     lambda ctx, now: _bucket_or_unspecified(ctx.opp.remote_scope)),
    FacetDefinition("employment_type", "enum", "Full-time / contract / etc.",
                     lambda ctx, now: _bucket_or_unspecified(ctx.opp.employment_type)),
    FacetDefinition("seniority_level", "enum", "Inferred seniority level.",
                     lambda ctx, now: _bucket_or_unspecified(ctx.opp.seniority_level)),
    FacetDefinition("title_family", "enum", "matching/title_family.py's assigned title family.",
                     lambda ctx, now: _bucket_or_unspecified(ctx.opp.title_family)),
    FacetDefinition("track", "enum", "Employment vs. procurement track.",
                     lambda ctx, now: _bucket_or_unspecified(ctx.opp.track)),
    FacetDefinition("source_id", "enum", "Source adapter this opportunity came from.",
                     lambda ctx, now: _bucket_or_unspecified(ctx.opp.source_id)),
    FacetDefinition("employer", "string", "Hiring organization.",
                     lambda ctx, now: _bucket_or_unspecified(ctx.opp.organization)),
    FacetDefinition("posted_within", "date-window", "How recently the opportunity was posted.",
                     _posted_within_bucket),
    FacetDefinition("compensation_stated", "boolean", "Whether any compensation amount was extracted.",
                     _compensation_stated_bucket),
    FacetDefinition("decision", "enum", "The latest qualification decision.",
                     lambda ctx, now: _bucket_or_unspecified(ctx.decision)),
    FacetDefinition("fit_score", "range", "Fit score bucketed in quartiles.",
                     _fit_score_bucket),
    FacetDefinition(
        "language", "enum", "Posting language.",
        lambda ctx, now: "unspecified",
        available=False,
        unavailable_reason=_LANGUAGE_UNAVAILABLE_REASON,
    ),
)
FACET_DEFINITIONS_BY_ID: dict[str, FacetDefinition] = {fd.facet_id: fd for fd in FACET_DEFINITIONS}


# ---------------------------------------------------------------------------
# Settings, application, counts
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FacetSettingsRow:
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FacetOutcome:
    hidden_by: list[str] = field(default_factory=list)


def facet_value(fd: FacetDefinition, ctx: OpportunityFilterContext, now: datetime) -> str:
    return fd.value_of(ctx, now)


def facet_hides(fd: FacetDefinition, ctx: OpportunityFilterContext, row: FacetSettingsRow | None, now: datetime) -> bool:
    """True when `fd`'s current founder-set include/exclude selection hides
    `ctx`. A facet with no row (or an empty include/exclude row -- the "off"
    state, and every facet's default) never hides anything, regardless of
    `available`."""
    if row is None or not fd.available:
        return False
    if not row.include and not row.exclude:
        return False
    value = facet_value(fd, ctx, now)
    if row.include and value not in row.include:
        return True
    if row.exclude and value in row.exclude:
        return True
    return False


def apply_facets(
    ctx: OpportunityFilterContext,
    facet_settings: dict[str, FacetSettingsRow],
    now: datetime | None = None,
) -> FacetOutcome:
    now = now or datetime.now(timezone.utc)
    hidden_by: list[str] = []
    for fd in FACET_DEFINITIONS:
        if not fd.available:
            continue
        row = facet_settings.get(fd.facet_id)
        if facet_hides(fd, ctx, row, now):
            hidden_by.append(fd.facet_id)
    return FacetOutcome(hidden_by=hidden_by)


def facet_payload(
    contexts: list[OpportunityFilterContext],
    facet_settings: dict[str, FacetSettingsRow],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """`GET /api/facets` body. `contexts` is expected to already exclude rows
    hidden by a hide-mode policy filter (`api/routes_api.py::list_facets`
    mirrors the same base set `GET /api/opportunities` uses without
    `include_hidden`) -- a facet only ever narrows what the policy filters
    already show. Counts and `excluded_count` are computed independent of any
    *other* currently-active facet (documented assumption, see
    `orders/C1-facets.md` return notes): every value's count is over the full
    policy-visible set, and `excluded_count` is how many of those rows this
    facet's own current selection hides -- exactly the number the UI needs
    for "Show N excluded by <facet>"."""
    now = now or datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    for fd in FACET_DEFINITIONS:
        if not fd.available:
            results.append(
                {
                    "facet_id": fd.facet_id,
                    "value_type": fd.value_type,
                    "description": fd.description,
                    "available": False,
                    "unavailable_reason": fd.unavailable_reason,
                    "values": [],
                    "excluded_count": 0,
                    "include": [],
                    "exclude": [],
                }
            )
            continue
        row = facet_settings.get(fd.facet_id)
        include = list(row.include) if row else []
        exclude = list(row.exclude) if row else []
        counts: dict[str, int] = {}
        excluded = 0
        for ctx in contexts:
            value = facet_value(fd, ctx, now)
            counts[value] = counts.get(value, 0) + 1
            if facet_hides(fd, ctx, row, now):
                excluded += 1
        values = [
            {
                "value": value,
                "count": count,
                "state": "include" if value in include else ("exclude" if value in exclude else "off"),
            }
            for value, count in sorted(counts.items())
        ]
        results.append(
            {
                "facet_id": fd.facet_id,
                "value_type": fd.value_type,
                "description": fd.description,
                "available": True,
                "unavailable_reason": None,
                "values": values,
                "excluded_count": excluded,
                "include": include,
                "exclude": exclude,
            }
        )
    return results


# ---------------------------------------------------------------------------
# C4: hidden-reasons audit
# ---------------------------------------------------------------------------


def hidden_reasons_for_context(
    ctx: OpportunityFilterContext,
    hidden_by_filters: list[str],
    hidden_by_facets: list[str],
    truth_graph: Any,
) -> list[str]:
    """The specific, named reason(s) `ctx` is currently hidden -- one entry
    per mechanism that hid it (a row hidden by two independent mechanisms at
    once contributes to both reasons' counts). `red_lines` and
    `excluded_industries` resolve to the *specific* matched rule/industry
    (`red line: gambling`, `excluded industry: fraud`) via
    `api/filters.py`'s audit hooks, per the brief's own examples; any other
    hide-mode policy filter names itself (`filter: min_fit_score`); a facet
    names itself (`facet: location_country`)."""
    reasons: list[str] = []
    for filter_id in hidden_by_filters:
        if filter_id == "red_lines":
            rule = matched_red_line_rule(ctx, truth_graph)
            reasons.append(f"red line: {rule.reason}" if rule is not None else "red line: unspecified")
        elif filter_id == "excluded_industries":
            industry = matched_excluded_industry(ctx, truth_graph)
            reasons.append(f"excluded industry: {industry}" if industry else "excluded industry: unspecified")
        else:
            reasons.append(f"filter: {filter_id}")
    for facet_id in hidden_by_facets:
        reasons.append(f"facet: {facet_id}")
    return reasons


def hidden_reasons_audit(
    contexts: list[OpportunityFilterContext],
    filter_settings: dict[str, Any],
    facet_settings: dict[str, FacetSettingsRow],
    truth_graph: Any,
    now: datetime | None = None,
) -> dict[str, int]:
    """reason -> count of currently-hidden rows over the full corpus (C4:
    "the dashboard's HIDDEN number links to a table")."""
    now = now or datetime.now(timezone.utc)
    counts: dict[str, int] = {}
    for ctx in contexts:
        filter_outcome = apply_filters(ctx, filter_settings)
        facet_outcome = apply_facets(ctx, facet_settings, now=now)
        for reason in hidden_reasons_for_context(ctx, filter_outcome.hidden_by, facet_outcome.hidden_by, truth_graph):
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def unhide_by_reason(session, reason: str, now: datetime) -> bool:
    """The one-click "unhide all by this reason" action. The schema (frozen
    for this order -- `0004` has no per-rule override column) only offers two
    levers: clear a facet's include/exclude back to off (`facet: <id>`
    reasons), or disable the one policy filter responsible (`red_lines`,
    `excluded_industries`, or any other hide-mode filter). A `red line: X` or
    `excluded industry: X` reason therefore disables the whole `red_lines` /
    `excluded_industries` filter rather than un-hiding only rule `X` --
    documented limitation, named in this order's return notes; the coarser
    action is still genuinely one click and still honours "an excluded row is
    always one click away". Returns False for an unrecognised reason string
    (nothing to unhide), True otherwise."""
    from storage.models import FounderFacetRecord, FounderFilterSettingRecord

    if reason.startswith("facet: "):
        facet_id = reason[len("facet: "):]
        if facet_id not in FACET_DEFINITIONS_BY_ID:
            return False
        row = session.query(FounderFacetRecord).filter_by(facet_id=facet_id).first()
        if row is None:
            row = FounderFacetRecord(facet_id=facet_id, mode="off", values_json=json.dumps({"include": [], "exclude": []}), updated_at=now)
            session.add(row)
        else:
            row.mode = "off"
            row.values_json = json.dumps({"include": [], "exclude": []})
            row.updated_at = now
        session.commit()
        return True

    if reason.startswith("red line: "):
        filter_id = "red_lines"
    elif reason.startswith("excluded industry: "):
        filter_id = "excluded_industries"
    elif reason.startswith("filter: "):
        filter_id = reason[len("filter: "):]
    else:
        return False

    from .filters import FILTER_DEFINITIONS_BY_ID

    fd = FILTER_DEFINITIONS_BY_ID.get(filter_id)
    if fd is None:
        return False
    row = session.query(FounderFilterSettingRecord).filter_by(filter_id=filter_id).first()
    if row is None:
        row = FounderFilterSettingRecord(
            filter_id=filter_id, enabled=False, mode=fd.default_mode,
            params_json=json.dumps(dict(fd.default_params)), updated_at=now,
        )
        session.add(row)
    else:
        row.enabled = False
        row.updated_at = now
    session.commit()
    return True


# ---------------------------------------------------------------------------
# C4: the 10%-of-a-poll warning
# ---------------------------------------------------------------------------


def poll_hide_fraction_warnings(
    poll_inserted: int,
    new_contexts: list[OpportunityFilterContext],
    filter_settings: dict[str, Any],
    facet_settings: dict[str, FacetSettingsRow],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """One warning entry per hide-mode policy filter or active facet that
    hides more than 10% of `new_contexts` -- which must be exactly the
    contexts for the opportunities a single poll run inserted, and
    `poll_inserted` that poll's own new-row count
    (`SourcePollRunRecord.inserted`). Strictly greater than 10%, never
    inclusive: a poll at exactly 10% does not warn (brief: "hiding more than
    10%")."""
    now = now or datetime.now(timezone.utc)
    warnings: list[dict[str, Any]] = []
    if poll_inserted <= 0:
        return warnings

    for fd in FILTER_DEFINITIONS:
        row = filter_settings.get(fd.filter_id)
        enabled = row.enabled if row is not None else fd.default_enabled
        mode = row.mode if row is not None else fd.default_mode
        if not enabled or mode != "hide":
            continue
        params = row.params if row is not None else fd.default_params
        count = filter_affected_count(fd, params, new_contexts)
        fraction = count / poll_inserted
        if fraction > 0.10:
            warnings.append({"cause": f"filter: {fd.filter_id}", "hidden": count, "of": poll_inserted, "fraction": fraction})

    for facet_fd in FACET_DEFINITIONS:
        if not facet_fd.available:
            continue
        row = facet_settings.get(facet_fd.facet_id)
        if row is None or (not row.include and not row.exclude):
            continue
        count = sum(1 for ctx in new_contexts if facet_hides(facet_fd, ctx, row, now))
        fraction = count / poll_inserted
        if fraction > 0.10:
            warnings.append({"cause": f"facet: {facet_fd.facet_id}", "hidden": count, "of": poll_inserted, "fraction": fraction})

    return warnings
