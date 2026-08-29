import unittest

from recon.classification import classify
from recon.geography import eligibility_for, extract
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

    def test_stored_rule_cases(self):
        cases = [
            ("Global", "Sponsorship not available for this position.", {"WORLDWIDE"}, {"NO_SPONSORSHIP"}, "unstated", "excluded"),
            ("Anywhere", "Restricted to residents of the EEA.", {"EEA"}, {"RESIDENCY_REQUIRED:EEA"}, "unstated", "excluded"),
            ("Remote", "Hiring in: US, UK, Germany.", {"US", "GB", "DE"}, set(), "remote", "excluded"),
            ("Remote", "Must hold a valid Schengen visa.", set(), {"RESIDENCY_REQUIRED:EU"}, "remote", "excluded"),
            ("Cairo", "On-site five days a week.", {"EG"}, set(), "onsite", "eligible"),
        ]
        for location, body, allows, denies, mode, expected in cases:
            with self.subTest(body=body):
                extracted = extract(record(location, body))
                self.assertEqual(allows, {token for token, _ in extracted.geo_allow})
                self.assertEqual(denies, {token for token, _ in extracted.geo_deny})
                self.assertEqual(mode, extracted.work_mode[0])
                self.assertEqual(expected, eligibility_for(extracted)[0])

    def test_region_membership_and_unbounded_allow(self):
        from recon.regions import includes
        for region in ("AFRICA", "NORTH_AFRICA", "MENA", "EMEA"):
            self.assertTrue(includes(region, "EG"))
        for region in ("EU", "EEA", "EUROPE"):
            self.assertFalse(includes(region, "EG"))
        self.assertTrue(includes("WORLDWIDE", "EG"))
        self.assertTrue(includes("WORLDWIDE", "JP"))
        self.assertEqual("eligible", eligibility_for(extract(record("Worldwide")))[0])

    def test_eu_membership_complete(self):
        """Test that all 27 EU member states are included."""
        from recon.regions import includes
        eu_members = {
            "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE",
            "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT",
            "RO", "SK", "SI", "ES", "SE"
        }
        for country in eu_members:
            self.assertTrue(includes("EU", country), f"{country} should be in EU")
        # Verify non-EU countries are not in EU
        self.assertFalse(includes("EU", "GB"))
        self.assertFalse(includes("EU", "NO"))
        self.assertFalse(includes("EU", "EG"))

    def test_eea_membership_complete(self):
        """Test that EEA includes EU-27 plus Norway, Iceland, Liechtenstein."""
        from recon.regions import includes
        eu_members = {
            "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE",
            "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT",
            "RO", "SK", "SI", "ES", "SE"
        }
        eea_extra = {"NO", "IS", "LI"}
        for country in eu_members | eea_extra:
            self.assertTrue(includes("EEA", country), f"{country} should be in EEA")
        # Verify non-EEA countries are not in EEA
        self.assertFalse(includes("EEA", "GB"))
        self.assertFalse(includes("EEA", "EG"))
        self.assertFalse(includes("EEA", "US"))

    def test_europe_membership_complete(self):
        """Test that EUROPE includes EEA plus additional European countries."""
        from recon.regions import includes
        eea_members = {
            "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE",
            "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT",
            "RO", "SK", "SI", "ES", "SE", "NO", "IS", "LI"
        }
        extra_european = {"GB", "CH", "AL", "BA", "ME", "MK", "RS", "UA"}
        for country in eea_members | extra_european:
            self.assertTrue(includes("EUROPE", country), f"{country} should be in EUROPE")
        # Verify non-European countries are not in EUROPE
        self.assertFalse(includes("EUROPE", "EG"))
        self.assertFalse(includes("EUROPE", "US"))
        self.assertFalse(includes("EUROPE", "JP"))

    def test_africa_membership_representative(self):
        """Test that representative African countries are in AFRICA region."""
        from recon.regions import includes
        # Test sample of African countries across regions
        african_sample = {
            "EG",  # North Africa
            "ZA",  # Southern Africa
            "NG",  # West Africa
            "KE",  # East Africa
            "MA",  # North Africa
            "TN",  # North Africa
            "DZ",  # North Africa
            "LY",  # North Africa
            "SD",  # North Africa
            "ET",  # East Africa
            "GH",  # West Africa
            "UG",  # East Africa
            "TZ",  # East Africa
            "SN",  # West Africa
            "RW",  # Central Africa
            "CI",  # West Africa (Ivory Coast)
            "CM",  # Central Africa
            "AO",  # Southern Africa
            "MZ",  # Southern Africa
            "NA",  # Southern Africa
            "ZW",  # Southern Africa
            "BW",  # Southern Africa
            "MU",  # Southern Africa (Mauritius)
        }
        for country in african_sample:
            self.assertTrue(includes("AFRICA", country), f"{country} should be in AFRICA")

    def test_north_africa_membership(self):
        """Test that North African countries are correctly grouped."""
        from recon.regions import includes
        north_africa = {"EG", "MA", "TN", "DZ", "LY", "SD"}
        for country in north_africa:
            self.assertTrue(includes("NORTH_AFRICA", country), f"{country} should be in NORTH_AFRICA")
        # Verify non-North African countries are not in NORTH_AFRICA
        self.assertFalse(includes("NORTH_AFRICA", "ZA"))
        self.assertFalse(includes("NORTH_AFRICA", "NG"))
        self.assertFalse(includes("NORTH_AFRICA", "ET"))

    def test_mena_membership(self):
        """Test that MENA region includes Middle East and North African countries."""
        from recon.regions import includes
        mena_countries = {
            "EG", "SA", "AE", "QA", "KW", "BH", "OM", "JO", "LB", "IQ", "PS",
            "YE", "SY", "MA", "TN", "DZ", "LY", "SD"
        }
        for country in mena_countries:
            self.assertTrue(includes("MENA", country), f"{country} should be in MENA")
        # Verify non-MENA countries are not in MENA
        self.assertFalse(includes("MENA", "US"))
        self.assertFalse(includes("MENA", "JP"))
        self.assertFalse(includes("MENA", "ZA"))

    def test_emea_comprehensive(self):
        """Test that EMEA includes Europe, Middle East, and Africa."""
        from recon.regions import includes
        # Sample of countries from each region
        emea_sample = {
            # Europe
            "DE", "FR", "GB", "IT", "ES", "SE", "PL", "UA", "NO", "CH",
            # Middle East
            "EG", "SA", "AE", "QA", "JO", "LB", "IQ",
            # Africa
            "ZA", "NG", "KE", "MA", "GH", "ET"
        }
        for country in emea_sample:
            self.assertTrue(includes("EMEA", country), f"{country} should be in EMEA")

    def test_gcc_membership(self):
        """Test that GCC includes Gulf Cooperation Council countries."""
        from recon.regions import includes
        gcc_countries = {"SA", "AE", "QA", "KW", "BH", "OM"}
        for country in gcc_countries:
            self.assertTrue(includes("GCC", country), f"{country} should be in GCC")
        # Verify non-GCC countries are not in GCC
        self.assertFalse(includes("GCC", "EG"))
        self.assertFalse(includes("GCC", "US"))

    def test_americas_membership(self):
        """Test that Americas region is correctly defined."""
        from recon.regions import includes
        americas_countries = {"US", "CA", "BR", "MX", "AR"}
        for country in americas_countries:
            self.assertTrue(includes("AMERICAS", country), f"{country} should be in AMERICAS")

    def test_latam_membership(self):
        """Test that LATAM includes Latin American countries."""
        from recon.regions import includes
        latam_countries = {"BR", "MX", "AR", "CL", "CO", "PE"}
        for country in latam_countries:
            self.assertTrue(includes("LATAM", country), f"{country} should be in LATAM")

    def test_apac_membership(self):
        """Test that APAC includes Asia-Pacific countries."""
        from recon.regions import includes
        apac_countries = {"AU", "NZ", "IN", "JP", "SG", "KR"}
        for country in apac_countries:
            self.assertTrue(includes("APAC", country), f"{country} should be in APAC")

    def test_regional_hierarchy_invariants(self):
        """Test mathematical set hierarchy invariants across defined regions."""
        from recon.regions import REGIONS
        self.assertTrue(REGIONS["EU"].issubset(REGIONS["EEA"]), "EU must be a subset of EEA")
        self.assertTrue(REGIONS["EEA"].issubset(REGIONS["EUROPE"]), "EEA must be a subset of EUROPE")
        self.assertTrue(REGIONS["EUROPE"].issubset(REGIONS["EMEA"]), "EUROPE must be a subset of EMEA")
        self.assertTrue(REGIONS["AFRICA"].issubset(REGIONS["EMEA"]), "AFRICA must be a subset of EMEA")
        self.assertTrue(REGIONS["MENA"].issubset(REGIONS["EMEA"]), "MENA must be a subset of EMEA")
        self.assertTrue(REGIONS["NORTH_AFRICA"].issubset(REGIONS["AFRICA"]), "NORTH_AFRICA must be a subset of AFRICA")
        self.assertTrue(REGIONS["NORTH_AFRICA"].issubset(REGIONS["MENA"]), "NORTH_AFRICA must be a subset of MENA")
        self.assertTrue(REGIONS["GCC"].issubset(REGIONS["MENA"]), "GCC must be a subset of MENA")
        self.assertTrue(REGIONS["LATAM"].issubset(REGIONS["AMERICAS"]), "LATAM must be a subset of AMERICAS")

    def test_egypt_region_consistency(self):
        """Test Egypt's membership is consistent with ADR-0003."""
        from recon.regions import includes
        # Egypt should be in these regions
        for region in ("AFRICA", "NORTH_AFRICA", "MENA", "EMEA", "WORLDWIDE"):
            self.assertTrue(includes(region, "EG"), f"EG should be in {region}")
        # Egypt should NOT be in these regions
        for region in ("EU", "EEA", "EUROPE", "GCC", "AMERICAS", "LATAM", "APAC"):
            self.assertFalse(includes(region, "EG"), f"EG should NOT be in {region}")

    def test_derivation_egypt_default(self):
        """Test that eligibility_for defaults to Egypt (ADR-0003)."""
        # Test with MENA region should be eligible for Egypt
        extracted = extract(record("MENA"))
        result, _ = eligibility_for(extracted)
        self.assertEqual("eligible", result)
        # Test with Egypt-specific location
        extracted = extract(record("Cairo, Egypt"))
        result, _ = eligibility_for(extracted)
        self.assertEqual("eligible", result)

    def test_eeo_citizenship_mention_is_not_a_work_authorization_requirement(self):
        body = "We do not discriminate without regard to race, religion, sex, citizenship, age, or disability."
        extracted = extract(record("Anywhere", body))

        self.assertNotIn("WORK_AUTH_REQUIRED:US", {token for token, _ in extracted.geo_deny})
        self.assertEqual("eligible", classify(record("Anywhere", body)).eligibility)

    def test_explicit_citizenship_requirements_are_excluded(self):
        requirements = [
            "U.S. citizenship required.",
            "Candidates must possess US citizenship.",
            "Proof of citizenship required.",
            "Green card or citizenship required.",
        ]
        for body in requirements:
            with self.subTest(body=body):
                extracted = extract(record("Anywhere", body))
                self.assertIn("WORK_AUTH_REQUIRED:US", {token for token, _ in extracted.geo_deny})
                self.assertEqual("excluded", classify(record("Anywhere", body)).eligibility)

    def test_non_us_only_locations_use_their_own_residency_tokens(self):
        cases = {
            "France only": "RESIDENCY_REQUIRED:FR",
            "Japan only": "RESIDENCY_REQUIRED:JP",
            "Brazil only": "RESIDENCY_REQUIRED:BR",
            "India only": "RESIDENCY_REQUIRED:IN",
            "Canada only": "RESIDENCY_REQUIRED:CA",
            "LATAM only": "RESIDENCY_REQUIRED:LATAM",
            "EU only": "RESIDENCY_REQUIRED:EU",
        }
        for location, expected in cases.items():
            with self.subTest(location=location):
                extracted = extract(record(location, "Remote role."))
                deny_tokens = {token for token, _ in extracted.geo_deny}
                self.assertIn(expected, deny_tokens)
                self.assertNotIn("RESIDENCY_REQUIRED:US", deny_tokens)
