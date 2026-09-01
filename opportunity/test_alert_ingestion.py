import unittest
from opportunity.alert_ingestion import AlertIngestionEngine
from opportunity.models import Track

class TestAlertIngestionEngine(unittest.TestCase):
    def test_parse_linkedin_job_alert(self):
        subject = "Job Alert: Principal Cloud Architect at Amazon"
        body = "A new job matching your alert was posted:\n\nPrincipal Cloud Architect\nAmazon Web Services\nApply: https://www.linkedin.com/jobs/view/99887766"
        opp = AlertIngestionEngine.parse_alert_message("LINKEDIN", "jobalerts-noreply@linkedin.com", subject, body)
        
        self.assertIsNotNone(opp)
        self.assertIn("Principal Cloud Architect", opp.title)
        self.assertEqual(opp.organization, "Amazon")
        self.assertEqual(opp.track, Track.EMPLOYMENT)
        self.assertEqual(opp.source_id, "alert:linkedin")
        self.assertEqual(opp.source_url, "https://www.linkedin.com/jobs/view/99887766")
        self.assertGreaterEqual(len(opp.field_provenances), 3)

    def test_parse_upwork_freelance_alert(self):
        subject = "Upwork Alert: Python Distributed Backend Specialist"
        body = "New freelance job posted: Python Distributed Backend Specialist at ShyftLabs.\nBudget: $5000\nLink: https://www.upwork.com/jobs/~0123456789"
        opp = AlertIngestionEngine.parse_alert_message("UPWORK", "donotreply@upwork.com", subject, body)
        
        self.assertIsNotNone(opp)
        self.assertEqual(opp.track, Track.FREELANCE)
        self.assertIn("Python Distributed Backend", opp.title)
        self.assertEqual(opp.source_id, "alert:upwork")
        self.assertEqual(opp.source_url, "https://www.upwork.com/jobs/~0123456789")

    def test_parse_procurement_tender_alert(self):
        subject = "Tender Notice: Cloud Infrastructure Modernization"
        body = "Tender RFP published by Ministry of Communications. View tender at https://etimad.sa/tenders/999"
        opp = AlertIngestionEngine.parse_alert_message("ETIMAD", "tenders@etimad.sa", subject, body)
        
        self.assertIsNotNone(opp)
        self.assertEqual(opp.track, Track.PROCUREMENT)
        self.assertIn("Cloud Infrastructure Modernization", opp.title)


if __name__ == "__main__":
    unittest.main()
