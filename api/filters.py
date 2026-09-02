"""D3 (BRIEF-FR-005) founder-controlled filters -- the matching engine that
decides whether a row is hidden, ranked, or merely labelled.

Placement note (why this lives in `api/`, not `matching/`): every signal a
filter reads here is already materialised API-layer data -- persisted
`evaluation_detail_json` / `dimension_scores_json` columns
(`api/serialization.py`), `OpportunityRecord` columns, `FieldProvenanceRecord`
rows, and the loaded truth pack's `TruthGraph` (already exposed to
`api/routes_api.py` via `request.app.state.loaded_truth_pack`). No filter here
computes a new hard constraint or a new scoring rule -- `geo_eligibility` and
`work_mode_onsite` read the qualifier's *already-persisted* verdict,
`premium_fulltime_onsite` reads D2's *already-persisted* `compensation_fit`
gap text, and the rest read opportunity/truth-pack data verbatim. Keeping
this in `api/` also keeps `truth/test_predicates.py`'s glob of `matching/*.py`
(which enforces the predicate-literal registry contract) completely
unaffected -- this module never adds a file there.

The invariant every matcher below must honour (contract section 2 / brief
Appendix rule 2): **a filter never changes `decision` or `fit_score`**. Every
matcher here is a pure, read-only predicate over already-computed data; the
demotion machinery (`FilterOutcome.rank_penalty`) is consumed only as a sort
key by `api/routes_api.py`, never written back into the score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from storage.models import FieldProvenanceRecord, OpportunityRecord
from truth import predicates
from truth.graph import TruthGraph
from truth.models import CapabilityProfile, VerificationStatus

from .serialization import unpack_dimension_scores, unpack_evaluation_detail

FILTER_MODES: tuple[str, ...] = ("hide", "rank_only", "label_only")


def to_naive_utc(value: datetime) -> datetime:
    """Convert an already-UTC-or-naive `datetime` to the naive-but-UTC shape
    every `DateTime` column in this codebase stores (see the timezone hazard
    note in `storage/models.py::FounderFilterSettingRecord` and
    `matching/evaluate_persist.py::_to_naive_utc`, which this mirrors): strip
    tzinfo *before* the value reaches psycopg2 so nothing is left for
    PostgreSQL's session `timezone` GUC to silently convert."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# ---------------------------------------------------------------------------
# Per-opportunity context: every already-persisted signal a matcher may read,
# gathered once per opportunity so all ten filters share a single query pass.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpportunityFilterContext:
    opp: OpportunityRecord
    decision: str | None
    fit_score: float | None
    reasons: list[dict[str, Any]]
    evaluation_detail: dict[str, Any]
    dimension_scores: list[dict[str, Any]]
    compensation_min: float | None
    compensation_max: float | None
    compensation_currency: str | None
    truth_graph: TruthGraph | None


@dataclass(frozen=True, slots=True)
class FilterOutcome:
    hidden_by: list[str] = field(default_factory=list)
    flagged_by: list[str] = field(default_factory=list)
    rank_penalty: int = 0


@dataclass(frozen=True, slots=True)
class FilterSettingsRow:
    enabled: bool
    mode: str
    params: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FilterDefinition:
    filter_id: str
    default_enabled: bool
    default_mode: str
    default_params: dict[str, Any]
    description: str
    matcher: Callable[[OpportunityFilterContext, dict[str, Any]], bool]


# ---------------------------------------------------------------------------
# Matchers. Each returns True when the opportunity is one this filter names
# as its target -- what happens next (hidden / demoted / labelled / nothing)
# is decided entirely by the filter's current `enabled`/`mode`, never here.
# ---------------------------------------------------------------------------


