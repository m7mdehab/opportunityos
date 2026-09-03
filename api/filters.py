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
signal tag, and the rest read opportunity/truth-pack data verbatim. Keeping
this in `api/` also keeps `truth/test_predicates.py`'s glob of `matching/*.py`
(which enforces the predicate-literal registry contract) completely
unaffected -- this module never adds a file there.

The invariant every matcher below must honour (contract section 2 / brief
Appendix rule 2): **a filter never changes `decision` or `fit_score`**. Every
matcher here is a pure, read-only predicate over already-computed data; the
demotion machinery (`FilterOutcome.rank_penalty`) is consumed only as a sort
key by `api/routes_api.py`, never written back into the score.

Council repair round (post-merge review of D3+D5) fixed six defects here:
defect 1 (malformed params bricking the feed -- see `validate_filter_params`
and the `_safe_float` guards in the matchers), defects 2/3 (silent no-op
filters -- see `FilterDefinition.availability` / `unavailable_reason`),
defect 4 (`target_roles` string-order accident -- see the token-set matcher),
defect 5 (`excluded_industries` substring over-match -- see the word-boundary
regex), and defect 6 (`premium_fulltime_onsite` keying off scorer prose --
see the `signal_tags` read).
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


def _safe_float(value: Any) -> float | None:
    """Best-effort numeric coercion that never raises.

    Council defect 1: `validate_filter_params` (below) is the primary
    defence -- it rejects a non-numeric `min_score`/`floor` at PUT time,
    before anything is committed. This is the *second*, independent line of
    defence for a row a database already holds a bad value in (e.g. one
    written by an older version of this code, or edited directly): a matcher
    must degrade to "does not match" rather than crash the entire feed with
    an unguarded `float(...)`.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


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


def _always_available(truth_graph: TruthGraph | None) -> str | None:
    return None


@dataclass(frozen=True, slots=True)
class FilterDefinition:
    filter_id: str
    default_enabled: bool
    default_mode: str
    default_params: dict[str, Any]
    description: str
    matcher: Callable[[OpportunityFilterContext, dict[str, Any]], bool]
    #: Council defects 2/3. Returns a human-readable reason the filter cannot
    #: currently match anything meaningful (missing pack data, or a pipeline
    #: gap upstream), or None when the filter has a real data source to work
    #: from. `GET /api/filters` exposes this so the drawer can distinguish
    #: "0 matches because nothing qualifies" from "0 matches because there is
    #: no signal to evaluate at all" -- the founder's stated requirement is
    #: that nothing filters silently, and a filter with no data source is
    #: exactly that if left unmarked.
    availability: Callable[[TruthGraph | None], str | None] = _always_available


# ---------------------------------------------------------------------------
# Params validation (council defect 1). Every parametrised filter's `params`
# gets a small explicit schema; unknown keys and out-of-range/wrong-typed
# values are rejected with a ParamValidationError BEFORE anything is
# persisted, so `PUT /api/filters/{id}` can never write a value the matchers
# would later choke on. `api/routes_api.py::update_filter` calls
# `validate_filter_params` before `session.commit()`.
# ---------------------------------------------------------------------------


class ParamValidationError(ValueError):
    """Raised by `validate_filter_params` for a malformed `params` payload.
    The message is written to be safe to return directly in a 422 body."""


def _validate_no_params(filter_id: str, params: dict[str, Any]) -> dict[str, Any]:
    if params:
        raise ParamValidationError(f"{filter_id!r} does not accept params; got keys {sorted(params)}")
    return {}


def _validate_number(filter_id: str, key: str, value: Any, *, minimum: float, maximum: float | None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParamValidationError(f"{filter_id!r}.{key} must be a number, got {value!r}")
    numeric = float(value)
    if numeric < minimum or (maximum is not None and numeric > maximum):
        bound = f">= {minimum}" if maximum is None else f"between {minimum} and {maximum}"
        raise ParamValidationError(f"{filter_id!r}.{key} must be {bound}, got {numeric!r}")
    return numeric


def _validate_min_fit_score_params(filter_id: str, params: dict[str, Any]) -> dict[str, Any]:
    allowed = {"min_score"}
    unknown = set(params) - allowed
    if unknown:
        raise ParamValidationError(f"{filter_id!r} does not accept params {sorted(unknown)}")
    result: dict[str, Any] = {}
    if "min_score" in params:
        result["min_score"] = _validate_number(filter_id, "min_score", params["min_score"], minimum=0.0, maximum=100.0)
    return result


def _validate_compensation_floor_params(filter_id: str, params: dict[str, Any]) -> dict[str, Any]:
    allowed = {"floor", "currency"}
    unknown = set(params) - allowed
    if unknown:
        raise ParamValidationError(f"{filter_id!r} does not accept params {sorted(unknown)}")
    result: dict[str, Any] = {}
    if "floor" in params:
        result["floor"] = _validate_number(filter_id, "floor", params["floor"], minimum=0.0, maximum=None)
    if "currency" in params:
        currency = params["currency"]
        if currency is not None and not isinstance(currency, str):
            raise ParamValidationError(f"{filter_id!r}.currency must be a string or null, got {currency!r}")
        result["currency"] = currency
    return result


_PARAM_VALIDATORS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "min_fit_score": _validate_min_fit_score_params,
    "compensation_floor": _validate_compensation_floor_params,
}


def validate_filter_params(filter_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validate (and coerce numerics in) a `params` payload for `filter_id`.

    Raises `ParamValidationError` on anything malformed; the caller is
    expected to turn that into a 422 *before* touching the database. Filters
    with no `_PARAM_VALIDATORS` entry take no params at all (`{}`).
    """
    validator = _PARAM_VALIDATORS.get(filter_id, _validate_no_params)
    return validator(filter_id, dict(params or {}))


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


