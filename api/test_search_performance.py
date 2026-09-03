"""BRIEF-FR-006 C2.5: the search timing run(s).

Two tests share `_measure_p95` below:

- `SearchPerformanceSmokeTest` (**ungated** -- runs in every plain
  `unittest discover`, including the C2.1 acceptance row) at
  `SMOKE_ROW_COUNT` rows. It proves the measurement code path itself works
  on every normal run, but does **not** evidence the brief's own >= 20,000
  row claim (A-15) -- it is explicitly a smaller smoke figure, printed and
  labelled as such.
- `SearchPerformanceTest` (gated on `OPPORTUNITYOS_RUN_SEARCH_PERF=1`,
  skipped otherwise) at the full `ROW_COUNT = 20_000`. **The A-15 p95
  figure comes only from this gated run** -- run it explicitly with that
  env var set; it is not exercised by a normal `unittest discover`.

The brief's own words: "A local Windows PostgreSQL is not a performance
reference and an honest miss is a better outcome than a tuned benchmark."
Both tests print whatever they measure, including a miss.
"""

from __future__ import annotations

import os
import time
import unittest
import uuid
from datetime import datetime, timezone

from storage.models import OpportunityRecord
from storage.repository import backfill_search_tsv

from api.search import search_opportunity_ids
from api.test_api import ApiTestCase

ROW_COUNT = 20_000
SMOKE_ROW_COUNT = 2_000
REPS_PER_QUERY = 20

QUERY_SET = (
    "pytorch",
    '"customer engineer"',
    'pytorch -"customer engineer"',
    "engineer -customer",
    "python OR golang",
)


def _insert_synthetic_opportunities(session, row_count: int) -> float:
    """Bulk-insert `row_count` synthetic opportunities (every 7th mentions
    pytorch, every 11th is titled "Customer Engineer", so the negated-phrase
    query set entry has real rows to exclude) and return the insert wall
    time in seconds. Shared by both the gated 20k run and the ungated smoke
    run so their row shapes -- and therefore their `ts_rank` behaviour --
    cannot drift apart into two different benchmarks."""
    now = datetime.now(timezone.utc)
    mappings = []
    for i in range(row_count):
        has_pytorch = i % 7 == 0
        is_customer_engineer = i % 11 == 0
        title = "Customer Engineer" if is_customer_engineer else f"Role {i}"
        description = (
            "Uses pytorch for model training and evaluation pipelines."
            if has_pytorch
            else "General responsibilities and requirements for this role."
        )
        mappings.append(
            {
                "id": f"perf-{uuid.uuid4().hex[:16]}",
                "track": "employment",
                "title": title,
                "organization": f"Org {i % 500}",
                "description": description,
                "source_id": "himalayas",
                "source_url": f"https://himalayas.app/jobs/perf-{i}",
                "content_hash": f"perf-hash-{i}",
                "is_stale": False,
                "work_mode": "unspecified",
                "remote_scope": "unspecified",
                "employment_type": "unspecified",
                "seniority_level": "unspecified",
                "created_at": now,
            }
        )
    start = time.perf_counter()
    session.bulk_insert_mappings(OpportunityRecord, mappings)
    session.commit()
    return time.perf_counter() - start


def _measure_p95(session, *, reps_per_query: int = REPS_PER_QUERY) -> tuple[int, float]:
    """Run every query in `QUERY_SET` `reps_per_query` times against
    `search_opportunity_ids` and return `(sample_size, p95_ms)`."""
    timings_ms: list[float] = []
    for query in QUERY_SET:
        for _ in range(reps_per_query):
            start = time.perf_counter()
            search_opportunity_ids(session, query)
            timings_ms.append((time.perf_counter() - start) * 1000.0)
    timings_ms.sort()
    sample_size = len(timings_ms)
    p95_index = max(0, int(round(0.95 * (sample_size - 1))))
    return sample_size, timings_ms[p95_index]


class SearchPerformanceSmokeTest(ApiTestCase):
    """Ungated: runs by default, at `SMOKE_ROW_COUNT` rows. Does not
    evidence the >= 20,000-row A-15 claim on its own -- see module
    docstring and `SearchPerformanceTest` below for that."""

    def test_p95_query_latency_smoke(self):
        insert_elapsed = _insert_synthetic_opportunities(self.session, SMOKE_ROW_COUNT)
        touched = backfill_search_tsv(self.session, only_missing=True)
        row_count = self.session.query(OpportunityRecord).count()
        self.assertGreaterEqual(row_count, SMOKE_ROW_COUNT)
        self.assertGreaterEqual(touched, SMOKE_ROW_COUNT)

        sample_size, p95_ms = _measure_p95(self.session)
        print(
            f"C2.5 SMOKE (ungated, runs by default; NOT the A-15 20k claim): "
            f"row_count={row_count} inserted_in={insert_elapsed:.2f}s "
            f"query_set={list(QUERY_SET)} sample_size={sample_size} p95={p95_ms:.2f}ms"
        )


@unittest.skipUnless(
    os.environ.get("OPPORTUNITYOS_RUN_SEARCH_PERF") == "1",
    "set OPPORTUNITYOS_RUN_SEARCH_PERF=1 to run the C2.5/A-15 20k-row timing run",
)
class SearchPerformanceTest(ApiTestCase):
    """Gated: the ONLY source of the A-15 >= 20,000-row p95 claim. Skipped
    under a plain `unittest discover` -- run explicitly with
    `OPPORTUNITYOS_RUN_SEARCH_PERF=1` for that figure."""

    def test_p95_query_latency_over_20k_rows(self):
        insert_elapsed = _insert_synthetic_opportunities(self.session, ROW_COUNT)

        backfill_start = time.perf_counter()
        touched = backfill_search_tsv(self.session, only_missing=True)
        backfill_elapsed = time.perf_counter() - backfill_start

        row_count = self.session.query(OpportunityRecord).count()
        self.assertGreaterEqual(row_count, ROW_COUNT)
        self.assertGreaterEqual(touched, ROW_COUNT)

        print(
            f"C2.5: inserted {row_count} rows in {insert_elapsed:.2f}s; "
            f"backfill_search_tsv indexed {touched} rows in {backfill_elapsed:.2f}s"
        )

        sample_size, p95_ms = _measure_p95(self.session)

        print(f"C2.5: row_count={row_count}")
        print(f"C2.5: query_set={list(QUERY_SET)}")
        print(f"C2.5: sample_size={sample_size} (queries x {REPS_PER_QUERY} reps each)")
        print(f"C2.5: p95={p95_ms:.2f}ms")
        print(f"C2.5: THIS IS THE A-15 FIGURE -- gated run, OPPORTUNITYOS_RUN_SEARCH_PERF=1, {row_count} rows.")
        if p95_ms >= 200.0:
            print(f"C2.5: MISS -- p95 {p95_ms:.2f}ms >= 200ms target (reporting honestly, not tuning)")
        else:
            print(f"C2.5: p95 {p95_ms:.2f}ms < 200ms target")

        # This test's job is to *measure and print* the figure, not to gate
        # the suite on a local Windows PostgreSQL being a performance
        # reference -- see module docstring. No latency assertion here.