def _hard_constraint_passed(ctx: OpportunityFilterContext, constraint_name: str) -> tuple[bool, bool | None]:
    """(found, passed) for a named hard constraint read out of this
    opportunity's already-persisted `evaluation_detail_json["hard_constraints"]`
    -- never recomputed by re-running `matching/qualification.py`. `found` is
    False when the constraint was never evaluated for this opportunity (e.g.
    a remote posting has no `work_mode_onsite` entry at all), which must not
    be conflated with an evaluated-and-uncertain result."""
    for entry in ctx.evaluation_detail.get("hard_constraints", []):
        if entry.get("constraint_name") == constraint_name:
            return True, entry.get("passed")
    return False, None


def _geo_eligibility_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    found, passed = _hard_constraint_passed(ctx, "geographic_eligibility")
    return found and passed is not True


def _work_mode_onsite_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    found, passed = _hard_constraint_passed(ctx, "work_mode_onsite")
    return found and passed is not True


def _red_lines_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    if ctx.truth_graph is None:
        return False
    red_lines, _never_claims = ctx.truth_graph.rules()
    if not red_lines:
        return False
    text = f"{ctx.opp.title}\n{ctx.opp.description}\n{ctx.opp.organization}"
    for rule in red_lines:
        try:
            if re.search(rule.pattern, text, flags=re.IGNORECASE):
                return True
        except re.error:
            # An invalid pattern is a truth-pack authoring defect surfaced
            # elsewhere (truth/validator.py raises on it when validating a
            # generated claim); a filter scan must not crash the feed over it.
            continue
    return False


def _excluded_industries(truth_graph: TruthGraph) -> tuple[str, ...]:
    industries: list[str] = []
    for profile in truth_graph.profiles.values():
        if isinstance(profile, CapabilityProfile):
            industries.extend(profile.excluded_industries)
    return tuple(industries)


def _excluded_industries_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    if ctx.truth_graph is None:
        return False
    excluded = _excluded_industries(ctx.truth_graph)
    if not excluded:
        return False
    haystack = f"{ctx.opp.title} {ctx.opp.organization} {ctx.opp.description}".casefold()
    return any(industry.casefold() in haystack for industry in excluded if industry.strip())


_KNOWN_TRACK_TOKENS = {"employment", "procurement"}


def _founder_track_preference(truth_graph: TruthGraph | None) -> str | None:
    """The founder's declared first-choice track, from the `preference.track`
    assertion (e.g. `"employment"` or an ordered `"employment,procurement"` --
    only the first token is a preference order). Returns None (no opinion) if
    unasserted, unverified, or not one of the two known `Track` values --
    never guessed."""
    if truth_graph is None:
        return None
    candidates = sorted(
        (
            a
            for a in truth_graph.assertions.values()
            if a.predicate == predicates.PREFERENCE_TRACK and a.verification_status == VerificationStatus.VERIFIED
        ),
        key=lambda a: a.id,
    )
    if not candidates:
        return None
    first_token = str(candidates[0].value).split(",")[0].strip().casefold()
    return first_token if first_token in _KNOWN_TRACK_TOKENS else None


def _track_preference_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    preferred = _founder_track_preference(ctx.truth_graph)
    if preferred is None:
        return False
    return ctx.opp.track.casefold() != preferred


def _founder_target_roles(truth_graph: TruthGraph | None) -> tuple[str, ...]:
    if truth_graph is None:
        return ()
    return tuple(
        str(a.value).strip()
        for a in truth_graph.assertions.values()
        if a.predicate == predicates.CAREER_TARGET_ROLE
        and a.verification_status == VerificationStatus.VERIFIED
        and str(a.value).strip()
    )


def _target_roles_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    targets = _founder_target_roles(ctx.truth_graph)
    if not targets:
        return False
    title_cf = ctx.opp.title.casefold()
    return not any(target.casefold() in title_cf for target in targets)


def _premium_fulltime_onsite_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    """Surfaces D2's already-computed premium full-time/on-site ranking
    signal (`matching/scorer.py`'s `compensation_fit` dimension) rather than
    recomputing the currency-threshold comparison itself: that rule already
    appends a gap note containing "premium" only when it fires (see
    `matching/test_scorer.py::TestPremiumFullTimeOnsiteRule`), so reading that
    gap text back is a genuine read of the persisted signal, not a guess."""
    for dim in ctx.dimension_scores:
        if dim.get("dimension_name") == "compensation_fit":
            gaps = dim.get("gaps") or []
            return any("premium" in str(gap).casefold() for gap in gaps)
    return False


