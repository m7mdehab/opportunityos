import unittest

from recon.classification import classify
from recon.models import Record


def record(location="", body="", track="employment"):
    return Record("synthetic", track, "Data Engineer", "Example", location, "https://example.test", "", body, "synthetic")


EXCLUDED = [
    ("E01", "Anywhere", "Must be authorized to work in the United States."), ("E02", "Remote", "You must be authorized to work in the US."), ("E03", "Worldwide", "US work authorization is required."), ("E04", "US Only", "Fully remote position."), ("E05", "USA Only", "Remote role."), ("E06", "United States only", "Remote."), ("E07", "Remote", "This is a US-based role."), ("E08", "Anywhere", "Green card or citizenship required."), ("E09", "EU only", "Remote within the EU."), ("E10", "Remote", "Candidates must reside in Germany."), ("E11", "India Only", "Remote role for India."), ("E12", "LATAM only", "Remote, LATAM candidates only."), ("E13", "Worldwide", "No visa sponsorship is available."), ("E14", "Anywhere in the world", "This role is US only."), ("E15", "EMEA", "Candidates must reside in Germany."), ("E16", "Remote - Global", "Applicants must hold a green card."), ("E17", "Canada", "Must have Canadian work authorization."), ("E18", "Remote (UK)", "Must be based in the United Kingdom."), ("E19", "Worldwide", "Applicants must be located in Australia."), ("E20", "Remote", "Eligible countries: United States, Canada."),
]
ELIGIBLE = [("A01", "Worldwide", "Remote."), ("A02", "Anywhere", "Fully remote team."), ("A03", "Remote - Global", "Distributed team."), ("A04", "Remote (Worldwide)", "Engineering role."), ("A05", "Anywhere in the world", "Remote."), ("A06", "Egypt", "Remote role."), ("A07", "Cairo, Egypt", "Hybrid role."), ("A08", "EMEA", "Remote."), ("A09", "MENA", "Remote."), ("A10", "Middle East", "Remote."), ("A11", "Remote", "Open to candidates anywhere in the world."), ("A12", "Global", "We hire from any country.")]
UNCLEAR = [("U01", "Remote", "We are a distributed team."), ("U02", "", "Great opportunity for a motivated engineer."), ("U03", "Remote", "Some overlap with CET is required."), ("U04", "Remote - Europe", "Remote role.")]
INDEPENDENT = [("I01", "Open to individual consultants.", "individual_ok"), ("I02", "Applications from natural persons are welcome.", "individual_ok"), ("I03", "Bidders must provide a valid commercial registration.", "entity_required"), ("I04", "A bid bond of 2% is required.", "entity_required"), ("I05", "Minimum annual turnover of USD 500,000.", "entity_required"), ("I06", "Only registered legal entities may apply.", "entity_required"), ("I07", "Consultancy services for water infrastructure.", "unclear")]
GENERALIZATION = [("G01", "Remote", "Right to work in the U.S. is mandatory.", "excluded"), ("G02", "Global", "Applicants need US citizenship.", "excluded"), ("G03", "Remote", "Based in France only.", "excluded"), ("G04", "Anywhere", "Australian residents only.", "excluded"), ("G05", "Remote", "Applicants must live in Japan.", "excluded"), ("G06", "Africa", "Remote team.", "eligible"), ("G07", "Middle East", "Distributed engineering.", "eligible"), ("G08", "Remote", "Candidates from any country are welcome.", "eligible"), ("G09", "Global", "Work from anywhere.", "eligible"), ("G10", "Remote", "EMEA hours preferred.", "unclear"), ("G11", "Remote - Europe", "CET overlap.", "unclear"), ("G12", "", "Distributed company.", "unclear"), ("G13", "MENA", "No sponsorship available.", "excluded"), ("G14", "Worldwide", "Must be located in Brazil.", "excluded"), ("G15", "Anywhere", "Eligible countries: Egypt, Jordan.", "eligible")]


class ClassificationTests(unittest.TestCase):
    def test_mandated_exclusions(self):
        for identifier, location, body in EXCLUDED:
            with self.subTest(identifier):
                decision = classify(record(location, body))
                self.assertEqual("excluded", decision.eligibility)
                self.assertTrue(decision.eligibility_reason)

    def test_mandated_eligibility(self):
        for identifier, location, body in ELIGIBLE:
            with self.subTest(identifier):
                self.assertEqual("eligible", classify(record(location, body)).eligibility)

    def test_mandated_unclear(self):
        for identifier, location, body in UNCLEAR:
            with self.subTest(identifier):
                self.assertEqual("unclear", classify(record(location, body)).eligibility)

    def test_mandated_individual_eligibility(self):
        for identifier, body, expected in INDEPENDENT:
            with self.subTest(identifier):
                self.assertEqual(expected, classify(record(body=body, track="independent")).individual_eligibility)

    def test_generalization_cases(self):
        for identifier, location, body, expected in GENERALIZATION:
            with self.subTest(identifier):
                self.assertEqual(expected, classify(record(location, body)).eligibility)
