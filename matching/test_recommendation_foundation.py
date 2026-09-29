from __future__ import annotations

import unittest
from types import SimpleNamespace

from matching.recommendation_foundation import (
    classify_application_access,
    classify_founder_geography,
    classify_required_credentials,
    classify_role_relevance,
)


class RecommendationFoundationTests(unittest.TestCase):
    def test_role_relevance_uses_existing_families_and_requires_adjacent_evidence(self):
        self.assertEqual(classify_role_relevance("Senior Data Engineer").classification, "core")
        self.assertEqual(
            classify_role_relevance("Backend Engineer", "Build a data platform with SQL pipelines").classification,
            "non_target",
        )
        self.assertEqual(
            classify_role_relevance("Backend Engineer - Data Platform").classification,
            "core",
        )
        self.assertEqual(
            classify_role_relevance("Backend Engineer - AI Tooling").classification,
            "adjacent",
        )
        self.assertEqual(
            classify_role_relevance(
                "Backend Engineer",
                "Build distributed services. About Us: We are leaders in machine learning and AI data platforms.",
            ).classification,
            "non_target",
        )
        self.assertEqual(
            classify_role_relevance(
                "Staff BESS Electrical Design Engineer, EPC",
                "Design electrical battery storage systems for construction projects.",
            ).classification,
            "non_target",
        )
        # The AI/ML token can describe a consumer product rather than the
        # discipline of the role. These live titles must not enter For You.
        for title in (
            "Product Manager - AI Neobank App",
            "Product Lead - AI Neobank App",
            "Mobile Application Developer - AI Neobank App",
        ):
            with self.subTest(title=title):
                self.assertEqual(classify_role_relevance(title).classification, "non_target")
        # These stored live rows had stale adjacent labels from an older pass.
        for title in (
            "Data Center Engineer",
            "Global Safety & Security Manager",
            "Business Developer",
            "Senior Network Engineer",
        ):
            with self.subTest(title=title):
                self.assertEqual(classify_role_relevance(title).classification, "non_target")
        self.assertEqual(classify_role_relevance("Risk Analyst", "Our company builds AI tools").classification, "non_target")
        self.assertEqual(classify_role_relevance("Associate Demo Engineer", "About Us: AI analytics platform").classification, "non_target")
        self.assertEqual(
            classify_role_relevance("Backend Engineer", "Build distributed services").classification,
            "non_target",
        )
        self.assertEqual(classify_role_relevance("Gardener").classification, "non_target")

    def test_us_employer_or_office_is_not_an_applicant_restriction(self):
        state, _ = classify_founder_geography(
            description="Remote role for a US company, USD compensation.",
            location_country="US",
            work_mode="remote",
        )
        self.assertEqual(state, "review")

    def test_explicit_egypt_scope_and_restrictions_are_distinguished(self):
        self.assertEqual(classify_founder_geography(
            description="We hire worldwide.", work_mode="remote"
        )[0], "likely_eligible")
        self.assertEqual(classify_founder_geography(
            description="US applicants only; must have US work authorization."
        )[0], "ineligible")
        self.assertEqual(classify_founder_geography(
            description="Eligible countries: United States and Canada."
        )[0], "ineligible")
        self.assertEqual(classify_founder_geography(
            description="Eligible countries: Egypt, United States."
        )[0], "likely_eligible")
        self.assertEqual(classify_founder_geography(
            description="Must be based in US Eastern time zone."
        )[0], "review")
        self.assertEqual(classify_founder_geography(
            description="On-site role", location_country="US", work_mode="onsite"
        )[0], "ineligible")

    def test_geography_precedence_adversarial_matrix(self):
        classify = classify_founder_geography
        compatible = (
            ("Egypt remote", dict(description="Remote position open to applicants in Egypt.", work_mode="remote"), "likely_eligible"),
            ("Worldwide remote", dict(remote_scope="worldwide", work_mode="remote"), "likely_eligible"),
            ("EMEA remote", dict(remote_scope="region_restricted", remote_scope_regions=("EMEA",), work_mode="remote"), "likely_eligible"),
            ("source Home Based EMEA label", dict(location_region="Home Based - EMEA", work_mode="remote"), "likely_eligible"),
            ("description based remotely in EMEA", dict(description="This role will be based remotely in the EMEA region.", work_mode="remote"), "likely_eligible"),
            ("global hiring language in job-specific text", dict(title="Remote infrastructure role", description="This role is fully remote, we are hiring globally.", work_mode="remote"), "likely_eligible"),
            ("salary applicability is not candidate residency restriction", dict(title="Product Marketing Lead", description="This role is based remotely in EMEA. The salary range listed for this role applies to US-based candidates only.", location_region="EMEA - Remote US", work_mode="remote"), "likely_eligible"),
            ("MENA remote", dict(remote_scope="region_restricted", remote_scope_regions=("MENA",), work_mode="remote"), "likely_eligible"),
            ("Africa remote", dict(remote_scope="region_restricted", remote_scope_regions=("Africa",), work_mode="remote"), "likely_eligible"),
            ("Egypt in country list", dict(description="Eligible countries: Egypt, United States.", work_mode="remote"), "likely_eligible"),
            ("US employer and global salary metadata", dict(description="Remote role. Open to applicants worldwide. US employer; USD compensation.", location_country="US", work_mode="remote"), "likely_eligible"),
            ("US salary and offices do not defeat explicit world access", dict(description="Remote role open to applicants worldwide. The employer has US offices and pays USD.", location_country="US", work_mode="remote"), "likely_eligible"),
            ("Canonical globally remote location", dict(description="Location: Globally remote. This home-based role may be performed worldwide.", work_mode="remote"), "likely_eligible"),
            ("work from home available worldwide", dict(description="Work-from-home roles are available worldwide.", work_mode="remote"), "likely_eligible"),
            ("remote all time zones", dict(description="This remote role has teams in all time zones.", work_mode="remote"), "likely_eligible"),
            ("CET plus or minus three hours includes Egypt", dict(description="Remote role, timezone CET ±3-hour requirement.", work_mode="remote"), "likely_eligible"),
            ("UTC minus six to plus eight includes Egypt", dict(description="Remote role; work between UTC−6 to UTC+8.", work_mode="remote"), "likely_eligible"),
        )
        incompatible = (
            ("country list excludes Egypt", dict(description="Eligible countries: United States and Canada.", work_mode="remote"), "ineligible"),
            ("onsite Egypt", dict(location_country="EG", work_mode="onsite"), "eligible"),
            ("onsite US", dict(location_country="US", location_region="Vandenberg, CA", work_mode="onsite"), "ineligible"),
            ("hybrid US", dict(location_country="US", location_region="New York", work_mode="hybrid"), "ineligible"),
            ("onsite US beats global boilerplate", dict(title="Data Engineer", description="We are a global company with teams worldwide.", location_country="US", location_region="Vandenberg, CA", work_mode="onsite"), "ineligible"),
            ("US Remote title beats global footer", dict(title="Senior Backend Engineer | US | Remote", description="About Us: We are a global company with employees worldwide.", location_country="US", work_mode="remote"), "ineligible"),
            ("Remote — US title", dict(title="Data Engineer — Remote — US", work_mode="remote"), "ineligible"),
            ("Remote within United States title", dict(title="Remote within United States", work_mode="remote"), "ineligible"),
            ("US Remote label", dict(location_region="US Remote", work_mode="remote"), "ineligible"),
            ("Remote (US) label", dict(location_region="Remote (US)", work_mode="remote"), "ineligible"),
            ("US remote location label beats worldwide metadata", dict(title="Data Engineer", location_country="US", location_region="US | Remote", remote_scope="worldwide", work_mode="remote"), "ineligible"),
            ("contradictory Canada title and US source remote label stays review", dict(title="Senior Backend Engineer - Analytics | Canada | Remote", location_country="US", location_region="USA (Remote)", remote_scope="region_restricted", work_mode="remote"), "review"),
            ("description on-site line beats remote/worldwide metadata", dict(title="AI Security Engineer", description="Location: McLean, VA | On-site (5 days/week)\nWe are a global company with teams worldwide.", location_country="US", location_region="Appian Corporation - US", remote_scope="worldwide", work_mode="remote"), "ineligible"),
            ("description hybrid line beats remote/worldwide metadata", dict(title="Data Engineer", description="Work arrangement: Hybrid, Austin, TX\nWe hire globally.", location_country="US", location_region="Austin, TX", remote_scope="worldwide", work_mode="unspecified"), "ineligible"),
            ("mixed remote and on-site line stays review", dict(title="Data Engineer", description="Location: Remote or On-site, United States", location_country="US", remote_scope="worldwide", work_mode="unspecified"), "review"),
            ("Brazil and LATAM remote label beats broad inferred worldwide", dict(title="Data Engineer", location_country="BR", location_region="Brazil & Latin America / Remote", remote_scope="worldwide", work_mode="remote"), "ineligible"),
            ("Egypt remote location label is compatible", dict(title="Data Engineer", location_country="EG", location_region="Egypt / Remote", remote_scope="region_restricted", work_mode="remote"), "likely_eligible"),
            ("US-only description beats worldwide title", dict(title="Data Engineer — Worldwide Remote", description="Applicants from the United States only.", work_mode="remote"), "ineligible"),
        )
        review = (
            ("ambiguous remote", dict(title="Data Engineer", work_mode="remote", location_country="US"), "review"),
            ("global company footer only", dict(description="About Us:\nWe hire employees anywhere worldwide.", work_mode="remote"), "review"),
            ("job scope before company footer remains valid", dict(description="Applicants in Egypt may work remotely.\nAbout Us:\nOur global team works anywhere worldwide.", work_mode="remote"), "likely_eligible"),
            ("US authorization unverified", dict(description="Remote. Must be authorized to work in the US.", work_mode="remote"), "review"),
            ("US citizenship unverified", dict(description="US citizenship required.", work_mode="remote"), "review"),
            ("must reside in US", dict(description="Remote position. Must reside in the United States.", work_mode="remote"), "ineligible"),
            ("must already be based in Sweden", dict(description="This remote role is for candidates who must be based in Sweden.", location_country="SE", work_mode="remote"), "ineligible"),
            ("US timezone is not applicant restriction", dict(description="Remote role open to applicants worldwide. Work with teams in US Eastern time zone.", work_mode="remote"), "likely_eligible"),
            ("US hours are a schedule requirement", dict(title="Head of Technical Support", description="Work from anywhere. Work during US hours. Do not apply if you cannot work US hours.", location_region="Anywhere in the World", work_mode="remote"), "likely_eligible"),
            ("US office-hours parenthetical is not a residency label", dict(title="Remote (US hours)", location_region="Anywhere in the World", work_mode="remote"), "review"),
            ("required office days override stale remote mode", dict(description="Location & Travel Expectations: This role will be based out of Blythewood. This role requires 4-5 days per week in the office.", location_country="US", location_region="Blythewood, SC", work_mode="remote"), "ineligible"),
            ("physical site takes precedence over unrelated export clause", dict(description="Location: Auckland office. This is an onsite role. For candidates seeking to work in US offices only, employees must be a U.S. citizen.", location_country="NZ", location_city="Auckland", work_mode="onsite"), "ineligible"),
        )
        for name, kwargs, expected in (*compatible, *incompatible, *review):
            with self.subTest(case=name):
                self.assertEqual(classify(**kwargs)[0], expected)

    def test_required_clearance_uses_verified_truth_graph(self):
        posting = "Required qualifications: Active Secret security clearance required."
        self.assertEqual(
            classify_required_credentials(posting),
            ("review", "required_clearance_unverified"),
        )

        from truth import predicates
        from truth.models import Modality, Polarity, VerificationStatus
        name = SimpleNamespace(
            predicate=predicates.CERTIFICATION_NAME,
            value="Secret security clearance",
            subject_id="cert-clearance",
            verification_status=VerificationStatus.VERIFIED,
            modality=Modality.DEFINITE,
            polarity=Polarity.POSITIVE,
        )
        state = SimpleNamespace(
            predicate=predicates.CERTIFICATION_STATE,
            value="completed",
            subject_id="cert-clearance",
            verification_status=VerificationStatus.VERIFIED,
            modality=Modality.DEFINITE,
            polarity=Polarity.POSITIVE,
        )
        graph = SimpleNamespace(assertions={"name": name, "state": state})
        self.assertEqual(classify_required_credentials(posting, graph), (None, None))

        contradicted = SimpleNamespace(
            predicate=predicates.CERTIFICATION_NAME,
            value="Secret security clearance",
            subject_id="cert-clearance",
            verification_status=VerificationStatus.VERIFIED,
            modality=Modality.DEFINITE,
            polarity=Polarity.NEGATIVE,
        )
        graph.assertions = {"negative": contradicted}
        self.assertEqual(
            classify_required_credentials(posting, graph),
            ("ineligible", "founder_lacks_required_credential"),
        )

    def test_unrelated_physical_engineering_titles_are_not_data_adjacent(self):
        for title in (
            "Staff BESS Electrical Design Engineer, EPC",
            "Staff Mechanical Design Engineer, EPC",
            "Staff Cathode Engineer",
            "Packaging Engineer",
            "Chemical Engineer",
            "Functional Safety Engineer, Energy Storage",
            "Software Validation Engineer, Energy Storage",
        ):
            with self.subTest(title=title):
                self.assertEqual(classify_role_relevance(title, "").classification, "non_target")

        self.assertEqual(
            classify_role_relevance("Senior Software Engineer, Data Engineering", "").classification,
            "adjacent",
        )

    def test_clearance_and_citizenship_requirements_remain_review_without_founder_evidence(self):
        state, reason = classify_founder_geography(
            description=(
                "Remote from Egypt. Active Top Secret clearance required. "
                "Must be a U.S. citizen."
            ),
            work_mode="remote",
        )
        credential_state, credential_reason = classify_required_credentials(
            "Active Top Secret clearance required."
        )
        self.assertEqual((state, reason), ("review", "required_us_citizenship_unverified"))
        self.assertEqual((credential_state, credential_reason), ("review", "required_clearance_unverified"))

    def test_onsite_outside_egypt_requires_place_specific_verified_relocation_preference(self):
        self.assertEqual(classify_founder_geography(
            location_country="US", location_region="Arlington, VA", work_mode="onsite",
        )[0], "ineligible")

        from truth import predicates
        from truth.models import Modality, Polarity, VerificationStatus
        relocation = SimpleNamespace(
            predicate=predicates.PREFERENCE_RELOCATION,
            value="willing to relocate to the United States",
            verification_status=VerificationStatus.VERIFIED,
            modality=Modality.DEFINITE,
            polarity=Polarity.POSITIVE,
        )
        graph = SimpleNamespace(assertions={"relocation": relocation})
        state, reason = classify_founder_geography(
            location_country="US", location_region="Arlington, VA", work_mode="onsite",
            truth_graph=graph,
        )
        self.assertEqual(state, "review")
        self.assertIn("relocation", reason)

        relocation.value = "willing to relocate within Egypt"
        self.assertEqual(classify_founder_geography(
            location_country="US", location_region="Arlington, VA", work_mode="onsite",
            truth_graph=graph,
        )[0], "ineligible")

    def test_public_ats_url_overrides_aggregator_route(self):
        result = classify_application_access(
            "we_work_remotely",
            "https://weworkremotely.com/remote-jobs/example",
            "https://boards.greenhouse.io/example/jobs/123",
        )
        self.assertEqual((result.route, result.access), ("ats", "direct_free"))
        self.assertEqual(result.application_url, "https://boards.greenhouse.io/example/jobs/123")

    def test_unverified_application_access_remains_unknown(self):
        result = classify_application_access(
            "himalayas", "https://himalayas.app/jobs/data-engineer"
        )
        self.assertEqual(result.access, "unknown")


if __name__ == "__main__":
    unittest.main()