def _stale_postings_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    return bool(ctx.opp.is_stale)


def _min_fit_score_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    threshold = params.get("min_score")
    if threshold is None or ctx.fit_score is None:
        return False
    return ctx.fit_score < float(threshold)


def _compensation_floor_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    floor = params.get("floor")
    if floor is None:
        return False
    amount = ctx.compensation_max if ctx.compensation_max is not None else ctx.compensation_min
    if amount is None:
        return False
    required_currency = params.get("currency")
    if required_currency is not None:
        if not ctx.compensation_currency:
            return False
        if ctx.compensation_currency.strip().casefold() != str(required_currency).strip().casefold():
            return False
    return amount < float(floor)


# ---------------------------------------------------------------------------
# The registry. Order matches contract section 3's table exactly -- that
# order is also the deterministic order `hidden_by`/`flagged_by` entries
# appear in for a given opportunity.
# ---------------------------------------------------------------------------

FILTER_DEFINITIONS: tuple[FilterDefinition, ...] = (
    FilterDefinition(
        filter_id="geo_eligibility",
        default_enabled=True,
        default_mode="label_only",
        default_params={},
        description=(
            "Opportunities whose geographic eligibility hard constraint did not pass "
            "verification (failed, or unresolved/uncertain)."
        ),
        matcher=_geo_eligibility_matches,
    ),
    FilterDefinition(
        filter_id="work_mode_onsite",
        default_enabled=True,
        default_mode="label_only",
        default_params={},
        description=(
            "Opportunities whose mandatory on-site attendance hard constraint did not pass "
            "verification (failed, or unresolved/uncertain)."
        ),
        matcher=_work_mode_onsite_matches,
    ),
    FilterDefinition(
        filter_id="red_lines",
        default_enabled=True,
        default_mode="hide",
        default_params={},
        description="Opportunities matching a red line in your truth pack.",
        matcher=_red_lines_matches,
    ),
    FilterDefinition(
        filter_id="excluded_industries",
        default_enabled=True,
        default_mode="hide",
        default_params={},
        description="Opportunities mentioning an industry your truth pack excludes.",
        matcher=_excluded_industries_matches,
    ),
    FilterDefinition(
        filter_id="track_preference",
        default_enabled=True,
        default_mode="rank_only",
        default_params={},
        description="Opportunities outside your declared track preference order.",
        matcher=_track_preference_matches,
    ),
    FilterDefinition(
        filter_id="target_roles",
        default_enabled=True,
        default_mode="rank_only",
        default_params={},
        description="Opportunities whose title does not mention your declared target role.",
        matcher=_target_roles_matches,
    ),
    FilterDefinition(
        filter_id="premium_fulltime_onsite",
        default_enabled=True,
        default_mode="rank_only",
        default_params={},
        description=(
            "Full-time, on-site opportunities below your declared full-time on-site "
            "compensation premium threshold."
        ),
        matcher=_premium_fulltime_onsite_matches,
    ),
    FilterDefinition(
        filter_id="stale_postings",
        default_enabled=True,
        default_mode="label_only",
        default_params={},
        description="Opportunities flagged stale (no longer reverifiable at the source).",
        matcher=_stale_postings_matches,
    ),
    FilterDefinition(
        filter_id="min_fit_score",
        default_enabled=False,
        default_mode="hide",
        default_params={"min_score": 0},
        description="Opportunities below a founder-set minimum fit score.",
        matcher=_min_fit_score_matches,
    ),
    FilterDefinition(
        filter_id="compensation_floor",
        default_enabled=False,
        default_mode="rank_only",
        default_params={"floor": 0, "currency": None},
        description="Opportunities below a founder-set compensation floor.",
        matcher=_compensation_floor_matches,
    ),
)

