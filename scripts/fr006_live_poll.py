#!/usr/bin/env python3
"""FR-006 A-9 live-poll acceptance runner.

Runs one real, policy-permitted source through the production worker seam into a
fresh PostgreSQL database, using only the repository's synthetic founder graph.
No private Founder Truth Pack is read.  A 403/429 is recorded by the worker and
causes this acceptance run to fail closed rather than retrying or bypassing the
source.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# Keep direct ``python scripts/...`` execution pinned to this checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opportunity.registry import SourceRegistry
from storage.engine import get_engine, get_session_factory
from storage.models import MatchEvaluationRecord, OpportunityRecord, SourcePollRunRecord
from truth.fixtures import founder_shaped_graph
from truth.pack import LoadedPack, PackValidationReport
from worker.handlers import make_poll_source_handler

SOURCE_ID = os.environ.get("FR006_LIVE_SOURCE_ID", "himalayas")
SYNTHETIC_HASH = "fr006-a9-synthetic-live-v1"


def _synthetic_pack(_path: object) -> LoadedPack:
    graph = founder_shaped_graph()
    return LoadedPack(
        graph=graph,
        report=PackValidationReport(valid=True, section_counts=(("synthetic", 1),), findings=()),
        truth_pack_hash=SYNTHETIC_HASH,
    )


def main() -> int:
    db_url = os.environ.get("OPPORTUNITYOS_DB_URL", "")
    if not db_url:
        raise RuntimeError("OPPORTUNITYOS_DB_URL is required")
    db_name = db_url.rsplit("/", 1)[-1].split("?", 1)[0]
    if db_name not in {"opportunityos_alpha", "opportunityos_a23_alpha"}:
        raise RuntimeError(
            f"live acceptance must run on a fresh alpha database, got {db_name!r}"
        )

    registry = SourceRegistry()
    if not registry.is_read_allowed(SOURCE_ID):
        raise RuntimeError(f"source {SOURCE_ID!r} is not read-allowed by SourceRegistry")

    engine = get_engine(db_url)
    session_factory = get_session_factory(engine)
    handler = make_poll_source_handler(
        registry=registry,
        session_factory=session_factory,
        pack_loader=_synthetic_pack,
    )

    print(f"A-9 live source={SOURCE_ID} database={db_name} policy=read_allowed")
    handler({"source_id": SOURCE_ID, "job_id": "fr006-a9-live"})

    session = session_factory()
    try:
        poll = (
            session.query(SourcePollRunRecord)
            .filter(SourcePollRunRecord.source_id == SOURCE_ID)
            .order_by(SourcePollRunRecord.started_at.desc())
            .first()
        )
        if poll is None:
            raise AssertionError("worker produced no source_poll_runs record")
        print(
            "poll_result "
            f"status={poll.status} raw={poll.raw_ingested} unique={poll.unique_opportunities} "
            f"inserted={poll.inserted} unchanged={poll.unchanged} updated={poll.updated} "
            f"refusal={poll.refusal_reason or 'none'} error={poll.error_message or 'none'}"
        )
        if poll.status != "ok":
            raise AssertionError(
                f"live source poll did not complete normally: status={poll.status} "
                f"refusal={poll.refusal_reason!r} error={poll.error_message!r}"
            )

        rows = session.query(OpportunityRecord).filter(OpportunityRecord.source_id == SOURCE_ID).all()
        row_ids = {row.id for row in rows}
        evaluations = (
            session.query(MatchEvaluationRecord)
            .filter(MatchEvaluationRecord.opportunity_id.in_(row_ids))
            .filter(MatchEvaluationRecord.truth_pack_hash == SYNTHETIC_HASH)
            .all()
            if row_ids
            else []
        )

        # A zero-row public poll is still evidence that the complete live seam ran,
        # per the frozen claim.  When rows are returned, however, every persisted
        # row from this poll must also have reached evaluation.
        if rows and len(evaluations) != len(rows):
            raise AssertionError(
                f"persist/evaluate seam incomplete: opportunities={len(rows)} evaluations={len(evaluations)}"
            )

        bad_example = [row.id for row in rows if "example.com" in (row.source_url or "").casefold()]
        if bad_example:
            raise AssertionError(f"fixture/example URLs leaked into live poll: {bad_example[:3]}")
        bad_source = [row.id for row in rows if row.source_id != SOURCE_ID or row.source_id.startswith("src-")]
        if bad_source:
            raise AssertionError(f"non-registry/fixture source ids found: {bad_source[:3]}")

        domains = sorted({urlparse(row.source_url).netloc for row in rows if row.source_url})
        print(
            "persist_evaluate "
            f"opportunities={len(rows)} evaluations={len(evaluations)} "
            f"fixture_rows=0 source_ids={[SOURCE_ID]} domains={domains[:8]}"
        )
        print("A-9 LIVE POLL PASS")
        return 0
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
