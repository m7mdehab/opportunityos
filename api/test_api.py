"""Case W: FastAPI service tests against real PostgreSQL.

Every class below builds its own `FastAPI` app via `create_app(settings=...)`
with an explicit `Settings` object -- never the module-level `api.app.app`
-- so each test controls its own truth-pack path and never touches
`private/`. `OPPORTUNITYOS_DB_URL` is read from the environment (the real
PostgreSQL database set up for this worktree); `OPPORTUNITYOS_FOUNDER_PASSWORD`
and `OPPORTUNITYOS_SESSION_SECRET` are supplied directly.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from storage.engine import get_engine, get_session_factory
from storage.models import (
    Base,
    FieldProvenanceRecord,
    FounderFeedbackRecord,
    FounderOpportunityViewRecord,
    FounderTriageStateRecord,
    IdempotencyReservationRecord,
    MatchEvaluationRecord,
    OpportunityRecord,
    OutboundActionRecordModel,
    SourcePollRunRecord,
    WorkerJobRecord,
)
from truth.graph import TruthGraph
from truth.models import CareerProfile, EvidenceRecord, SkillRecord

from api.app import create_app
from api.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PACK_PATH = REPO_ROOT / "docs" / "templates" / "truth_pack.template.yaml"

FOUNDER_PASSWORD = "correct-horse-battery-staple-9x"
SESSION_SECRET = "unit-test-session-secret-do-not-use-in-prod"


def _db_url() -> str:
    db_url = os.environ.get("OPPORTUNITYOS_DB_URL")
    if not db_url or not db_url.startswith("postgresql"):
        raise unittest.SkipTest(
            f"api.test_api requires a real PostgreSQL OPPORTUNITYOS_DB_URL, got: {db_url!r}"
        )
    return db_url


class ApiTestCase(unittest.TestCase):
    """Shared PostgreSQL setup/teardown for every Case W class.

    `OPPORTUNITYOS_FOUNDER_PASSWORD` / `OPPORTUNITYOS_SESSION_SECRET` are set
    here to synthetic values for the duration of this test class and
    restored afterward -- this suite must not require CI (or any other
    caller of `python -m unittest discover`) to define them. `make_app()`
    below also always passes an explicit `Settings` object rather than
    relying on these ambient variables; they are set defensively in case
    anything else in the import graph reads them from the environment.
    """

    _ENV_KEYS = ("OPPORTUNITYOS_FOUNDER_PASSWORD", "OPPORTUNITYOS_SESSION_SECRET")

    @classmethod
    def setUpClass(cls):
        cls.db_url = _db_url()
        cls.engine = get_engine(cls.db_url)
        cls.session_factory = get_session_factory(cls.engine)

        cls._saved_env = {key: os.environ.get(key) for key in cls._ENV_KEYS}
        os.environ["OPPORTUNITYOS_FOUNDER_PASSWORD"] = FOUNDER_PASSWORD
        os.environ["OPPORTUNITYOS_SESSION_SECRET"] = SESSION_SECRET

        alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", cls.db_url)
        command.upgrade(alembic_cfg, "head")

        cls.tmp_dir = tempfile.mkdtemp(prefix="oos-api-test-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)
        cls.engine.dispose()
        for key, value in cls._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def setUp(self):
        with self.engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE;'))
        self.session = self.session_factory()

    def tearDown(self):
        self.session.close()

    # -- helpers ------------------------------------------------------

    def missing_pack_path(self) -> str:
        return str(Path(self.tmp_dir) / f"missing-{uuid.uuid4().hex}.yaml")

    def valid_pack_path(self) -> str:
        target = Path(self.tmp_dir) / f"valid-{uuid.uuid4().hex}.yaml"
        shutil.copyfile(TEMPLATE_PACK_PATH, target)
        return str(target)

    def broken_pack_path(self) -> str:
        target = Path(self.tmp_dir) / f"broken-{uuid.uuid4().hex}.yaml"
        target.write_text(
            'evidence: []\n'
            'career_profile:\n'
            '  id: "career-broken"\n'
            '  skills:\n'
            '    - id: "skill-x"\n'
            '      name: "Rust"\n'
            '      evidence_ids: ["ev-missing"]\n',
            encoding="utf-8",
        )
        return str(target)

    def make_app(self, *, truth_pack_path: str | None = None, high_fit_threshold: float = 70.0):
        settings = Settings(
            db_url=self.db_url,
            founder_password=FOUNDER_PASSWORD,
            session_secret=SESSION_SECRET,
            high_fit_threshold=high_fit_threshold,
            truth_pack_path=truth_pack_path or self.missing_pack_path(),
        )
        return create_app(settings=settings)

    def logged_in_client(self, app) -> TestClient:
        client = TestClient(app)
        response = client.post("/api/auth/login", json={"password": FOUNDER_PASSWORD})
        assert response.status_code == 200, response.text
        return client

    def seed_opportunity(
        self,
        opp_id: str,
        *,
        track: str = "employment",
        created_at: datetime | None = None,
        posted_date: str | None = None,
        is_stale: bool = False,
    ) -> OpportunityRecord:
        record = OpportunityRecord(
            id=opp_id,
            track=track,
            title=f"Title {opp_id}",
            organization=f"Org {opp_id}",
            description="A synthetic opportunity for API tests.",
            source_id="himalayas",
            source_url=f"https://himalayas.app/jobs/{opp_id}",
            content_hash=f"hash-{opp_id}",
            posted_date=posted_date,
            is_stale=is_stale,
            created_at=created_at or datetime.now(timezone.utc),
        )
        self.session.add(record)
        self.session.add(
            FieldProvenanceRecord(
                opportunity_id=opp_id,
                field_name="title",
                raw_value=record.title,
                normalized_value=record.title,
                derivation_type="verbatim",
                raw_pointer=f"raw.{opp_id}.title",
                record_checksum=f"chk-{opp_id}",
            )
        )
        self.session.commit()
        return record

    def seed_evaluation(
        self,
        opp_id: str,
        *,
        decision: str,
        fit_score: float | None,
        hard_constraints: list[dict] | None = None,
        evaluated_at: datetime | None = None,
        top_reasons: list[str] | None = None,
        truth_pack_hash: str = "hash-fixture",
    ) -> MatchEvaluationRecord:
        dimension_scores = [
            {
                "dimension_name": "core_skills",
                "raw_score": 0.5,
                "weight": 0.35,
                "weighted_score": 0.175,
                "explanation": "partial skill overlap",
            }
        ]
        reasons_json = json.dumps(
            {
                "top_reasons": top_reasons or ["reason one", "reason two", "reason three"],
                "hard_constraints": hard_constraints or [],
                "strengths": ["strength one"],
                "gaps": ["gap one"],
                "unknowns": ["unknown one"],
                "uncertainty_penalty": 0.1,
                "explanation": "synthetic evaluation for API tests",
            }
        )
        record = MatchEvaluationRecord(
            id=f"eval-{uuid.uuid4().hex[:12]}",
            opportunity_id=opp_id,
            truth_pack_hash=truth_pack_hash,
            qualification_decision=decision,
            fit_score=fit_score if fit_score is not None else 0.0,
            dimension_scores_json=json.dumps(dimension_scores),
            reasons_json=reasons_json,
            policy_version="policy-v1",
            evaluated_at=evaluated_at or datetime.now(timezone.utc),
        )
        self.session.add(record)
        self.session.commit()
        return record


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class AuthFailClosedTest(ApiTestCase):
    def test_every_non_auth_route_401s_without_a_session(self):
        # `app.routes` in the installed FastAPI wraps each `include_router`
        # call in an opaque `_IncludedRouter` object rather than exposing a
        # flat list of `APIRoute`s (an internal representation change in
        # this FastAPI version). The authoritative, non-hand-maintained
        # route table is therefore the actual `api_router` this app mounts
        # wholesale via `app.include_router(api_router)` in `api/app.py` --
        # every route added to it (now or in the future) is enumerated here
        # automatically, with no separate list to fall out of date. Requests
        # are still made against the real, fully-constructed `app` via
        # `TestClient`, so this exercises the live fail-closed behaviour,
        # not just the router's declared shape.
        from api.routes_api import router as protected_router

        app = self.make_app()
        client = TestClient(app)

        checked = 0
        for route in protected_router.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if not path or not methods:
                continue
            self.assertTrue(path.startswith("/api/"), path)
            self.assertFalse(path.startswith("/api/auth/"), path)

            concrete_path = path
            while "{" in concrete_path and "}" in concrete_path:
                start = concrete_path.index("{")
                end = concrete_path.index("}", start) + 1
                concrete_path = concrete_path[:start] + "test-id" + concrete_path[end:]

            for method in methods:
                if method in ("HEAD", "OPTIONS"):
                    continue
                checked += 1
                if method == "GET":
                    response = client.get(concrete_path)
                elif method == "POST":
                    response = client.post(concrete_path, json={})
                elif method == "DELETE":
                    response = client.delete(concrete_path)
                elif method == "PUT":
                    response = client.put(concrete_path, json={})
                else:
                    continue
                self.assertEqual(
                    response.status_code,
                    401,
                    f"{method} {concrete_path} did not fail closed: {response.status_code} {response.text}",
                )

        self.assertGreater(checked, 0, "route enumeration found nothing to check")


class AuthSessionTest(ApiTestCase):
    def test_login_me_logout_cycle(self):
        app = self.make_app()
        client = TestClient(app)

        me_before = client.get("/api/auth/me")
        self.assertEqual(me_before.status_code, 401)

        wrong = client.post("/api/auth/login", json={"password": "not-the-password"})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json()["detail"], "invalid credentials")

        login = client.post("/api/auth/login", json={"password": FOUNDER_PASSWORD})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json(), {"authenticated": True})
        self.assertIn("oos_session", client.cookies)

        me_after = client.get("/api/auth/me")
        self.assertEqual(me_after.status_code, 200)
        self.assertEqual(me_after.json(), {"authenticated": True})

        opportunities = client.get("/api/opportunities")
        self.assertEqual(opportunities.status_code, 200)

        logout = client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(logout.json(), {"authenticated": False})

        me_final = client.get("/api/auth/me")
        self.assertEqual(me_final.status_code, 401)


class AuthRateLimitTest(ApiTestCase):
    def test_sixth_attempt_in_a_window_is_rate_limited(self):
        app = self.make_app()
        client = TestClient(app)

        for _ in range(5):
            response = client.post("/api/auth/login", json={"password": "wrong"})
            self.assertEqual(response.status_code, 401)

        limited = client.post("/api/auth/login", json={"password": "wrong"})
        self.assertEqual(limited.status_code, 429)
        body = limited.json()
        self.assertEqual(body["detail"], "too many attempts")
        self.assertIsInstance(body["retry_after_seconds"], int)
        self.assertGreater(body["retry_after_seconds"], 0)

        # Even the correct password is rejected once rate-limited.
        still_limited = client.post("/api/auth/login", json={"password": FOUNDER_PASSWORD})
        self.assertEqual(still_limited.status_code, 429)


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------


class OpportunityRoutesTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.client = self.logged_in_client(self.app)

    def test_list_filters_sorts_and_paginates(self):
        self.seed_opportunity("opp-high", posted_date="2026-08-20")
        self.seed_evaluation("opp-high", decision="qualified", fit_score=90.0)

        self.seed_opportunity("opp-low", posted_date="2026-08-21")
        self.seed_evaluation("opp-low", decision="qualified", fit_score=40.0)

        self.seed_opportunity("opp-none")  # no evaluation -> fit_score null, decision null

        response = self.client.get("/api/opportunities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 3)
        ids_in_order = [item["id"] for item in body["items"]]
        # fit_score descending, nulls last
        self.assertEqual(ids_in_order, ["opp-high", "opp-low", "opp-none"])
        self.assertIsNone(body["items"][2]["fit_score"])
        self.assertIsNone(body["items"][2]["decision"])

        filtered = self.client.get("/api/opportunities", params={"min_score": 50})
        self.assertEqual(filtered.status_code, 200)
        filtered_ids = [item["id"] for item in filtered.json()["items"]]
        self.assertEqual(filtered_ids, ["opp-high"])

        paged = self.client.get("/api/opportunities", params={"page": 1, "page_size": 1})
        self.assertEqual(paged.status_code, 200)
        self.assertEqual(paged.json()["page_size"], 1)
        self.assertEqual(len(paged.json()["items"]), 1)

    def test_detail_reaches_pass_fail_unknown_and_uncertain(self):
        self.seed_opportunity("opp-uncertain")
        self.seed_evaluation(
            "opp-uncertain",
            decision="uncertain",
            fit_score=55.5,
            hard_constraints=[
                {
                    "constraint_name": "work_authorization",
                    "passed": True,
                    "reason": "authorized",
                    "required_field": "work_authorization",
                    "founder_fact": "authorized in Exampleland",
                    "is_hard_failure": False,
                    "provenance_pointer": "career_profile.work_authorizations.0",
                },
                {
                    "constraint_name": "minimum_experience_years",
                    "passed": False,
                    "reason": "insufficient years",
                    "required_field": "employment.experience_years",
                    "founder_fact": "2 years",
                    "is_hard_failure": True,
                    "provenance_pointer": "career_profile.employment.0",
                },
                {
                    "constraint_name": "security_clearance",
                    "passed": None,
                    "reason": "no evidence either way",
                    "required_field": "security_clearance",
                    "founder_fact": "",
                    "is_hard_failure": False,
                    "provenance_pointer": "",
                },
            ],
        )

        response = self.client.get("/api/opportunities/opp-uncertain")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["qualification"]["decision"], "uncertain")

        outcomes = {c["constraint_name"]: c["outcome"] for c in body["qualification"]["constraints"]}
        self.assertEqual(outcomes["work_authorization"], "PASS")
        self.assertEqual(outcomes["minimum_experience_years"], "FAIL")
        self.assertEqual(outcomes["security_clearance"], "UNKNOWN")
        # UNKNOWN must never be coerced into FAIL.
        self.assertNotEqual(outcomes["security_clearance"], "FAIL")

        self.assertEqual(body["scoring"]["fit_score"], 55.5)
        self.assertEqual(len(body["scoring"]["dimension_scores"]), 1)
        self.assertEqual(body["scoring"]["dimension_scores"][0]["dimension"], "core_skills")
        self.assertIn("score", body["scoring"]["dimension_scores"][0])

        self.assertEqual(len(body["fields"]), 1)
        self.assertEqual(body["fields"][0]["field_name"], "title")

    def test_detail_records_a_founder_opportunity_view(self):
        self.seed_opportunity("opp-viewed")
        response = self.client.get("/api/opportunities/opp-viewed")
        self.assertEqual(response.status_code, 200)

        views = self.session.query(FounderOpportunityViewRecord).filter_by(opportunity_id="opp-viewed").all()
        self.assertEqual(len(views), 1)

    def test_detail_404_for_missing_opportunity(self):
        response = self.client.get("/api/opportunities/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "opportunity not found")


# ---------------------------------------------------------------------------
# Artifacts -- the 409 no-docx path
# ---------------------------------------------------------------------------


def _mismatched_truth_pack_graph() -> TruthGraph:
    """A deliberately unverifiable graph.

    `TruthGraph.add_career_profile` itself enforces evidence-supported field
    provenance (a proximity-scoped negation check: it only blocks a value
    when a negative marker sits immediately next to it), so a value that is
    merely *somewhere* in negatively-marked evidence text still passes graph
    construction. `ClaimValidator.validate_claim` is stricter: it rejects
    any claim drawn from evidence containing a negative marker at all,
    unless the claim itself also carries one (see
    `truth.validator.ClaimValidator` step 4, "polarity ... safety"). That
    gap is what this fixture exercises: the evidence text contains "Not"
    far from the skill name, so the graph accepts it, but the validator
    must not -- this is the fixture that proves the 409 path.
    """
    evidence = (
        EvidenceRecord(
            "ev-mismatch",
            "Not officially certified, but has hands-on experience with Kubernetes from personal projects.",
            "synthetic_cv",
            "skills.0",
        ),
    )
    graph = TruthGraph(evidence)
    profile = CareerProfile(
        id="career-mismatch",
        evidence_ids=("ev-mismatch",),
        skills=(SkillRecord("skill-mismatch", "Kubernetes", ("ev-mismatch",)),),
    )
    graph.add_career_profile(profile)
    return graph


def _clean_truth_pack_graph() -> TruthGraph:
    """A minimal, fully evidence-supported graph: one verified skill, no
    employment record.

    Deliberately does not use `truth.fixtures.synthetic_graph()` (which
    includes a `MetricAssertion`): `EmploymentArtifactCompiler.compile_tailored_cv`'s
    metrics section reads `MetricAssertion.semantic_context`, an attribute
    that does not exist on `truth.models.MetricAssertion` (the real field is
    `context`). That is a pre-existing bug in `matching/compiler_employment.py`,
    which is out of D6's file scope to fix; this fixture avoids the metrics
    codepath entirely so the clean 200 case does not trip over it.

    Also deliberately has no employment/title assertion: the compiler's
    "Professional Summary" section cites both the title assertion's
    evidence and each highlighted skill's evidence in one composite claim,
    which `ClaimValidator` correctly refuses unless those evidence records
    are relationally linked in the graph (`are_relationally_linked`) --
    itself correct claim-validator behaviour, not a bug. Omitting the
    employment record keeps this fixture to a single, single-evidence
    skill claim so it exercises the artifact export's clean-approval path
    without also having to construct that graph relation.
    """
    evidence = (
        EvidenceRecord("ev-python", "Uses Python for data engineering.", "synthetic_cv", "skills.0"),
    )
    graph = TruthGraph(evidence)
    profile = CareerProfile(
        id="career-clean",
        evidence_ids=(),
        skills=(SkillRecord("skill-python", "Python", ("ev-python",)),),
    )
    graph.add_career_profile(profile)
    return graph


class ArtifactRoutesTest(ApiTestCase):
    def setUp(self):
        super().setUp()

    def test_artifact_200_on_clean_fixture(self):
        import unittest.mock as mock

        self.seed_opportunity("opp-clean")
        app = self.make_app()
        client = self.logged_in_client(app)

        with mock.patch("api.routes_api.load_founder_pack") as loader:
            from truth.pack import LoadedPack, PackValidationReport

            graph = _clean_truth_pack_graph()
            loader.return_value = LoadedPack(
                graph=graph,
                report=PackValidationReport(valid=True, section_counts=(("evidence", 1),)),
                truth_pack_hash="clean-hash",
            )
            reload_response = client.post("/api/truth/reload")
            self.assertEqual(reload_response.status_code, 200)
            self.assertTrue(reload_response.json()["loaded"])

            response = client.get("/api/opportunities/opp-clean/artifacts/cv.docx")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertTrue(response.content.startswith(b"PK"), "response body is not a docx/zip payload")
        self.assertIn("attachment", response.headers["content-disposition"])

    def test_artifact_409_never_returns_docx_bytes(self):
        import unittest.mock as mock

        self.seed_opportunity("opp-mismatch")
        app = self.make_app()
        client = self.logged_in_client(app)

        with mock.patch("api.routes_api.load_founder_pack") as loader:
            from truth.pack import LoadedPack, PackValidationReport

            graph = _mismatched_truth_pack_graph()
            loader.return_value = LoadedPack(
                graph=graph,
                report=PackValidationReport(valid=True, section_counts=(("evidence", 1),)),
                truth_pack_hash="mismatch-hash",
            )
            client.post("/api/truth/reload")

            response = client.get("/api/opportunities/opp-mismatch/artifacts/cv.docx")

        self.assertEqual(response.status_code, 409)
        self.assertNotEqual(
            response.headers.get("content-type", ""),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        # The response body must never contain docx/zip bytes on rejection.
        self.assertFalse(response.content.startswith(b"PK"))
        body = response.json()
        self.assertEqual(body["detail"], "claim validation failed")
        self.assertGreaterEqual(len(body["findings"]), 1)
        finding = body["findings"][0]
        self.assertIn("claim", finding)
        self.assertIn("assertion_type", finding)
        self.assertIn("rejection_reasons", finding)

    def test_artifact_412_when_no_truth_pack_loaded(self):
        self.seed_opportunity("opp-nopack")
        app = self.make_app(truth_pack_path=self.missing_pack_path())
        client = self.logged_in_client(app)

        response = client.get("/api/opportunities/opp-nopack/artifacts/cv.docx")
        self.assertEqual(response.status_code, 412)
        body = response.json()
        self.assertEqual(body["detail"], "no truth pack loaded")
        self.assertIn("reason", body)


# ---------------------------------------------------------------------------
# Feedback and actions
# ---------------------------------------------------------------------------


class FeedbackAndActionTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.client = self.logged_in_client(self.app)
        self.seed_opportunity("opp-fb")

    def test_feedback_valid_label_persists(self):
        response = self.client.post(
            "/api/opportunities/opp-fb/feedback", json={"label": "good_match", "note": "great fit"}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["feedback_label"], "good_match")
        self.assertEqual(body["notes"], "great fit")

        rows = self.session.query(FounderFeedbackRecord).filter_by(opportunity_id="opp-fb").all()
        self.assertEqual(len(rows), 1)

    def test_feedback_unknown_label_422(self):
        response = self.client.post("/api/opportunities/opp-fb/feedback", json={"label": "not_a_real_label"})
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["detail"], "unknown feedback label")
        self.assertIn("good_match", body["allowed"])

    def test_mark_applied_writes_outbound_action_without_idempotency_reservation(self):
        before = self.session.query(IdempotencyReservationRecord).count()

        response = self.client.post("/api/opportunities/opp-fb/actions", json={"type": "mark_applied"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["action_state"], "submitted")
        self.assertIsNotNone(body["action_id"])

        after = self.session.query(IdempotencyReservationRecord).count()
        self.assertEqual(before, after, "mark_applied must not reserve or consume an idempotency reservation")

        actions = self.session.query(OutboundActionRecordModel).filter_by(opportunity_id="opp-fb").all()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_status, "submitted")
        self.assertEqual(actions[0].execution_mode, "dry_run")

    def test_dismiss_and_snooze_write_triage_state_not_outbound_actions(self):
        dismiss = self.client.post("/api/opportunities/opp-fb/actions", json={"type": "dismiss"})
        self.assertEqual(dismiss.status_code, 200)
        self.assertEqual(dismiss.json()["action_state"], "dismissed")

        triage = self.session.query(FounderTriageStateRecord).filter_by(opportunity_id="opp-fb").first()
        self.assertIsNotNone(triage)
        self.assertEqual(triage.state, "dismissed")

        actions = self.session.query(OutboundActionRecordModel).filter_by(opportunity_id="opp-fb").all()
        self.assertEqual(len(actions), 0)

        future = (date.today() + timedelta(days=5)).isoformat()
        snooze = self.client.post("/api/opportunities/opp-fb/actions", json={"type": "snooze", "until": future})
        self.assertEqual(snooze.status_code, 200)
        self.assertEqual(snooze.json()["action_state"], "snoozed")
        self.assertEqual(snooze.json()["until"], future)

    def test_snooze_without_future_until_is_422(self):
        response = self.client.post("/api/opportunities/opp-fb/actions", json={"type": "snooze"})
        self.assertEqual(response.status_code, 422)

        past = (date.today() - timedelta(days=1)).isoformat()
        response_past = self.client.post("/api/opportunities/opp-fb/actions", json={"type": "snooze", "until": past})
        self.assertEqual(response_past.status_code, 422)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class DashboardTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app(high_fit_threshold=70.0)
        self.client = self.logged_in_client(self.app)

    def _day_start(self, days_ago: int) -> datetime:
        today = datetime.now(timezone.utc).date()
        day = today - timedelta(days=days_ago)
        return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)

    def test_daily_counters_over_a_three_day_seeded_fixture(self):
        today_start = self._day_start(0)
        yesterday_start = self._day_start(1)
        # day 2 (two days ago) is deliberately left empty.

        self.seed_opportunity("opp-today", created_at=today_start + timedelta(hours=1))
        self.seed_evaluation(
            "opp-today", decision="qualified", fit_score=85.0, evaluated_at=today_start + timedelta(hours=2)
        )
        self.session.add(
            FounderOpportunityViewRecord(
                id="view-today", opportunity_id="opp-today", viewed_at=today_start + timedelta(hours=3)
            )
        )
        self.session.add(
            SourcePollRunRecord(
                id="poll-today",
                source_id="himalayas",
                started_at=today_start + timedelta(minutes=30),
                status="success",
                raw_ingested=12,
                unique_opportunities=3,
                inserted=1,
                unchanged=2,
                updated=0,
            )
        )
        self.session.commit()

        self.client.post("/api/opportunities/opp-today/feedback", json={"label": "good_match"})
        self.client.post("/api/opportunities/opp-today/actions", json={"type": "mark_applied"})

        self.seed_opportunity("opp-yesterday", created_at=yesterday_start + timedelta(hours=1))
        self.seed_evaluation(
            "opp-yesterday",
            decision="ineligible",
            fit_score=20.0,
            evaluated_at=yesterday_start + timedelta(hours=2),
        )

        response = self.client.get("/api/dashboard/daily", params={"days": 4})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["days"], 4)
        self.assertEqual(body["high_fit_threshold"], 70.0)
        self.assertEqual(len(body["series"]), 4)

        by_date = {row["date"]: row for row in body["series"]}
        today_row = by_date[today_start.date().isoformat()]
        self.assertEqual(today_row["fetched"], 12)
        self.assertEqual(today_row["unique_new"], 1)
        self.assertEqual(today_row["qualified"], 1)
        self.assertEqual(today_row["high_fit"], 1)
        self.assertEqual(today_row["opened"], 1)
        self.assertEqual(today_row["labelled"], 1)
        self.assertEqual(today_row["applied"], 1)

        yesterday_row = by_date[yesterday_start.date().isoformat()]
        self.assertEqual(yesterday_row["unique_new"], 1)
        self.assertEqual(yesterday_row["qualified"], 0)
        self.assertEqual(yesterday_row["high_fit"], 0)

        empty_day = self._day_start(2).date().isoformat()
        empty_row = by_date[empty_day]
        self.assertEqual(
            empty_row,
            {
                "date": empty_day,
                "fetched": 0,
                "unique_new": 0,
                "qualified": 0,
                "high_fit": 0,
                "opened": 0,
                "labelled": 0,
                "applied": 0,
            },
        )


# ---------------------------------------------------------------------------
# Truth pack routes
# ---------------------------------------------------------------------------


class TruthRoutesTest(ApiTestCase):
    def setUp(self):
        super().setUp()

    def test_status_returns_200_even_when_no_pack_loaded(self):
        app = self.make_app(truth_pack_path=self.missing_pack_path())
        client = self.logged_in_client(app)

        response = client.get("/api/truth/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["loaded"])
        self.assertIsNone(body["hash"])
        self.assertFalse(body["validator"]["ok"])
        self.assertGreaterEqual(body["validator"]["error_count"], 1)

    def test_reload_with_valid_pack(self):
        app = self.make_app(truth_pack_path=self.valid_pack_path())
        client = self.logged_in_client(app)

        response = client.post("/api/truth/reload")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["loaded"])
        self.assertIsNotNone(body["hash"])
        self.assertTrue(body["validator"]["ok"])
        self.assertGreater(len(body["sections"]), 0)

    def test_reload_with_invalid_pack(self):
        app = self.make_app(truth_pack_path=self.broken_pack_path())
        client = self.logged_in_client(app)

        response = client.post("/api/truth/reload")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["loaded"])
        self.assertGreaterEqual(len(body["validator"]["findings"]), 1)


# ---------------------------------------------------------------------------
# Sources and worker
# ---------------------------------------------------------------------------


class SourcesAndWorkerTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.client = self.logged_in_client(self.app)

    def test_sources_health_reports_registered_sources(self):
        self.session.add(
            SourcePollRunRecord(
                id="poll-1",
                source_id="himalayas",
                started_at=datetime.now(timezone.utc),
                status="success",
                raw_ingested=7,
                unique_opportunities=2,
                inserted=1,
                unchanged=1,
                updated=0,
            )
        )
        self.session.commit()

        response = self.client.get("/api/sources/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("sources", body)
        self.assertGreater(len(body["sources"]), 0)
        for source in body["sources"]:
            self.assertIn(source["read_policy"], ("allowed", "disabled"))

        himalayas = next(s for s in body["sources"] if s["source_id"] == "himalayas")
        self.assertEqual(himalayas["last_record_count"], 7)
        self.assertIsNotNone(himalayas["last_poll"])

    def test_poll_now_enqueues_only_read_allowed_sources(self):
        response = self.client.post("/api/worker/poll-now")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("enqueued", body)
        self.assertIn("skipped", body)
        self.assertGreater(len(body["enqueued"]) + len(body["skipped"]), 0)
        for skip in body["skipped"]:
            self.assertEqual(skip["reason"], "read_disabled_by_policy")

        job_count = self.session.query(WorkerJobRecord).count()
        self.assertEqual(job_count, len(body["enqueued"]))


if __name__ == "__main__":
    unittest.main()
