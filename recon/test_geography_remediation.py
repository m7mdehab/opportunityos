import unittest
from dataclasses import replace

from recon.classification import classify
from recon.geography import eligibility_for, extract
from recon.models import Record


def record(location="", body=""):
    return Record(
        "synthetic", "employment", "Data Engineer", "Example", location,
        "https://example.test", "", body, "synthetic",
    )


def tokens(rules):
    return {token for token, _ in rules}


class WorldwideScopeTests(unittest.TestCase):
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
                self.assertEqual({"JP"}, tokens(extracted.geo_allow))
                self.assertEqual("excluded", eligibility_for(extracted, "EG")[0])

    def test_collaboration_and_product_boilerplate_never_creates_worldwide(self):
        boilerplate = (
            "Our product helps teams work together in real time from anywhere in the world.",
            "The platform empowers teams to collaborate anywhere in the world.",
            "Our software lets users work from anywhere in the world.",
            "Customers collaborate from anywhere in the world using our product.",
        )
        for body in boilerplate:
            with self.subTest(body=body):
                extracted = extract(record("Remote", body))
                self.assertNotIn("WORLDWIDE", tokens(extracted.geo_allow))
                self.assertEqual("unclear", eligibility_for(extracted)[0])

    def test_bare_anywhere_in_world_prose_is_not_applicant_scope(self):
        extracted = extract(record(body="Our services are available anywhere in the world."))
        self.assertEqual((), extracted.geo_allow)
        self.assertEqual("unclear", eligibility_for(extracted)[0])

    def test_explicit_applicant_worldwide_language_is_allowed(self):
        bodies = (
            "Open to candidates anywhere in the world.",
            "We hire from any country.",
            "Candidates may work from anywhere globally.",
            "This role is available anywhere in the world.",
            "Applicants can be based worldwide.",
            "Work from anywhere in the world.",
        )
        for body in bodies:
            with self.subTest(body=body):
                extracted = extract(record("Remote", body))
                self.assertIn("WORLDWIDE", tokens(extracted.geo_allow))
                self.assertEqual("eligible", eligibility_for(extracted)[0])

    def test_timezone_qualified_anywhere_is_not_worldwide(self):
        body = "Candidates located anywhere within the Eastern Time Zone may apply."
        extracted = extract(record("Remote", body))
        self.assertEqual({"US"}, tokens(extracted.geo_allow))
        self.assertIn("TIMEZONE_ONLY", tokens(extracted.geo_deny))
        self.assertNotIn("WORLDWIDE", tokens(extracted.geo_allow))
        self.assertEqual("excluded", eligibility_for(extracted, "EG")[0])
        self.assertEqual("unclear", eligibility_for(extracted, "US")[0])

    def test_explicit_listing_is_bounded_to_its_clause(self):
        body = "Eligible countries: Japan. Join us and help our global customers everywhere."
        extracted = extract(record("Remote", body))
        self.assertEqual({"JP"}, tokens(extracted.geo_allow))
        self.assertEqual("excluded", eligibility_for(extracted)[0])


