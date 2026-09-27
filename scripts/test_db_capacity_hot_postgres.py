from __future__ import annotations

import json
import os
import unittest
import uuid
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scripts.db_capacity_maintenance import (
    compact_hot_dimension_scores,
    hot_dimension_compaction_plan,
)
from storage.models import MatchEvaluationRecord, OpportunityRecord


@unittest.skipUnless(
    os.environ.get("OPPORTUNITYOS_DB_URL", "").startswith("postgresql"),
    "requires disposable PostgreSQL",
)
class HotEvaluationCapacityMaintenancePostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(os.environ["OPPORTUNITYOS_DB_URL"], pool_pre_ping=True)
        self.opp_id = f"capacity-hot-{uuid.uuid4().hex[:12]}"
        verbose_dimension = {
            "dimension_name": "compensation_fit",
            "raw_score": 0.75,
            "weight": 0.2,
            "weighted_score": 0.15,
            "explanation": "Synthetic rationale retained by the Founder API.",
            "strengths": ["synthetic strength"],
            "gaps": ["synthetic gap"],
            "unknowns": ["synthetic unknown"],
            "evidence_refs": ["ev-synthetic"],
            "opportunity_field_refs": ["compensation"],
            "signal_tags": ["premium_shortfall"],
        }
        with Session(self.engine) as session:
            session.add(
                OpportunityRecord(
                    id=self.opp_id,
                    track="employment",
                    title="Synthetic capacity role",
                    organization="Synthetic Org",
                    description="Synthetic description",
                    source_id="himalayas",
                    source_url=f"https://example.invalid/{self.opp_id}",
                    content_hash=f"hash-{self.opp_id}",
                    lifecycle_tier="hot",
                )
            )
            session.commit()
            session.add(
                MatchEvaluationRecord(
                    id=f"eval-{uuid.uuid4().hex[:20]}",
                    opportunity_id=self.opp_id,
                    truth_pack_hash="synthetic-capacity-pack",
                    content_hash=f"hash-{self.opp_id}",
                    qualification_decision="qualified",
                    fit_score=75.0,
                    dimension_scores_json=json.dumps([verbose_dimension]),
                    reasons_json="[]",
                    evaluation_detail_json=json.dumps({"hard_constraints": []}),
                    policy_version="synthetic",
                    evaluated_at=datetime.utcnow(),
                )
            )
            session.commit()

    def tearDown(self) -> None:
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "DELETE FROM match_evaluations WHERE opportunity_id = %s",
                (self.opp_id,),
            )
            connection.exec_driver_sql(
                "DELETE FROM opportunities WHERE id = %s",
                (self.opp_id,),
            )
        self.engine.dispose()

    def test_hot_compaction_preserves_live_contract_and_signal_tags(self) -> None:
        with self.engine.begin() as connection:
            before = hot_dimension_compaction_plan(connection)
            result = compact_hot_dimension_scores(connection, confirm=True)
            payload = connection.exec_driver_sql(
                "SELECT dimension_scores_json FROM match_evaluations WHERE opportunity_id = %s",
                (self.opp_id,),
            ).scalar_one()

        self.assertGreater(before["logical_savings_bytes"], 0)
        self.assertGreaterEqual(result["rows_rewritten"], 1)
        dimensions = json.loads(payload)
        self.assertEqual(len(dimensions), 1)
        self.assertEqual(
            set(dimensions[0]),
            {
                "dimension_name",
                "raw_score",
                "weight",
                "weighted_score",
                "explanation",
                "signal_tags",
            },
        )
        self.assertEqual(dimensions[0]["signal_tags"], ["premium_shortfall"])
        self.assertEqual(
            dimensions[0]["explanation"],
            "Synthetic rationale retained by the Founder API.",
        )

        with self.engine.begin() as connection:
            repeated = compact_hot_dimension_scores(connection, confirm=True)
        self.assertEqual(repeated["rows_rewritten"], 0)


if __name__ == "__main__":
    unittest.main()
