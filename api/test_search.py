"""BRIEF-FR-006 work order C2: full-text search.

These tests build on `ApiTestCase` (real PostgreSQL, see `api/test_api.py`'s
module docstring) plus one pure-`unittest.TestCase` class for
`api.search.rank_key`, which needs no database at all.
"""

from __future__ import annotations

import unittest

from storage.models import MatchEvaluationRecord, OpportunityRecord
from storage.repository import backfill_search_tsv

from api.search import is_query_unparseable, rank_key, search_opportunity_ids
from api.test_api import ApiTestCase, _install_truth_graph
from truth.graph import TruthGraph


# ---------------------------------------------------------------------------
# C2.7 (part 1): the ranking formula itself, as a pure function -- no
# database, so ordering claims here are exact, not dependent on reasoning
# about Postgres's actual `ts_rank` output.
# ---------------------------------------------------------------------------


class RankKeyFormulaTest(unittest.TestCase):
    """`api.search.rank_key`: relevance x fit (fit normalised 0-100 -> 0-1;
    `None` fit_score -> neutral 0.5 multiplier)."""

    def test_higher_fit_at_equal_relevance_ranks_higher(self):
        self.assertGreater(rank_key(0.5, 90.0), rank_key(0.5, 10.0))

    def test_higher_relevance_at_equal_fit_ranks_higher(self):
        self.assertGreater(rank_key(0.8, 50.0), rank_key(0.2, 50.0))

    def test_relevance_can_outweigh_a_large_fit_gap(self):
        # This is the case that actually distinguishes "relevance x fit"
        # from "fit_score alone": a very-high-relevance, low-fit row can
        # still outrank a barely-relevant, very-high-fit row.
        self.assertGreater(rank_key(1.0, 5.0), rank_key(0.01, 100.0))

    def test_missing_fit_score_uses_neutral_half_multiplier(self):
        self.assertAlmostEqual(rank_key(0.4, None), 0.4 * 0.5)

    def test_zero_relevance_is_always_zero_regardless_of_fit(self):
        self.assertEqual(rank_key(0.0, 100.0), 0.0)
        self.assertEqual(rank_key(0.0, None), 0.0)


# ---------------------------------------------------------------------------
# C2.4: adversarial input must never produce a 500.
# ---------------------------------------------------------------------------


class SearchAdversarialTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.client = self.logged_in_client(self.app)
        self.seed_opportunity(
            "opp-baseline", title="Data Engineer", description="Works with pytorch and airflow."
        )

    def _assert_never_500(self, q: str) -> dict:
        response = self.client.get("/api/opportunities", params={"q": q})
        self.assertNotEqual(response.status_code, 500, response.text)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsInstance(body["items"], list)
        return body

    def test_unbalanced_quote(self):
        body = self._assert_never_500('pytorch "unterminated phrase')
        print(f"C2.4 unbalanced-quote -> status=200 items={len(body['items'])} message={body['message']!r}")

    def test_lone_dash(self):
        body = self._assert_never_500("-")
        print(f"C2.4 lone-dash -> status=200 items={len(body['items'])} message={body['message']!r}")

    def test_empty_query(self):
        body = self._assert_never_500("")
        print(f"C2.4 empty-query -> status=200 items={len(body['items'])} message={body['message']!r}")

    def test_very_long_query(self):
        long_q = "pytorch " * 2000  # ~18,000 characters
        body = self._assert_never_500(long_q)
        print(
            f"C2.4 very-long-query ({len(long_q)} chars) -> status=200 "
            f"items={len(body['items'])} message={body['message']!r}"
        )

    def test_tsquery_operator_characters(self):
        body = self._assert_never_500("a & b | c ! (d) : e 'f' <-> *g")
        print(f"C2.4 operator-characters -> status=200 items={len(body['items'])} message={body['message']!r}")


# ---------------------------------------------------------------------------
# Storage V2 compact-search contract: card fields are indexed, archived source
# descriptions are not duplicated into PostgreSQL's searchable corpus.
# ---------------------------------------------------------------------------


