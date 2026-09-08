"""Unit tests for deterministic normalization and field lineage."""
import unittest

from opportunity.models import (
    CompensationInterval,
    DerivationType,
    EmploymentType,
    RemotePolicy,
    RemoteScope,
    SeniorityLevel,
    Track,
    WorkMode,
)
from opportunity.normalization import (
    clean_text,
    create_field_provenance,
    derive_geographic_eligibility,
    extract_compensation,
    extract_employment_type,
    extract_list_sections,
    extract_remote_policy,
    extract_seniority,
    extract_skills_from_text,
    extract_track,
    extract_work_location,
    extract_work_mode,
    parse_iso_date,
)


class NormalizationTests(unittest.TestCase):
    def test_clean_text(self) -> None:
        self.assertEqual(clean_text("<p>Hello &amp; welcome &lt;world&gt;!</p>"), "Hello & welcome <world>!")
        self.assertEqual(clean_text("   Lots   of \n\n whitespace \t here  "), "Lots of whitespace here")
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text({"eng": ["Software Engineer"]}), "Software Engineer")

    def test_extract_seniority(self) -> None:
        self.assertEqual(extract_seniority("Senior Software Engineer"), SeniorityLevel.SENIOR)
        self.assertEqual(extract_seniority("Lead DevOps Engineer"), SeniorityLevel.LEAD)
        self.assertEqual(extract_seniority("Principal Architect"), SeniorityLevel.PRINCIPAL)
        self.assertEqual(extract_seniority("VP of Engineering"), SeniorityLevel.EXECUTIVE)
        self.assertEqual(extract_seniority("Junior Python Developer"), SeniorityLevel.ENTRY)
        self.assertEqual(extract_seniority("Mid-level Data Scientist"), SeniorityLevel.MID)
        self.assertEqual(extract_seniority("Software Engineer"), SeniorityLevel.UNSPECIFIED)

    def test_extract_employment_type(self) -> None:
        self.assertEqual(extract_employment_type("full_time"), EmploymentType.FULL_TIME)
        self.assertEqual(extract_employment_type("Part-time"), EmploymentType.PART_TIME)
        self.assertEqual(extract_employment_type("contract"), EmploymentType.CONTRACT)
        self.assertEqual(extract_employment_type("freelance"), EmploymentType.FREELANCE)
        self.assertEqual(extract_employment_type("internship"), EmploymentType.INTERNSHIP)
        self.assertEqual(extract_employment_type(""), EmploymentType.UNSPECIFIED)

    def test_extract_track_deterministic(self) -> None:
        self.assertEqual(extract_track(Track.EMPLOYMENT, "full_time"), Track.EMPLOYMENT)
        self.assertEqual(extract_track(Track.EMPLOYMENT, "contract"), Track.CONTRACT)
        self.assertEqual(extract_track(Track.EMPLOYMENT, "1099 contractor"), Track.CONTRACT)
        self.assertEqual(extract_track(Track.EMPLOYMENT, "freelance"), Track.FREELANCE)
        self.assertEqual(extract_track(Track.EMPLOYMENT, "freelancer needed"), Track.FREELANCE)
        self.assertEqual(extract_track(Track.PROCUREMENT, "tender"), Track.PROCUREMENT)

    def test_extract_remote_policy(self) -> None:
        self.assertEqual(extract_remote_policy("Remote"), RemotePolicy.REMOTE)
        self.assertEqual(extract_remote_policy("Hybrid - San Francisco, CA"), RemotePolicy.HYBRID)
        self.assertEqual(extract_remote_policy("On-site New York, NY"), RemotePolicy.ON_SITE)
        self.assertEqual(extract_remote_policy("San Francisco, CA"), RemotePolicy.UNSPECIFIED)

    # --- BRIEF-FR-006 A1: work_mode / location / remote_scope inference engine ---

    def test_extract_work_mode_generic(self) -> None:
        self.assertEqual(extract_work_mode("Remote"), WorkMode.REMOTE)
        self.assertEqual(extract_work_mode("Hybrid - San Francisco, CA"), WorkMode.HYBRID)
        self.assertEqual(extract_work_mode("On-site New York, NY"), WorkMode.ONSITE)
        self.assertEqual(extract_work_mode("Just a job title, no location signal"), WorkMode.UNSPECIFIED)

    def test_worked_example_1_remote_us_only(self) -> None:
        """Brief worked example: 'Remote (US only)' -> remote, region-restricted [US]."""
        result = extract_work_location("Remote (US only)", "")
        self.assertEqual(WorkMode.REMOTE, result.work_mode)
        self.assertEqual("inference", result.work_mode_source)
        self.assertEqual(RemoteScope.REGION_RESTRICTED, result.remote_scope)
        self.assertEqual(("US",), result.remote_scope_regions)

    def test_worked_example_2_hybrid_cairo(self) -> None:
        """Brief worked example: 'Hybrid — Cairo' -> hybrid, EG/Cairo."""
        result = extract_work_location("Hybrid — Cairo", "")
        self.assertEqual(WorkMode.HYBRID, result.work_mode)
        self.assertEqual("EG", result.location_country)
        self.assertEqual("Cairo", result.location_city)

    def test_worked_example_3_onsite_multi_country(self) -> None:
        """Brief worked example: 'Egypt, Saudi Arabia, or UAE' -> onsite, multi-country."""
        result = extract_work_location("Egypt, Saudi Arabia, or UAE", "")
        self.assertEqual(WorkMode.ONSITE, result.work_mode)
        self.assertIn("EG", result.location_region)
        self.assertIn("SA", result.location_region)
        self.assertIn("AE", result.location_region)

    def test_native_mapping_wins_over_inference(self) -> None:
        """Adapter-native work_mode must never be overwritten by text inference."""
        result = extract_work_location(
            "Onsite in Berlin", "This role is fully remote.", native_work_mode=WorkMode.HYBRID
        )
        self.assertEqual(WorkMode.HYBRID, result.work_mode)
        self.assertEqual("adapter", result.work_mode_source)

    def test_no_signal_yields_unspecified_and_none_source(self) -> None:
        result = extract_work_location("", "")
        self.assertEqual(WorkMode.UNSPECIFIED, result.work_mode)
        self.assertEqual("none", result.work_mode_source)
        self.assertEqual(RemoteScope.UNSPECIFIED, result.remote_scope)
        self.assertEqual("", result.location_country)

    def test_country_name_inference(self) -> None:
        result = extract_work_location("Onsite - Cairo, Egypt", "")
        self.assertEqual("EG", result.location_country)

    def test_extract_compensation_no_fabricated_defaults(self) -> None:
        # 1. "5-10 years experience" -> NO compensation
        self.assertIsNone(extract_compensation("Requires 5-10 years experience in distributed systems."))
        self.assertIsNone(extract_compensation("5-10 years of experience with Python."))

        # 2. "10-20 engineers" -> NO compensation
        self.assertIsNone(extract_compensation("Managing a team of 10-20 engineers across MENA."))

        # 3. "USD 120k-180k annually" -> 120000-180000 USD YEARLY
        comp_usd = extract_compensation("Salary: USD 120k-180k annually")
        self.assertIsNotNone(comp_usd)
        self.assertEqual(comp_usd.min_amount, 120000.0)
        self.assertEqual(comp_usd.max_amount, 180000.0)
        self.assertEqual(comp_usd.currency, "USD")
        self.assertEqual(comp_usd.interval, CompensationInterval.YEARLY)

        # 4. Both k suffixes parse correctly: 120k-180k -> 120000 and 180000 (not 120000 and 180)
        comp_k = extract_compensation("Rate: $120k - $180k")
        self.assertIsNotNone(comp_k)
        self.assertEqual(comp_k.min_amount, 120000.0)
        self.assertEqual(comp_k.max_amount, 180000.0)

        # 5. Bare "$" must NOT automatically prove USD unless source semantics explicitly guarantee USD
        self.assertIsNone(comp_k.currency)

        # 6. Do not infer YEARLY from numeric magnitude alone
        comp_mag = extract_compensation("Salary: $140,000 - $180,000")
        self.assertIsNotNone(comp_mag)
        self.assertEqual(comp_mag.min_amount, 140000.0)
        self.assertEqual(comp_mag.max_amount, 180000.0)
        self.assertIsNone(comp_mag.currency)
        self.assertEqual(comp_mag.interval, CompensationInterval.UNSPECIFIED)

        # EUR with monthly interval
        comp_eur = extract_compensation("€4,000 – €6,000 per month")
        self.assertIsNotNone(comp_eur)
        self.assertEqual(comp_eur.min_amount, 4000.0)
        self.assertEqual(comp_eur.max_amount, 6000.0)
        self.assertEqual(comp_eur.currency, "EUR")
        self.assertEqual(comp_eur.interval, CompensationInterval.MONTHLY)

        # Numbers without explicit currency or interval MUST NOT default to USD or YEARLY
        comp3 = extract_compensation("Rate: 50 - 80")
        self.assertIsNotNone(comp3)
        self.assertEqual(comp3.min_amount, 50.0)
        self.assertEqual(comp3.max_amount, 80.0)
        self.assertIsNone(comp3.currency)
        self.assertEqual(comp3.interval, CompensationInterval.UNSPECIFIED)

        # Unparseable or absent returns None
        self.assertIsNone(extract_compensation("Competitive equity and benefits"))

    def test_parse_iso_date(self) -> None:
        self.assertEqual(parse_iso_date("2026-08-30"), "2026-08-30")
        self.assertEqual(parse_iso_date("2026-08-30T12:00:00Z"), "2026-08-30")
        self.assertEqual(parse_iso_date("Wed, 28 Aug 2026 14:00:00 GMT"), "2026-08-28")
        self.assertEqual(parse_iso_date("August 25, 2026"), "2026-08-25")
        self.assertIsNone(parse_iso_date("invalid-date"))
        self.assertIsNone(parse_iso_date(None))

    def test_extract_skills(self) -> None:
        text = "We are seeking a senior Python developer experienced with AWS, Docker, and PostgreSQL."
        skills = extract_skills_from_text(text)
        self.assertIn("Python", skills)
        self.assertIn("AWS", skills)
        self.assertIn("Docker", skills)
        self.assertIn("PostgreSQL", skills)

    def test_extract_list_sections(self) -> None:
        html = """
        <h3>What you'll do:</h3>
        <ul>
            <li>Build resilient distributed services</li>
            <li>Maintain high test coverage</li>
        </ul>
        <h3>Requirements:</h3>
        <ul>
            <li>5+ years backend experience</li>
            <li>Strong Python skills</li>
        </ul>
        """
        resps = extract_list_sections(html, r"what\s+you'?ll\s+do")
        self.assertEqual(len(resps), 2)
        self.assertIn("Build resilient distributed services", resps)

        reqs = extract_list_sections(html, r"requirement")
        self.assertEqual(len(reqs), 2)
        self.assertIn("5+ years backend experience", reqs)

    def test_derive_geographic_eligibility(self) -> None:
        geo_eligible = derive_geographic_eligibility("Senior Engineer", "Worldwide (Remote)", "Work from anywhere in the world.")
        self.assertEqual(geo_eligible.status, "eligible")

        geo_excluded = derive_geographic_eligibility("Backend Engineer", "US Only (Remote)", "Must reside in the United States.")
        self.assertEqual(geo_excluded.status, "excluded")

    def test_create_field_provenance(self) -> None:
        fp = create_field_provenance(
            field_name="title",
            raw_val="<p>Lead Engineer</p>",
            norm_val="Lead Engineer",
            derivation_type=DerivationType.RAW_EXTRACTION,
            raw_pointer="jobs[0].title",
            record_checksum="sha256abc",
            rule_id="clean_text",
        )
        self.assertEqual(fp.field_name, "title")
        self.assertEqual(fp.raw_value, "<p>Lead Engineer</p>")
        self.assertEqual(fp.normalized_value, "Lead Engineer")
        self.assertEqual(fp.derivation_type, "raw_extraction")

    # --- Adversarial Channel Segregation Tests (BRIEF-FR-006 Inference Safety Delta) ---

    def test_adversarial_channel_segregation_negative_control_a(self) -> None:
        """Negative control A: 'We are a global company. This role is onsite in Cairo.'
        Must NOT infer remote/worldwide from generic employer prose; onsite + Cairo/EG only.
        """
        result = extract_work_location("", "We are a global company. This role is onsite in Cairo.")
        self.assertEqual(WorkMode.ONSITE, result.work_mode)
        self.assertEqual(RemoteScope.UNSPECIFIED, result.remote_scope)
        self.assertEqual("EG", result.location_country)
        self.assertEqual("Cairo", result.location_city)

    def test_adversarial_channel_segregation_negative_control_b(self) -> None:
        """Negative control B: 'Support customers in California and India. Role location: Cairo.'
        Must NOT infer US or India as job country; Cairo/EG inferred from explicit role-location.
        """
        result = extract_work_location("", "Support customers in California and India. Role location: Cairo.")
        self.assertNotIn(result.location_country, ("US", "IN"))
        self.assertEqual("EG", result.location_country)
        self.assertEqual("Cairo", result.location_city)

    def test_adversarial_channel_segregation_negative_control_c(self) -> None:
        """Negative control C: 'Global team; hybrid role in London.'
        Must NOT infer worldwide remote; hybrid + London/GB only.
        """
        result = extract_work_location("", "Global team; hybrid role in London.")
        self.assertEqual(WorkMode.HYBRID, result.work_mode)
        self.assertEqual(RemoteScope.UNSPECIFIED, result.remote_scope)
        self.assertEqual("GB", result.location_country)
        self.assertEqual("London", result.location_city)

    def test_adversarial_channel_segregation_negative_control_d(self) -> None:
        """Negative control D: 'Work with teams anywhere in the world.'
        With no role/candidate location semantics, must NOT infer remote/worldwide.
        """
        result = extract_work_location("", "Work with teams anywhere in the world.")
        self.assertEqual(WorkMode.UNSPECIFIED, result.work_mode)
        self.assertEqual(RemoteScope.UNSPECIFIED, result.remote_scope)

    def test_adversarial_channel_segregation_positive_control_e(self) -> None:
        """Positive control E: raw location = 'Worldwide' -> remote / worldwide."""
        result = extract_work_location("Worldwide", "")
        self.assertEqual(WorkMode.REMOTE, result.work_mode)
        self.assertEqual(RemoteScope.WORLDWIDE, result.remote_scope)

    def test_adversarial_channel_segregation_positive_control_f(self) -> None:
        """Positive control F: 'This position is fully remote and may be worked from anywhere.' -> remote / worldwide."""
        result = extract_work_location("", "This position is fully remote and may be worked from anywhere.")
        self.assertEqual(WorkMode.REMOTE, result.work_mode)
        self.assertEqual(RemoteScope.WORLDWIDE, result.remote_scope)

    def test_adversarial_channel_segregation_positive_control_g(self) -> None:
        """Positive control G: 'Must be based in California.' -> US."""
        result = extract_work_location("", "Must be based in California.")
        self.assertEqual("US", result.location_country)


if __name__ == "__main__":
    unittest.main()