def matched_red_line_rule(ctx: OpportunityFilterContext, truth_graph: TruthGraph | None):
    """C4 audit hook: the *specific* `RedLineRule` (not just the boolean
    `_red_lines_matches` result) that hid `ctx`, or `None` if none matched.
    `api/facets.py::hidden_reasons_for_context` uses this to name the actual
    rule in the hidden-reasons table (`"red line: <rule.reason>"`) instead of
    the generic filter id -- the brief's own example (`red line: gambling`)
    names the specific cause, not the filter."""
    if truth_graph is None:
        return None
    red_lines, _never_claims = truth_graph.rules()
    if not red_lines:
        return None
    text = f"{ctx.opp.title}\n{ctx.opp.description}\n{ctx.opp.organization}"
    for rule in red_lines:
        try:
            if re.search(rule.pattern, text, flags=re.IGNORECASE):
                return rule
        except re.error:
            continue
    return None


def matched_excluded_industry(ctx: OpportunityFilterContext, truth_graph: TruthGraph | None) -> str | None:
    """C4 audit hook: the specific excluded-industry string that hid `ctx`
    (word-boundary matched, same as `_excluded_industries_matches`), or
    `None` if none matched."""
    if truth_graph is None:
        return None
    excluded = _excluded_industries(truth_graph)
    if not excluded:
        return None
    haystack = f"{ctx.opp.title} {ctx.opp.organization} {ctx.opp.description}"
    for industry in excluded:
        name = industry.strip()
        if not name:
            continue
        try:
            if re.search(rf"\b{re.escape(name)}\b", haystack, flags=re.IGNORECASE):
                return name
        except re.error:
            continue
    return None


def _excluded_industries(truth_graph: TruthGraph) -> tuple[str, ...]:
    industries: list[str] = []
    for profile in truth_graph.profiles.values():
        if isinstance(profile, CapabilityProfile):
            industries.extend(profile.excluded_industries)
    return tuple(industries)


