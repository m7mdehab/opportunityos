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
import secrets
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
    FounderFilterSettingRecord,
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
from truth.models import (
    AtomicAssertion,
    CapabilityProfile,
    CareerProfile,
    EmploymentRecord,
    EvidenceRecord,
    RedLineRule,
    SkillRecord,
    VerificationStatus,
)
from truth.pack import LoadedPack, PackValidationReport
from truth.validator import ClaimValidator

from api.app import create_app
from api.filters import FILTER_DEFINITIONS, FILTER_DEFINITIONS_BY_ID
from api.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PACK_PATH = REPO_ROOT / "docs" / "templates" / "truth_pack.template.yaml"

def _synthetic_value(prefix: str, entropy_bytes: int) -> str:
    """Build a throwaway test value that is generated, never hard-coded.

    A literal assigned to a name like PASSWORD or SECRET is exactly the shape
    `scripts/check_guard.py` rejects, and it should keep rejecting it rather
    than learn an exception for this file. Generating instead of hard-coding
    is also better practice on its own: a value that differs every run cannot
    be copied into anything real by accident. Nothing here is a credential.
    """
    return prefix + secrets.token_urlsafe(entropy_bytes)


FOUNDER_PASSWORD = _synthetic_value("pw-", 12)
SESSION_SECRET = _synthetic_value("sig-", 24)


# ---------------------------------------------------------------------------
# D3 (BRIEF-FR-005) test fixtures: founder_filter_settings reseeding and
# synthetic truth-pack graphs.
# ---------------------------------------------------------------------------


def _reseed_founder_filter_settings(session) -> None:
    """Insert `founder_filter_settings` rows for every filter in
    `api.filters.FILTER_DEFINITIONS`, at each filter's own default
    enabled/mode/params. Mirrors migration 0003's `_D3_FILTER_SEED` exactly
    (`FilterSeedSyncTest` asserts the two never drift apart) -- called from
    `ApiTestCase.setUp` because the shared TRUNCATE-every-table loop there
    also empties this table, and a real fresh-migrated database never has an
    empty `founder_filter_settings`."""
    from api.filters import to_naive_utc

    now = to_naive_utc(datetime.now(timezone.utc))
    for fd in FILTER_DEFINITIONS:
        session.add(
            FounderFilterSettingRecord(
                filter_id=fd.filter_id,
                enabled=fd.default_enabled,
                mode=fd.default_mode,
                params_json=json.dumps(dict(fd.default_params)),
                updated_at=now,
            )
        )
    session.commit()


def _install_truth_graph(app, graph: TruthGraph) -> None:
    """Hand `app.state` a `TruthGraph` built directly in-test (the same
    pattern `matching/test_scorer.py::_with_premium_threshold` uses),
    bypassing YAML file loading entirely. Filter fixtures need very specific
    assertions/red-lines/excluded-industries; building the graph in Python is
    far less brittle than hand-writing evidence-perfect YAML for each case."""
    app.state.loaded_truth_pack = LoadedPack(
        graph=graph,
        report=PackValidationReport(valid=True, section_counts=(), findings=()),
        truth_pack_hash="test-truth-pack-hash",
    )


def _graph_with_red_line_and_excluded_industry() -> TruthGraph:
    """A minimal graph carrying one career red line ("guaranteed placement")
    and one capability excluded industry ("Gambling") -- the same values the
    shipped `docs/templates/truth_pack.template.yaml` uses, built directly
    rather than through YAML ingest so no evidence-wording gymnastics are
    needed."""
    graph = TruthGraph()
    graph.add_evidence(
        EvidenceRecord(
            id="ev-cap-summary",
            content="Targets Widget Manufacturing and excludes the Gambling industry.",
            source="manual",
            locator="capability_profile.summary",
        )
    )
    graph.add_career_profile(
        CareerProfile(
            id="career-fixture",
            red_lines=(
                RedLineRule(
                    id="rl-guarantee",
                    pattern=r"guarant(?:eed?)\s+placement",
                    reason="Never imply guaranteed employment outcomes.",
                ),
            ),
        )
    )
    graph.add_capability_profile(
        CapabilityProfile(
            id="cap-fixture",
            evidence_ids=("ev-cap-summary",),
            excluded_industries=("Gambling",),
        )
    )
    return graph


