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

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

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


def _to_utc_naive(value: datetime) -> datetime:
    """Normalize to a naive ``datetime`` carrying UTC wall-clock time, for
    writing into ``MatchEvaluationRecord.evaluated_at`` (``DateTime``, i.e.
    PostgreSQL ``TIMESTAMP WITHOUT TIME ZONE`` -- the whole codebase's
    documented convention, see ``worker/runner.py``'s ``_as_aware_utc``, is
    "naive but always UTC").

    This matters because psycopg2 does not simply drop the tzinfo off a
    tz-aware ``datetime`` when writing it into such a column: PostgreSQL
    converts the value to the *session's* ``timezone`` GUC first and only
    then stores it naive. On a session whose timezone isn't UTC (verified
    against this project's own local dev database, which defaults to
    ``Africa/Cairo``), a tz-aware UTC value written straight through comes
    back several hours off from what was actually passed in -- exactly the
    kind of silent corruption of ``evaluated_at`` that would misdate rows on
    the founder-facing dashboard. Converting to UTC and stripping tzinfo
    *before* the value reaches psycopg2 avoids the conversion entirely: the
    naive value handed to the driver already IS the intended UTC wall-clock
    time, so there is nothing left for PostgreSQL to convert.
    """
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


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
            "signal_tags": list(ds.signal_tags),
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


def _evaluation_detail_json(evaluation: MatchEvaluation) -> str:
    """Serialize the D6 detail-route payload: full hard-constraint checklist
    plus the evaluation-level strengths/gaps/unknowns/uncertainty_penalty/
    preference_score/explanation. ``passed`` is written as literal JSON
    ``true``/``false``/
    ``null`` -- ``null`` means UNKNOWN (``HardConstraintResult.passed is
    None``) and is never coerced to ``false``.
    """
    payload = {
        "hard_constraints": [
            {
                "constraint_name": hc.constraint_name,
                "passed": hc.passed,
                "reason": hc.reason,
                "required_field": hc.required_field,
                "founder_fact": hc.founder_fact,
                "is_hard_failure": hc.is_hard_failure,
                "provenance_pointer": hc.provenance_pointer,
                "constraint_type": hc.constraint_type,
                "job_evidence_text": hc.job_evidence_text,
                "job_evidence_field": hc.job_evidence_field,
                "source_pointer": hc.source_pointer,
                "founder_side_evidence": hc.founder_side_evidence,
                "decision": hc.decision,
                "confidence": hc.confidence,
                "requirement_mandatory": hc.requirement_mandatory,
                "explanation": hc.explanation,
            }
            for hc in evaluation.hard_constraints
        ],
        "strengths": list(evaluation.strengths),
        "gaps": list(evaluation.gaps),
        "unknowns": list(evaluation.unknowns),
        "uncertainty_penalty": evaluation.uncertainty_penalty,
        "preference_score": evaluation.preference_score,
        "explanation": evaluation.explanation,
    }
    return json.dumps(payload, sort_keys=True)


