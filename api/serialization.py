"""Serialisation helpers between persisted `match_evaluations` JSON columns
and the fixed API contract shapes.

`storage.models.MatchEvaluationRecord` (frozen for D6; owned by D4) has only
two free-form JSON text columns: `dimension_scores_json` and `reasons_json`.
There is no dedicated column for hard constraints, strengths/gaps/unknowns,
uncertainty_penalty, or the evaluation-level explanation. D6 defines the JSON
shape written into those two columns (documented here) because D4's writer
(`matching/evaluate_persist.py`) has not landed on this branch yet -- D6 is
the first and, as of this deliverable, only reader/writer of these columns.
Field names deliberately mirror `matching.models.HardConstraintResult` and
`matching.models.MatchDimensionScore` so a future D4 writer can serialise
those dataclasses directly with `dataclasses.asdict`-shaped dicts.

`dimension_scores_json` -> JSON list of:
    {"dimension_name", "raw_score", "weight", "weighted_score", "explanation"}

`reasons_json` -> JSON object:
    {"top_reasons": [str, ...],
     "hard_constraints": [{"constraint_name", "passed" (true|false|null),
                            "reason", "required_field", "founder_fact",
                            "is_hard_failure", "provenance_pointer"}, ...],
     "strengths": [str, ...], "gaps": [str, ...], "unknowns": [str, ...],
     "uncertainty_penalty": float, "explanation": str}

This is a coordination risk flagged back to the Master: when
`matching/evaluate_persist.py` (D4) is implemented, it must write this exact
shape or the API's read side here must change to match.
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


def pack_dimension_scores(dimension_scores: list[dict[str, Any]]) -> str:
    return json.dumps(dimension_scores, separators=(",", ":"))


def unpack_dimension_scores(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


def pack_reasons(
    *,
    top_reasons: list[str] | None = None,
    hard_constraints: list[dict[str, Any]] | None = None,
    strengths: list[str] | None = None,
    gaps: list[str] | None = None,
    unknowns: list[str] | None = None,
    uncertainty_penalty: float = 0.0,
    explanation: str = "",
) -> str:
    envelope = {
        "top_reasons": list(top_reasons or []),
        "hard_constraints": list(hard_constraints or []),
        "strengths": list(strengths or []),
        "gaps": list(gaps or []),
        "unknowns": list(unknowns or []),
        "uncertainty_penalty": uncertainty_penalty,
        "explanation": explanation,
    }
    return json.dumps(envelope, separators=(",", ":"))


def unpack_reasons(raw: str | None) -> dict[str, Any]:
    default: dict[str, Any] = {
        "top_reasons": [],
        "hard_constraints": [],
        "strengths": [],
        "gaps": [],
        "unknowns": [],
        "uncertainty_penalty": 0.0,
        "explanation": "",
    }
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
