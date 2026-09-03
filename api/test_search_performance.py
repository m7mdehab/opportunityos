"""BRIEF-FR-006 C2.5: the 20k-row search timing run.

Not part of the default `api`/`storage` `unittest discover` sweep's normal
cost budget -- synthesising and indexing >= 20,000 rows takes real wall time
and this is a one-shot performance claim, not a correctness test that needs
to run on every invocation. Guarded on `OPPORTUNITYOS_RUN_SEARCH_PERF=1`
(skipped otherwise, including under plain `unittest discover`) and run
explicitly for the C2.5 acceptance row.

The brief's own words: "A local Windows PostgreSQL is not a performance
reference and an honest miss is a better outcome than a tuned benchmark."
This test prints whatever it measures, including a miss.
"""

from __future__ import annotations

import os
import time
import unittest
import uuid
from datetime import datetime, timezone

from storage.repository import backfill_search_tsv

from api.search import search_opportunity_ids
from api.test_api import ApiTestCase

ROW_COUNT = 20_000
REPS_PER_QUERY = 20

QUERY_SET = (
    "pytorch",
    '"customer engineer"',
    'pytorch -"customer engineer"',
    "engineer -customer",
    "python OR golang",
)


@unittest.skipUnless(
    os.environ.get("OPPORTUNITYOS_RUN_SEARCH_PERF") == "1",
    "set OPPORTUNITYOS_RUN_SEARCH_PERF=1 to run the C2.5 20k-row timing run",
)
class SearchPerformanceTest(ApiTestCase):
    def test_p95_query_latency_over_20k_rows(self):
        now = datetime.now(timezone.utc)
        mappings = []
        for i in range(ROW_COUNT):
            # Every 7th row mentions pytorch; every 11th is titled "Customer
            # Engineer" (so the negated-phrase query set entry has real rows
            # to exclude, not just rows to not-match).
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

        from storage.models import OpportunityRecord

        insert_start = time.perf_counter()
        self.session.bulk_insert_mappings(OpportunityRecord, mappings)
        self.session.commit()
        insert_elapsed = time.perf_counter() - insert_start

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

        timings_ms: list[float] = []
        for query in QUERY_SET:
            for _ in range(REPS_PER_QUERY):
                start = time.perf_counter()
                search_opportunity_ids(self.session, query)
                timings_ms.append((time.perf_counter() - start) * 1000.0)

        timings_ms.sort()
        sample_size = len(timings_ms)
        p95_index = max(0, int(round(0.95 * (sample_size - 1))))
        p95_ms = timings_ms[p95_index]

        print(f"C2.5: row_count={row_count}")
        print(f"C2.5: query_set={list(QUERY_SET)}")
        print(f"C2.5: sample_size={sample_size} (queries x {REPS_PER_QUERY} reps each)")
        print(f"C2.5: p95={p95_ms:.2f}ms")
        if p95_ms >= 200.0:
            print(f"C2.5: MISS -- p95 {p95_ms:.2f}ms >= 200ms target (reporting honestly, not tuning)")
        else:
            print(f"C2.5: p95 {p95_ms:.2f}ms < 200ms target")

        # This test's job is to *measure and print* the figure, not to gate
        # the suite on a local Windows PostgreSQL being a performance
        # reference -- see module docstring. No latency assertion here.