class PytorchCorpusSearchTest(ApiTestCase):
    """Storage V2 search indexes compact card fields, not source bodies."""

    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.client = self.logged_in_client(self.app)

    def test_compact_search_uses_card_fields_and_not_archived_description(self):
        self.seed_opportunity(
            "opp-compact-pytorch",
            title="PyTorch Platform Engineer",
            organization="Cedar Systems",
            description="This full source body is deliberately not part of compact search.",
        )
        self.seed_opportunity(
            "opp-description-only",
            title="Platform Engineer",
            organization="Juniper Labs",
            description="quasarneedle appears only in the archived source description.",
        )
        self.seed_opportunity(
            "opp-customer-engineer",
            title="Customer Engineer",
            organization="Cloudflare",
            description="Support customer deployments.",
        )

        response = self.client.get("/api/opportunities", params={"q": "pytorch"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            {item["id"] for item in response.json()["items"]},
            {"opp-compact-pytorch"},
        )

        body_only = self.client.get("/api/opportunities", params={"q": "quasarneedle"})
        self.assertEqual(body_only.status_code, 200, body_only.text)
        self.assertNotIn(
            "opp-description-only",
            {item["id"] for item in body_only.json()["items"]},
            "full descriptions stay in the archive and are not duplicated in the hot search vector",
        )

        with_ce = self.client.get("/api/opportunities", params={"q": '"customer engineer"'})
        self.assertEqual(with_ce.status_code, 200, with_ce.text)
        ce_items = with_ce.json()["items"]
        ce_ids = {item["id"] for item in ce_items}
        self.assertEqual(ce_ids, {"opp-customer-engineer"})

        negated = self.client.get("/api/opportunities", params={"q": 'engineer -"customer engineer"'})
        self.assertEqual(negated.status_code, 200, negated.text)
        negated_ids = {item["id"] for item in negated.json()["items"]}
        self.assertFalse(
            negated_ids & ce_ids,
            "negated phrase must exclude every row the un-negated phrase matched",
        )
        self.assertNotIn("opp-customer-engineer", negated_ids)


# ---------------------------------------------------------------------------
# C2.6: facet/filter composition -- search results respect the active
# founder-controlled exclusion mechanism (`api.filters`, the "facet" system
# that actually exists on this branch's base today; `api/facets.py` is owned
# by concurrent work order C1 and had not landed here at the time this order
# ran).
# ---------------------------------------------------------------------------


class FacetCompositionTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        _install_truth_graph(self.app, TruthGraph())
        self.client = self.logged_in_client(self.app)

    def test_search_intersects_with_active_hide_filter(self):
        self.seed_opportunity("opp-keep", title="Pytorch Engineer", description="pytorch")
        self.seed_evaluation("opp-keep", decision="qualified", fit_score=90.0)

        self.seed_opportunity("opp-hidden", title="Pytorch Researcher", description="pytorch")
        self.seed_evaluation("opp-hidden", decision="qualified", fit_score=10.0)

        self.seed_opportunity("opp-no-match", title="Backend Engineer", description="golang services")
        self.seed_evaluation("opp-no-match", decision="qualified", fit_score=95.0)

        put_resp = self.client.put(
            "/api/filters/min_fit_score",
            json={"enabled": True, "mode": "hide", "params": {"min_score": 50}},
        )
        self.assertEqual(put_resp.status_code, 200, put_resp.text)
        from worker.runner import WorkerRunner
        from worker.handlers import default_handler_registry
        WorkerRunner(
            self.session_factory,
            handlers=default_handler_registry(
                session_factory=self.session_factory,
                pack_loader=lambda _path: self.app.state.loaded_truth_pack,
            ),
            worker_id=f"search-test-maintenance-{id(self)}",
        ).run_once()

        response = self.client.get("/api/opportunities", params={"q": "pytorch"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        ids = {item["id"] for item in body["items"]}
        self.assertEqual(ids, {"opp-keep"})
        self.assertNotIn("opp-no-match", ids)  # passes the filter, but doesn't match the search text
        self.assertNotIn("opp-hidden", ids)  # matches the search text, but excluded by the filter

        # The excluded-but-matching row is still counted, not silently dropped.
        self.assertEqual(body["hidden_count"], 1)
        print(f"C2.6: intersection ids={sorted(ids)} hidden_count={body['hidden_count']}")

        with_hidden = self.client.get(
            "/api/opportunities", params={"q": "pytorch", "include_hidden": True}
        )
        self.assertEqual(with_hidden.status_code, 200, with_hidden.text)
        hidden_item = next(i for i in with_hidden.json()["items"] if i["id"] == "opp-hidden")
        self.assertIn("min_fit_score", hidden_item["hidden_by"])


# ---------------------------------------------------------------------------
# C2.7 (part 2): search must never rewrite `decision`/`fit_score` in the
# database.
# ---------------------------------------------------------------------------


class NoReJudgementTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.client = self.logged_in_client(self.app)

    def test_search_never_mutates_decision_or_fit_score(self):
        self.seed_opportunity("opp-x", title="Pytorch Engineer", description="pytorch")
        self.seed_evaluation("opp-x", decision="qualified", fit_score=77.25)
        self.seed_opportunity("opp-y", title="Pytorch Machine Learning Lead", description="a compact card-field match")
        self.seed_evaluation("opp-y", decision="uncertain", fit_score=12.5)

        before = {
            row.opportunity_id: (row.qualification_decision, row.fit_score)
            for row in self.session.query(MatchEvaluationRecord).all()
        }

        response = self.client.get("/api/opportunities", params={"q": "pytorch"})
        self.assertEqual(response.status_code, 200, response.text)
        items = {item["id"]: item for item in response.json()["items"]}
        self.assertEqual(set(items), {"opp-x", "opp-y"})

        after = {
            row.opportunity_id: (row.qualification_decision, row.fit_score)
            for row in self.session.query(MatchEvaluationRecord).all()
        }
        self.assertEqual(before, after, "search must never rewrite decision/fit_score")
        print(f"C2.7: decision/fit_score byte-identical before/after search: {after}")

        for opp_id, (decision, fit_score) in after.items():
            self.assertEqual(items[opp_id]["decision"], decision)
            self.assertEqual(items[opp_id]["fit_score"], fit_score)


# ---------------------------------------------------------------------------
# C2.8: a row written by the backfill path is findable by search.
# ---------------------------------------------------------------------------


class BackfillVisibilityTest(ApiTestCase):
    def test_backfilled_row_is_searchable(self):
        record = OpportunityRecord(
            id="opp-backfill-me",
            track="employment",
            title="PyTorch Quant Researcher",
            organization="Backfill Co",
            description="Signal research requirements remain in the source archive.",
            source_id="himalayas",
            source_url="https://himalayas.app/jobs/opp-backfill-me",
            content_hash="hash-opp-backfill-me",
        )
        # Written directly, bypassing `StorageRepository.save_opportunity`
        # (the only path that populates `search_tsv` on write) -- this is
        # deliberately the "row search would otherwise miss" case.
        self.session.add(record)
        self.session.commit()

        self.assertIsNone(
            self.session.query(OpportunityRecord.search_tsv).filter_by(id="opp-backfill-me").scalar()
        )
        before_hits = {h.opportunity_id for h in search_opportunity_ids(self.session, "pytorch")}
        self.assertNotIn("opp-backfill-me", before_hits)

        touched = backfill_search_tsv(self.session)
        self.assertGreaterEqual(touched, 1)
        print(f"C2.8: backfill_search_tsv touched {touched} row(s)")

        after_hits = {h.opportunity_id for h in search_opportunity_ids(self.session, "pytorch")}
        self.assertIn("opp-backfill-me", after_hits)

    def test_backfill_is_idempotent(self):
        record = OpportunityRecord(
            id="opp-backfill-idempotent",
            track="employment",
            title="Data Scientist",
            organization="Backfill Co",
            description="pytorch modelling",
            source_id="himalayas",
            source_url="https://himalayas.app/jobs/opp-backfill-idempotent",
            content_hash="hash-opp-backfill-idempotent",
        )
        self.session.add(record)
        self.session.commit()

        first = backfill_search_tsv(self.session)
        second = backfill_search_tsv(self.session)
        self.assertGreaterEqual(first, 1)
        self.assertEqual(second, 0, "a second run with only_missing=True must touch zero already-indexed rows")


# ---------------------------------------------------------------------------
# C2.4 (unit-level): `is_query_unparseable` distinguishes "no searchable
# terms" from "blank query" and from "parses fine, zero rows match".
# ---------------------------------------------------------------------------


class QueryUnparseableTest(ApiTestCase):
    def test_blank_query_is_not_unparseable(self):
        self.assertFalse(is_query_unparseable(self.session, ""))
        self.assertFalse(is_query_unparseable(self.session, "   "))

    def test_lone_dash_is_unparseable(self):
        self.assertTrue(is_query_unparseable(self.session, "-"))

    def test_ordinary_term_is_not_unparseable(self):
        self.assertFalse(is_query_unparseable(self.session, "pytorch"))
