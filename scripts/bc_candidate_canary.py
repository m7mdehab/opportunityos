"""Persist the exact BC replacement candidates through canonical pipeline contracts.

This is a deliberately narrow one-shot production transaction. It admits only
the two audited VRChat Lever records and the LiveKit Ashby role discovered in
an existing Hacker News item, then refreshes only those three plus the three
already-present Canonical records. It never polls or schedules a source.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlalchemy import text

from opportunity.persistence import persist_evaluated_batch
from opportunity.pipeline import OpportunityPipeline
from scripts.replay_bc_production import replay
from scripts.db_capacity_guard import inspect_connection
from storage.engine import get_engine, get_session_factory
from storage.feed_projection import FeedProjectionRecord
from storage.feed_projection_service import refresh_opportunity_projection
from storage.models import (
    FounderActivityEventRecord,
    FounderFeedbackRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
    WorkerJobRecord,
)
from storage.repository import StorageRepository
from truth.pack import CANONICAL_REPO_TRUTH_PACK, load_founder_pack


TRANSACTION_ABORT_BYTES = 398 * 1024 * 1024
NEW_CANDIDATE_IDS = (
    "lever:vrchat:f6d04b6b-8d9f-4261-9d1c-4fbf867d636c",
    "lever:vrchat:93875494-9d42-446d-a069-9c14296e46ed",
    "hacker_news_who_is_hiring:49570095_software-engineer-agents",
)
EXISTING_CANDIDATE_IDS = (
    "greenhouse:canonical:5667860",
    "greenhouse:canonical:6394147",
    "greenhouse:canonical:6783943",
)
REFRESH_IDS = EXISTING_CANDIDATE_IDS + NEW_CANDIDATE_IDS
FOUNDER_STATE_TABLES = (
    "founder_identity",
    "founder_feedback",
    "founder_activity_events",
    "founder_triage_states",
    "founder_cv_selections",
    "outbound_actions",
)
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


class PartialCanaryFailure(RuntimeError):
    def __init__(
        self,
        cause: Exception,
        *,
        inserted_ids: list[str],
        unchanged_ids: list[str],
        capacity_measurements: list[dict[str, Any]],
    ) -> None:
        super().__init__(f"canary stopped after bounded commits: {type(cause).__name__}: {cause}")
        self.inserted_ids = list(inserted_ids)
        self.unchanged_ids = list(unchanged_ids)
        self.capacity_measurements = list(capacity_measurements)


def _founder_state_snapshot(session) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for table_name in FOUNDER_STATE_TABLES:
        query = text(
            f"SELECT count(*) AS row_count, "
            f"md5(coalesce(string_agg(md5(to_jsonb(t)::text), '' "
            f"ORDER BY md5(to_jsonb(t)::text)), '')) AS snapshot_md5 "
            f"FROM public.{table_name} AS t"
        )
        row = session.execute(query).mappings().one()
        snapshot[table_name] = {
            "row_count": int(row["row_count"]),
            "snapshot_md5": str(row["snapshot_md5"]),
        }
    return snapshot


def _load_payload(filename: str) -> str:
    return (FIXTURE_DIR / filename).read_text(encoding="utf-8")


def _canonical_candidates() -> tuple[Any, dict[str, Any]]:
    pipeline = OpportunityPipeline()
    hn_item = json.loads(
        _load_payload("bc_hn_livekit_item_49570095_2026-10-01.json")
    )
    batch = pipeline.process_payloads(
        {
            "lever:vrchat": _load_payload("bc_lever_vrchat_probe_2026-10-01.json"),
            "hacker_news_who_is_hiring": json.dumps(
                {
                    "thread_id": 49522897,
                    "thread_title": "Who is hiring?",
                    "comments": [hn_item],
                },
                ensure_ascii=False,
            ),
        },
        now_iso="2026-10-01",
        run_id="bc-final-canary-2026-10-01",
        status_codes={"lever:vrchat": 200, "hacker_news_who_is_hiring": 200},
    )
    selected = {item.id: item for item in batch.opportunities if item.id in NEW_CANDIDATE_IDS}
    if set(selected) != set(NEW_CANDIDATE_IDS):
        raise RuntimeError(
            "canonical pipeline did not reproduce the exact three new canary IDs: "
            f"{sorted(selected)}"
        )
    # Validate the frozen multi-source supply gate against the same corrected
    # offline replay that was reviewed before this canary. The live write path
    # must never depend on the source merely producing three parseable rows.
    replay_result = replay(FIXTURE_DIR / "bc_clean_candidate_replay_2026-10-01.json")
    if replay_result["gate_counts"].get("For_You") != 6:
        raise RuntimeError(
            "frozen candidate replay no longer clears the six-candidate gate: "
            f"{replay_result['gate_counts']}"
        )
    if set(replay_result["for_you_employers"]) != {"Canonical", "Vrchat", "LiveKit"}:
        raise RuntimeError("frozen candidate replay no longer spans the audited employers")
    if {
        item["source_id"].split(":", 1)[0] for item in replay_result["candidates"]
    } != {"greenhouse", "lever", "hacker_news_who_is_hiring"}:
        raise RuntimeError("frozen candidate replay no longer spans three source families")
    # Independently verify that newly normalized payloads still clear the
    # persisted role/geography/access gates before opening a database session.
    from matching.recommendation_foundation import (
        classify_application_access,
        classify_founder_geography,
        classify_required_credentials,
        classify_role_relevance,
    )
    from opportunity.persistence import _build_opp_data

    for opportunity_id, opportunity in selected.items():
        stored = _build_opp_data(opportunity, is_stale=False)
        credential_state, _ = classify_required_credentials(
            f"{opportunity.title}\n{opportunity.description}"
        )
        role = classify_role_relevance(opportunity.title, opportunity.description)
        geography, _ = classify_founder_geography(
            title=opportunity.title,
            description=opportunity.description,
            location_country=opportunity.location_country,
            location_city=opportunity.location_city,
            location_region=opportunity.location_region,
            work_mode=opportunity.work_mode.value,
            remote_scope=opportunity.remote_scope.value,
            remote_scope_regions=opportunity.remote_scope_regions,
        )
        access = classify_application_access(
            opportunity.source,
            opportunity.source_url,
            opportunity.canonical_outbound_url or opportunity.source_url,
        )
        if role.classification not in {"core", "adjacent"}:
            raise RuntimeError(f"candidate role gate changed for {opportunity_id}")
        if geography not in {"eligible", "likely_eligible"}:
            raise RuntimeError(f"candidate geography gate changed for {opportunity_id}: {geography}")
        if credential_state is not None:
            raise RuntimeError(
                f"candidate credential gate changed for {opportunity_id}: {credential_state}"
            )
        if access.access not in {"direct_free", "free_intermediary"} or not access.application_url:
            raise RuntimeError(f"candidate access gate changed for {opportunity_id}: {access.access}")
        if stored["application_access"] != access.access:
            raise RuntimeError(f"persistence access mapping changed for {opportunity_id}")
    single_candidates = replace(
        batch,
        opportunities=tuple(selected[opportunity_id] for opportunity_id in NEW_CANDIDATE_IDS),
        total_unique_opportunities=len(NEW_CANDIDATE_IDS),
    )
    return single_candidates, selected


def run_canary(*, execute: bool) -> dict[str, Any]:
    if not execute:
        raise ValueError("production canary requires the explicit --execute flag")

    loaded_pack = load_founder_pack(CANONICAL_REPO_TRUTH_PACK)
    batch, opportunities = _canonical_candidates()
    engine = get_engine()
    Session = get_session_factory(engine)
    inserted: list[str] = []
    unchanged: list[str] = []
    capacity_measurements: list[dict[str, Any]] = []

    with Session() as session:
        before_capacity = inspect_connection(session.connection())
        before_bytes = before_capacity.database_size_bytes
        if before_bytes >= TRANSACTION_ABORT_BYTES:
            raise RuntimeError(f"capacity abort before canary: {before_bytes} bytes")

        active_queue = int(
            session.query(WorkerJobRecord)
            .filter(WorkerJobRecord.status.in_(("PENDING", "RETRY", "RUNNING")))
            .count()
        )
        if active_queue:
            raise RuntimeError(f"refusing canary while {active_queue} queue jobs are active")

        founder_before = _founder_state_snapshot(session)
        new_existing = dict(
            session.query(OpportunityRecord.id, OpportunityRecord.content_hash)
            .filter(OpportunityRecord.id.in_(NEW_CANDIDATE_IDS))
            .all()
        )
        mismatched_existing = [
            opportunity_id
            for opportunity_id, content_hash in new_existing.items()
            if content_hash != opportunities[opportunity_id].content_hash
        ]
        if mismatched_existing:
            raise RuntimeError(
                "existing canary identity has changed content; refusing overwrite: "
                + ",".join(mismatched_existing)
            )
        existing_rows = {
            row.id: row
            for row in session.query(
                OpportunityRecord.id,
                OpportunityRecord.title,
                OpportunityRecord.organization,
                OpportunityRecord.source_url,
            )
            .filter(OpportunityRecord.id.in_(EXISTING_CANDIDATE_IDS))
            .all()
        }
        if set(existing_rows) != set(EXISTING_CANDIDATE_IDS):
            raise RuntimeError("the three frozen Canonical candidates are not all present")
        replay_candidates = {
            item["opportunity_id"]: item
            for item in json.loads(
                _load_payload("bc_clean_candidate_replay_2026-10-01.json")
            )["candidates"]
        }
        for opportunity_id, row in existing_rows.items():
            expected = replay_candidates[opportunity_id]
            if (
                row.title != expected["title"]
                or row.organization != expected["organization"]
                or row.source_url != expected["source_url"]
            ):
                raise RuntimeError(
                    f"existing candidate identity/source changed; refusing refresh: {opportunity_id}"
                )
        founder_negative = session.query(FounderFeedbackRecord.opportunity_id).filter(
            FounderFeedbackRecord.opportunity_id.in_(REFRESH_IDS),
            FounderFeedbackRecord.feedback_label.in_(
                ("bad_match", "irrelevant_role", "eligibility_wrong", "clearance_required")
            ),
        ).all()
        if founder_negative:
            raise RuntimeError("a frozen candidate now has explicit negative Founder feedback")
        terminal_activity = session.query(FounderActivityEventRecord.id).filter(
            FounderActivityEventRecord.opportunity_id.in_(REFRESH_IDS),
            FounderActivityEventRecord.action_type.in_(
                ("mark_applied", "mark_submitted", "reject", "dismiss")
            ),
        ).all()
        terminal_triage = session.query(FounderTriageStateRecord.opportunity_id).filter(
            FounderTriageStateRecord.opportunity_id.in_(REFRESH_IDS),
            FounderTriageStateRecord.state.in_(
                ("applied", "submitted", "rejected", "dismissed")
            ),
        ).all()
        if terminal_activity or terminal_triage:
            raise RuntimeError("a frozen candidate now has terminal Founder activity or triage")
        session.rollback()

    # Evaluate before the first persistence write. Each id is then committed
    # separately so physical capacity is measured after every admitted job.
    repository_session = Session()
    repository = StorageRepository(repository_session)
    try:
        for opportunity_id in NEW_CANDIDATE_IDS:
            with engine.connect() as connection:
                current_bytes = inspect_connection(connection).database_size_bytes
            if current_bytes >= TRANSACTION_ABORT_BYTES:
                raise RuntimeError(f"capacity abort before {opportunity_id}: {current_bytes} bytes")
            single = replace(
                batch,
                opportunities=(opportunities[opportunity_id],),
                total_unique_opportunities=1,
            )
            result = persist_evaluated_batch(
                single,
                repository,
                truth_graph=loaded_pack.graph,
                truth_pack_hash=loaded_pack.truth_pack_hash,
            )
            if (
                tuple(result.inserted_ids + result.unchanged_ids) != (opportunity_id,)
                or result.updated_ids
            ):
                raise RuntimeError(
                    f"expected one canonical insert or exact unchanged row for {opportunity_id}; got {result}"
                )
            inserted.extend(result.inserted_ids)
            unchanged.extend(result.unchanged_ids)
            with engine.connect() as connection:
                after_one = inspect_connection(connection).database_size_bytes
            capacity_measurements.append(
                {
                    "opportunity_id": opportunity_id,
                    "database_bytes_after_candidate": after_one,
                }
            )
            if after_one >= TRANSACTION_ABORT_BYTES:
                raise RuntimeError(
                    f"capacity abort after {opportunity_id}: {after_one} bytes"
                )

        # Refresh only the six individually audited IDs under the current pack.
        with repository_session.begin():
            for opportunity_id in REFRESH_IDS:
                projected = refresh_opportunity_projection(
                    repository_session,
                    opportunity_id=opportunity_id,
                    truth_graph=loaded_pack.graph,
                    truth_pack_hash=loaded_pack.truth_pack_hash,
                    reclassify_role=True,
                )
                if projected is None:
                    raise RuntimeError(f"projection refresh returned no row for {opportunity_id}")

        states = {
            opportunity_id: state
            for opportunity_id, state in repository_session.query(
                FeedProjectionRecord.opportunity_id,
                FeedProjectionRecord.recommendation_state,
            ).filter(
                FeedProjectionRecord.opportunity_id.in_(REFRESH_IDS),
                FeedProjectionRecord.truth_pack_hash == loaded_pack.truth_pack_hash,
            ).all()
        }
        if states != {opportunity_id: "for_you" for opportunity_id in REFRESH_IDS}:
            raise RuntimeError(f"bounded refresh did not produce six For You rows: {states}")

        after_capacity = inspect_connection(repository_session.connection())
        after_bytes = after_capacity.database_size_bytes
        if after_bytes >= TRANSACTION_ABORT_BYTES:
            raise RuntimeError(f"capacity abort after projection refresh: {after_bytes} bytes")
        founder_after = _founder_state_snapshot(repository_session)
        if founder_before != founder_after:
            raise RuntimeError("Founder state changed during the bounded candidate canary")
        active_after = int(
            repository_session.query(WorkerJobRecord)
            .filter(WorkerJobRecord.status.in_(("PENDING", "RETRY", "RUNNING")))
            .count()
        )
        if active_after != active_queue:
            raise RuntimeError("queue state changed during the bounded candidate canary")

        return {
            "committed": True,
            "truth_pack_hash": loaded_pack.truth_pack_hash,
            "database_bytes_before": before_bytes,
            "database_bytes_after": after_bytes,
            "database_bytes_delta": after_bytes - before_bytes,
            "transaction_abort_bytes": TRANSACTION_ABORT_BYTES,
            "queue_active_before": active_queue,
            "queue_active_after": active_after,
            "inserted_ids": inserted,
            "unchanged_ids": unchanged,
            "refreshed_ids": list(REFRESH_IDS),
            "projection_states": states,
            "capacity_after_each_insert": capacity_measurements,
            "founder_state_unchanged": True,
            "founder_state_counts": {
                name: value["row_count"] for name, value in founder_before.items()
            },
            "source_families_added": ["Lever", "Hacker News/Ashby"],
        }
    except Exception as error:
        raise PartialCanaryFailure(
            error,
            inserted_ids=inserted,
            unchanged_ids=unchanged,
            capacity_measurements=capacity_measurements,
        ) from error
    finally:
        repository_session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(run_canary(execute=args.execute), sort_keys=True))
    except Exception as error:  # emit only a concise, secret-free failure
        result: dict[str, Any] = {"error": f"{type(error).__name__}: {error}"}
        if isinstance(error, PartialCanaryFailure):
            result.update(
                {
                    "partial": True,
                    "inserted_ids": error.inserted_ids,
                    "unchanged_ids": error.unchanged_ids,
                    "capacity_after_each_insert": error.capacity_measurements,
                }
            )
        else:
            result["committed"] = False
        print(json.dumps(result, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
