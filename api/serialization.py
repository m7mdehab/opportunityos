"""Serialisation helpers between persisted `match_evaluations` JSON columns
and the fixed API contract shapes.

`storage.models.MatchEvaluationRecord` writes (`matching/evaluate_persist.py`)
five JSON-bearing columns this module reads:

`dimension_scores_json` -> JSON list of:
    {"dimension_name", "raw_score", "weight", "weighted_score", "explanation",
     ...}
    (the writer also includes `strengths`/`gaps`/`unknowns`/`evidence_refs`/
    `opportunity_field_refs` per entry; this module only reads the five
    fields the API contract exposes.)

`reasons_json` -> JSON **list** (not an object) of:
    {"kind": "strength"|"gap"|"unknown"|"hard_failure", "dimension": str,
     "text": str}
    Capped at 5 entries per kind by the writer, in dimension order.

`evaluation_detail_json` -> nullable JSON object:
    {"hard_constraints": [{"constraint_name", "passed" (true|false|null),
                            "reason", "required_field", "founder_fact",
                            "is_hard_failure", "provenance_pointer",
                            "constraint_type", "job_evidence_text",
                            "job_evidence_field", "source_pointer",
                            "founder_side_evidence", "decision", "confidence",
                            "requirement_mandatory", "explanation"}, ...],
     "strengths": [str, ...], "gaps": [str, ...], "unknowns": [str, ...],
     "uncertainty_penalty": float, "explanation": str}
    Nullable because rows persisted before this column existed have no
    detail payload -- see `unpack_evaluation_detail`.

`passed` is `true | false | null`; `null` is UNKNOWN and must never be read
or rendered as FAIL (`constraint_outcome` below is the single place that
mapping happens).

For a row whose `evaluation_detail_json` is null (written before the column
existed), this module falls back to deriving `strengths`/`gaps`/`unknowns`
(capped, per the writer's own cap on `reasons_json`) from `reasons_json`,
and reports empty `hard_constraints` / zero `uncertainty_penalty` / empty
`explanation` for that row -- decision and fit_score are unaffected either
way, since those live in their own dedicated, non-nullable columns.
"""

from __future__ import annotations

import json
from typing import Any


def constraint_outcome(passed: bool | None) -> str:
    """Map `HardConstraintResult.passed` (True|False|None) to the API's
    `outcome` vocabulary. `UNKNOWN` is never coerced to `FAIL`."""
    if passed is True:
        return "PASS"
    if passed is False:
        return "FAIL"
    return "UNKNOWN"


def unpack_dimension_scores(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


def unpack_reasons(raw: str | None) -> list[dict[str, Any]]:
    """`reasons_json` is a JSON list of `{"kind", "dimension", "text"}`."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


_EVALUATION_DETAIL_DEFAULT: dict[str, Any] = {
    "hard_constraints": [],
    "strengths": [],
    "gaps": [],
    "unknowns": [],
    "uncertainty_penalty": 0.0,
    "explanation": "",
}


def unpack_evaluation_detail(raw: str | None) -> dict[str, Any]:
    """`evaluation_detail_json` -> the object shape documented above.

    `raw` is `None` for rows persisted before this column existed, or for
    any row a caller has not yet backfilled -- that is real, expected,
    historical data, not a sign of a missing column. Returns the all-empty
    default in that case (or if the stored JSON is somehow unparseable)
    rather than raising, so the rest of the response (decision, fit_score,
    dimension_scores, top reasons) is never blocked by one row's detail
    payload being absent.
    """
    default = dict(_EVALUATION_DETAIL_DEFAULT)
    if not raw:
        return default
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
    if not isinstance(data, dict):
        return default
    default.update({k: v for k, v in data.items() if k in default})
    return default


def top_reasons_from_list(reasons: list[dict[str, Any]], limit: int = 3) -> list[str]:
    """The list route's `top_reasons`: the first `limit` reason texts, in
    the writer's own kind/dimension order (strengths, then gaps, then
    unknowns, then hard failures)."""
    return [entry["text"] for entry in reasons[:limit] if entry.get("text")]


def strengths_gaps_unknowns_from_reasons(
    reasons: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    """Fallback derivation of strengths/gaps/unknowns from `reasons_json`
    for rows written before `evaluation_detail_json` existed or was
    populated. Capped at whatever the writer capped `reasons_json` at
    (5 per kind) -- less complete than `evaluation_detail_json`, but never
    wrong."""
    strengths = [r["text"] for r in reasons if r.get("kind") == "strength" and r.get("text")]
    gaps = [r["text"] for r in reasons if r.get("kind") == "gap" and r.get("text")]
    unknowns = [r["text"] for r in reasons if r.get("kind") == "unknown" and r.get("text")]
    return strengths, gaps, unknowns


def serialize_dimension_score(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "dimension": entry.get("dimension_name"),
        "score": entry.get("raw_score"),
        "weight": entry.get("weight"),
        "weighted_score": entry.get("weighted_score"),
        "rationale": entry.get("explanation", ""),
    }


def unpack_remote_scope_regions(raw: str | None) -> list[str]:
    """`OpportunityRecord.remote_scope_regions` is a nullable JSON-encoded
    list of region codes (see `opportunity/persistence.py`,
    `worker/handlers.py::_reconstruct_opportunity`). Returns `[]` for a
    genuinely absent value or unparseable JSON rather than raising -- this
    is a read-only display helper, never a validation gate."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(v) for v in data] if isinstance(data, list) else []


