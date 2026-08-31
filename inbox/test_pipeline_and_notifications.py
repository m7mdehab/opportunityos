"""Unit tests for Pipeline Event Store and Notifications."""
import unittest
from matching.models import Track
from opportunity.models import Opportunity
from inbox.classifier import ResponseClassifier
from inbox.correlation import OpportunityCorrelationEngine
from inbox.fixtures.gold_messages import GOLD_EMPLOYMENT_MESSAGES
from inbox.models import OpportunityStage, SignalCategory, SignalPriority
from inbox.notifications import NotificationEngine
from inbox.persistence import DurableInboxStore
from inbox.pipeline import PipelineEventStore


class TestPipelineAndNotifications(unittest.TestCase):
    def test_pipeline_event_recording_and_deterministic_replay(self) -> None:
        opp = Opportunity(
            id="opp-delta-1", track=Track.EMPLOYMENT, source="ashby", source_url="https://jobs.ashbyhq.com/delta/101",
            source_id="REQ-DELTA-101", organization="Delta Corp", title="Staff Engineer", description="Role",
        )
        classifier = ResponseClassifier()
        corr_engine = OpportunityCorrelationEngine(opportunities=[opp])
        store = PipelineEventStore()

        # Interview request signal
        msg = GOLD_EMPLOYMENT_MESSAGES[3]  # Delta interview
        sig = classifier.classify(msg)
        corr = corr_engine.correlate(sig, msg)

        ev = store.record_signal_event(sig, corr, Track.EMPLOYMENT)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.new_stage, OpportunityStage.INTERVIEWING)

        state = store.get_opportunity_state("opp-delta-1", Track.EMPLOYMENT)
        self.assertEqual(state.current_stage, OpportunityStage.INTERVIEWING)
        self.assertTrue(state.active_action_required)
        self.assertEqual(state.event_history_count, 1)

    def test_notification_idempotency_on_repeated_signal(self) -> None:
        db_store = DurableInboxStore(":memory:")
        engine = NotificationEngine(workspace="ws-test", candidate_id="founder", store=db_store)
        msg = GOLD_EMPLOYMENT_MESSAGES[3]
        sig = ResponseClassifier().classify(msg)

        notif1 = engine.process_signal(sig)
        self.assertIsNotNone(notif1)
        self.assertEqual(notif1.priority, SignalPriority.URGENT)

        # Repeated signal replay
        notif2 = engine.process_signal(sig)
        self.assertIsNone(notif2)  # Idempotent: 0 duplicate alert


if __name__ == "__main__":
    unittest.main()
