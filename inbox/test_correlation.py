"""Unit tests for Deterministic Opportunity Correlation."""
import unittest
from matching.models import Track
from opportunity.models import Opportunity
from outbound.models import (
    ActionStatus,
    ConfirmationEvidence,
    ExecutionMode,
    OutboundActionRecord,
    QualificationDecision,
)
from .classifier import ResponseClassifier
from .correlation import OpportunityCorrelationEngine
from .fixtures.gold_messages import GOLD_EMPLOYMENT_MESSAGES
from .models import CorrelationStatus


class TestOpportunityCorrelation(unittest.TestCase):
    def setUp(self) -> None:
        self.opp1 = Opportunity(
            id="opp-acme-1", track=Track.EMPLOYMENT, source="greenhouse",
            source_url="https://boards.greenhouse.io/acme/jobs/500", source_id="REQ-ACME-500",
            organization="Acme Corp", title="Senior Architect", description="Role",
        )
        self.rec1 = OutboundActionRecord(
            action_id="act-acme-1", opportunity_id="opp-acme-1", opportunity_content_hash="hash-1",
            workspace="default", candidate_id="founder", track=Track.EMPLOYMENT, source="greenhouse",
            adapter_name="greenhouse", adapter_version="1.0.0", execution_mode=ExecutionMode.CONTROLLED_SUBMIT,
            qualification_decision=QualificationDecision.QUALIFIED, match_score_snapshot=0.9,
            artifact_ids=(), artifact_hashes=(), manifest_hash="mhash-1", action_status=ActionStatus.CONFIRMED,
            idempotency_key="key-1", created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z",
            external_reference_id="REQ-ACME-500",
        )
        self.classifier = ResponseClassifier()

    def test_exact_reference_id_correlation(self) -> None:
        msg = GOLD_EMPLOYMENT_MESSAGES[0]  # Contains REQ-ACME-500
        sig = self.classifier.classify(msg)
        engine = OpportunityCorrelationEngine(opportunities=[self.opp1], outbound_records=[self.rec1])
        corr = engine.correlate(sig, msg)

        self.assertEqual(corr.status, CorrelationStatus.EXACT_REFERENCE_MATCH)
        self.assertEqual(corr.opportunity_id, "opp-acme-1")
        self.assertEqual(corr.outbound_action_id, "act-acme-1")
        self.assertTrue(corr.is_authoritative)

    def test_ambiguous_same_company_distinct_opportunities_strictly_unlinked(self) -> None:
        # Two applications at same company with identical title tokens
        opp_a = Opportunity(
            id="opp-gamma-1", track=Track.EMPLOYMENT, source="lever", source_url="https://jobs.lever.co/gamma/1",
            source_id="G1", organization="Gamma Systems", title="Lead Data Architect", description="Role 1",
        )
        opp_b = Opportunity(
            id="opp-gamma-2", track=Track.EMPLOYMENT, source="lever", source_url="https://jobs.lever.co/gamma/2",
            source_id="G2", organization="Gamma Systems", title="Lead Data Architect", description="Role 2",
        )
        msg = GOLD_EMPLOYMENT_MESSAGES[2]  # Gamma Systems - Lead Data Architect without req ID
        sig = self.classifier.classify(msg)
        engine = OpportunityCorrelationEngine(opportunities=[opp_a, opp_b])
        corr = engine.correlate(sig, msg)

        self.assertEqual(corr.status, CorrelationStatus.AMBIGUOUS_MULTI_CANDIDATE)
        self.assertIsNone(corr.opportunity_id)
        self.assertFalse(corr.is_authoritative)


if __name__ == "__main__":
    unittest.main()
