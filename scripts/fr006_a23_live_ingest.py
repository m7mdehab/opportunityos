#!/usr/bin/env python3
"""FR-006 A-23 bounded live production-ingestion acceptance.

Poll exactly eight newly registered, already verified public ATS boards through
the production worker handler and prove that each source produces persisted and
evaluated Opportunity rows.  The run is read-only at every external source and
uses only the repository's synthetic founder graph.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# Keep direct ``python scripts/...`` execution pinned to this checkout instead
# of any older editable install that may exist on the operator's machine.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opportunity.adapters import get_all_standard_adapters
from opportunity.registry import SourceRegistry
from storage.engine import get_engine, get_session_factory
from storage.models import MatchEvaluationRecord, OpportunityRecord, SourcePollRunRecord
from truth.fixtures import founder_shaped_graph
from truth.pack import LoadedPack, PackValidationReport
from worker.handlers import make_poll_source_handler

SOURCE_IDS = (
    "greenhouse:ada18",
    "greenhouse:ampsortation",
    "greenhouse:aquaticcapitalmanagement",
    "lever:brilliant",
    "lever:demiurgestudios",
    "lever:gauntlet",
    "lever:teleo",
    "lever:vailsys",
)
SYNTHETIC_HASH = "fr006-a23-synthetic-live-v1"


def _synthetic_pack(_path: object) -> LoadedPack:
    return LoadedPack(
        graph=founder_shaped_graph(),
        report=PackValidationReport(valid=True, section_counts=(("synthetic", 1),), findings=()),
        truth_pack_hash=SYNTHETIC_HASH,
    )


def validate_bindings(registry: SourceRegistry) -> None:
    """Fail before network I/O unless every bounded source is policy-allowed and bound."""
    bound = {adapter.source_id for adapter in get_all_standard_adapters(registry=registry)}
    for source_id in SOURCE_IDS:
        if not registry.is_read_allowed(source_id):
            raise RuntimeError(f"source {source_id!r} is not read-allowed")
        if source_id not in bound:
            raise RuntimeError(f"source {source_id!r} has no production adapter binding")


def main() -> int:
    db_url = os.environ.get("OPPORTUNITYOS_DB_URL", "")
    if not db_url:
        raise RuntimeError("OPPORTUNITYOS_DB_URL is required")
    db_name = db_url.rsplit("/", 1)[-1].split("?", 1)[0]
    if db_name not in {"opportunityos_alpha", "opportunityos_a23_alpha"}:
        raise RuntimeError(f"A-23 requires a fresh alpha database, got {db_name!r}")

    registry = SourceRegistry()
    validate_bindings(registry)
    adapters = get_all_standard_adapters(registry=registry)
    engine = get_engine(db_url)
    session_factory = get_session_factory(engine)
    handler = make_poll_source_handler(
        registry=registry,
        adapters=adapters,
        session_factory=session_factory,
        pack_loader=_synthetic_pack,
    )

    print(f"A-23 live production ingestion database={db_name} bounded_sources={len(SOURCE_IDS)}")
    passed: list[str] = []
    try:
        for index, source_id in enumerate(SOURCE_IDS, start=1):
            handler({"source_id": source_id, "job_id": f"fr006-a23-live-{index}"})
            session = session_factory()
            try:
                poll = (
                    session.query(SourcePollRunRecord)
                    .filter(SourcePollRunRecord.source_id == source_id)
                    .order_by(SourcePollRunRecord.started_at.desc())
                    .first()
                )
                if poll is None:
                    raise AssertionError(f"{source_id}: no source_poll_runs row")
                rows = session.query(OpportunityRecord).filter_by(source_id=source_id).all()
                row_ids = {row.id for row in rows}
                evaluations = (
                    session.query(MatchEvaluationRecord)
                    .filter(MatchEvaluationRecord.opportunity_id.in_(row_ids))
                    .filter(MatchEvaluationRecord.truth_pack_hash == SYNTHETIC_HASH)
                    .all()
                    if row_ids
                    else []
                )
                domains = sorted({urlparse(row.source_url).netloc for row in rows if row.source_url})
                print(
                    f"source={source_id} status={poll.status} raw={poll.raw_ingested} "
                    f"unique={poll.unique_opportunities} inserted={poll.inserted} "
                    f"unchanged={poll.unchanged} updated={poll.updated} "
                    f"persisted={len(rows)} evaluated={len(evaluations)} domains={domains}"
                )
                if poll.status != "ok":
                    raise AssertionError(
                        f"{source_id}: status={poll.status} refusal={poll.refusal_reason!r} "
                        f"error={poll.error_message!r}"
                    )
                if not rows:
                    raise AssertionError(f"{source_id}: production ingestion persisted zero rows")
                if len(evaluations) != len(rows):
                    raise AssertionError(
                        f"{source_id}: persisted={len(rows)} evaluated={len(evaluations)}"
                    )
                if any("example.com" in (row.source_url or "").casefold() for row in rows):
                    raise AssertionError(f"{source_id}: fixture/example URL reached live database")
                passed.append(source_id)
            finally:
                session.close()

        if len(passed) < 8:
            raise AssertionError(f"A-23 persisted source yield {len(passed)}/8")
        print(f"A-23 PERSISTED SOURCE YIELD PASS: {len(passed)}/8 source_ids={passed}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
