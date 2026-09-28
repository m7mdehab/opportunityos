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

from matching.recommendation_foundation import classify_role_relevance
from scripts.db_capacity_guard import assert_heavy_work_allowed, inspect_connection
from storage.engine import get_engine, get_session_factory
from storage.feed_projection import FeedProjectionRecord
from storage.feed_projection_service import (
    _load_founder_behavior_signals,
    refresh_feed_projection_candidates,
)
from storage.models import OpportunityRecord
from truth.pack import TruthPackInvalid, TruthPackMissing, load_founder_pack


MAX_CANDIDATES = 100
_ACTIONABLE_ACCESS = frozenset({"direct_free", "free_intermediary", "free_account_required"})


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reclassify and refresh up to 100 explicitly selected visible feed candidates"
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--opportunity-id", action="append")
    selection.add_argument(
        "--discover-current-candidates", action="store_true",
        help="select up to --candidate-limit recent actionable HOT/PROTECTED feed rows without logging their IDs",
    )
    parser.add_argument("--candidate-limit", type=int, default=MAX_CANDIDATES)
    parser.add_argument("--truth-pack", default=None)
    parser.add_argument(
        "--execute", action="store_true",
        help="commit only when every requested candidate passes the live For You gates",
    )
    args = parser.parse_args(argv)
    ids = tuple(dict.fromkeys(value.strip() for value in (args.opportunity_id or ()) if value.strip()))
    if not ids:
        parser.error("at least one non-empty --opportunity-id is required")
    if args.candidate_limit < 1 or args.candidate_limit > MAX_CANDIDATES:
        parser.error(f"--candidate-limit must be between 1 and {MAX_CANDIDATES}")
    if ids and len(ids) > MAX_CANDIDATES:
        parser.error(f"at most {MAX_CANDIDATES} candidate IDs may be refreshed per run")

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