def serialize_opportunity_extraction_fields(opp: Any, family_size: int | None = None) -> dict[str, Any]:
    """BRIEF-FR-006 C5: the founder's original complaint ("no card said
    whether the job was remote, hybrid, or on-site, or where it was") is
    only fixed once these `opportunities` columns (migration
    `0004_founder_control`) actually reach the API contract. Every field
    here is read straight off the `OpportunityRecord` row -- the
    authoritative source per `worker/handlers.py::_reconstruct_opportunity`'s
    own docstring -- never re-derived or defaulted to something that reads
    as data. `work_mode='unspecified'` is a real, storable value (migration
    0004's own column default) and is returned verbatim so the UI can render
    "not stated" instead of inventing silence.

    `family_size` is `OpportunityFamilyRecord.member_count` for this row's
    `family_key`, looked up by the caller (this module has no session), and
    is only included when the row actually belongs to a clustered family
    (`family_key` is not null) -- an unclustered row gets `family_size=None`
    rather than a misleading `1`.
    """
    return {
        "work_mode": opp.work_mode,
        "work_mode_source": opp.work_mode_source,
        "location_country": opp.location_country,
        "location_city": opp.location_city,
        "location_region": opp.location_region,
        "remote_scope": opp.remote_scope,
        "remote_scope_regions": unpack_remote_scope_regions(opp.remote_scope_regions),
        "employment_type": opp.employment_type,
        "seniority_level": opp.seniority_level,
        "compensation_min": opp.compensation_min,
        "compensation_max": opp.compensation_max,
        "compensation_currency": opp.compensation_currency,
        "compensation_period": opp.compensation_period,
        "title_family": opp.title_family,
        "title_level": opp.title_level,
        "family_key": opp.family_key,
        "family_size": family_size if opp.family_key else None,
    }


def serialize_constraint(entry: dict[str, Any]) -> dict[str, Any]:
    constraint_name = entry.get("constraint_name", entry.get("constraint_type"))
    passed = entry.get("decision", entry.get("passed"))
    required_field = entry.get("job_evidence_field", entry.get("required_field", ""))
    founder_fact = entry.get("founder_side_evidence", entry.get("founder_fact", ""))
    reason = entry.get("explanation", entry.get("reason", ""))
    source_pointer = entry.get("source_pointer", entry.get("provenance_pointer", ""))
    return {
        # Compatibility fields retained for current UI clients.
        "constraint_name": constraint_name,
        "outcome": constraint_outcome(passed),
        "reason": reason,
        "required_field": entry.get("required_field", required_field),
        "founder_fact": entry.get("founder_fact", founder_fact),
        "is_hard_failure": bool(entry.get("is_hard_failure", False)),
        "provenance_pointer": entry.get("provenance_pointer", source_pointer),
        # FR-008 evidence contract fields.
        "constraint_type": entry.get("constraint_type", constraint_name),
        "job_evidence_text": entry.get("job_evidence_text", ""),
        "job_evidence_field": required_field,
        "source_pointer": source_pointer,
        "founder_side_evidence": founder_fact,
        "decision": passed,
        "confidence": entry.get("confidence"),
        "requirement_mandatory": entry.get("requirement_mandatory"),
        "explanation": reason,
    }