class StructuredPlaceTests(unittest.TestCase):
    def test_new_country_and_region_aliases_resolve(self):
        cases = {
            "Cyprus": "CY", "Colombia": "CO", "Israel": "IL", "Singapore": "SG",
            "New Zealand": "NZ", "Argentina": "AR", "Chile": "CL", "Peru": "PE",
            "North America": "AMERICAS", "South America": "AMERICAS",
        }
        for location, expected in cases.items():
            with self.subTest(location=location):
                self.assertIn(expected, tokens(extract(record(location)).geo_allow))

    def test_all_required_city_expansions_resolve(self):
        groups = {
            "US": ("SF", "NYC", "New York City", "Chicago", "Boston", "Atlanta", "Denver", "Seattle", "Austin", "Washington DC", "San Francisco", "New York"),
            "GB": ("London", "Sherborne", "Glasgow", "Newcastle Upon Tyne", "Manchester", "Edinburgh", "Bristol"),
            "IN": ("Bengaluru", "Bangalore", "Hyderabad", "Mumbai", "New Delhi", "Chennai", "Greater Chennai Area", "Pune"),
            "CA": ("Toronto", "Vancouver", "Montreal", "Quebec", "Grand Falls-Windsor", "Ottawa", "Calgary"),
            "BR": ("São Paulo", "Sao Paulo", "Rio de Janeiro"),
            "IL": ("Tel Aviv", "Jerusalem"),
            "AU": ("Sydney", "Melbourne", "Alice Springs", "Brisbane", "Perth"),
            "JP": ("Tokyo", "Osaka", "Kyoto"),
            "SG": ("Singapore",), "KR": ("Seoul",),
            "EG": ("Cairo", "Alexandria", "Giza"),
            "AE": ("Dubai", "Abu Dhabi"), "SA": ("Riyadh", "Jeddah"), "QA": ("Doha",),
            "DE": ("Berlin", "Munich", "Frankfurt"), "FR": ("Paris",),
            "NL": ("Amsterdam",), "IE": ("Dublin",), "ES": ("Madrid", "Barcelona"),
            "PT": ("Lisbon",), "SE": ("Stockholm",), "PL": ("Warsaw",),
        }
        for expected, cities in groups.items():
            for city in cities:
                with self.subTest(city=city):
                    self.assertIn(expected, tokens(extract(record(city)).geo_allow))

    def test_city_country_and_subdivision_combinations_resolve(self):
        cases = {
            "Seattle, WA": "US", "London, England": "GB", "Toronto, ON": "CA",
            "Berlin, Germany": "DE", "Tokyo, Japan": "JP", "Madrid, Spain": "ES",
        }
        for location, expected in cases.items():
            with self.subTest(location=location):
                self.assertIn(expected, tokens(extract(record(location)).geo_allow))

    def test_mojibake_and_accents_are_normalized(self):
        cases = {"QuÃ©bec": ("Quebec", "CA"), "SÃ£o Paulo": ("Sao Paulo", "BR"), "São Paulo": ("Sao Paulo", "BR")}
        for location, (normalized, expected) in cases.items():
            with self.subTest(location=location):
                extracted = extract(record(location))
                self.assertEqual(normalized, extracted.location_text)
                self.assertIn(expected, tokens(extracted.geo_allow))

    def test_ambiguous_city_or_subdivision_without_context_is_not_mapped(self):
        for location in ("Cambridge", "Springfield", "WA", "ON"):
            with self.subTest(location=location):
                self.assertEqual((), extract(record(location)).geo_allow)

    def test_structured_location_header_resolves(self):
        extracted = extract(record("Remote", "Location: Berlin, Germany\nAbout us: global leader."))
        self.assertIn("DE", tokens(extracted.geo_allow))
        self.assertNotIn("WORLDWIDE", tokens(extracted.geo_allow))


class RestrictionExtractionTests(unittest.TestCase):
    def test_us_work_authorization_variants(self):
        bodies = (
            "Verify your eligibility to work in the U.S.",
            "You must be authorized to work in the US.",
            "Work authorization in the United States is required.",
            "Applicants must hold a green card.",
            "Citizenship required.",
        )
        for body in bodies:
            with self.subTest(body=body):
                extracted = extract(record("Worldwide", body))
                self.assertIn("WORK_AUTH_REQUIRED:US", tokens(extracted.geo_deny))
                self.assertEqual("excluded", eligibility_for(extracted)[0])

    def test_canadian_residency_list_is_a_country_restriction(self):
        body = "Candidates residing in Alberta, British Columbia, Manitoba, Ontario, or Quebec may apply."
        extracted = extract(record("Remote", body))
        self.assertIn("RESIDENCY_REQUIRED:CA", tokens(extracted.geo_deny))
        self.assertEqual("excluded", eligibility_for(extracted)[0])

    def test_us_registered_entity_residency_requirement(self):
        body = "You must live in a state where Acme has a registered entity."
        extracted = extract(record("Remote", body))
        self.assertIn("RESIDENCY_REQUIRED:US", tokens(extracted.geo_deny))
        self.assertEqual("excluded", eligibility_for(extracted)[0])

    def test_us_only_and_us_based_are_residency_requirements(self):
        for body in ("US only.", "This is a US-based position."):
            with self.subTest(body=body):
                self.assertIn("RESIDENCY_REQUIRED:US", tokens(extract(record("Remote", body)).geo_deny))

    def test_no_sponsorship_variants(self):
        bodies = (
            "No visa sponsorship.", "No sponsorship for this role.",
            "Sponsorship not available.", "Will not sponsor."
        )
        for body in bodies:
            with self.subTest(body=body):
                extracted = extract(record("Worldwide", body))
                self.assertIn("NO_SPONSORSHIP", tokens(extracted.geo_deny))
                self.assertEqual("excluded", eligibility_for(extracted)[0])

    def test_timezone_schedule_variants(self):
        bodies = (
            "ET", "EST", "EDT", "CET", "UTC",
            "Working hours are 10 AM - 6 PM EST.",
            "Some overlap with CET is required.", "EMEA hours",
            "UTC+1 to UTC+3 timezone range", "Eastern Time Zone schedule",
        )
        for body in bodies:
            with self.subTest(body=body):
                extracted = extract(record("Remote", body))
                self.assertIn("TIMEZONE_ONLY", tokens(extracted.geo_deny))
                self.assertEqual("unclear", eligibility_for(extracted)[0])
                self.assertEqual("unclear", classify(record("Remote", body)).eligibility)


