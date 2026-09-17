from __future__ import annotations

import argparse
import json

from storage.engine import get_engine, get_session_factory
from storage.feed_projection_service import rebuild_feed_projection
from truth.pack import TruthPackInvalid, TruthPackMissing, load_founder_pack


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the durable FR-007 founder feed projection"
    )
    parser.add_argument(
        "--truth-pack",
        default=None,
        help="Founder truth-pack path; defaults to private/truth_pack.yaml",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--start-after",
        default=None,
        help="Resume after this opportunity id (exclusive)",
    )
    args = parser.parse_args(argv)

    try:
        loaded = load_founder_pack(args.truth_pack)
    except (TruthPackMissing, TruthPackInvalid) as error:
        print(f"feed projection rebuild refused: {error}")
        return 2

    engine = get_engine()
    Session = get_session_factory(engine)
    session = Session()
    try:
        stats = rebuild_feed_projection(
            session,
            truth_graph=loaded.graph,
            truth_pack_hash=loaded.truth_pack_hash,
            batch_size=args.batch_size,
            start_after=args.start_after,
            commit_each_batch=True,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()

    # Counts/ids only. Never emit truth-pack contents, connection strings, or
    # other runtime secrets into logs/evidence.
    print(
        json.dumps(
            {
                "truth_pack_hash": loaded.truth_pack_hash,
                "inserted": stats.inserted,
                "updated": stats.updated,
                "skipped_without_evaluation": stats.skipped_without_evaluation,
                "batches": stats.batches,
                "last_opportunity_id": stats.last_opportunity_id,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