FILTER_DEFINITIONS_BY_ID: dict[str, FilterDefinition] = {fd.filter_id: fd for fd in FILTER_DEFINITIONS}


# ---------------------------------------------------------------------------
# Context construction and application.
# ---------------------------------------------------------------------------

_COMPENSATION_FIELD_NAMES = ("compensation.min_amount", "compensation.max_amount", "compensation.currency")


def _latest_evaluation_for_context(session: Session, opportunity_id: str):
    # Local import to avoid a circular import with api.routes_api (which
    # imports this module); routes_api's own `_latest_evaluation` does the
    # identical query, this is not new query logic.
    from storage.models import MatchEvaluationRecord

    return (
        session.query(MatchEvaluationRecord)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(MatchEvaluationRecord.evaluated_at.desc(), MatchEvaluationRecord.created_at.desc())
        .first()
    )


def build_filter_contexts(
    session: Session,
    truth_graph: TruthGraph | None,
    opportunities: list[OpportunityRecord],
) -> list[OpportunityFilterContext]:
    from .serialization import unpack_reasons

    contexts: list[OpportunityFilterContext] = []
    for opp in opportunities:
        evaluation = _latest_evaluation_for_context(session, opp.id)
        evaluation_detail = unpack_evaluation_detail(evaluation.evaluation_detail_json if evaluation else None)
        dimension_scores = unpack_dimension_scores(evaluation.dimension_scores_json if evaluation else None)
        reasons = unpack_reasons(evaluation.reasons_json if evaluation else None)

        comp_rows = (
            session.query(FieldProvenanceRecord)
            .filter(
                FieldProvenanceRecord.opportunity_id == opp.id,
                FieldProvenanceRecord.field_name.in_(_COMPENSATION_FIELD_NAMES),
            )
            .all()
        )
        comp_by_field = {row.field_name: row.normalized_value for row in comp_rows}

        def _to_float(raw: str | None) -> float | None:
            if raw is None:
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

        contexts.append(
            OpportunityFilterContext(
                opp=opp,
                decision=evaluation.qualification_decision if evaluation else None,
                fit_score=evaluation.fit_score if evaluation else None,
                reasons=reasons,
                evaluation_detail=evaluation_detail,
                dimension_scores=dimension_scores,
                compensation_min=_to_float(comp_by_field.get("compensation.min_amount")),
                compensation_max=_to_float(comp_by_field.get("compensation.max_amount")),
                compensation_currency=comp_by_field.get("compensation.currency"),
                truth_graph=truth_graph,
            )
        )
    return contexts


def apply_filters(ctx: OpportunityFilterContext, settings: dict[str, FilterSettingsRow]) -> FilterOutcome:
    """Evaluate all ten filters for one opportunity against the founder's
    current settings. A disabled filter is not evaluated at all (contract
    section 4): it contributes to neither `hidden_by` nor `flagged_by`."""
    hidden_by: list[str] = []
    flagged_by: list[str] = []
    rank_penalty = 0

    for fd in FILTER_DEFINITIONS:
        row = settings.get(fd.filter_id)
        enabled = row.enabled if row is not None else fd.default_enabled
        if not enabled:
            continue
        mode = row.mode if row is not None else fd.default_mode
        params = row.params if row is not None else fd.default_params

        if not fd.matcher(ctx, params):
            continue

        if mode == "hide":
            hidden_by.append(fd.filter_id)
        elif mode == "rank_only":
            flagged_by.append(fd.filter_id)
            rank_penalty += 1
        elif mode == "label_only":
            flagged_by.append(fd.filter_id)

    return FilterOutcome(hidden_by=hidden_by, flagged_by=flagged_by, rank_penalty=rank_penalty)


def affected_count(fd: FilterDefinition, params: dict[str, Any], contexts: list[OpportunityFilterContext]) -> int:
    """The number of opportunities `fd` currently matches, computed
    regardless of `enabled` (contract section 5: `GET /api/filters`)."""
    return sum(1 for ctx in contexts if fd.matcher(ctx, params))
