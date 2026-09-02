"""Serialisation helpers between persisted `match_evaluations` JSON columns
and the fixed API contract shapes.

These are the Master-fixed, authoritative persisted shapes (D4/D4b owns the
writer, `matching/evaluate_persist.py`; D6 only reads):

`dimension_scores_json` -> JSON list of:
    {"dimension_name", "raw_score", "weight", "weighted_score", "explanation",
     ...}
    (D4b also writes `strengths`/`gaps`/`unknowns`/`evidence_refs`/
    `opportunity_field_refs` per entry; D6 only reads the five fields the API
    contract exposes.)

`reasons_json` -> JSON **list** (not an object) of:
    {"kind": "strength"|"gap"|"unknown"|"hard_failure", "dimension": str,
     "text": str}
    Capped at 5 entries per kind by the writer, in dimension order.

`evaluation_detail_json` -> JSON object (a column D4b is adding; may not
    exist yet on every deployed schema -- see `unpack_evaluation_detail`):
    {"hard_constraints": [{"constraint_name", "passed" (true|false|null),
                            "reason", "required_field", "founder_fact",
                            "is_hard_failure", "provenance_pointer"}, ...],
     "strengths": [str, ...], "gaps": [str, ...], "unknowns": [str, ...],
     "uncertainty_penalty": float, "explanation": str}

`passed` is `true | false | null`; `null` is UNKNOWN and must never be read
or rendered as FAIL (`constraint_outcome` below is the single place that
mapping happens).

Until `evaluation_detail_json` is migrated in and populated everywhere, this
module falls back to deriving `strengths`/`gaps`/`unknowns` (capped, per the
writer's own cap) from `reasons_json`, and reports empty `hard_constraints`
/ zero `uncertainty_penalty` / empty `explanation` -- decision and fit_score
are unaffected either way, since those live in their own dedicated columns.
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

    Defensive by design: this column is new and may be absent (unmigrated)
    or empty (not yet backfilled) on a given row. Missing or unparseable
    input returns the all-empty default rather than raising, so the rest of
    the response (decision, fit_score, dimension_scores, top reasons) is
    never blocked by this column's readiness.
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


def serialize_constraint(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "constraint_name": entry.get("constraint_name"),
        "outcome": constraint_outcome(entry.get("passed")),
        "reason": entry.get("reason", ""),
        "required_field": entry.get("required_field", ""),
        "founder_fact": entry.get("founder_fact", ""),
        "is_hard_failure": bool(entry.get("is_hard_failure", False)),
        "provenance_pointer": entry.get("provenance_pointer", ""),
    }