def _excluded_industries_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    """Council defect 5: a plain `in` substring check hid postings on
    accidental substring collisions (e.g. an excluded "Finance" matching
    "Financial", or an excluded short word matching inside an unrelated
    longer one). Word-boundary regex matching fixes that: an excluded
    industry only matches whole words in the opportunity text."""
    if ctx.truth_graph is None:
        return False
    excluded = _excluded_industries(ctx.truth_graph)
    if not excluded:
        return False
    haystack = f"{ctx.opp.title} {ctx.opp.organization} {ctx.opp.description}"
    for industry in excluded:
        name = industry.strip()
        if not name:
            continue
        try:
            if re.search(rf"\b{re.escape(name)}\b", haystack, flags=re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


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


def _track_preference_availability(truth_graph: TruthGraph | None) -> str | None:
    if _founder_track_preference(truth_graph) is None:
        return (
            "Your truth pack has no verified preference.track assertion, so this "
            "filter has nothing to compare an opportunity's track against."
        )
    return None


# Council defect 4: job-title words this filter ignores on both sides of the
# comparison (the founder's declared target role AND the opportunity title)
# before comparing. Seniority/level qualifiers carry no bearing on *what* the
# role is -- a target of "Backend Engineer" must align with "Senior Backend
# Engineer" and with a posting that omits the word entirely; connective/filler
# words carry no role identity either. This is a job-title-specific list,
# deliberately separate from `truth/connective_terms.txt` (ADR-0014's claim-
# validation stop-list governs a different, narrower concern -- see that
# file's own docstring -- and must not be repurposed here).
_TITLE_STOPWORDS: frozenset[str] = frozenset({
    "senior", "sr", "junior", "jr", "lead", "staff", "principal", "associate",
    "entry", "level", "intern", "internship", "trainee", "graduate",
    "i", "ii", "iii", "iv", "v",
    "and", "the", "of", "for", "a", "an", "in", "at", "to", "on", "with",
})

_TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _significant_title_tokens(text: str) -> frozenset[str]:
    return frozenset(
        token for token in _TITLE_TOKEN_RE.findall(text.casefold()) if token not in _TITLE_STOPWORDS
    )


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
    """Council defect 4: matching used to be a raw phrase substring check
    (`target.casefold() in title_cf`), which is sensitive to word order and
    punctuation -- "Senior Software Engineer, Backend" does not contain the
    literal substring "backend engineer" even though it plainly *is* a
    Backend Engineer posting, so it was wrongly flagged as misaligned and
    demoted below far worse matches. This compares token *sets* instead
    (order-independent, seniority/connective words ignored on both sides):
    the opportunity aligns with a declared target role if every significant
    token of that role appears somewhere in the title."""
    targets = _founder_target_roles(ctx.truth_graph)
    if not targets:
        return False
    title_tokens = _significant_title_tokens(ctx.opp.title)
    for target in targets:
        target_tokens = _significant_title_tokens(target)
        if target_tokens and target_tokens.issubset(title_tokens):
            return False  # aligned with at least one declared target role
    return True


def _target_roles_availability(truth_graph: TruthGraph | None) -> str | None:
    if not _founder_target_roles(truth_graph):
        return (
            "Your truth pack has no verified career.target_role assertion, so this "
            "filter has no declared role to compare opportunity titles against."
        )
    return None


def _founder_premium_threshold_configured(truth_graph: TruthGraph | None) -> bool:
    if truth_graph is None:
        return False
    return any(
        a.predicate == predicates.PREFERENCE_FULLTIME_ONSITE_PREMIUM_MONTHLY
        and a.verification_status == VerificationStatus.VERIFIED
        for a in truth_graph.assertions.values()
    )


def _premium_fulltime_onsite_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    """Council defect 6: this used to key off `"premium" in gap.casefold()`,
    a bare substring search on the scorer's free-text sentence -- a reword of
    that sentence would have silently disabled the filter with nothing to
    catch it. `matching/scorer.py` now emits a stable, code-owned
    `signal_tags` entry ("premium_shortfall") on the `compensation_fit`
    dimension only on the one branch that actually found a shortfall
    (`matching/models.py::MatchDimensionScore.signal_tags`,
    `matching/evaluate_persist.py::_dimension_scores_to_json`); this reads
    that tag verbatim, not prose."""
    for dim in ctx.dimension_scores:
        if dim.get("dimension_name") == "compensation_fit":
            tags = dim.get("signal_tags") or []
            return "premium_shortfall" in tags
    return False


def _premium_fulltime_onsite_availability(truth_graph: TruthGraph | None) -> str | None:
    if not _founder_premium_threshold_configured(truth_graph):
        return (
            "Your truth pack has no verified preference.fulltime_onsite_premium_monthly "
            "assertion, so this filter has no threshold to compare full-time on-site "
            "compensation against."
        )
    return None


def _stale_postings_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    return bool(ctx.opp.is_stale)


_STALE_POSTINGS_UNAVAILABLE_REASON = (
    "Staleness is never computed by the current pipeline: "
    "opportunity/persistence.py always writes is_stale=False on ingest, and "
    "opportunity/reverification.py's results are computed but not persisted "
    "by any worker. This filter cannot match anything until a future brief "
    "wires reverification results back into is_stale."
)


def _stale_postings_availability(truth_graph: TruthGraph | None) -> str | None:
    return _STALE_POSTINGS_UNAVAILABLE_REASON


def _min_fit_score_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    threshold = _safe_float(params.get("min_score"))
    if threshold is None or ctx.fit_score is None:
        return False
    return ctx.fit_score < threshold


def _compensation_floor_matches(ctx: OpportunityFilterContext, params: dict[str, Any]) -> bool:
    floor = _safe_float(params.get("floor"))
    if floor is None:
        return False
    amount = ctx.compensation_max if ctx.compensation_max is not None else ctx.compensation_min
    if amount is None:
        return False
    required_currency = params.get("currency")
    if required_currency is not None:
        if not isinstance(required_currency, str) or not ctx.compensation_currency:
            return False
        if ctx.compensation_currency.strip().casefold() != required_currency.strip().casefold():
            return False
    return amount < floor


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
        availability=_track_preference_availability,
    ),
    FilterDefinition(
        filter_id="target_roles",
        default_enabled=True,
        # B3 (BRIEF-FR-006), Overseer decision at FR-005 review §3.1: reverts
        # the council-defect-4 demotion to label_only (see the superseded
        # comment this replaces) back to rank_only now that matching/
        # title_family.py gives the target-role comparison a committed,
        # code-owned family taxonomy instead of a raw token-set heuristic.
        # This is a data change only -- no migration -- because
        # `apply_filters` (below) always falls back to `default_mode` for
        # any founder with no explicit `FounderFilterSettingRecord` row for
        # this filter, so updating this constant is itself the idempotent
        # settings-seed update: a founder with no saved override picks up
        # rank_only on the next read, and a founder who already saved an
        # explicit mode is untouched either way.
        default_mode="rank_only",
        default_params={},
        description="Opportunities whose title does not mention your declared target role.",
        matcher=_target_roles_matches,
        availability=_target_roles_availability,
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
        availability=_premium_fulltime_onsite_availability,
    ),
    FilterDefinition(
        filter_id="stale_postings",
        default_enabled=True,
        default_mode="label_only",
        default_params={},
        description="Opportunities flagged stale (no longer reverifiable at the source).",
        matcher=_stale_postings_matches,
        availability=_stale_postings_availability,
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


def unavailable_reason(fd: FilterDefinition, truth_graph: TruthGraph | None) -> str | None:
    """Council defects 2/3: the reason `fd` cannot currently match anything
    meaningful, or None when it has a real data source. `GET /api/filters`
    exposes this per filter so the drawer can tell "0 matches, nothing
    qualifies" apart from "0 matches, there is no signal at all"."""
    return fd.availability(truth_graph)


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

        contexts.append(
            OpportunityFilterContext(
                opp=opp,
                decision=evaluation.qualification_decision if evaluation else None,
                fit_score=evaluation.fit_score if evaluation else None,
                reasons=reasons,
                evaluation_detail=evaluation_detail,
                dimension_scores=dimension_scores,
                compensation_min=_safe_float(comp_by_field.get("compensation.min_amount")),
                compensation_max=_safe_float(comp_by_field.get("compensation.max_amount")),
                compensation_currency=comp_by_field.get("compensation.currency"),
                truth_graph=truth_graph,
            )
        )
    return contexts


def apply_filters(ctx: OpportunityFilterContext, settings: dict[str, FilterSettingsRow]) -> FilterOutcome:
    """Evaluate all ten filters for one opportunity against the founder's
    current settings. A disabled filter is not evaluated at all (contract
    section 4): it contributes to neither `hidden_by` nor `flagged_by`.

    Council defect 1 (belt-and-suspenders, layer (b)): every matcher here
    reads `params` defensively (`_safe_float`, structural `.get(...)` checks)
    rather than trusting it, so a row a database already holds a malformed
    value in degrades to "does not match" instead of raising -- layer (a),
    `validate_filter_params`, is what stops a bad value from being written in
    the first place (see `api/routes_api.py::update_filter`).
    """
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

        try:
            matched = fd.matcher(ctx, params)
        except (TypeError, ValueError, AttributeError):
            # Defensive last resort: a matcher must never take the feed down.
            matched = False

        if not matched:
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
    count = 0
    for ctx in contexts:
        try:
            if fd.matcher(ctx, params):
                count += 1
        except (TypeError, ValueError, AttributeError):
            continue
    return count
