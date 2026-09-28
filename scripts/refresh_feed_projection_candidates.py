"""Safely refresh an explicitly bounded set of visible feed candidates.

Without ``--execute`` this stages the normal projection service in a
transaction, reports the candidate outcome, then rolls it back. Commits are
refused unless every requested opportunity remains a visible HOT/PROTECTED
candidate and is classified ``for_you`` after applying current hard gates.
"""
from __future__ import annotations

import argparse
import json

from scripts.db_capacity_guard import assert_heavy_work_allowed, inspect_connection
from storage.engine import get_engine, get_session_factory
from sqlalchemy import func

from storage.feed_projection import FeedProjectionRecord
from storage.feed_projection_service import refresh_feed_projection_candidates
from truth.pack import TruthPackInvalid, TruthPackMissing, load_founder_pack


MAX_CANDIDATES = 100


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reclassify and refresh up to 100 explicitly selected visible feed candidates"
    )
    parser.add_argument("--opportunity-id", action="append", required=True)
    parser.add_argument("--truth-pack", default=None)
    parser.add_argument(
        "--execute", action="store_true",
        help="commit only when every requested candidate passes the live For You gates",
    )
    args = parser.parse_args(argv)
    ids = tuple(dict.fromkeys(value.strip() for value in args.opportunity_id if value.strip()))
    if not ids:
        parser.error("at least one non-empty --opportunity-id is required")
    if len(ids) > MAX_CANDIDATES:
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