class EligibilityDerivationTests(unittest.TestCase):
    def test_disqualifying_conditions_beat_worldwide(self):
        deny_tokens = (
            "NO_SPONSORSHIP", "WORK_AUTH_REQUIRED:US", "RESIDENCY_REQUIRED:CA", "ENTITY_REQUIRED:US",
        )
        for deny_token in deny_tokens:
            with self.subTest(deny_token=deny_token):
                extracted = replace(record(), geo_allow=(("WORLDWIDE", "global"),), geo_deny=((deny_token, "restriction"),))
                self.assertEqual("excluded", eligibility_for(extracted, "EG")[0])

    def test_timezone_with_empty_or_worldwide_allow_is_unclear(self):
        for allows in ((), (("WORLDWIDE", "global"),)):
            with self.subTest(allows=allows):
                extracted = replace(record(), geo_allow=allows, geo_deny=(("TIMEZONE_ONLY", "CET overlap"),))
                self.assertEqual(("unclear", "CET overlap"), eligibility_for(extracted, "EG"))

    def test_timezone_with_country_allowlist_omitting_country_is_excluded(self):
        extracted = replace(record(), geo_allow=(("US", "United States"), ("CA", "Canada")), geo_deny=(("TIMEZONE_ONLY", "ET"),))
        self.assertEqual(("excluded", "United States"), eligibility_for(extracted, "EG"))

    def test_timezone_with_matching_country_is_still_unclear(self):
        extracted = replace(record(), geo_allow=(("US", "United States"),), geo_deny=(("TIMEZONE_ONLY", "ET"),))
        self.assertEqual(("unclear", "ET"), eligibility_for(extracted, "US"))

    def test_specific_location_precedes_worldwide_body_signal(self):
        extracted = extract(record("New York", "Open to candidates anywhere in the world."))
        self.assertEqual({"US", "WORLDWIDE"}, tokens(extracted.geo_allow))
        self.assertEqual("excluded", eligibility_for(extracted, "EG")[0])
        self.assertEqual("eligible", eligibility_for(extracted, "US")[0])

    def test_matching_country_or_region_allow_is_eligible(self):
        for allow_token in ("EG", "MENA", "EMEA", "AFRICA"):
            with self.subTest(allow_token=allow_token):
                extracted = replace(record(), geo_allow=((allow_token, allow_token),))
                self.assertEqual("eligible", eligibility_for(extracted, "EG")[0])

    def test_allowlist_omitting_country_is_excluded(self):
        extracted = replace(record(), geo_allow=(("US", "United States"), ("CA", "Canada")))
        self.assertEqual("excluded", eligibility_for(extracted, "EG")[0])

    def test_south_africa_maps_to_za_not_africa(self):
        extracted = extract(record("South Africa", "Remote position."))
        self.assertEqual({"ZA"}, tokens(extracted.geo_allow))
        self.assertNotIn("AFRICA", tokens(extracted.geo_allow))
        self.assertEqual("excluded", eligibility_for(extracted, "EG")[0])

    def test_work_from_anywhere_within_us_maps_to_us_not_worldwide(self):
        extracted = extract(record("Remote", "You can work from anywhere within the United States."))
        self.assertIn("US", tokens(extracted.geo_allow))
        self.assertNotIn("WORLDWIDE", tokens(extracted.geo_allow))
        self.assertEqual("excluded", eligibility_for(extracted, "EG")[0])

    def test_us_central_time_schedule_is_timezone_only(self):
        extracted = extract(record("Remote", "Work from anywhere. Hours aligned with US Central Time."))
        self.assertIn("TIMEZONE_ONLY", tokens(extracted.geo_deny))
        self.assertEqual("unclear", eligibility_for(extracted, "EG")[0])


if __name__ == "__main__":
    unittest.main()
