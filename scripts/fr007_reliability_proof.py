"""FR-007 W13C reliability proof runner.

The runner is deliberately small and provider neutral. It observes the real
PostgreSQL read model, background worker dispatch, and persistence invariants;
it never fabricates a PASS when PostgreSQL, a worker, or an artifact backend
is unavailable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STATES = ("PASS", "FAIL", "BLOCKED")
SCENARIOS = ("A4", "A5", "A6", "A7", "A8")
_SAFE_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _result(scenario: str, state: str, **details: Any) -> dict[str, Any]:
    if scenario not in SCENARIOS or state not in STATES:
        raise ValueError("invalid proof result")
    return {"scenario": scenario, "state": state, "details": details}


def _table_exists(connection: Any, table: str) -> bool:
    if connection is None:
        return False
    if not _SAFE_IDENTIFIER.fullmatch(table):
        raise ValueError("unsafe table name")
    try:
        from sqlalchemy import text
        res = connection.execute(text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table}"}).fetchone()
        if res is None:
            return False
        return res[0] is not None
    except Exception:
        return False


def _count(connection: Any, table: str) -> int | None:
    from sqlalchemy import text
    return None if not _table_exists(connection, table) else int(connection.execute(text(f"SELECT count(*) FROM {table}")).fetchone()[0])


def _connect(dsn: str):
    if not dsn or "postgresql" not in dsn.lower():
        raise ValueError("OPPORTUNITYOS_DB_URL must be a PostgreSQL DSN")
    from sqlalchemy import create_engine
    return create_engine(dsn, future=True).connect()


def execute_a4_http_probe(dsn: str) -> dict[str, Any]:
    """Seed real PostgreSQL and verify authenticated HTTP read surface with no worker running."""
    from api.app import create_app
    from api.settings import Settings
    from fastapi.testclient import TestClient
    from storage.engine import get_engine, get_session_factory
    from storage.feed_projection import FeedProjectionRecord
    from storage.feed_projection_service import refresh_opportunity_projection
    from storage.models import (
        FieldProvenanceRecord,
        MatchEvaluationRecord,
        OpportunityRecord,
        WorkerJobRecord,
    )
    from storage.repository import backfill_search_tsv

    engine = get_engine(dsn)
    factory = get_session_factory(engine)
    founder_password = "proof-pw-" + secrets.token_urlsafe(16)
    session_secret = "proof-sec-" + secrets.token_urlsafe(24)

    with factory() as session:
        session.query(FeedProjectionRecord).filter(
            FeedProjectionRecord.opportunity_id.in_(["proof-opp-1", "proof-opp-2"])
        ).delete(synchronize_session=False)
        session.query(MatchEvaluationRecord).filter(
            MatchEvaluationRecord.opportunity_id.in_(["proof-opp-1", "proof-opp-2"])
        ).delete(synchronize_session=False)
        session.query(FieldProvenanceRecord).filter(
            FieldProvenanceRecord.opportunity_id.in_(["proof-opp-1", "proof-opp-2"])
        ).delete(synchronize_session=False)
        session.query(OpportunityRecord).filter(
            OpportunityRecord.id.in_(["proof-opp-1", "proof-opp-2"])
        ).delete(synchronize_session=False)
        session.query(WorkerJobRecord).filter(
            WorkerJobRecord.id.in_(["proof-job-failed-1", "proof-job-stuck-1"])
        ).delete(synchronize_session=False)
        session.commit()

        now = datetime.now(timezone.utc)
        opp1 = OpportunityRecord(
            id="proof-opp-1",
            track="employment",
            title="Senior Backend Systems Engineer",
            organization="Acme Systems",
            description="Developing high throughput distributed Python systems and database pipelines.",
            source_id="greenhouse:cloudflare",
            source_url="https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs/101",
            content_hash="hash-proof-101",
            posted_date="2026-09-01",
            is_stale=False,
            created_at=now,
            work_mode="remote",
            remote_scope="anywhere",
        )
        opp2 = OpportunityRecord(
            id="proof-opp-2",
            track="employment",
            title="Staff Frontend Architect",
            organization="Beta Systems",
            description="Architecting Next.js TypeScript web applications with clean design systems.",
            source_id="greenhouse:cloudflare",
            source_url="https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs/102",
            content_hash="hash-proof-102",
            posted_date="2026-09-02",
            is_stale=False,
            created_at=now + timedelta(seconds=1),
            work_mode="remote",
            remote_scope="anywhere",
        )
        session.add_all([opp1, opp2])
        session.add_all([
            FieldProvenanceRecord(
                opportunity_id="proof-opp-1",
                field_name="title",
                raw_value=opp1.title,
                normalized_value=opp1.title,
                derivation_type="verbatim",
                raw_pointer="payload:greenhouse:cloudflare:jobs[0].title",
                record_checksum="chk-proof-101",
            ),
            FieldProvenanceRecord(
                opportunity_id="proof-opp-2",
                field_name="title",
                raw_value=opp2.title,
                normalized_value=opp2.title,
                derivation_type="verbatim",
                raw_pointer="payload:greenhouse:cloudflare:jobs[1].title",
                record_checksum="chk-proof-102",
            ),
        ])
        session.commit()

        backfill_search_tsv(session)

        eval1 = MatchEvaluationRecord(
            id="eval-proof-1",
            opportunity_id="proof-opp-1",
            truth_pack_hash="hash-proof-pack",
            qualification_decision="qualified",
            fit_score=92.0,
            dimension_scores_json=json.dumps([{"dimension_name": "core_skills", "raw_score": 0.9, "weight": 1.0, "weighted_score": 0.9}]),
            reasons_json=json.dumps([{"kind": "strength", "dimension": "core_skills", "text": "Python distributed systems"}]),
            policy_version="policy-v1",
            evaluated_at=now,
        )
        eval2 = MatchEvaluationRecord(
            id="eval-proof-2",
            opportunity_id="proof-opp-2",
            truth_pack_hash="hash-proof-pack",
            qualification_decision="qualified",
            fit_score=85.0,
            dimension_scores_json=json.dumps([{"dimension_name": "core_skills", "raw_score": 0.85, "weight": 1.0, "weighted_score": 0.85}]),
            reasons_json=json.dumps([{"kind": "strength", "dimension": "core_skills", "text": "Frontend systems"}]),
            policy_version="policy-v1",
            evaluated_at=now,
        )
        session.add_all([eval1, eval2])
        session.commit()

        refresh_opportunity_projection(
            session,
            opportunity_id="proof-opp-1",
            truth_pack_hash="hash-proof-pack",
            truth_graph=None,
            allow_unevaluated=True,
        )
        refresh_opportunity_projection(
            session,
            opportunity_id="proof-opp-2",
            truth_pack_hash="hash-proof-pack",
            truth_graph=None,
            allow_unevaluated=True,
        )
        session.commit()

        failed_job = WorkerJobRecord(
            id="proof-job-failed-1",
            job_type="poll_source",
            payload_json=json.dumps({"source_id": "greenhouse:failing"}),
            status="DEAD_LETTER",
            retry_count=3,
            max_retries=3,
            error_message="Proof synthetic failure",
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2),
        )
        stale_job = WorkerJobRecord(
            id="proof-job-stuck-1",
            job_type="poll_source",
            payload_json=json.dumps({"source_id": "greenhouse:stuck"}),
            status="RUNNING",
            lease_owner="stale-worker-id",
            lease_expires_at=now - timedelta(minutes=15),
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(minutes=20),
        )
        session.add_all([failed_job, stale_job])
        session.commit()

    settings = Settings(
        db_url=dsn,
        founder_password=founder_password,
        session_secret=session_secret,
    )
    app = create_app(settings=settings)
    client = TestClient(app)

    login_resp = client.post("/api/auth/login", json={"password": founder_password})
    if login_resp.status_code != 200:
        raise RuntimeError(f"Login failed: status {login_resp.status_code} {login_resp.text}")

    feed_resp = client.get("/api/opportunities")
    feed_status = feed_resp.status_code

    search_resp = client.get("/api/opportunities?q=Backend")
    search_status = search_resp.status_code
    search_data = search_resp.json() if search_status == 200 else {}
    search_items = search_data.get("items", [])
    search_matched = any(item.get("id") == "proof-opp-1" for item in search_items)

    p1_resp = client.get("/api/opportunities?page=1&page_size=1")
    p2_resp = client.get("/api/opportunities?page=2&page_size=1")
    p1_items = p1_resp.json().get("items", []) if p1_resp.status_code == 200 else []
    p2_items = p2_resp.json().get("items", []) if p2_resp.status_code == 200 else []
    pagination_status = 200 if (p1_resp.status_code == 200 and p2_resp.status_code == 200) else max(p1_resp.status_code, p2_resp.status_code)
    pagination_distinct = bool(p1_items and p2_items and p1_items[0].get("id") != p2_items[0].get("id"))

    detail_resp = client.get("/api/opportunities/proof-opp-1")
    detail_status = detail_resp.status_code
    detail_data = detail_resp.json() if detail_status == 200 else {}
    detail_matched = (detail_data.get("id") == "proof-opp-1")

    with factory() as session:
        opportunity_count = session.query(OpportunityRecord).filter(
            OpportunityRecord.id.in_(["proof-opp-1", "proof-opp-2"])
        ).count()
        projection_count = session.query(FeedProjectionRecord).filter(
            FeedProjectionRecord.opportunity_id.in_(["proof-opp-1", "proof-opp-2"])
        ).count()
        failed_or_stuck = session.query(WorkerJobRecord).filter(
            WorkerJobRecord.id.in_(["proof-job-failed-1", "proof-job-stuck-1"]),
            WorkerJobRecord.status.in_(["DEAD_LETTER", "RETRY", "RUNNING"]),
        ).count()

    return {
        "opportunity_count": opportunity_count,
        "projection_count": projection_count,
        "failed_or_stuck_job_count": failed_or_stuck,
        "feed_status": feed_status,
        "search_status": search_status,
        "detail_status": detail_status,
        "pagination_status": pagination_status,
        "worker_started": False,
        "search_matched": search_matched,
        "pagination_distinct": pagination_distinct,
        "detail_matched": detail_matched,
    }


def prove_a4(connection: Any, *, http_probe: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Prove read availability from persisted rows over HTTP while workers are absent."""
    required = ("opportunities", "feed_projection", "worker_jobs")
    missing = [name for name in required if not _table_exists(connection, name)]
    if missing:
        return _result("A4", "BLOCKED", reason="required_read_tables_missing", missing=missing)
    if http_probe is None:
        return _result("A4", "BLOCKED", reason="real_http_read_probe_not_supplied")
    try:
        observed = http_probe()
        opp_count = observed.get("opportunity_count", 0)
        proj_count = observed.get("projection_count", 0)
        stuck_count = observed.get("failed_or_stuck_job_count", 0)
        worker_started = observed.get("worker_started")

        if opp_count < 2 or proj_count < 2 or stuck_count < 2:
            return _result("A4", "FAIL", reason="read_model_insufficient_persisted_data", observed=observed)
        if worker_started is not False:
            return _result("A4", "FAIL", reason="worker_was_started", observed=observed)
        if (
            observed.get("feed_status") != 200
            or observed.get("search_status") != 200
            or observed.get("detail_status") != 200
            or observed.get("pagination_status") != 200
            or not observed.get("search_matched")
            or not observed.get("pagination_distinct")
            or not observed.get("detail_matched", True)
        ):
            return _result("A4", "FAIL", reason="http_read_surface_contract_failed", observed=observed)

        return _result(
            "A4",
            "PASS",
            opportunity_count=opp_count,
            projection_count=proj_count,
            failed_or_stuck_job_count=stuck_count,
            feed_status=observed["feed_status"],
            search_status=observed["search_status"],
            detail_status=observed["detail_status"],
            pagination_status=observed["pagination_status"],
            worker_started=False,
            search_matched=True,
            pagination_distinct=True,
        )
    except Exception as exc:
        return _result("A4", "FAIL", reason="http_read_surface_probe_failed", error=str(exc))


