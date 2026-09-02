"""Match evaluation persistence: runs the qualification + scoring engines once
and upserts the resulting decision onto ``match_evaluations``.

``QualificationEngine.evaluate`` and ``OpportunityScorer.evaluate`` are pure,
in-memory functions (matching/qualification.py, matching/scorer.py, both
frozen for this deliverable); this module is the seam between those engines
and ``storage.models.MatchEvaluationRecord`` -- exactly analogous to how
``opportunity/persistence.py`` is the seam between ``opportunity.pipeline``
and ``storage.models.OpportunityRecord``.

Identity: one row per ``(opportunity_id, truth_pack_hash)`` -- the schema's
own ``UniqueConstraint`` (``storage/models.py``). A re-evaluation under the
*same* truth-pack hash overwrites that row in place (idempotent re-run,
mirrors ``opportunity.persistence``'s "identical re-poll is a no-op-ish
upsert" spirit). A re-evaluation under a *different* truth-pack hash --
because the founder's truth pack changed -- is a brand new row: the prior
hash's decision is never touched, so the founder's evaluation history stays
intact across truth-pack revisions. ``truth_pack_hash`` is always supplied by
the caller (``truth.pack.load_founder_pack(...).truth_pack_hash``); this
module never recomputes it, so it never silently evaluates against the wrong
pack version.

``qualification_decision`` is stored as ``QualificationDecision.value``
verbatim -- ``"qualified"``, ``"ineligible"``, or ``"uncertain"`` -- for every
branch. There is no coercion anywhere in this module: an ``uncertain``
decision is never rewritten to ``ineligible`` (or anything else) on the way
into the database.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from matching.models import MatchEvaluation
from matching.scorer import OpportunityScorer
from opportunity.models import Opportunity
from storage.models import MatchEvaluationRecord
from storage.repository import StorageRepository
from truth.graph import TruthGraph

#: Cap on how many reasons of each kind (strength / gap / unknown) are kept in
#: ``reasons_json``. Keeps the payload UI-sized without needing prose
#: summarization -- the founder-facing dashboard renders these directly.
_MAX_REASONS_PER_KIND = 5


def _dimension_scores_to_json(evaluation: MatchEvaluation) -> str:
    """Serialize every ``MatchDimensionScore`` verbatim (all documented fields)."""
    payload = [
        {
            "dimension_name": ds.dimension_name,
            "raw_score": ds.raw_score,
            "weight": ds.weight,
            "weighted_score": ds.weighted_score,
            "explanation": ds.explanation,
            "strengths": list(ds.strengths),
            "gaps": list(ds.gaps),
            "unknowns": list(ds.unknowns),
            "evidence_refs": list(ds.evidence_refs),
            "opportunity_field_refs": list(ds.opportunity_field_refs),
        }
        for ds in evaluation.dimension_scores
    ]
    return json.dumps(payload, sort_keys=True)


def _build_reasons(evaluation: MatchEvaluation) -> list[dict[str, Any]]:
    """Build a machine-readable, structured list of top reasons.

    Each entry is ``{"kind": ..., "dimension": ..., "text": ...}``:

    - ``kind`` is one of ``"strength"``, ``"gap"``, ``"unknown"``, or
      ``"hard_failure"`` -- never free-form prose the caller has to parse.
    - ``dimension`` is the originating ``MatchDimensionScore.dimension_name``
      (or the failed ``HardConstraintResult.constraint_name`` for
      ``hard_failure`` entries); a UI can group/link straight back to the
      dimension breakdown in ``dimension_scores_json``.
    - ``text`` is the underlying human-readable reason string, taken verbatim
      from the engine's own output (never re-authored or summarized here).

    Capped at ``_MAX_REASONS_PER_KIND`` per kind, walked in the evaluation's
    own dimension order, so this is deterministic and reproducible from the
    stored ``MatchEvaluation`` alone.
    """
    reasons: list[dict[str, Any]] = []
    for kind, attr in (("strength", "strengths"), ("gap", "gaps"), ("unknown", "unknowns")):
        count = 0
        for dim in evaluation.dimension_scores:
            for text in getattr(dim, attr):
                if count >= _MAX_REASONS_PER_KIND:
                    break
                reasons.append({"kind": kind, "dimension": dim.dimension_name, "text": text})
                count += 1
            if count >= _MAX_REASONS_PER_KIND:
                break

    for hard_result in evaluation.hard_constraints:
        if hard_result.is_hard_failure:
            reasons.append(
                {
                    "kind": "hard_failure",
                    "dimension": hard_result.constraint_name,
                    "text": hard_result.reason,
                }
            )

    return reasons


def evaluate_and_store(
    opportunity: Opportunity,
    truth_graph: TruthGraph,
    repository: StorageRepository,
    *,
    truth_pack_hash: str,
    evaluated_at: Optional[datetime] = None,
    scorer: Optional[OpportunityScorer] = None,
) -> MatchEvaluationRecord:
    """Evaluate ``opportunity`` against ``truth_graph`` and upsert its row.

    ``truth_pack_hash`` is a required input (never recomputed here) -- it is
    part of the upsert key, so the caller controls exactly which pack version
    this evaluation is recorded against.

    ``evaluated_at`` must be a real UTC ``datetime``; if omitted,
    ``datetime.now(timezone.utc)`` is used. ``OpportunityScorer.evaluate``'s
    own ``evaluated_at`` parameter defaults to the fixed string
    ``"2026-08-30"`` -- that default is never reached from this function,
    since a real timestamp (or ``datetime.now``) is always passed through
    explicitly.
    """
    if not truth_pack_hash:
        raise ValueError("truth_pack_hash is required and must be non-empty")

    resolved_evaluated_at = evaluated_at if evaluated_at is not None else datetime.now(timezone.utc)

    engine_scorer = scorer if scorer is not None else OpportunityScorer()
    evaluation = engine_scorer.evaluate(
        opportunity, truth_graph, evaluated_at=resolved_evaluated_at.isoformat()
    )

    # Stored verbatim: "qualified" | "ineligible" | "uncertain". No branch here
    # (or anywhere else in this module) rewrites "uncertain" to any other value.
    decision_value = evaluation.qualification_decision.value

    dimension_scores_json = _dimension_scores_to_json(evaluation)
    reasons_json = json.dumps(_build_reasons(evaluation), sort_keys=True)

    session = repository.session
    existing = (
        session.query(MatchEvaluationRecord)
        .filter_by(opportunity_id=opportunity.id, truth_pack_hash=truth_pack_hash)
        .first()
    )

    if existing is not None:
        existing.qualification_decision = decision_value
        existing.fit_score = evaluation.overall_fit_score
        existing.dimension_scores_json = dimension_scores_json
        existing.reasons_json = reasons_json
        existing.policy_version = evaluation.policy_version
        existing.evaluated_at = resolved_evaluated_at
        session.commit()
        return existing

    record_id = hashlib.sha256(
        f"{opportunity.id}:{truth_pack_hash}".encode("utf-8")
    ).hexdigest()[:32]
    record = MatchEvaluationRecord(
        id=record_id,
        opportunity_id=opportunity.id,
        truth_pack_hash=truth_pack_hash,
        qualification_decision=decision_value,
        fit_score=evaluation.overall_fit_score,
        dimension_scores_json=dimension_scores_json,
        reasons_json=reasons_json,
        policy_version=evaluation.policy_version,
        evaluated_at=resolved_evaluated_at,
    )
    session.add(record)
    session.commit()
    return record
