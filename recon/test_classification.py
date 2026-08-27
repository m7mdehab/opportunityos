import unittest

from recon.classification import classify
from recon.models import Record


def record(**changes: str) -> Record:
    values = dict(source="synthetic", track="employment", title="Data Engineer", organization="Example", location_text="", url="https://example.test", posted_date="", description="", raw_payload_pointer="synthetic")
    values.update(changes)
    return Record(**values)


class ClassificationTests(unittest.TestCase):
    def test_us_authorization_beats_anywhere(self) -> None:
        decision = classify(record(location_text="Anywhere", description="Remote role; US work authorization is required."))
        self.assertEqual(decision.eligibility, "excluded")
        self.assertIn("US", decision.eligibility_reason)

    def test_egypt_is_eligible(self) -> None:
        self.assertEqual(classify(record(location_text="Remote - Egypt")).eligibility, "eligible")

    def test_remote_without_geography_is_unclear(self) -> None:
        self.assertEqual(classify(record(location_text="Remote")).eligibility, "unclear")

    def test_individual_requirement_is_explainable(self) -> None:
        decision = classify(record(track="independent", description="Open to an individual consultant."))
        self.assertEqual(decision.individual_eligibility, "individual_ok")

    def test_entity_requirement_is_explainable(self) -> None:
        decision = classify(record(track="independent", description="Registered company and bid bond required."))
        self.assertEqual(decision.individual_eligibility, "entity_required")