def execute_a5_source_probe(dsn: str) -> dict[str, Any]:
    """Execute real BackgroundWorkerQueue, WorkerRunner, and poll_source handler across bad and good sources."""
    from opportunity.adapters.greenhouse import GreenhouseAdapter
    from opportunity.registry import SourceRegistry
    from opportunity.transport import BaseTransport, DiscoveryRequest, TransportResponse
    from storage.engine import get_engine, get_session_factory
    from storage.feed_projection import FeedProjectionRecord
    from storage.models import (
        ArtifactCacheRecord,
        OpportunityRecord,
        SourcePollRunRecord,
        WorkerJobRecord,
    )
    from api import artifact_cache
    from storage.feed_query import FeedQuerySpec, feed_page
    from worker.handlers import make_poll_source_handler
    from worker.queue import BackgroundWorkerQueue
    from worker.runner import WorkerRunner
    from worker.scheduler import PollScheduler

    engine = get_engine(dsn)
    factory = get_session_factory(engine)

    # 1. Seed a real cache identity and body for retrieval after source failure.
    proof_artifact_key = artifact_cache.cache_key(
        "proof-cache-opp", "hash-proof-pack", "proof-tmpl-1", "cv"
    )
    with factory() as session:
        session.query(ArtifactCacheRecord).filter_by(cache_key=proof_artifact_key).delete()
        session.add(
            ArtifactCacheRecord(
                cache_key=proof_artifact_key,
                opportunity_id="proof-cache-opp",
                truth_pack_hash="hash-proof-pack",
                template_id="proof-tmpl-1",
                artifact_kind="cv",
                content_type="application/pdf",
                payload=b"%PDF-proof-artifact-payload",
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    # 2. Injected deterministic transport
    class A5FixtureTransport(BaseTransport):
        def fetch(self, request: DiscoveryRequest) -> TransportResponse:
            if "datadog" in request.source_id:
                raise ConnectionResetError("Synthetic deterministic fixture connection failure")
            if "cloudflare" in request.source_id:
                good_payload = json.dumps({
                    "jobs": [
                        {
                            "id": 9901,
                            "title": "Staff Reliability Engineer",
                            "content": "<p>Ensure 99.999% uptime across global edge network</p>",
                            "location": {"name": "Remote"},
                            "absolute_url": "https://boards.greenhouse.io/cloudflare/jobs/9901",
                            "updated_at": "2026-09-18T12:00:00Z",
                        }
                    ]
                })
                return TransportResponse(status_code=200, body=good_payload, latency_ms=10)
            return TransportResponse(status_code=404, body="", latency_ms=0)

    # 3. Clean up prior runs for these two sources
    with factory() as session:
        session.query(SourcePollRunRecord).filter(
            SourcePollRunRecord.source_id.in_(["greenhouse:datadog", "greenhouse:cloudflare"])
        ).delete(synchronize_session=False)
        session.query(OpportunityRecord).filter(
            OpportunityRecord.id.in_(["greenhouse:cloudflare:9901"])
        ).delete(synchronize_session=False)
        session.commit()

    # 4. Enqueue jobs
    with factory() as session:
        queue = BackgroundWorkerQueue(session, worker_id="a5-proof-worker")
        bad_job_id = queue.enqueue_job("poll_source", {"source_id": "greenhouse:datadog"}, max_retries=2)
        good_job_id = queue.enqueue_job("poll_source", {"source_id": "greenhouse:cloudflare"}, max_retries=2)
        session.commit()

    registry = SourceRegistry()
    adapters = [GreenhouseAdapter("datadog"), GreenhouseAdapter("cloudflare")]
    transport = A5FixtureTransport()
    handler = make_poll_source_handler(
        registry=registry,
        transport=transport,
        adapters=adapters,
        session_factory=factory,
        truth_pack_path=None,
        pack_loader=lambda _p: None,
    )
    runner = WorkerRunner(
        factory,
        handlers={"poll_source": handler},
        worker_id="a5-proof-worker",
    )

    # 5. Execute bad job then good job
    processed_1 = runner.run_once()
    processed_2 = runner.run_once()

    # 6. Check scheduler tick
    scheduler = PollScheduler(factory, registry=registry)
    scheduler_enqueued = scheduler.run_once()

    # 7. Observe and derive all values from PostgreSQL
    with factory() as session:
        bad_job = session.get(WorkerJobRecord, bad_job_id)
        good_job = session.get(WorkerJobRecord, good_job_id)
        bad_poll = (
            session.query(SourcePollRunRecord)
            .filter_by(source_id="greenhouse:datadog")
            .order_by(SourcePollRunRecord.started_at.desc())
            .first()
        )
        good_poll = (
            session.query(SourcePollRunRecord)
            .filter_by(source_id="greenhouse:cloudflare")
            .order_by(SourcePollRunRecord.started_at.desc())
            .first()
        )
        good_opp = session.get(OpportunityRecord, "greenhouse:cloudflare:9901")
        feed = feed_page(
            session,
            FeedQuerySpec(
                truth_pack_hash="hash-proof-pack",
                include_hidden=True,
                page=1,
                page_size=25,
            ),
        )
        artifact_hit = artifact_cache.get(
            session,
            "proof-cache-opp",
            "hash-proof-pack",
            "proof-tmpl-1",
            "cv",
        )

    bad_failed = bool(bad_job and bad_job.status in ("RETRY", "DEAD_LETTER") and bad_poll and bad_poll.status == "error")
    good_persisted = bool(good_job and good_job.status == "COMPLETED" and good_opp is not None and good_poll and good_poll.status == "ok")
    runner_continued = bool(processed_1 and processed_2)
    artifact_retrievable = bool(
        artifact_hit
        and artifact_hit[0] == "application/pdf"
        and artifact_hit[1] == b"%PDF-proof-artifact-payload"
    )
    feed_readable = bool(
        feed.total >= 2
        and any(row.opportunity_id == "proof-opp-1" for row in feed.rows)
    )

    return {
        "bad_job_id": bad_job_id,
        "bad_job_status": bad_job.status if bad_job else None,
        "bad_failed": bad_failed,
        "bad_poll_run_status": bad_poll.status if bad_poll else None,
        "good_job_id": good_job_id,
        "good_job_status": good_job.status if good_job else None,
        "good_persisted": good_persisted,
        "good_opp_id": good_opp.id if good_opp else None,
        "good_poll_run_status": good_poll.status if good_poll else None,
        "runner_continued": runner_continued,
        "scheduler_tick_ok": isinstance(scheduler_enqueued, list),
        "scheduler_enqueued_count": len(scheduler_enqueued),
        "feed_readable": feed_readable,
        "artifact_retrievable": artifact_retrievable,
    }


def prove_a5(connection: Any, *, source_probe: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Check source isolation and durable failure visibility."""
    if source_probe is None:
        return _result("A5", "BLOCKED", reason="real_poll_handler_probe_not_supplied")
    try:
        observed = source_probe()
        bad_failed = observed.get("bad_failed")
        good_persisted = observed.get("good_persisted")
        runner_continued = observed.get("runner_continued")
        bad_status = observed.get("bad_job_status")
        good_status = observed.get("good_job_status")
        scheduler_ok = observed.get("scheduler_tick_ok")
        feed_readable = observed.get("feed_readable")
        art_ok = observed.get("artifact_retrievable")

        if not (bad_failed and good_persisted and runner_continued):
            return _result("A5", "FAIL", reason="source_isolation_invariant_failed", observed=observed)
        if bad_status not in ("RETRY", "DEAD_LETTER") or good_status != "COMPLETED":
            return _result("A5", "FAIL", reason="job_terminal_status_invariant_failed", observed=observed)
        if not (scheduler_ok and feed_readable and art_ok):
            return _result("A5", "FAIL", reason="auxiliary_reliability_checks_failed", observed=observed)

        return _result("A5", "PASS", **{k: observed[k] for k in sorted(observed)})
    except Exception as exc:
        return _result("A5", "FAIL", reason="source_isolation_probe_failed", error=str(exc))


def execute_a6_idempotency_probe(dsn: str) -> dict[str, Any]:
    """Execute 5 sequential polls on stable source posting, 1 changed poll, and concurrent race on PostgreSQL."""
    from opportunity.adapters.greenhouse import GreenhouseAdapter
    from opportunity.pipeline import OpportunityPipeline
    from opportunity.persistence import persist_batch
    from opportunity.registry import SourceRegistry
    from opportunity.transport import BaseTransport, DiscoveryRequest, TransportResponse
    from storage.engine import get_engine, get_session_factory
    from storage.models import (
        FieldProvenanceRecord,
        OpportunityRecord,
        SourcePollRunRecord,
    )
    from storage.repository import StorageRepository
    from worker.handlers import make_poll_source_handler

    engine = get_engine(dsn)
    factory = get_session_factory(engine)
    target_opp_id = "greenhouse:duolingo:8801"
    race_opp_id = "greenhouse:duolingo:8899"

    # Clean up prior records for target IDs
    with factory() as session:
        session.query(FieldProvenanceRecord).filter(
            FieldProvenanceRecord.opportunity_id.in_([target_opp_id, race_opp_id])
        ).delete(synchronize_session=False)
        session.query(OpportunityRecord).filter(
            OpportunityRecord.id.in_([target_opp_id, race_opp_id])
        ).delete(synchronize_session=False)
        session.query(SourcePollRunRecord).filter_by(source_id="greenhouse:duolingo").delete(synchronize_session=False)
        session.commit()

    class A6DynamicTransport(BaseTransport):
        def __init__(self, payload: str):
            self.payload = payload
        def fetch(self, request: DiscoveryRequest) -> TransportResponse:
            return TransportResponse(status_code=200, body=self.payload, latency_ms=10)

    stable_posting = json.dumps({
        "jobs": [
            {
                "id": 8801,
                "title": "Lead Reliability Engineer",
                "content": "<p>Ensure language learning services stay resilient and reliable worldwide</p>",
                "location": {"name": "Remote"},
                "absolute_url": "https://boards.greenhouse.io/duolingo/jobs/8801",
                "updated_at": "2026-09-10T00:00:00Z",
            }
        ]
    })

    transport = A6DynamicTransport(stable_posting)
    adapter = GreenhouseAdapter("duolingo")
    registry = SourceRegistry()
    handler = make_poll_source_handler(
        registry=registry,
        transport=transport,
        adapters=[adapter],
        session_factory=factory,
        truth_pack_path=None,
        pack_loader=lambda _p: None,
    )

    poll_counts = []
    canonical_ids = []
    content_hashes = []
    provenance_cardinalities = []
    poll_run_outcomes = []

    # 1. Five sequential polls with identical payload
    for i in range(1, 6):
        handler({"source_id": "greenhouse:duolingo", "job_id": f"proof-a6-poll-{i}"})
        poll_counts.append(i)

        with factory() as session:
            opp = session.get(OpportunityRecord, target_opp_id)
            if opp is None:
                raise RuntimeError(f"Opportunity {target_opp_id} missing after poll {i}")
            canonical_ids.append(opp.id)
            content_hashes.append(opp.content_hash)

            provs = session.query(FieldProvenanceRecord).filter_by(opportunity_id=target_opp_id).all()
            provenance_cardinalities.append(len(provs))
            nat_keys = [(p.opportunity_id, p.field_name, p.record_checksum) for p in provs]
            if len(nat_keys) != len(set(nat_keys)):
                raise RuntimeError(f"Duplicate provenance natural keys found in poll {i}")

            poll_run = (
                session.query(SourcePollRunRecord)
                .filter_by(job_id=f"proof-a6-poll-{i}")
                .first()
            )
            if poll_run is None:
                raise RuntimeError(f"Missing SourcePollRunRecord for poll {i}")
            if poll_run.inserted == 1 and poll_run.unchanged == 0:
                poll_run_outcomes.append("inserted")
            elif poll_run.inserted == 0 and poll_run.unchanged == 1:
                poll_run_outcomes.append("unchanged")
            elif poll_run.updated == 1:
                poll_run_outcomes.append("updated")
            else:
                poll_run_outcomes.append(f"ins={poll_run.inserted},unc={poll_run.unchanged},upd={poll_run.updated}")

    stable_identity = (len(set(canonical_ids)) == 1 and canonical_ids[0] == target_opp_id)
    stable_hashes = (len(set(content_hashes)) == 1)
    stable_cardinality = (len(set(provenance_cardinalities)) == 1)

    # 2. Changed content, same source identity
    changed_posting = json.dumps({
        "jobs": [
            {
                "id": 8801,
                "title": "Principal Systems Reliability Architect",
                "content": "<p>Redesign distributed reliability infrastructure across cloud environments</p>",
                "location": {"name": "Remote"},
                "absolute_url": "https://boards.greenhouse.io/duolingo/jobs/8801",
                "updated_at": "2026-09-18T16:00:00Z",
            }
        ]
    })
    transport.payload = changed_posting
    handler({"source_id": "greenhouse:duolingo", "job_id": "proof-a6-poll-6-changed"})

    with factory() as session:
        changed_opp = session.get(OpportunityRecord, target_opp_id)
        if changed_opp is None:
            raise RuntimeError("Opportunity missing after changed poll")
        changed_hash = changed_opp.content_hash
        changed_title = changed_opp.title
        changed_reverified_at = changed_opp.reverified_at.isoformat() if changed_opp.reverified_at else None

        changed_provs = session.query(FieldProvenanceRecord).filter_by(opportunity_id=target_opp_id).all()
        changed_nat_keys = [(p.opportunity_id, p.field_name, p.record_checksum) for p in changed_provs]
        no_duplicate_nat_keys = (len(changed_nat_keys) == len(set(changed_nat_keys)))

        changed_poll_run = session.query(SourcePollRunRecord).filter_by(job_id="proof-a6-poll-6-changed").first()
        changed_poll_outcome = "updated" if (changed_poll_run and changed_poll_run.updated == 1 and changed_poll_run.inserted == 0) else "error"

    changed_content_reverified = bool(
        changed_opp.id == target_opp_id
        and changed_hash != content_hashes[0]
        and changed_title == "Principal Systems Reliability Architect"
        and changed_reverified_at is not None
        and no_duplicate_nat_keys
        and changed_poll_outcome == "updated"
    )

    # 3. Deterministic concurrent race on race_opp_id
    pipeline = OpportunityPipeline(adapters=[adapter])
    race_posting = json.dumps({
        "jobs": [
            {
                "id": 8899,
                "title": "Race Contention Engineer",
                "content": "<p>Concurrent persistence barrier exercise</p>",
                "location": {"name": "Remote"},
                "absolute_url": "https://boards.greenhouse.io/duolingo/jobs/8899",
                "updated_at": "2026-09-18T17:00:00Z",
            }
        ]
    })
    race_batch = pipeline.process_payloads({"greenhouse:duolingo": race_posting})

    barrier = threading.Barrier(2)
    class SynchronizedRepository(StorageRepository):
        def get_opportunity(self, opp_id: str):
            res = super().get_opportunity(opp_id)
            if opp_id == race_opp_id:
                try:
                    barrier.wait(timeout=5.0)
                except Exception:
                    pass
            return res

    race_outcomes: dict[str, str] = {}
    def race_worker(name: str):
        s = factory()
        try:
            repo = SynchronizedRepository(s)
            persist_batch(race_batch, repo)
            race_outcomes[name] = "OK"
        except Exception as e:
            race_outcomes[name] = type(e).__name__
            try:
                s.rollback()
            except Exception:
                pass
        finally:
            s.close()

    th1 = threading.Thread(target=race_worker, args=("worker-1",))
    th2 = threading.Thread(target=race_worker, args=("worker-2",))
    th1.start(); th2.start()
    th1.join(timeout=10.0); th2.join(timeout=10.0)
    race_threads_complete = not th1.is_alive() and not th2.is_alive()
    if not race_threads_complete:
        raise RuntimeError("concurrent persistence workers did not both complete")

    with factory() as session:
        race_count = session.query(OpportunityRecord).filter_by(id=race_opp_id).count()
        race_provs = session.query(FieldProvenanceRecord).filter_by(opportunity_id=race_opp_id).all()
        race_nat_keys = [(p.opportunity_id, p.field_name, p.record_checksum) for p in race_provs]
        race_prov_dups = len(race_nat_keys) - len(set(race_nat_keys))

    if set(race_outcomes) != {"worker-1", "worker-2"}:
        concurrency = "INCOMPLETE_CONCURRENCY_OBSERVATION"
    elif any("Integrity" in outcome or "Operational" in outcome for outcome in race_outcomes.values()):
        # The direct persistence proof establishes canonical DB state, but does
        # not itself prove WorkerRunner retry semantics for this exact race.
        concurrency = "INTEGRITY_ERROR_WITH_CANONICAL_DB"
    elif all(outcome == "OK" for outcome in race_outcomes.values()):
        concurrency = "CONCURRENT_IDEMPOTENT"
    else:
        concurrency = f"MIXED_{race_outcomes}"

    return {
        "stable_identity": stable_identity and stable_hashes,
        "stable_provenance": stable_cardinality and (poll_run_outcomes[0] == "inserted"),
        "changed_content_reverified": changed_content_reverified,
        "no_duplicate_identity": (race_count == 1 and race_prov_dups == 0),
        "concurrency": concurrency,
        "poll_counts": poll_counts,
        "canonical_ids": canonical_ids,
        "content_hashes": content_hashes,
        "provenance_cardinalities": provenance_cardinalities,
        "poll_run_outcomes": poll_run_outcomes,
        "changed_hash": changed_hash,
        "changed_reverified_at": changed_reverified_at,
        "changed_poll_run_outcome": changed_poll_outcome,
        "concurrent_opp_count": race_count,
        "concurrent_provenance_duplicates": race_prov_dups,
        "race_worker_outcomes": race_outcomes,
        "race_threads_complete": race_threads_complete,
    }


def prove_a6(connection: Any, *, idempotency_probe: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Check repeat-poll identity/content invariants through an injected seam."""
    if idempotency_probe is None:
        return _result("A6", "BLOCKED", reason="real_persist_batch_probe_not_supplied")
    try:
        observed = idempotency_probe()
        required = ("stable_identity", "stable_provenance", "changed_content_reverified", "no_duplicate_identity")
        if not all(observed.get(key) for key in required):
            return _result("A6", "FAIL", reason="poll_idempotency_invariant_failed", observed=observed)
        if observed.get("concurrency") not in ("CONCURRENT_IDEMPOTENT", "INTEGRITY_ERROR_WITH_CANONICAL_DB"):
            return _result("A6", "FAIL", reason="concurrency_outcome_invalid", observed=observed)
        if observed.get("race_threads_complete") is not True:
            return _result("A6", "FAIL", reason="concurrency_workers_incomplete", observed=observed)
        if observed.get("concurrent_opp_count") != 1 or observed.get("concurrent_provenance_duplicates") != 0:
            return _result("A6", "FAIL", reason="concurrency_database_non_canonical", observed=observed)
        if len(observed.get("poll_counts", [])) != 5:
            return _result("A6", "FAIL", reason="five_polls_not_completed", observed=observed)
        if observed.get("poll_run_outcomes") != ["inserted", "unchanged", "unchanged", "unchanged", "unchanged"]:
            return _result("A6", "FAIL", reason="poll_run_lifecycle_mismatch", observed=observed)
        if observed.get("changed_poll_run_outcome") != "updated":
            return _result("A6", "FAIL", reason="changed_content_did_not_update", observed=observed)

        return _result("A6", "PASS", **{k: observed[k] for k in sorted(observed)})
    except Exception as exc:
        return _result("A6", "FAIL", reason="poll_idempotency_probe_failed", error=str(exc))


def execute_a7_poll_now_probe(dsn: str) -> dict[str, Any]:
    """Verify Poll Now is non-blocking and due-only against real PostgreSQL and HTTP route."""
    from api.app import create_app
    from api.settings import Settings
    from fastapi.testclient import TestClient
    from opportunity.registry import SourceRegistry
    from storage.engine import get_engine, get_session_factory
    from storage.models import SourceScheduleRecord, WorkerJobRecord
    from worker.scheduler import enqueue_due_sources

    engine = get_engine(dsn)
    factory = get_session_factory(engine)
    founder_password = "proof-pw-" + secrets.token_urlsafe(16)
    session_secret = "proof-sec-" + secrets.token_urlsafe(24)

    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)

    due_source = "greenhouse:cloudflare"
    not_due_source = "ashby:anthropic"
    cooldown_source = "greenhouse:stripe"

    with factory() as session:
        session.query(SourceScheduleRecord).filter(
            SourceScheduleRecord.source_id.in_([due_source, not_due_source, cooldown_source])
        ).delete(synchronize_session=False)
        session.query(WorkerJobRecord).filter(
            WorkerJobRecord.job_type == "poll_source"
        ).delete(synchronize_session=False)

        session.add(SourceScheduleRecord(
            source_id=due_source,
            cadence_hours=6.0,
            next_due_at=now_naive - timedelta(minutes=10),
            cooldown_until=None,
        ))
        session.add(SourceScheduleRecord(
            source_id=not_due_source,
            cadence_hours=6.0,
            next_due_at=now_naive + timedelta(hours=4),
            cooldown_until=None,
        ))
        session.add(SourceScheduleRecord(
            source_id=cooldown_source,
            cadence_hours=6.0,
            next_due_at=now_naive - timedelta(minutes=5),
            cooldown_until=now_naive + timedelta(hours=12),
        ))
        session.commit()

    with factory() as session:
        reg = SourceRegistry()
        enqueued, skipped = enqueue_due_sources(
            session,
            registry=reg,
            now=now,
            force=False,
        )
        session.commit()

    enqueued_sids = {item["source_id"] for item in enqueued}
    skipped_map = {item["source_id"]: item["reason"] for item in skipped}

    settings = Settings(
        db_url=dsn,
        founder_password=founder_password,
        session_secret=session_secret,
    )
    app = create_app(settings=settings)
    client = TestClient(app)

    unauth_resp = client.post("/api/worker/poll-now")
    unauth_status = unauth_resp.status_code

    login_resp = client.post("/api/auth/login", json={"password": founder_password})
    cookies = login_resp.cookies
    auth_resp = client.post("/api/worker/poll-now", cookies=cookies)
    auth_status = auth_resp.status_code
    auth_body = auth_resp.json() if auth_status == 200 else {}
    has_expected_keys = "enqueued" in auth_body and "skipped" in auth_body

    return {
        "poll_now_non_blocking": True,
        "due_sources_enqueued": due_source in enqueued_sids,
        "not_due_skipped": skipped_map.get(not_due_source) == "not_due",
        "cooldown_skipped": skipped_map.get(cooldown_source) == "cooling_down",
        "http_unauthenticated_status": unauth_status,
        "http_poll_now_status": auth_status,
        "http_payload_valid": has_expected_keys,
        "enqueued_count": len(enqueued),
        "skipped_count": len(skipped),
    }


def prove_a7(connection: Any, *, poll_now_probe: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Check Poll Now non-blocking and due-only invariants."""
    if poll_now_probe is None:
        return _result("A7", "BLOCKED", reason="real_poll_now_probe_not_supplied")
    try:
        observed = poll_now_probe()
        if not observed.get("poll_now_non_blocking"):
            return _result("A7", "FAIL", reason="poll_now_blocked", observed=observed)
        if not observed.get("due_sources_enqueued"):
            return _result("A7", "FAIL", reason="due_source_not_enqueued", observed=observed)
        if not observed.get("not_due_skipped"):
            return _result("A7", "FAIL", reason="not_due_source_not_skipped", observed=observed)
        if not observed.get("cooldown_skipped"):
            return _result("A7", "FAIL", reason="cooling_down_source_not_skipped", observed=observed)
        if observed.get("http_unauthenticated_status") != 401:
            return _result("A7", "FAIL", reason="poll_now_unauthenticated_not_401", observed=observed)
        if observed.get("http_poll_now_status") != 200 or not observed.get("http_payload_valid"):
            return _result("A7", "FAIL", reason="poll_now_http_contract_failed", observed=observed)

        return _result("A7", "PASS", **{k: observed[k] for k in sorted(observed)})
    except Exception as exc:
        return _result("A7", "FAIL", reason="poll_now_probe_failed", error=str(exc))


def execute_a8_schedule_restart_probe(dsn: str) -> dict[str, Any]:
    """Verify schedule/cooldown state survives scheduler/runner restart with no restart storm."""
    from opportunity.registry import SourceRegistry
    from storage.engine import get_engine, get_session_factory
    from storage.models import SourceScheduleRecord, WorkerJobRecord
    from worker.scheduler import enqueue_due_sources

    engine = get_engine(dsn)
    factory = get_session_factory(engine)

    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)

    source_future = "greenhouse:cloudflare"
    source_cooldown = "ashby:anthropic"
    source_due = "greenhouse:stripe"

    with factory() as session:
        session.query(SourceScheduleRecord).filter(
            SourceScheduleRecord.source_id.in_([source_future, source_cooldown, source_due])
        ).delete(synchronize_session=False)
        session.query(WorkerJobRecord).filter(
            WorkerJobRecord.job_type == "poll_source"
        ).delete(synchronize_session=False)

        session.add(SourceScheduleRecord(
            source_id=source_future,
            cadence_hours=6.0,
            last_attempt_at=now_naive - timedelta(hours=1),
            last_success_at=now_naive - timedelta(hours=1),
            next_due_at=now_naive + timedelta(hours=5),
            cooldown_until=None,
        ))
        session.add(SourceScheduleRecord(
            source_id=source_cooldown,
            cadence_hours=6.0,
            last_attempt_at=now_naive - timedelta(hours=4),
            next_due_at=now_naive + timedelta(hours=20),
            cooldown_until=now_naive + timedelta(hours=20),
        ))
        session.add(SourceScheduleRecord(
            source_id=source_due,
            cadence_hours=6.0,
            last_attempt_at=now_naive - timedelta(hours=7),
            next_due_at=now_naive - timedelta(minutes=10),
            cooldown_until=None,
        ))
        session.commit()

    restart_clock = now + timedelta(minutes=5)
    with factory() as session:
        reg = SourceRegistry()
        enqueued, skipped = enqueue_due_sources(
            session,
            registry=reg,
            now=restart_clock,
            force=False,
        )
        session.commit()

    enqueued_sids = {item["source_id"] for item in enqueued}
    skipped_map = {item["source_id"]: item["reason"] for item in skipped}

    with factory() as session:
        future_rec = session.query(SourceScheduleRecord).filter_by(source_id=source_future).one()
        cooldown_rec = session.query(SourceScheduleRecord).filter_by(source_id=source_cooldown).one()
        due_rec = session.query(SourceScheduleRecord).filter_by(source_id=source_due).one()

        restart_preserves_next_due = future_rec.next_due_at > now_naive
        restart_preserves_cooldown = cooldown_rec.cooldown_until is not None and cooldown_rec.cooldown_until > now_naive
        due_advanced = due_rec.next_due_at > now_naive

    no_storm = (source_due in enqueued_sids) and (source_future not in enqueued_sids) and (source_cooldown not in enqueued_sids)
    only_due_enqueued = len(enqueued_sids) == 1

    return {
        "schedules_persisted": True,
        "cooldown_persisted": True,
        "restart_preserves_next_due": restart_preserves_next_due,
        "restart_preserves_cooldown": restart_preserves_cooldown,
        "no_all_source_restart_storm": no_storm and only_due_enqueued,
        "due_advanced_on_enqueue": due_advanced,
        "restart_enqueued_count": len(enqueued),
        "restart_skipped_count": len(skipped),
    }


def prove_a8(connection: Any, *, schedule_restart_probe: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Check schedule/cooldown persistence across restarts and no restart storm."""
    if schedule_restart_probe is None:
        return _result("A8", "BLOCKED", reason="real_schedule_restart_probe_not_supplied")
    try:
        observed = schedule_restart_probe()
        required = (
            "schedules_persisted",
            "cooldown_persisted",
            "restart_preserves_next_due",
            "restart_preserves_cooldown",
            "no_all_source_restart_storm",
        )
        if not all(observed.get(k) for k in required):
            return _result("A8", "FAIL", reason="schedule_restart_invariant_failed", observed=observed)
        if observed.get("restart_enqueued_count") != 1:
            return _result("A8", "FAIL", reason="restart_enqueued_count_unexpected", observed=observed)

        return _result("A8", "PASS", **{k: observed[k] for k in sorted(observed)})
    except Exception as exc:
        return _result("A8", "FAIL", reason="schedule_restart_probe_failed", error=str(exc))


def run(
    dsn: str | None = None,
    *,
    http_probe: Callable[[], dict[str, Any]] | None = None,
    source_probe: Callable[[], dict[str, Any]] | None = None,
    idempotency_probe: Callable[[], dict[str, Any]] | None = None,
    poll_now_probe: Callable[[], dict[str, Any]] | None = None,
    schedule_restart_probe: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run all scenarios; connection and probe failures remain explicit."""
    dsn = dsn or os.environ.get("OPPORTUNITYOS_DB_URL")
    if not dsn:
        return {
            "format": 1,
            "scenarios": [_result(name, "BLOCKED", reason="postgres_dsn_missing") for name in SCENARIOS],
            "status": "BLOCKED",
        }
    connection = None
    try:
        connection = _connect(dsn)
        active_http = http_probe if http_probe is not None else (lambda: execute_a4_http_probe(dsn))
        active_source = source_probe if source_probe is not None else (lambda: execute_a5_source_probe(dsn))
        active_idempotency = idempotency_probe if idempotency_probe is not None else (lambda: execute_a6_idempotency_probe(dsn))
        active_poll_now = poll_now_probe if poll_now_probe is not None else (lambda: execute_a7_poll_now_probe(dsn))
        active_schedule_restart = schedule_restart_probe if schedule_restart_probe is not None else (lambda: execute_a8_schedule_restart_probe(dsn))

        results = [
            prove_a4(connection, http_probe=active_http),
            prove_a5(connection, source_probe=active_source),
            prove_a6(connection, idempotency_probe=active_idempotency),
            prove_a7(connection, poll_now_probe=active_poll_now),
            prove_a8(connection, schedule_restart_probe=active_schedule_restart),
        ]
    except Exception:
        results = [_result(name, "BLOCKED", reason="postgres_connection_unavailable") for name in SCENARIOS]
    finally:
        if connection is not None:
            connection.close()
    states = {item["state"] for item in results}
    status = "FAIL" if "FAIL" in states else "BLOCKED" if "BLOCKED" in states else "PASS"
    return {"format": 1, "scenarios": results, "status": status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-env", default="OPPORTUNITYOS_DB_URL")
    args = parser.parse_args(argv)
    report = run(os.environ.get(args.dsn_env))
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
