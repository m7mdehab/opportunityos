"""Unit tests for deterministic normalization and field extraction."""
import unittest

from opportunity.models import (
    CompensationInterval,
    EmploymentType,
    RemotePolicy,
    SeniorityLevel,
    Track,
)
from opportunity.normalization import (
    clean_text,
    derive_geographic_eligibility,
    extract_compensation,
    extract_employment_type,
    extract_list_sections,
    extract_remote_policy,
    extract_seniority,
    extract_skills_from_text,
    parse_iso_date,
)


class NormalizationTests(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual("Hello & World", clean_text("<p>Hello &amp; World</p>"))
        self.assertEqual("Clean text", clean_text("<div>Clean \n\t  text</div>"))
        self.assertEqual("", clean_text(None))

    def test_extract_seniority(self):
        self.assertEqual(SeniorityLevel.SENIOR, extract_seniority("Senior Software Engineer"))
        self.assertEqual(SeniorityLevel.LEAD, extract_seniority("Tech Lead - Platform"))
        self.assertEqual(SeniorityLevel.PRINCIPAL, extract_seniority("Principal Systems Architect"))
        self.assertEqual(SeniorityLevel.ENTRY, extract_seniority("Junior Python Developer"))
        self.assertEqual(SeniorityLevel.EXECUTIVE, extract_seniority("VP of Engineering"))
        self.assertEqual(SeniorityLevel.UNSPECIFIED, extract_seniority("Software Engineer"))

    def test_extract_employment_type(self):
        self.assertEqual(EmploymentType.FULL_TIME, extract_employment_type("Full-time"))
        self.assertEqual(EmploymentType.CONTRACT, extract_employment_type("C2C / 1099 Contractor"))
        self.assertEqual(EmploymentType.PART_TIME, extract_employment_type("Part Time"))
        self.assertEqual(EmploymentType.FREELANCE, extract_employment_type("Freelance consultant"))
        self.assertEqual(EmploymentType.INTERNSHIP, extract_employment_type("Summer Internship"))
        self.assertEqual(EmploymentType.UNSPECIFIED, extract_employment_type(""))

    def test_extract_remote_policy(self):
        self.assertEqual(RemotePolicy.REMOTE, extract_remote_policy("Remote - Worldwide"))
        self.assertEqual(RemotePolicy.HYBRID, extract_remote_policy("Hybrid - London"))
        self.assertEqual(RemotePolicy.ON_SITE, extract_remote_policy("On-site New York"))
        self.assertEqual(RemotePolicy.UNSPECIFIED, extract_remote_policy("London, UK"))

    def test_extract_compensation(self):
        c1 = extract_compensation("$120,000 - $160,000 per year")
        self.assertIsNotNone(c1)
        self.assertEqual(120000.0, c1.min_amount)  # type: ignore
        self.assertEqual(160000.0, c1.max_amount)  # type: ignore
        self.assertEqual("USD", c1.currency)  # type: ignore
        self.assertEqual(CompensationInterval.YEARLY, c1.interval)  # type: ignore

        c2 = extract_compensation("€70 - €95 / hour")
        self.assertIsNotNone(c2)
        self.assertEqual(70.0, c2.min_amount)  # type: ignore
        self.assertEqual(95.0, c2.max_amount)  # type: ignore
        self.assertEqual("EUR", c2.currency)  # type: ignore
        self.assertEqual(CompensationInterval.HOURLY, c2.interval)  # type: ignore

        c3 = extract_compensation("Competitive salary with equity")
        self.assertNull = self.assertIsNone(c3)

    def test_parse_iso_date(self):
        self.assertEqual("2026-08-30", parse_iso_date("2026-08-30T15:30:00Z"))
        self.assertEqual("2026-08-30", parse_iso_date("Sun, 30 Aug 2026 12:00:00 GMT"))
        self.assertEqual("2026-08-25", parse_iso_date("2026-08-25"))
        self.assertIsNone(parse_iso_date("invalid date string"))

    def test_extract_skills(self):
        text = "Looking for an engineer proficient with Python, PostgreSQL, AWS, and Docker."
        skills = extract_skills_from_text(text)
        self.assertIn("Python", skills)
        self.assertIn("PostgreSQL", skills)
        self.assertIn("AWS", skills)
        self.assertIn("Docker", skills)

    def test_extract_list_sections(self):
        html_content = """
        <h2>About</h2><p>Overview text.</p>
        <h3>Requirements:</h3>
        <ul>
          <li>5+ years experience</li>
          <li>Strong Python skills</li>
        </ul>
        <h3>What you will do:</h3>
        <ul>
          <li>Build APIs</li>
          <li>Optimize performance</li>
        </ul>
        """
        reqs = extract_list_sections(html_content, r"requirements")
        self.assertEqual(2, len(reqs))
        self.assertEqual("5+ years experience", reqs[0])

        duties = extract_list_sections(html_content, r"what\s+you\s+will\s+do")
        self.assertEqual(2, len(duties))
        self.assertEqual("Build APIs", duties[0])

    def test_derive_geographic_eligibility(self):
        # Worldwide remote -> eligible
        geo1 = derive_geographic_eligibility("Backend Engineer", "Remote - Worldwide", "Work from anywhere in the world.")
        self.assertEqual("eligible", geo1.status)

        # US Only -> excluded
        geo2 = derive_geographic_eligibility("Frontend Engineer", "Remote - US Only", "Must reside in the United States.")
        self.assertEqual("excluded", geo2.status)

        # Unclear location -> unclear
        geo3 = derive_geographic_eligibility("Engineer", "", "Vague description without geographic terms.")
        self.assertEqual("unclear", geo3.status)


if __name__ == "__main__":
    unittest.main()
