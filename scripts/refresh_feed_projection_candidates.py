"""Safely refresh an explicitly bounded set of visible feed candidates.

Without ``--execute`` this stages the normal projection service in a
transaction, reports the candidate outcome, then rolls it back. Commits are
refused unless every requested opportunity remains a visible HOT/PROTECTED
candidate and is classified ``for_you`` after applying current hard gates.
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import func
from sqlalchemy import text

from matching.recommendation_foundation import classify_role_relevance
from scripts.db_capacity_guard import assert_heavy_work_allowed, inspect_connection
from storage.engine import get_engine, get_session_factory
from storage.feed_projection import FeedProjectionRecord
from storage.feed_projection_service import (
    _load_founder_behavior_signals,
    refresh_feed_projection_candidates,
)
from storage.models import OpportunityRecord, WorkerJobRecord
from truth.pack import TruthPackInvalid, TruthPackMissing, load_founder_pack


MAX_CANDIDATES = 100
MAX_RECONCILIATION_CANDIDATES = 200
TRANSACTION_ABORT_BYTES = 398 * 1024 * 1024
_ACTIONABLE_ACCESS = frozenset({"direct_free", "free_intermediary", "free_account_required"})
_FOUNDER_STATE_TABLES = (
    "founder_identity",
    "founder_feedback",
    "founder_activity_events",
    "founder_triage_states",
    "founder_cv_selections",
    "outbound_actions",
)


def _founder_state_snapshot(session) -> dict[str, tuple[int, str]]:
    snapshot: dict[str, tuple[int, str]] = {}
    for table_name in _FOUNDER_STATE_TABLES:
        row = session.execute(text(
            f"SELECT count(*) AS row_count, "
            f"md5(coalesce(string_agg(md5(to_jsonb(t)::text), '' "
            f"ORDER BY md5(to_jsonb(t)::text)), '')) AS snapshot_md5 "
            f"FROM public.{table_name} AS t"
        )).mappings().one()
        snapshot[table_name] = (int(row["row_count"]), str(row["snapshot_md5"]))
    return snapshot


def _active_queue_count(session) -> int:
    return int(
        session.query(WorkerJobRecord)
        .filter(WorkerJobRecord.status.in_(("PENDING", "RETRY", "RUNNING")))
        .count()
    )


def discover_current_for_you_ids(
    session, *, truth_pack_hash: str, limit: int = MAX_RECONCILIATION_CANDIDATES,
) -> tuple[str, ...]:
    """Select the bounded currently surfaced set for canonical re-projection.

    This intentionally selects only rows already shown in For You. It is a
    stale-projection repair path, not a corpus backfill.
    """
    if not 1 <= limit <= MAX_RECONCILIATION_CANDIDATES:
        raise ValueError(f"reconciliation limit must be between 1 and {MAX_RECONCILIATION_CANDIDATES}")
    query = (
        session.query(FeedProjectionRecord.opportunity_id)
        .join(OpportunityRecord, OpportunityRecord.id == FeedProjectionRecord.opportunity_id)
        .filter(
            FeedProjectionRecord.truth_pack_hash == truth_pack_hash,
            FeedProjectionRecord.visible.is_(True),
            FeedProjectionRecord.recommendation_state == "for_you",
            OpportunityRecord.lifecycle_tier.in_(("hot", "protected")),
        )
        .order_by(
            FeedProjectionRecord.recommendation_priority.desc(),
            FeedProjectionRecord.opportunity_id.asc(),
        )
    )
    count = int(query.count())
    if count > limit:
        raise ValueError(
            f"current For You set has {count} rows, above bounded limit {limit}; use reviewed shards"
        )
    return tuple(str(row[0]) for row in query.all())


def summarize_reconciliation_states(
    states: dict[str, int], *, expected_count: int,
) -> dict[str, int]:
    allowed = {"for_you", "review", "excluded"}
    if set(states) - allowed or sum(states.values()) != expected_count:
        raise ValueError("projection refresh returned an invalid or incomplete recommendation state set")
    return {
        "for_you": states.get("for_you", 0),
        "review": states.get("review", 0),
        "excluded": states.get("excluded", 0),
        "suppressed_from_for_you": states.get("review", 0) + states.get("excluded", 0),
    }


def reconciliation_refresh_is_complete(
    *, inserted: int, updated: int, skipped_without_evaluation: int, expected_count: int,
) -> bool:
    """True only when every selected feed row was recomputed from an evaluation."""
    return (
        skipped_without_evaluation == 0
        and inserted + updated == expected_count
    )


def discover_current_candidates(session, *, truth_pack_hash: str, limit: int = MAX_CANDIDATES) -> tuple[str, ...]:
    """Read a recent, already-actionable HOT/PROTECTED slice and classify in memory."""
    if not 1 <= limit <= MAX_CANDIDATES:
        raise ValueError(f"discovery limit must be between 1 and {MAX_CANDIDATES}")
    rows = (
        session.query(OpportunityRecord, FeedProjectionRecord.qualification_decision)
        .join(FeedProjectionRecord, FeedProjectionRecord.opportunity_id == OpportunityRecord.id)
        .filter(
            OpportunityRecord.lifecycle_tier.in_(("hot", "protected")),
            OpportunityRecord.is_stale.is_(False),
            OpportunityRecord.founder_geo_state.in_(("eligible", "likely_eligible")),
            OpportunityRecord.application_access.in_(_ACTIONABLE_ACCESS),
            OpportunityRecord.application_url.is_not(None),
            OpportunityRecord.application_url != "",
            FeedProjectionRecord.truth_pack_hash == truth_pack_hash,
            FeedProjectionRecord.visible.is_(True),
        )
        .order_by(OpportunityRecord.posted_date.desc().nullslast(), OpportunityRecord.id.asc())
        .limit(500)
        .all()
    )
    signals = {signal.opportunity_id: signal for signal in _load_founder_behavior_signals(session)}
    excluded_feedback = {"bad_match", "irrelevant_role", "eligibility_wrong", "seniority_wrong", "review_required", "duplicate_issue", "source_quality_issue"}
    excluded_actions = {"applied", "submitted", "rejected", "rejected_by_founder", "dismissed"}
    selected: list[tuple[int, object, str]] = []
    for opportunity, decision in rows:
        relevance = classify_role_relevance(opportunity.title or "", opportunity.description or "")
        if relevance.classification not in {"core", "adjacent"}:
            continue
        if (decision or "").casefold() == "ineligible":
            continue
        signal = signals.get(opportunity.id)
        if signal and (
            (signal.feedback_label or "").casefold() in excluded_feedback
            or (signal.action_type or "").casefold() in excluded_actions
        ):
            continue
        tier = 2 if relevance.classification == "core" else 1
        selected.append((tier, opportunity, opportunity.id))
    selected.sort(key=lambda item: item[2])
    selected.sort(key=lambda item: item[1].posted_date or "", reverse=True)
    selected.sort(key=lambda item: item[0], reverse=True)
    return tuple(item[2] for item in selected[:limit])


def _parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, tuple[str, ...]]:
    parser = argparse.ArgumentParser(
        description="Reclassify and refresh a bounded visible feed candidate set"
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--opportunity-id", action="append")
    selection.add_argument(
        "--discover-current-candidates", action="store_true",
        help="select up to --candidate-limit recent actionable HOT/PROTECTED feed rows",
    )
    selection.add_argument(
        "--reconcile-current-for-you", action="store_true",
        help="re-project only the currently visible HOT/PROTECTED For You set under current hard gates",
    )
    parser.add_argument("--candidate-limit", type=int, default=MAX_CANDIDATES)
    parser.add_argument("--truth-pack", default=None)
    parser.add_argument(
        "--execute", action="store_true",
        help="commit only when every requested candidate passes the live For You gates",
    )
    args = parser.parse_args(argv)
    ids = tuple(dict.fromkeys(value.strip() for value in (args.opportunity_id or ()) if value.strip()))
    if not args.discover_current_candidates and not args.reconcile_current_for_you and not ids:
        parser.error("select a discovery mode or provide at least one non-empty --opportunity-id")
    candidate_limit_max = (
        MAX_RECONCILIATION_CANDIDATES if args.reconcile_current_for_you else MAX_CANDIDATES
    )
    if args.candidate_limit < 1 or args.candidate_limit > candidate_limit_max:
        parser.error(f"--candidate-limit must be between 1 and {candidate_limit_max}")
    if ids and len(ids) > MAX_CANDIDATES:
        parser.error(f"at most {MAX_CANDIDATES} candidate IDs may be refreshed per run")
    return args, ids


def main(argv: list[str] | None = None) -> int:
    args, ids = _parse_args(argv)

    try:
        loaded = load_founder_pack(args.truth_pack)
    except (TruthPackMissing, TruthPackInvalid) as error:
        print(json.dumps({"error": f"truth pack unavailable: {error}"}, sort_keys=True))
        return 2

    engine = get_engine()
    Session = get_session_factory(engine)
    session = Session()
    before_bytes = None
    try:
        snapshot = inspect_connection(session.connection())
        before_bytes = snapshot.database_size_bytes
        assert_heavy_work_allowed(session.connection())

        if args.reconcile_current_for_you:
            if before_bytes >= TRANSACTION_ABORT_BYTES:
                raise RuntimeError(f"capacity abort before reconciliation: {before_bytes} bytes")
            active_before = _active_queue_count(session)
            if active_before:
                raise RuntimeError(f"refusing projection reconciliation while {active_before} queue jobs are active")
            founder_before = _founder_state_snapshot(session)
            ids = discover_current_for_you_ids(
                session,
                truth_pack_hash=loaded.truth_pack_hash,
                limit=args.candidate_limit,
            )
            if not ids:
                session.rollback()
                print(json.dumps({
                    "committed": False,
                    "mode": "no_current_for_you_rows",
                    "candidate_count": 0,
                    "database_bytes_before": before_bytes,
                    "database_bytes_after": before_bytes,
                }, sort_keys=True))
                return 2
            stats = refresh_feed_projection_candidates(
                session,
                ids,
                truth_graph=loaded.graph,
                truth_pack_hash=loaded.truth_pack_hash,
                max_candidates=MAX_RECONCILIATION_CANDIDATES,
            )
            if args.execute and not reconciliation_refresh_is_complete(
                inserted=stats.inserted,
                updated=stats.updated,
                skipped_without_evaluation=stats.skipped_without_evaluation,
                expected_count=len(ids),
            ):
                session.rollback()
                print(json.dumps({
                    "committed": False,
                    "mode": "execute_rejected",
                    "candidate_count": len(ids),
                    "inserted": stats.inserted,
                    "updated": stats.updated,
                    "skipped_without_evaluation": stats.skipped_without_evaluation,
                    "reason": "every current For You row must be recomputed before reconciliation commit",
                    "database_bytes_before": before_bytes,
                    "database_bytes_after": before_bytes,
                }, sort_keys=True))
                return 2
            session.flush()
            raw_states = dict(
                session.query(
                    FeedProjectionRecord.recommendation_state,
                    func.count(FeedProjectionRecord.id),
                )
                .filter(
                    FeedProjectionRecord.opportunity_id.in_(ids),
                    FeedProjectionRecord.truth_pack_hash == loaded.truth_pack_hash,
                )
                .group_by(FeedProjectionRecord.recommendation_state)
                .all()
            )
            state_counts = summarize_reconciliation_states(
                {str(state): int(count) for state, count in raw_states.items()},
                expected_count=len(ids),
            )
            if args.execute and state_counts["suppressed_from_for_you"] == 0:
                session.rollback()
                print(json.dumps({
                    "committed": False,
                    "mode": "execute_rejected",
                    "candidate_count": len(ids),
                    "projection_states": state_counts,
                    "reason": "reconciliation did not suppress any stale For You rows",
                    "database_bytes_before": before_bytes,
                    "database_bytes_after": before_bytes,
                }, sort_keys=True))
                return 2
            if _founder_state_snapshot(session) != founder_before:
                raise RuntimeError("Founder state changed during projection reconciliation")
            active_after = _active_queue_count(session)
            if active_after != active_before:
                raise RuntimeError("queue state changed during projection reconciliation")
            staged_capacity = inspect_connection(session.connection())
            if staged_capacity.database_size_bytes >= TRANSACTION_ABORT_BYTES:
                raise RuntimeError(
                    f"capacity abort before reconciliation commit: {staged_capacity.database_size_bytes} bytes"
                )
            if args.execute:
                session.commit()
                with engine.connect() as connection:
                    after_bytes = inspect_connection(connection).database_size_bytes
                if after_bytes >= TRANSACTION_ABORT_BYTES:
                    raise RuntimeError(f"capacity abort after reconciliation commit: {after_bytes} bytes")
            else:
                session.rollback()
                after_bytes = before_bytes
            print(json.dumps({
                "committed": bool(args.execute),
                "mode": "executed" if args.execute else "dry_run_reconciliation",
                "truth_pack_hash": loaded.truth_pack_hash,
                "candidate_count": len(ids),
                "projection_states": state_counts,
                "inserted": stats.inserted,
                "updated": stats.updated,
                "skipped_without_evaluation": stats.skipped_without_evaluation,
                "database_bytes_before": before_bytes,
                "database_bytes_after": after_bytes,
                "database_bytes_delta": after_bytes - before_bytes,
                "transaction_abort_bytes": TRANSACTION_ABORT_BYTES,
                "queue_active_before": active_before,
                "queue_active_after": active_after,
                "founder_state_unchanged": True,
            }, sort_keys=True))
            return 0

        if args.discover_current_candidates:
            ids = discover_current_candidates(
                session,
                truth_pack_hash=loaded.truth_pack_hash,
                limit=args.candidate_limit,
            )
            if not ids:
                session.rollback()
                print(json.dumps({
                    "committed": False,
                    "mode": "no_candidates",
                    "candidate_count": 0,
                    "database_bytes_before": before_bytes,
                    "database_bytes_after": before_bytes,
                }, sort_keys=True))
                return 2

        stats = refresh_feed_projection_candidates(
            session,
            ids,
            truth_graph=loaded.graph,
            truth_pack_hash=loaded.truth_pack_hash,
            max_candidates=MAX_CANDIDATES,
        )
        session.flush()
        states = dict(
            session.query(
                FeedProjectionRecord.recommendation_state,
                func.count(FeedProjectionRecord.id),
            )
            .filter(
                FeedProjectionRecord.opportunity_id.in_(ids),
                FeedProjectionRecord.truth_pack_hash == loaded.truth_pack_hash,
            )
            .group_by(FeedProjectionRecord.recommendation_state)
            .all()
        )
        state_counts = {str(state): int(count) for state, count in states.items()}

        if sum(state_counts.values()) != len(ids):
            raise ValueError("candidate refresh did not produce one projection per requested opportunity")
        if state_counts != {"for_you": len(ids)}:
            session.rollback()
            print(json.dumps({
                "committed": False,
                "mode": "dry_run_rejected" if args.execute else "dry_run",
                "candidate_count": len(ids),
                "projection_states": state_counts,
                "reason": "not every candidate passes the current For You gates",
                "database_bytes_before": before_bytes,
                "database_bytes_after": before_bytes,
                "inserted": stats.inserted,
                "updated": stats.updated,
            }, sort_keys=True))
            return 2 if args.execute else 0

        if args.execute:
            session.commit()
            with engine.connect() as connection:
                after_bytes = inspect_connection(connection).database_size_bytes
        else:
            session.rollback()
            after_bytes = before_bytes

        print(json.dumps({
            "committed": bool(args.execute),
            "mode": "executed" if args.execute else "dry_run",
            "truth_pack_hash": loaded.truth_pack_hash,
            "candidate_count": len(ids),
            "projection_states": state_counts,
            "inserted": stats.inserted,
            "updated": stats.updated,
            "skipped_without_evaluation": stats.skipped_without_evaluation,
            "database_bytes_before": before_bytes,
            "database_bytes_after": after_bytes,
            "database_bytes_delta": after_bytes - before_bytes,
        }, sort_keys=True))
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