def _graph_with_founder_preferences(
    *,
    preferred_track: str | None = None,
    target_role: str | None = None,
    premium_threshold: str | None = None,
) -> TruthGraph:
    """A graph carrying only the assertion-only predicates D3's
    `track_preference` / `target_roles` / `premium_fulltime_onsite` filters
    read (`truth/predicates.py`'s `PREFERENCE_TRACK`, `CAREER_TARGET_ROLE`,
    `PREFERENCE_FULLTIME_ONSITE_PREMIUM_MONTHLY`), each backed by its own
    evidence record whose text supports the value (required by
    `TruthGraph.add_assertion`'s value-support check)."""
    from truth import predicates

    graph = TruthGraph()
    if preferred_track is not None:
        graph.add_evidence(
            EvidenceRecord(
                id="ev-track-pref",
                content=f"Founder's declared track preference order: {preferred_track}.",
                source="manual",
                locator="assertions.track_preference",
            )
        )
        graph.add_assertion(
            AtomicAssertion(
                id="a-track-pref",
                subject_id="founder",
                predicate=predicates.PREFERENCE_TRACK,
                value=preferred_track,
                evidence_ids=("ev-track-pref",),
                verification_status=VerificationStatus.VERIFIED,
            )
        )
    if target_role is not None:
        graph.add_evidence(
            EvidenceRecord(
                id="ev-target-role",
                content=f"Founder's declared target role: {target_role}.",
                source="manual",
                locator="assertions.target_role",
            )
        )
        graph.add_assertion(
            AtomicAssertion(
                id="a-target-role",
                subject_id="founder",
                predicate=predicates.CAREER_TARGET_ROLE,
                value=target_role,
                evidence_ids=("ev-target-role",),
                verification_status=VerificationStatus.VERIFIED,
            )
        )
    if premium_threshold is not None:
        graph.add_evidence(
            EvidenceRecord(
                id="ev-premium-threshold",
                content=f"Minimum acceptable full-time on-site compensation: {premium_threshold} per month.",
                source="manual",
                locator="assertions.premium_threshold",
            )
        )
        graph.add_assertion(
            AtomicAssertion(
                id="a-premium-threshold",
                subject_id="founder",
                predicate=predicates.PREFERENCE_FULLTIME_ONSITE_PREMIUM_MONTHLY,
                value=premium_threshold,
                evidence_ids=("ev-premium-threshold",),
                verification_status=VerificationStatus.VERIFIED,
            )
        )
    return graph


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
        # D3 (BRIEF-FR-005): `founder_filter_settings` is truncated by the loop
        # above along with every other table, but migration 0003 only seeds its
        # ten default rows once, at migration time -- not on every TRUNCATE. A
        # real fresh-migrated database always has all ten rows present (that is
        # the whole point of "seeded by the migration"), so every test's fixture
        # must start from that same state rather than an empty table. This
        # reseed uses `api.filters.FILTER_DEFINITIONS` -- verified identical to
        # the migration's own `_D3_FILTER_SEED` by
        # `FilterSeedSyncTest.test_migration_seed_matches_filter_definitions`.
        _reseed_founder_filter_settings(self.session)

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
        title: str | None = None,
        organization: str | None = None,
        description: str | None = None,
    ) -> OpportunityRecord:
        record = OpportunityRecord(
            id=opp_id,
            track=track,
            title=title if title is not None else f"Title {opp_id}",
            organization=organization if organization is not None else f"Org {opp_id}",
            description=description if description is not None else "A synthetic opportunity for API tests.",
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

    def seed_compensation(
        self,
        opp_id: str,
        *,
        min_amount: float | None = None,
        max_amount: float | None = None,
        currency: str | None = None,
    ) -> None:
        """Seed the atomic `compensation.min_amount` / `compensation.max_amount`
        / `compensation.currency` `field_provenances` rows every adapter writes
        (`opportunity/adapters/*.py`) -- the real data source D3's
        `compensation_floor` filter reads, rather than a synthesized combined
        string."""
        fields = {
            "compensation.min_amount": None if min_amount is None else str(min_amount),
            "compensation.max_amount": None if max_amount is None else str(max_amount),
            "compensation.currency": currency,
        }
        for field_name, value in fields.items():
            if value is None:
                continue
            self.session.add(
                FieldProvenanceRecord(
                    opportunity_id=opp_id,
                    field_name=field_name,
                    raw_value=value,
                    normalized_value=value,
                    derivation_type="rule_derivation",
                    raw_pointer=f"raw.{opp_id}.{field_name}",
                    record_checksum=f"chk-{opp_id}-{field_name}",
                )
            )
        self.session.commit()

    def seed_evaluation(
        self,
        opp_id: str,
        *,
        decision: str,
        fit_score: float | None,
        evaluated_at: datetime | None = None,
        reasons: list[dict] | None = None,
        evaluation_detail: dict | None = None,
        dimension_scores: list[dict] | None = None,
        truth_pack_hash: str = "hash-fixture",
    ) -> MatchEvaluationRecord:
        """Seed a `match_evaluations` row using the canonical shapes
        `matching/evaluate_persist.py` actually writes:
        `dimension_scores_json` a JSON list of `MatchDimensionScore`-shaped
        dicts, `reasons_json` a JSON list of `{"kind", "dimension", "text"}`
        entries, and `evaluation_detail_json` (nullable) the
        `{"hard_constraints", "strengths", "gaps", "unknowns",
        "uncertainty_penalty", "explanation"}` object. `evaluation_detail`
        defaults to `None`, i.e. an unpopulated column -- exactly the state
        of a row persisted before this column existed -- so tests that need
        hard-constraint data pass it explicitly rather than relying on a
        default that would mask the null case. `dimension_scores` defaults to
        the single-`core_skills`-entry shape below (unchanged from before this
        parameter existed) -- pass it explicitly for tests (e.g. D3's
        `premium_fulltime_onsite` filter) that need a specific dimension,
        such as `compensation_fit`, present.
        """
        dimension_scores = dimension_scores if dimension_scores is not None else [
            {
                "dimension_name": "core_skills",
                "raw_score": 0.5,
                "weight": 0.35,
                "weighted_score": 0.175,
                "explanation": "partial skill overlap",
            }
        ]
        reasons_payload = (
            reasons
            if reasons is not None
            else [
                {"kind": "strength", "dimension": "core_skills", "text": "reason one"},
                {"kind": "gap", "dimension": "core_skills", "text": "reason two"},
                {"kind": "unknown", "dimension": "core_skills", "text": "reason three"},
            ]
        )
        record = MatchEvaluationRecord(
            id=f"eval-{uuid.uuid4().hex[:12]}",
            opportunity_id=opp_id,
            truth_pack_hash=truth_pack_hash,
            qualification_decision=decision,
            fit_score=fit_score if fit_score is not None else 0.0,
            dimension_scores_json=json.dumps(dimension_scores),
            reasons_json=json.dumps(reasons_payload),
            evaluation_detail_json=json.dumps(evaluation_detail) if evaluation_detail is not None else None,
            policy_version="policy-v1",
            evaluated_at=evaluated_at or datetime.now(timezone.utc),
        )
        self.session.add(record)
        self.session.commit()
        return record


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _iter_app_routes(router_or_app):
    """Recursively flatten every route reachable from an app/router's own
    `.routes`, including FastAPI's own built-in doc routes (`/openapi.json`,
    `/docs`, `/redoc`, ...) that are attached directly to `app.router` and
    every `include_router`-mounted sub-router.

    The installed FastAPI wraps each `include_router` call in an opaque
    `_IncludedRouter(original_router=..., ...)` object rather than exposing
    a flat list of `APIRoute`s at `app.routes` (an internal representation
    change in this FastAPI version) -- so walking only `app.routes` misses
    every route mounted that way, and walking only a sub-router (as this
    test used to) misses everything mounted directly on the app itself,
    which is exactly how the docs routes slipped through. This walks both:
    it is the actual, complete, authoritative route table this app serves,
    council-verified to catch app-level routes a sub-router enumeration is
    structurally blind to.
    """
    routes = getattr(router_or_app, "routes", None)
    if routes is None:
        return
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _iter_app_routes(original_router)
            continue
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            yield path, methods


class AuthFailClosedTest(ApiTestCase):
    def test_every_non_auth_route_401s_without_a_session(self):
        app = self.make_app()
        client = TestClient(app)

        checked = 0
        seen_paths = set()
        for path, methods in _iter_app_routes(app):
            seen_paths.add(path)
            is_auth_route = path.startswith("/api/auth/")

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

                if is_auth_route:
                    continue

                # Every non-auth route in the app -- API routes and FastAPI's
                # own built-in ones alike -- must never answer 200 without a
                # session. `/api/*` routes are gated to exactly 401; the
                # built-in doc routes are disabled entirely (docs_url=None
                # etc. in api/app.py) and so 404, which is equally not "200
                # with the schema in the body."
                self.assertNotEqual(
                    response.status_code,
                    200,
                    f"{method} {concrete_path} answered 200 without a session: {response.text[:200]}",
                )
                if path.startswith("/api/"):
                    self.assertEqual(
                        response.status_code,
                        401,
                        f"{method} {concrete_path} did not fail closed with 401: {response.status_code} {response.text}",
                    )

        self.assertGreater(checked, 0, "route enumeration found nothing to check")
        # `_iter_app_routes` walks `app.router.routes` (not a sub-router),
        # so it is not structurally blind to routes mounted directly on the
        # app -- which is exactly how FastAPI's own doc routes slipped past
        # the previous version of this test (council finding). Now that
        # `api/app.py` disables those routes outright, they are correctly
        # absent from what this enumeration finds -- `test_docs_routes_are_disabled_entirely`
        # is the direct proof that they answer 404, not a silent 200.
        self.assertNotIn("/openapi.json", seen_paths)
        self.assertNotIn("/docs", seen_paths)
        self.assertNotIn("/redoc", seen_paths)

    def test_docs_routes_are_disabled_entirely(self):
        """Finding 1 (council, auth review): FastAPI's own `/openapi.json`,
        `/docs`, and `/redoc` were unauthenticated and returned 200 with the
        full route schema in the body, with no cookie at all -- a direct
        violation of "every other route 401s without a valid session."
        `api/app.py` now disables them outright (`docs_url=None,
        redoc_url=None, openapi_url=None`), so they must 404, not 401 and
        not 200: there is nothing behind them to gate."""
        app = self.make_app()
        client = TestClient(app)

        for path in ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"):
            response = client.get(path)
            self.assertEqual(response.status_code, 404, f"{path} -> {response.status_code}")
            self.assertNotEqual(response.status_code, 200)


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

    def test_login_validation_error_does_not_echo_submitted_password(self):
        """Finding 4 (council, auth review): FastAPI's default 422 body
        echoes each field's submitted value back in an "input" key. For
        POST /api/auth/login that means a malformed request reflects the
        founder's own submitted password back into the response body (and
        from there, into any log or proxy that records response payloads).
        A non-string password fails type validation and is exactly the
        shape a real client bug would produce."""
        app = self.make_app()
        client = TestClient(app)

        marker = "secret-marker-should-never-appear-9182"
        response = client.post("/api/auth/login", json={"password": {"nested": marker}})

        self.assertEqual(response.status_code, 422)
        self.assertNotIn(marker, response.text)
        for error in response.json()["detail"]:
            self.assertNotIn("input", error)


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
        """`UNKNOWN` being structurally distinct from `FAIL` is the brief's
        single most emphatic requirement, so this proves it against real
        persisted data, not a mocked reader: a real `match_evaluations` row
        is inserted with a real `evaluation_detail_json` payload (constraints
        with `passed` true, false, and null), read back through the actual
        HTTP route, and asserted PASS/FAIL/UNKNOWN. The `null` case must not
        come back as `FAIL`."""
        self.seed_opportunity("opp-uncertain")
        self.seed_evaluation(
            "opp-uncertain",
            decision="uncertain",
            fit_score=55.5,
            evaluation_detail={
                "hard_constraints": [
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
                "strengths": ["strength one"],
                "gaps": ["gap one"],
                "unknowns": ["unknown one"],
                "uncertainty_penalty": 0.1,
                "explanation": "synthetic evaluation for API tests",
            },
        )

        # Confirm the row actually landed with a real evaluation_detail_json
        # payload before trusting the HTTP response derived from it.
        persisted = (
            self.session.query(MatchEvaluationRecord)
            .filter_by(opportunity_id="opp-uncertain")
            .one()
        )
        self.assertIsNotNone(persisted.evaluation_detail_json)
        self.assertIn("security_clearance", persisted.evaluation_detail_json)

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
        self.assertEqual(body["scoring"]["uncertainty_penalty"], 0.1)
        self.assertEqual(body["scoring"]["strengths"], ["strength one"])
        self.assertEqual(body["scoring"]["gaps"], ["gap one"])
        self.assertEqual(body["scoring"]["unknowns"], ["unknown one"])
        self.assertEqual(len(body["scoring"]["dimension_scores"]), 1)
        self.assertEqual(body["scoring"]["dimension_scores"][0]["dimension"], "core_skills")
        self.assertIn("score", body["scoring"]["dimension_scores"][0])

        self.assertEqual(len(body["fields"]), 1)
        self.assertEqual(body["fields"][0]["field_name"], "title")

    def test_detail_falls_back_to_reasons_derived_strengths_when_detail_is_null(self):
        """Legitimate backward compatibility for a row persisted before
        `evaluation_detail_json` existed (or simply never populated for it):
        with that column `NULL`, `strengths`/`gaps`/`unknowns` must still be
        populated by deriving them from `reasons_json`'s
        `{"kind", "dimension", "text"}` list, and `top_reasons` on the list
        route must read from that same list shape."""
        self.seed_opportunity("opp-fallback")
        self.seed_evaluation(
            "opp-fallback",
            decision="qualified",
            fit_score=72.0,
            reasons=[
                {"kind": "strength", "dimension": "core_skills", "text": "strong python background"},
                {"kind": "gap", "dimension": "domain_experience", "text": "no prior nonprofit work"},
                {"kind": "unknown", "dimension": "compensation_fit", "text": "salary range not disclosed"},
            ],
            # evaluation_detail intentionally omitted -> evaluation_detail_json is NULL.
        )

        persisted = (
            self.session.query(MatchEvaluationRecord)
            .filter_by(opportunity_id="opp-fallback")
            .one()
        )
        self.assertIsNone(persisted.evaluation_detail_json)

        detail = self.client.get("/api/opportunities/opp-fallback")
        self.assertEqual(detail.status_code, 200)
        scoring = detail.json()["scoring"]
        self.assertEqual(scoring["strengths"], ["strong python background"])
        self.assertEqual(scoring["gaps"], ["no prior nonprofit work"])
        self.assertEqual(scoring["unknowns"], ["salary range not disclosed"])
        # evaluation_detail_json is NULL -> hard_constraints has nowhere to
        # come from for this row, so it is empty rather than fabricated.
        self.assertEqual(detail.json()["qualification"]["constraints"], [])

        listing = self.client.get("/api/opportunities")
        self.assertEqual(listing.status_code, 200)
        item = next(i for i in listing.json()["items"] if i["id"] == "opp-fallback")
        self.assertEqual(
            item["top_reasons"],
            ["strong python background", "no prior nonprofit work", "salary range not disclosed"],
        )

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
    includes a `MetricAssertion`): exercising the metrics section of
    `EmploymentArtifactCompiler.compile_tailored_cv` pulls in
    `MetricAssertion.context` and the metric-specific validation path in
    `ClaimValidator`, which is unrelated to what this fixture needs to prove.
    This fixture avoids the metrics codepath entirely so the clean 200 case
    stays a single, minimal claim.

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


def _unsupported_skill_term_graph() -> TruthGraph:
    """ADR-0014 tripwire fixture: an unsupported FOUNDER-specific term must
    still be rejected once classes (b)/(c) are wired into
    `ClaimValidator.validate_claim`.

    This exploits a documented, pre-existing gap the same shape as
    `_mismatched_truth_pack_graph`'s polarity gap, but for lexical coverage
    instead of negation: `TruthGraph.add_career_profile`'s field-provenance
    check resolves a skill name through `truth.ingest.CANONICAL_SKILL_ALIASES`
    (so a skill literally named "K8s" is accepted against evidence that only
    ever says "Kubernetes" -- "k8s" -> "Kubernetes" is a known alias, and the
    canonical form's tokens are what the graph checks against the evidence).
    `ClaimValidator.validate_claim` has no such alias fallback: it requires
    the claim text's own literal words to be covered by cited evidence,
    `CONNECTIVE_TERMS`, or caller-supplied opportunity terms -- none of
    which is "k8s" here. The compiler's atomic skill claim (bare
    `str(skill.value)`, i.e. "K8s") is therefore rejected, proving classes
    (b)/(c) cannot rescue a term that is not genuinely evidence-backed,
    connective boilerplate, or a real opportunity field value.
    """
    evidence = (
        EvidenceRecord("ev-k8s", "Has hands-on Kubernetes experience.", "synthetic_cv", "skills.0"),
    )
    graph = TruthGraph(evidence)
    profile = CareerProfile(
        id="career-alias-gap",
        evidence_ids=(),
        skills=(SkillRecord("skill-k8s", "K8s", ("ev-k8s",)),),
    )
    graph.add_career_profile(profile)
    return graph


def _class_b_c_admissible_graph() -> TruthGraph:
    """ADR-0014 tripwire fixture: a claim whose only "uncovered" terms are
    class (b) (opportunity-provenanced, e.g. the target role/employer name)
    or class (c) (the committed `truth/connective_terms.txt` stop-list) must
    NOT be rejected.

    A single, evidence-backed employment title ("Data Engineer", cited to
    its own evidence) is enough to make `EmploymentArtifactCompiler.
    compile_cover_letter` emit the `claim-cover-role` claim, which by design
    (see `matching/compiler_employment.py`) combines that one founder fact
    with the target opportunity's own title/organization words -- admissible
    only because `_compile_and_export` derives `opportunity_terms` from this
    exact `Opportunity`'s real field values -- and generic letter-structure
    words ("professional", "background", "applying", "role") on the
    committed connective stop-list.
    """
    evidence = (
        EvidenceRecord(
            "ev-cb-org", "Prior Employer Ltd", "synthetic_cv", "employment.0.organization",
            metadata={"organization": "Prior Employer Ltd"},
        ),
        EvidenceRecord(
            "ev-cb-title", "Data Engineer", "synthetic_cv", "employment.0.title",
            metadata={"title": "Data Engineer"},
        ),
        EvidenceRecord("ev-cb-dates", "2020-01-01 to 2022-01-01", "synthetic_cv", "employment.0.dates"),
    )
    graph = TruthGraph(evidence)
    profile = CareerProfile(
        id="career-class-bc",
        evidence_ids=(),
        employment=(
            EmploymentRecord(
                id="job-class-bc", organization="Prior Employer Ltd", title="Data Engineer",
                start_date=date(2020, 1, 1), end_date=date(2022, 1, 1),
                evidence_ids=("ev-cb-org", "ev-cb-title", "ev-cb-dates"),
            ),
        ),
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

        # ADR-0014 tripwire, "saw_rejection" style: classes (b)/(c) must be
        # structurally incapable of rescuing an unsupported FOUNDER-specific
        # term. This calls `ClaimValidator.validate_claim` directly (fresh,
        # single-evidence graph, isolated from the polarity gap the HTTP
        # assertions above exercise) and would FAIL if guard 9 (material
        # lexical coverage) were ever neutralised, or if the boundary of
        # class (b)/(c) admissibility were ever loosened from "this exact,
        # closed set of words" to "any unrecognised word".
        clean_evidence = EvidenceRecord(
            "ev-tripwire-title", "Data Engineer with distributed systems background.",
            "synthetic_cv", "employment.title",
        )
        direct_graph = TruthGraph((clean_evidence,))
        direct_validator = ClaimValidator(direct_graph)
        fabricated_term = "zorbaflex"  # not a real word: cannot coincidentally
        # be evidence-backed, on the committed connective stop-list, or a real
        # opportunity field value.
        fabricated_claim = f"Data Engineer with {fabricated_term} background."

        rejected = direct_validator.validate_claim(fabricated_claim, ("ev-tripwire-title",))
        saw_rejection = not rejected.allowed and any(
            fabricated_term in reason for reason in rejected.reasons
        )
        self.assertTrue(
            saw_rejection,
            f"expected the validator to reject an unsupported founder term; got {rejected}",
        )

        # The SAME claim passes once (and only once) the fabricated term is
        # explicitly declared class (b) -- proving admissibility is scoped
        # exactly to the caller-supplied set, not a general escape hatch.
        rescued = direct_validator.validate_claim(
            fabricated_claim, ("ev-tripwire-title",), opportunity_terms={fabricated_term},
        )
        self.assertTrue(rescued.allowed, rescued.reasons)

    def test_artifact_409_on_unsupported_founder_term_via_skill_alias_gap(self):
        """ADR-0014: an unsupported FOUNDER-specific term still 409s and
        never returns docx bytes through the real HTTP path, even with
        classes (b)/(c) wired into `_compile_and_export`'s validation loop.
        See `_unsupported_skill_term_graph` for the exact mechanism."""
        import unittest.mock as mock

        self.seed_opportunity("opp-alias-gap")
        app = self.make_app()
        client = self.logged_in_client(app)

        with mock.patch("api.routes_api.load_founder_pack") as loader:
            from truth.pack import LoadedPack, PackValidationReport

            graph = _unsupported_skill_term_graph()
            loader.return_value = LoadedPack(
                graph=graph,
                report=PackValidationReport(valid=True, section_counts=(("evidence", 1),)),
                truth_pack_hash="alias-gap-hash",
            )
            client.post("/api/truth/reload")

            response = client.get("/api/opportunities/opp-alias-gap/artifacts/cv.docx")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.content.startswith(b"PK"))
        body = response.json()
        self.assertGreaterEqual(len(body["findings"]), 1)
        self.assertTrue(
            any("k8s" in finding["claim"].casefold() for finding in body["findings"]),
            body["findings"],
        )

    def test_artifact_200_when_only_uncovered_terms_are_opportunity_or_connective(self):
        """ADR-0014: a claim whose only uncovered terms are class (b)
        (opportunity-provenanced -- the target role/employer name, derived
        by `_compile_and_export` from this exact Opportunity's real field
        values) or class (c) (the committed connective stop-list) is not
        rejected. See `_class_b_c_admissible_graph` for the exact claim this
        exercises."""
        import unittest.mock as mock

        self.seed_opportunity("opp-class-bc")
        app = self.make_app()
        client = self.logged_in_client(app)

        with mock.patch("api.routes_api.load_founder_pack") as loader:
            from truth.pack import LoadedPack, PackValidationReport

            graph = _class_b_c_admissible_graph()
            loader.return_value = LoadedPack(
                graph=graph,
                report=PackValidationReport(valid=True, section_counts=(("evidence", 1),)),
                truth_pack_hash="class-bc-hash",
            )
            client.post("/api/truth/reload")

            response = client.get("/api/opportunities/opp-class-bc/artifacts/cover-letter.docx")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertTrue(response.content.startswith(b"PK"), "response body is not a docx/zip payload")

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

    def test_expired_snooze_resurfaces_instead_of_raising(self):
        """Council-flagged timezone hazard: every `DateTime` column is naive
        while every value this codebase writes is aware UTC
        (`datetime.now(timezone.utc)`), so a value read back through the ORM
        is naive but represents a UTC instant. Comparing that naive value
        directly against `datetime.now(timezone.utc)` used to raise
        `TypeError: can't compare offset-naive and offset-aware datetimes`.
        This seeds an already-expired `snoozed_until` (bypassing the
        actions route's own future-date validation, which cannot itself
        create an expired snooze) and proves the comparison neither raises
        nor keeps suppressing the opportunity forever."""
        expired_until = datetime.now(timezone.utc) - timedelta(days=1)
        self.session.add(
            FounderTriageStateRecord(
                opportunity_id="opp-fb",
                state="snoozed",
                snoozed_until=expired_until,
                created_at=datetime.now(timezone.utc) - timedelta(days=10),
                updated_at=datetime.now(timezone.utc) - timedelta(days=10),
            )
        )
        self.session.commit()

        detail = self.client.get("/api/opportunities/opp-fb")
        self.assertEqual(detail.status_code, 200)  # not a 500 from a naive/aware TypeError

        listing = self.client.get("/api/opportunities")
        self.assertEqual(listing.status_code, 200)
        item = next(i for i in listing.json()["items"] if i["id"] == "opp-fb")
        self.assertIsNone(item["action_state"], "an expired snooze must resurface the opportunity, not suppress it forever")

    def test_active_snooze_still_reports_snoozed(self):
        future_until = datetime.now(timezone.utc) + timedelta(days=3)
        self.session.add(
            FounderTriageStateRecord(
                opportunity_id="opp-fb",
                state="snoozed",
                snoozed_until=future_until,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()

        listing = self.client.get("/api/opportunities")
        self.assertEqual(listing.status_code, 200)
        item = next(i for i in listing.json()["items"] if i["id"] == "opp-fb")
        self.assertEqual(item["action_state"], "snoozed")


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
                # D3 (BRIEF-FR-005): every series entry also carries the count of
                # that day's opportunities currently hidden by an enabled `hide`
                # filter. Zero here because no opportunity was seeded for this day.
                "hidden_by_filters": 0,
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


# ---------------------------------------------------------------------------
# High-fit threshold default
# ---------------------------------------------------------------------------


class HighFitThresholdDefaultTest(unittest.TestCase):
    """`fit_score` is stored 0-100 (`MatchEvaluation.overall_fit_score`).
    The brief's own prose says 'default 0.7', which on a 0-100 column would
    make nearly every scored row count as high-fit and silently break the
    founder's measured daily number. Pins the real default at 70.0. Does
    not need PostgreSQL connectivity: `Settings`/`load_settings` only
    validate the URL's scheme string, and `get_engine` does not connect
    until a query is actually issued.
    """

    def test_settings_module_constant_is_70(self):
        from api.settings import DEFAULT_HIGH_FIT_THRESHOLD

        self.assertEqual(DEFAULT_HIGH_FIT_THRESHOLD, 70.0)

    def test_load_settings_defaults_to_70_when_env_var_unset(self):
        keys = (
            "OPPORTUNITYOS_DB_URL",
            "OPPORTUNITYOS_FOUNDER_PASSWORD",
            "OPPORTUNITYOS_SESSION_SECRET",
            "OPPORTUNITYOS_HIGH_FIT_THRESHOLD",
        )
        saved = {key: os.environ.get(key) for key in keys}
        try:
            os.environ["OPPORTUNITYOS_DB_URL"] = "postgresql+psycopg2://user:pw@localhost:5432/db"
            os.environ["OPPORTUNITYOS_FOUNDER_PASSWORD"] = "x"
            os.environ["OPPORTUNITYOS_SESSION_SECRET"] = "y"
            os.environ.pop("OPPORTUNITYOS_HIGH_FIT_THRESHOLD", None)

            from api.settings import load_settings

            settings = load_settings()
            self.assertEqual(settings.high_fit_threshold, 70.0)
            self.assertNotEqual(settings.high_fit_threshold, 0.7)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_settings_dataclass_default_is_70(self):
        from api.settings import Settings

        settings = Settings(
            db_url="postgresql+psycopg2://user:pw@localhost:5432/db",
            founder_password="x",
            session_secret="y",
        )
        self.assertEqual(settings.high_fit_threshold, 70.0)


# ---------------------------------------------------------------------------
# D3 (BRIEF-FR-005): founder-controlled filters
# ---------------------------------------------------------------------------


class FilterSeedSyncTest(unittest.TestCase):
    """Migration 0003's `_D3_FILTER_SEED` (a deliberate independent literal
    copy, not an import -- see that migration's module docstring) must never
    drift from `api.filters.FILTER_DEFINITIONS`'s defaults. No PostgreSQL
    connectivity needed: this only imports the migration module and compares
    two in-memory Python structures."""

    def test_migration_seed_matches_filter_definitions_defaults(self):
        import importlib.util

        migration_path = REPO_ROOT / "storage" / "migrations" / "versions" / "0003_provenance_identity.py"
        spec = importlib.util.spec_from_file_location("_d3_migration_0003", migration_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        seed_by_id = {row[0]: row for row in module._D3_FILTER_SEED}
        self.assertEqual(set(seed_by_id), {fd.filter_id for fd in FILTER_DEFINITIONS})
        for fd in FILTER_DEFINITIONS:
            _, enabled, mode, params = seed_by_id[fd.filter_id]
            self.assertEqual(enabled, fd.default_enabled, fd.filter_id)
            self.assertEqual(mode, fd.default_mode, fd.filter_id)
            self.assertEqual(params, fd.default_params, fd.filter_id)


class FilterSettingsRouteTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.client = self.logged_in_client(self.app)

    def test_get_filters_lists_all_ten_with_defaults(self):
        resp = self.client.get("/api/filters")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        by_id = {f["filter_id"]: f for f in body["filters"]}
        self.assertEqual(set(by_id), {fd.filter_id for fd in FILTER_DEFINITIONS})
        for fd in FILTER_DEFINITIONS:
            entry = by_id[fd.filter_id]
            self.assertEqual(entry["enabled"], fd.default_enabled, fd.filter_id)
            self.assertEqual(entry["mode"], fd.default_mode, fd.filter_id)
            self.assertEqual(entry["params"], fd.default_params, fd.filter_id)
            self.assertEqual(entry["affected_count"], 0, fd.filter_id)  # no opportunities seeded
            self.assertEqual(entry["description"], fd.description, fd.filter_id)

    def test_put_unknown_filter_id_404(self):
        resp = self.client.put("/api/filters/does-not-exist", json={"enabled": False})
        self.assertEqual(resp.status_code, 404)

    def test_put_invalid_mode_422(self):
        resp = self.client.put("/api/filters/stale_postings", json={"mode": "delete_forever"})
        self.assertEqual(resp.status_code, 422)

    def test_put_updates_only_supplied_fields(self):
        before = {f["filter_id"]: f for f in self.client.get("/api/filters").json()["filters"]}
        before_stale = before["stale_postings"]

        resp = self.client.put("/api/filters/stale_postings", json={"mode": "hide"})
        self.assertEqual(resp.status_code, 200, resp.text)
        updated = resp.json()
        self.assertEqual(updated["mode"], "hide")
        self.assertEqual(updated["enabled"], before_stale["enabled"])
        self.assertEqual(updated["params"], before_stale["params"])

        resp2 = self.client.put(
            "/api/filters/min_fit_score", json={"enabled": True, "params": {"min_score": 60}}
        )
        self.assertEqual(resp2.status_code, 200, resp2.text)
        updated2 = resp2.json()
        self.assertTrue(updated2["enabled"])
        self.assertEqual(updated2["mode"], "hide")  # unchanged default
        self.assertEqual(updated2["params"], {"min_score": 60})

    def test_affected_count_reflects_matches_regardless_of_enabled(self):
        self.seed_opportunity("opp-stale", is_stale=True)
        self.seed_evaluation("opp-stale", decision="qualified", fit_score=50.0)
        self.seed_opportunity("opp-fresh", is_stale=False)
        self.seed_evaluation("opp-fresh", decision="qualified", fit_score=50.0)

        resp = self.client.put("/api/filters/stale_postings", json={"enabled": False})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertFalse(resp.json()["enabled"])
        self.assertEqual(resp.json()["affected_count"], 1)

        body = self.client.get("/api/filters").json()
        entry = next(f for f in body["filters"] if f["filter_id"] == "stale_postings")
        self.assertFalse(entry["enabled"])
        self.assertEqual(entry["affected_count"], 1)


class FilterEngineOpportunitiesTest(ApiTestCase):
    """Contract section 7: each filter's three modes plus disabled, the A-13
    total-equals-table-count assertion, the defaults hidden set, and the
    red-line-toggled-off decision/fit_score invariant."""

    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.client = self.logged_in_client(self.app)

    # -- helpers ------------------------------------------------------

    def _set_filter(self, filter_id: str, *, enabled: bool, mode: str, params: dict | None = None):
        payload: dict = {"enabled": enabled, "mode": mode}
        if params is not None:
            payload["params"] = params
        resp = self.client.put(f"/api/filters/{filter_id}", json=payload)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def _items_by_id(self, **params):
        query = {"include_hidden": True}
        query.update(params)
        resp = self.client.get("/api/opportunities", params=query)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        return {item["id"]: item for item in body["items"]}, body

    def _assert_hide_rank_label_disabled(
        self, filter_id: str, *, matched_id: str, control_id: str, params: dict | None = None
    ):
        """The generic four-state check shared by every filter here whose
        match condition is independent of `fit_score` (all but
        `min_fit_score`, tested separately below). `matched_id` is always
        seeded with a *higher* fit_score than `control_id`, so `rank_only`
        demotion (matched sorts after control despite the higher score) is
        distinguishable from ordinary fit_score-descending order, which would
        already put `matched_id` first with no filter in effect."""
        # -- disabled: filter contributes to neither hidden_by nor flagged_by
        self._set_filter(filter_id, enabled=False, mode="hide", params=params)
        items, _ = self._items_by_id()
        self.assertEqual(items[matched_id]["hidden_by"], [])
        self.assertEqual(items[matched_id]["flagged_by"], [])

        matched_fit_score = items[matched_id]["fit_score"]
        matched_decision = items[matched_id]["decision"]

        # -- hide: hidden by default, visible only with include_hidden=true --
        self._set_filter(filter_id, enabled=True, mode="hide", params=params)
        items, _ = self._items_by_id()
        self.assertIn(filter_id, items[matched_id]["hidden_by"])
        self.assertNotIn(filter_id, items[control_id]["hidden_by"])
        # The invariant that outranks everything else in D3: a hide toggle
        # never touches decision or fit_score.
        self.assertEqual(items[matched_id]["fit_score"], matched_fit_score)
        self.assertEqual(items[matched_id]["decision"], matched_decision)

        default_ids = {item["id"] for item in self.client.get("/api/opportunities").json()["items"]}
        self.assertNotIn(matched_id, default_ids)
        self.assertIn(control_id, default_ids)

        # -- rank_only: never hidden, flagged, demoted below control despite
        # a strictly higher fit_score; fit_score itself is untouched --------
        self._set_filter(filter_id, enabled=True, mode="rank_only", params=params)
        items, body = self._items_by_id()
        self.assertEqual(items[matched_id]["hidden_by"], [])
        self.assertIn(filter_id, items[matched_id]["flagged_by"])
        self.assertEqual(items[matched_id]["fit_score"], matched_fit_score)
        self.assertEqual(items[matched_id]["decision"], matched_decision)
        order = [item["id"] for item in body["items"]]
        self.assertLess(order.index(control_id), order.index(matched_id))

        # -- label_only: flagged, but order is untouched -- matched keeps its
        # higher-fit_score rank ahead of control -----------------------------
        self._set_filter(filter_id, enabled=True, mode="label_only", params=params)
        items, body = self._items_by_id()
        self.assertEqual(items[matched_id]["hidden_by"], [])
        self.assertIn(filter_id, items[matched_id]["flagged_by"])
        order = [item["id"] for item in body["items"]]
        self.assertLess(order.index(matched_id), order.index(control_id))

    # -- one test per filter -------------------------------------------

    def test_geo_eligibility_modes(self):
        failing_detail = {
            "hard_constraints": [
                {
                    "constraint_name": "geographic_eligibility",
                    "passed": False,
                    "reason": "excluded",
                    "required_field": "geographic_eligibility",
                    "founder_fact": "policy exclusion",
                    "is_hard_failure": True,
                    "provenance_pointer": "p",
                }
            ],
            "strengths": [], "gaps": [], "unknowns": [], "uncertainty_penalty": 0.0, "explanation": "",
        }
        passing_detail = {
            "hard_constraints": [
                {
                    "constraint_name": "geographic_eligibility",
                    "passed": True,
                    "reason": "eligible",
                    "required_field": "geographic_eligibility",
                    "founder_fact": "ok",
                    "is_hard_failure": False,
                    "provenance_pointer": "p",
                }
            ],
            "strengths": [], "gaps": [], "unknowns": [], "uncertainty_penalty": 0.0, "explanation": "",
        }
        self.seed_opportunity("opp-match")
        self.seed_evaluation("opp-match", decision="ineligible", fit_score=90.0, evaluation_detail=failing_detail)
        self.seed_opportunity("opp-control")
        self.seed_evaluation("opp-control", decision="qualified", fit_score=50.0, evaluation_detail=passing_detail)
        self._assert_hide_rank_label_disabled("geo_eligibility", matched_id="opp-match", control_id="opp-control")

    def test_work_mode_onsite_modes(self):
        failing_detail = {
            "hard_constraints": [
                {
                    "constraint_name": "work_mode_onsite",
                    "passed": False,
                    "reason": "on-site mismatch",
                    "required_field": "remote_policy",
                    "founder_fact": "founder elsewhere",
                    "is_hard_failure": True,
                    "provenance_pointer": "p",
                }
            ],
            "strengths": [], "gaps": [], "unknowns": [], "uncertainty_penalty": 0.0, "explanation": "",
        }
        passing_detail = {
            "hard_constraints": [
                {
                    "constraint_name": "work_mode_onsite",
                    "passed": True,
                    "reason": "on-site matches founder location",
                    "required_field": "remote_policy",
                    "founder_fact": "founder co-located",
                    "is_hard_failure": False,
                    "provenance_pointer": "p",
                }
            ],
            "strengths": [], "gaps": [], "unknowns": [], "uncertainty_penalty": 0.0, "explanation": "",
        }
        self.seed_opportunity("opp-match")
        self.seed_evaluation("opp-match", decision="ineligible", fit_score=90.0, evaluation_detail=failing_detail)
        self.seed_opportunity("opp-control")
        self.seed_evaluation("opp-control", decision="qualified", fit_score=50.0, evaluation_detail=passing_detail)
        self._assert_hide_rank_label_disabled("work_mode_onsite", matched_id="opp-match", control_id="opp-control")

    def test_red_lines_modes(self):
        _install_truth_graph(self.app, _graph_with_red_line_and_excluded_industry())
        self.seed_opportunity(
            "opp-match", title="Sales Role",
            description="We guarantee placement for every candidate within 30 days.",
        )
        self.seed_evaluation("opp-match", decision="qualified", fit_score=90.0)
        self.seed_opportunity(
            "opp-control", title="Backend Engineer", description="A normal, unremarkable job posting."
        )
        self.seed_evaluation("opp-control", decision="qualified", fit_score=50.0)
        self._assert_hide_rank_label_disabled("red_lines", matched_id="opp-match", control_id="opp-control")

    def test_excluded_industries_modes(self):
        _install_truth_graph(self.app, _graph_with_red_line_and_excluded_industry())
        self.seed_opportunity(
            "opp-match", organization="Golden Gambling Corp", description="Operate our online gambling platform."
        )
        self.seed_evaluation("opp-match", decision="qualified", fit_score=90.0)
        self.seed_opportunity("opp-control", organization="Widget Co", description="Build widgets for clients.")
        self.seed_evaluation("opp-control", decision="qualified", fit_score=50.0)
        self._assert_hide_rank_label_disabled("excluded_industries", matched_id="opp-match", control_id="opp-control")

    def test_track_preference_modes(self):
        _install_truth_graph(self.app, _graph_with_founder_preferences(preferred_track="employment"))
        self.seed_opportunity("opp-match", track="procurement")
        self.seed_evaluation("opp-match", decision="qualified", fit_score=90.0)
        self.seed_opportunity("opp-control", track="employment")
        self.seed_evaluation("opp-control", decision="qualified", fit_score=50.0)
        self._assert_hide_rank_label_disabled("track_preference", matched_id="opp-match", control_id="opp-control")

    def test_target_roles_modes(self):
        _install_truth_graph(self.app, _graph_with_founder_preferences(target_role="Senior Backend Engineer"))
        self.seed_opportunity("opp-match", title="Marketing Coordinator")
        self.seed_evaluation("opp-match", decision="qualified", fit_score=90.0)
        self.seed_opportunity("opp-control", title="Senior Backend Engineer")
        self.seed_evaluation("opp-control", decision="qualified", fit_score=50.0)
        self._assert_hide_rank_label_disabled("target_roles", matched_id="opp-match", control_id="opp-control")

    def test_premium_fulltime_onsite_modes(self):
        premium_gap_dimension = [
            {
                "dimension_name": "compensation_fit",
                "raw_score": 0.35,
                "weight": 0.05,
                "weighted_score": 0.0175,
                "explanation": "Compensation evaluated against founder target policy.",
                "strengths": [],
                "gaps": [
                    "Full-time on-site compensation (~40000 EGP/month) is below the founder's full-time "
                    "on-site premium threshold (85000 EGP/month)"
                ],
                "unknowns": [],
                "evidence_refs": ["a-premium-threshold"],
                "opportunity_field_refs": ["compensation"],
            }
        ]
        no_gap_dimension = [
            {
                "dimension_name": "compensation_fit",
                "raw_score": 0.9,
                "weight": 0.05,
                "weighted_score": 0.045,
                "explanation": "Compensation evaluated against founder target policy.",
                "strengths": ["Opportunity compensation meets target"],
                "gaps": [],
                "unknowns": [],
                "evidence_refs": [],
                "opportunity_field_refs": ["compensation"],
            }
        ]
        self.seed_opportunity("opp-match")
        self.seed_evaluation(
            "opp-match", decision="qualified", fit_score=90.0, dimension_scores=premium_gap_dimension
        )
        self.seed_opportunity("opp-control")
        self.seed_evaluation(
            "opp-control", decision="qualified", fit_score=50.0, dimension_scores=no_gap_dimension
        )
        self._assert_hide_rank_label_disabled(
            "premium_fulltime_onsite", matched_id="opp-match", control_id="opp-control"
        )

    def test_stale_postings_modes(self):
        self.seed_opportunity("opp-match", is_stale=True)
        self.seed_evaluation("opp-match", decision="qualified", fit_score=90.0)
        self.seed_opportunity("opp-control", is_stale=False)
        self.seed_evaluation("opp-control", decision="qualified", fit_score=50.0)
        self._assert_hide_rank_label_disabled("stale_postings", matched_id="opp-match", control_id="opp-control")

    def test_compensation_floor_modes(self):
        self.seed_opportunity("opp-match")
        self.seed_evaluation("opp-match", decision="qualified", fit_score=90.0)
        self.seed_compensation("opp-match", min_amount=20000, max_amount=25000, currency="EGP")
        self.seed_opportunity("opp-control")
        self.seed_evaluation("opp-control", decision="qualified", fit_score=50.0)
        self.seed_compensation("opp-control", min_amount=90000, max_amount=95000, currency="EGP")
        self._assert_hide_rank_label_disabled(
            "compensation_floor",
            matched_id="opp-match",
            control_id="opp-control",
            params={"floor": 50000, "currency": "EGP"},
        )

    def test_min_fit_score_modes(self):
        """Bespoke, not `_assert_hide_rank_label_disabled`: this filter's own
        match condition (`fit_score < min_score`) is defined in terms of the
        exact value the generic helper otherwise uses to distinguish
        rank-demotion from ordinary score ordering, so it is tested directly
        instead."""
        self.seed_opportunity("opp-match")
        self.seed_evaluation("opp-match", decision="qualified", fit_score=20.0)
        self.seed_opportunity("opp-control")
        self.seed_evaluation("opp-control", decision="qualified", fit_score=80.0)
        params = {"min_score": 50}

        self._set_filter("min_fit_score", enabled=False, mode="hide", params=params)
        items, _ = self._items_by_id()
        self.assertEqual(items["opp-match"]["hidden_by"], [])
        self.assertEqual(items["opp-match"]["flagged_by"], [])

        self._set_filter("min_fit_score", enabled=True, mode="hide", params=params)
        items, _ = self._items_by_id()
        self.assertIn("min_fit_score", items["opp-match"]["hidden_by"])
        self.assertNotIn("min_fit_score", items["opp-control"]["hidden_by"])
        self.assertEqual(items["opp-match"]["fit_score"], 20.0)
        default_ids = {item["id"] for item in self.client.get("/api/opportunities").json()["items"]}
        self.assertNotIn("opp-match", default_ids)
        self.assertIn("opp-control", default_ids)

        self._set_filter("min_fit_score", enabled=True, mode="rank_only", params=params)
        items, body = self._items_by_id()
        self.assertEqual(items["opp-match"]["hidden_by"], [])
        self.assertIn("min_fit_score", items["opp-match"]["flagged_by"])
        self.assertEqual(items["opp-match"]["fit_score"], 20.0)
        order = [item["id"] for item in body["items"]]
        self.assertLess(order.index("opp-control"), order.index("opp-match"))

        self._set_filter("min_fit_score", enabled=True, mode="label_only", params=params)
        items, _ = self._items_by_id()
        self.assertEqual(items["opp-match"]["hidden_by"], [])
        self.assertIn("min_fit_score", items["opp-match"]["flagged_by"])

    # -- contract section 7's named, cross-cutting assertions -----------

    def test_a13_all_filters_off_include_hidden_total_equals_table_count(self):
        for fd in FILTER_DEFINITIONS:
            self._set_filter(fd.filter_id, enabled=False, mode=fd.default_mode)

        self.seed_opportunity("opp-1")
        self.seed_evaluation("opp-1", decision="qualified", fit_score=80.0)
        self.seed_opportunity("opp-2")  # never evaluated -> decision/fit_score null
        self.seed_opportunity("opp-3", is_stale=True)
        self.seed_evaluation("opp-3", decision="ineligible", fit_score=10.0)

        resp = self.client.get("/api/opportunities", params={"include_hidden": True})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()

        actual_count = self.session.query(OpportunityRecord).count()
        self.assertEqual(actual_count, 3)
        self.assertEqual(body["total"], actual_count)
        self.assertEqual(body["hidden_count"], 0)

    def test_defaults_hidden_set_is_exactly_red_line_and_excluded_industry_hits(self):
        _install_truth_graph(self.app, _graph_with_red_line_and_excluded_industry())

        self.seed_opportunity(
            "opp-redline", description="We guarantee placement for every candidate within 30 days."
        )
        self.seed_evaluation("opp-redline", decision="qualified", fit_score=80.0)

        self.seed_opportunity("opp-industry", organization="Golden Gambling Corp")
        self.seed_evaluation("opp-industry", decision="qualified", fit_score=70.0)

        self.seed_opportunity("opp-geo-uncertain")
        self.seed_evaluation(
            "opp-geo-uncertain",
            decision="uncertain",
            fit_score=60.0,
            evaluation_detail={
                "hard_constraints": [
                    {
                        "constraint_name": "geographic_eligibility",
                        "passed": None,
                        "reason": "unclear",
                        "required_field": "geographic_eligibility",
                        "founder_fact": "?",
                        "is_hard_failure": False,
                        "provenance_pointer": "p",
                    }
                ],
                "strengths": [], "gaps": [], "unknowns": [], "uncertainty_penalty": 0.0, "explanation": "",
            },
        )  # geo_eligibility is label_only by default -> flagged, never hidden

        self.seed_opportunity("opp-clean")
        self.seed_evaluation("opp-clean", decision="qualified", fit_score=50.0)

        resp = self.client.get("/api/opportunities", params={"include_hidden": True})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        hidden_ids = {item["id"] for item in body["items"] if item["hidden_by"]}
        self.assertEqual(hidden_ids, {"opp-redline", "opp-industry"})
        self.assertEqual(body["hidden_count"], 2)

        geo_item = next(item for item in body["items"] if item["id"] == "opp-geo-uncertain")
        self.assertEqual(geo_item["hidden_by"], [])
        self.assertIn("geo_eligibility", geo_item["flagged_by"])

    def test_red_line_toggled_off_shows_item_with_identical_decision_and_fit_score(self):
        _install_truth_graph(self.app, _graph_with_red_line_and_excluded_industry())
        self.seed_opportunity(
            "opp-redline", description="We guarantee placement for every candidate within 30 days."
        )
        self.seed_evaluation("opp-redline", decision="qualified", fit_score=77.0)

        on_items, _ = self._items_by_id()
        self.assertIn("red_lines", on_items["opp-redline"]["hidden_by"])
        decision_on = on_items["opp-redline"]["decision"]
        fit_score_on = on_items["opp-redline"]["fit_score"]

        self._set_filter("red_lines", enabled=False, mode="hide")
        default_resp = self.client.get("/api/opportunities")
        self.assertEqual(default_resp.status_code, 200, default_resp.text)
        default_items = {item["id"]: item for item in default_resp.json()["items"]}

        self.assertIn("opp-redline", default_items)
        off_item = default_items["opp-redline"]
        self.assertEqual(off_item["hidden_by"], [])
        self.assertEqual(off_item["decision"], decision_on)
        self.assertEqual(off_item["fit_score"], fit_score_on)


if __name__ == "__main__":
    unittest.main()
