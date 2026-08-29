import unittest

from recon.classification import classify
from recon.geography import eligibility_for, extract
from recon.models import Record


def record(location="", body=""):
    return Record(
        "synthetic",
        "employment",
        "Data Engineer",
        "Example",
        location,
        "https://example.test",
        "",
        body,
        "synthetic",
    )


class GeographyRemediationTests(unittest.TestCase):
    def test_company_marketing_does_not_create_worldwide_or_us_allow(self):
        marketing_phrases = (
            "We are a global leader in payments.",
            "Join our global team of engineers.",
            "We have a global presence and offices on five continents.",
            "Our global customers rely on us every day.",
        )
        for body in marketing_phrases:
            with self.subTest(body=body):
                extracted = extract(record("Tokyo, Japan", body))
                self.assertEqual({"JP"}, {token for token, _ in extracted.geo_allow})
                self.assertEqual("excluded", eligibility_for(extracted, "EG")[0])

    def test_bare_marketing_prose_has_no_geographic_rule(self):
        extracted = extract(record(body="Join us on our global team serving global customers."))
        self.assertEqual((), extracted.geo_allow)
        self.assertEqual("unclear", eligibility_for(extracted)[0])

    def test_candidate_worldwide_language_creates_worldwide_allow(self):
        bodies = (
            "Open to candidates anywhere in the world.",
            "We hire from any country.",
            "Candidates may work from anywhere globally.",
            "This role is available anywhere in the world.",
        )
        for body in bodies:
            with self.subTest(body=body):
                extracted = extract(record("Remote", body))
                self.assertIn("WORLDWIDE", {token for token, _ in extracted.geo_allow})
                self.assertEqual("eligible", eligibility_for(extracted)[0])

    def test_explicit_listing_is_bounded_to_its_clause(self):
        body = "Eligible countries: Japan. Join us and help our global customers everywhere."
        extracted = extract(record("Remote", body))
        self.assertEqual({"JP"}, {token for token, _ in extracted.geo_allow})
        self.assertEqual("excluded", eligibility_for(extracted)[0])

    def test_city_country_and_subdivision_locations_resolve(self):
        cases = {
            "Seattle, WA": "US",
            "Washington DC": "US",
            "Dublin": "IE",
            "Paris": "FR",
            "Bengaluru": "IN",
            "London, England": "GB",
            "Alice Springs": "AU",
            "Toronto, ON": "CA",
            "Berlin, Germany": "DE",
            "Tokyo, Japan": "JP",
            "Madrid, Spain": "ES",
            "Seoul, South Korea": "KR",
            "Mexico": "MX",
            "Cairo": "EG",
            "Alexandria": "EG",
        }
        for location, expected in cases.items():
            with self.subTest(location=location):
                extracted = extract(record(location))
                self.assertIn(expected, {token for token, _ in extracted.geo_allow})

    def test_representative_international_tech_hubs_resolve(self):
        cases = {
            "Amsterdam": "NL",
            "Lisbon": "PT",
            "Stockholm": "SE",
            "Warsaw": "PL",
            "Dubai": "AE",
            "Riyadh": "SA",
            "Doha": "QA",
            "Hyderabad": "IN",
            "Osaka": "JP",
        }
        for location, expected in cases.items():
            with self.subTest(location=location):
                self.assertIn(expected, {token for token, _ in extract(record(location)).geo_allow})

    def test_ambiguous_city_or_subdivision_without_context_is_not_mapped(self):
        for location in ("Cambridge", "Springfield", "WA", "ON"):
            with self.subTest(location=location):
                self.assertEqual((), extract(record(location)).geo_allow)

    def test_structured_location_header_resolves(self):
        extracted = extract(record("Remote", "Location: Berlin, Germany\nAbout us: global leader."))
        self.assertIn("DE", {token for token, _ in extracted.geo_allow})
        self.assertNotIn("WORLDWIDE", {token for token, _ in extracted.geo_allow})

    def test_timezone_patterns_are_evidence_only(self):
        bodies = (
            "ET Timezone",
            "Working hours are 8:00 AM - 4:00 PM EST.",
            "Some overlap with CET is required.",
            "EMEA hours",
            "UTC+1 or +2 timezone range",
        )
        for body in bodies:
            with self.subTest(body=body):
                extracted = extract(record("Remote", body))
                evidence = [value for token, value in extracted.geo_deny if token == "TIMEZONE_ONLY"]
                self.assertTrue(evidence)
                self.assertEqual("unclear", eligibility_for(extracted, "EG")[0])
                self.assertEqual("unclear", eligibility_for(extracted, "US")[0])
                self.assertEqual("unclear", classify(record("Remote", body)).eligibility)


if __name__ == "__main__":
    unittest.main()