def _upsert_match_evaluation(
    session: Any,
    *,
    record_id: str,
    opportunity_id: str,
    truth_pack_hash: str,
    values: dict[str, Any],
) -> MatchEvaluationRecord:
    """Race-safe upsert on ``(opportunity_id, truth_pack_hash)``.

    The plain SELECT-then-write this replaced had a race: two concurrent
    ``evaluate_and_store`` calls for the same opportunity+hash (e.g. two
    ``evaluate_new`` jobs claimed by different workers, or ``poll_source``'s
    inline evaluation racing a backfill ``evaluate_new`` run) could both miss
    on the SELECT, then both attempt to INSERT the same deterministic primary
    key -- the loser got an uncaught ``IntegrityError`` and burned a retry
    for no reason, since the row it wanted written already exists in
    substance.

    On PostgreSQL this uses a real ``INSERT ... ON CONFLICT ON CONSTRAINT
    uq_match_evaluations_opportunity_truth_pack DO UPDATE`` (atomic, no
    SELECT-then-write window at all). On any other dialect (SQLite, used by
    this module's own unit tests) there is no portable equivalent available
    through the ORM/Core in the same statement, so this falls back to
    SELECT-then-write but catches a lost-race ``IntegrityError`` and
    converts it into an ``UPDATE`` of the row the winner just inserted,
    instead of propagating.
    """
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""

    if dialect_name == "postgresql":
        table = MatchEvaluationRecord.__table__
        insert_values = {"id": record_id, "opportunity_id": opportunity_id, "truth_pack_hash": truth_pack_hash, **values}
        stmt = pg_insert(table).values(**insert_values)
        update_cols = {key: stmt.excluded[key] for key in values}
        stmt = stmt.on_conflict_do_update(
            constraint="uq_match_evaluations_opportunity_truth_pack",
            set_=update_cols,
        )
        session.execute(stmt)
        session.commit()
        return (
            session.query(MatchEvaluationRecord)
            .filter_by(opportunity_id=opportunity_id, truth_pack_hash=truth_pack_hash)
            .one()
        )

    existing = (
        session.query(MatchEvaluationRecord)
        .filter_by(opportunity_id=opportunity_id, truth_pack_hash=truth_pack_hash)
        .first()
    )
    if existing is not None:
        for key, value in values.items():
            setattr(existing, key, value)
        session.commit()
        return existing

    record = MatchEvaluationRecord(id=record_id, opportunity_id=opportunity_id, truth_pack_hash=truth_pack_hash, **values)
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = (
            session.query(MatchEvaluationRecord)
            .filter_by(opportunity_id=opportunity_id, truth_pack_hash=truth_pack_hash)
            .first()
        )
        if existing is None:
            raise
        for key, value in values.items():
            setattr(existing, key, value)
        session.commit()
        return existing
    return record


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
    evaluation_detail_json = _evaluation_detail_json(evaluation)

    record_id = hashlib.sha256(
        f"{opportunity.id}:{truth_pack_hash}".encode("utf-8")
    ).hexdigest()[:32]

    values = {
        "qualification_decision": decision_value,
        "fit_score": evaluation.overall_fit_score,
        "dimension_scores_json": dimension_scores_json,
        "reasons_json": reasons_json,
        "evaluation_detail_json": evaluation_detail_json,
        "policy_version": evaluation.policy_version,
        # Converted to naive UTC right before it reaches the DB column -- see
        # _to_utc_naive's docstring for why this is load-bearing, not cosmetic.
        "evaluated_at": _to_utc_naive(resolved_evaluated_at),
    }

    evaluation_record = _upsert_match_evaluation(
        repository.session,
        record_id=record_id,
        opportunity_id=opportunity.id,
        truth_pack_hash=truth_pack_hash,
        values=values,
    )
    from storage.feed_projection_service import refresh_opportunity_projection

    try:
        projection = refresh_opportunity_projection(
            repository.session,
            opportunity_id=opportunity.id,
            truth_pack_hash=truth_pack_hash,
            truth_graph=truth_graph,
            projected_at=resolved_evaluated_at,
        )
        if projection is None:
            raise RuntimeError("evaluation persisted but feed projection was not published")
        # Persist the exact fixed-CV identity selected by the authoritative
        # Python selector. The private object body is fetched and hash-checked
        # by the delivery boundary; only safe metadata is stored here.
        if getattr(opportunity, "track", None) == "employment":
            from matching.cv_selector import select_cv_for_opportunity
            from storage.models import FounderCVSelectionRecord
            selected = select_cv_for_opportunity(opportunity).selected
            cv_row = repository.session.get(FounderCVSelectionRecord, opportunity.id)
            if cv_row is None:
                cv_row = FounderCVSelectionRecord(opportunity_id=opportunity.id)
                repository.session.add(cv_row)
            cv_row.variant = selected.variant
            cv_row.object_path = selected.object_path
            cv_row.sha256 = selected.sha256
            cv_row.selected_at = _to_utc_naive(resolved_evaluated_at)
            cv_row.truth_pack_hash = truth_pack_hash
        repository.session.commit()
    except Exception:
        repository.session.rollback()
        raise
    return evaluation_record
