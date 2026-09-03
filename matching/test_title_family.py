"""Tests for B3 (BRIEF-FR-006) `matching/title_family.py::normalize_title`.

Covers: at least two positive and one negative case per family; the
brief-named non-collision pairs ("Data Engineer" vs "Customer Engineer",
"ML Engineer" vs "Sales Engineer"); case, punctuation, and suffix variants;
and level detection (intern/junior/mid/senior/staff/principal/unspecified).
"""
from __future__ import annotations

import unittest

from matching.title_family import normalize_title

_KNOWN_FAMILIES = frozenset({
    "customer_solutions_engineering", "ml_ai_engineering", "data_science",
    "data_migration", "analytics_bi", "tutoring", "data_engineering",
    "web_frontend", "backend", "devops_platform", "product",
    "project_program_management", "other",
})


class TestDataEngineeringFamily(unittest.TestCase):
    def test_data_engineer_basic(self) -> None:
        family, level, rule = normalize_title("Data Engineer")
        self.assertEqual(family, "data_engineering")
        self.assertEqual(level, "unspecified")
        self.assertTrue(rule.startswith("data_engineering#"))

    def test_data_engineer_senior_with_punctuation(self) -> None:
        family, level, rule = normalize_title("Senior Data Engineer, Platform (Remote — EU)")
        self.assertEqual(family, "data_engineering")
        self.assertEqual(level, "senior")
        self.assertTrue(rule.startswith("data_engineering#"))

    def test_lead_data_architect(self) -> None:
        family, level, _ = normalize_title("Lead Data Architect")
        self.assertEqual(family, "data_engineering")
        self.assertEqual(level, "senior")

    def test_data_engineer_negative_not_customer(self) -> None:
        family, _, _ = normalize_title("Customer Engineer")
        self.assertNotEqual(family, "data_engineering")


class TestCustomerSolutionsEngineeringFamily(unittest.TestCase):
    def test_customer_engineer_basic(self) -> None:
        family, level, rule = normalize_title("Senior Customer Engineer")
        self.assertEqual(family, "customer_solutions_engineering")
        self.assertEqual(level, "senior")
        self.assertTrue(rule.startswith("customer_solutions_engineering#"))

    def test_solutions_engineer_variant(self) -> None:
        family, _, _ = normalize_title("Solutions Engineer, EMEA")
        self.assertEqual(family, "customer_solutions_engineering")

    def test_data_engineer_vs_customer_engineer_no_collision(self) -> None:
        de_family, _, _ = normalize_title("Data Engineer")
        ce_family, _, _ = normalize_title("Customer Engineer")
        self.assertEqual(de_family, "data_engineering")
        self.assertEqual(ce_family, "customer_solutions_engineering")
        self.assertNotEqual(de_family, ce_family)


class TestMlAiEngineeringFamily(unittest.TestCase):
    def test_ml_engineer_basic(self) -> None:
        family, level, rule = normalize_title("ML Engineer")
        self.assertEqual(family, "ml_ai_engineering")
        self.assertEqual(level, "unspecified")
        self.assertTrue(rule.startswith("ml_ai_engineering#"))

    def test_machine_learning_engineer_senior(self) -> None:
        family, level, _ = normalize_title("Senior Machine Learning Engineer")
        self.assertEqual(family, "ml_ai_engineering")
        self.assertEqual(level, "senior")

    def test_sales_engineer_maps_customer_family(self) -> None:
        family, _, _ = normalize_title("Sales Engineer")
        self.assertEqual(family, "customer_solutions_engineering")

    def test_ml_engineer_vs_sales_engineer_no_collision(self) -> None:
        ml_family, _, _ = normalize_title("ML Engineer")
        sales_family, _, _ = normalize_title("Sales Engineer")
        self.assertEqual(ml_family, "ml_ai_engineering")
        self.assertEqual(sales_family, "customer_solutions_engineering")
        self.assertNotEqual(ml_family, sales_family)


class TestDataScienceFamily(unittest.TestCase):
    def test_data_scientist_basic(self) -> None:
        family, level, rule = normalize_title("Data Scientist")
        self.assertEqual(family, "data_science")
        self.assertEqual(level, "unspecified")
        self.assertTrue(rule.startswith("data_science#"))

    def test_statistical_consulting(self) -> None:
        family, _, _ = normalize_title("Statistical Consulting Services")
        self.assertEqual(family, "data_science")

    def test_data_scientist_vs_data_engineer_no_collision(self) -> None:
        ds_family, _, _ = normalize_title("Data Scientist")
        de_family, _, _ = normalize_title("Data Engineer")
        self.assertNotEqual(ds_family, de_family)


class TestDataMigrationFamily(unittest.TestCase):
    def test_data_migration_alias(self) -> None:
        family, level, rule = normalize_title("Data Migration Specialist")
        self.assertEqual(family, "data_migration")
        self.assertEqual(level, "unspecified")
        self.assertTrue(rule.startswith("data_migration#"))

    def test_cloud_migration_tender(self) -> None:
        family, _, _ = normalize_title("Enterprise Cloud Migration Tender")
        self.assertEqual(family, "data_migration")

    def test_cloud_security_assessment_is_not_migration(self) -> None:
        family, _, _ = normalize_title("Cloud Security Assessment")
        self.assertNotEqual(family, "data_migration")


class TestAnalyticsBiFamily(unittest.TestCase):
    def test_data_analyst_basic(self) -> None:
        family, level, rule = normalize_title("Data Analyst - Product Insights")
        self.assertEqual(family, "analytics_bi")
        self.assertEqual(level, "unspecified")
        self.assertTrue(rule.startswith("analytics_bi#"))

    def test_bi_analyst_variant(self) -> None:
        family, _, _ = normalize_title("BI Analyst")
        self.assertEqual(family, "analytics_bi")

    def test_analytics_bi_vs_data_engineer_no_collision(self) -> None:
        analyst_family, _, _ = normalize_title("Data Analyst - Product Insights")
        engineer_family, _, _ = normalize_title("Data Engineer")
        self.assertNotEqual(analyst_family, engineer_family)


class TestTutoringFamily(unittest.TestCase):
    def test_tutor_basic(self) -> None:
        family, level, rule = normalize_title("Mathematics Tutor")
        self.assertEqual(family, "tutoring")
        self.assertEqual(level, "unspecified")
        self.assertTrue(rule.startswith("tutoring#"))

    def test_private_tutor_variant(self) -> None:
        family, _, _ = normalize_title("Private Tutor - SAT Prep")
        self.assertEqual(family, "tutoring")

    def test_tutoring_negative_backend_title(self) -> None:
        family, _, _ = normalize_title("Backend Engineer")
        self.assertNotEqual(family, "tutoring")


class TestWebFrontendFamily(unittest.TestCase):
    def test_frontend_developer_basic(self) -> None:
        family, level, rule = normalize_title("Junior Frontend Developer")
        self.assertEqual(family, "web_frontend")
        self.assertEqual(level, "junior")
        self.assertTrue(rule.startswith("web_frontend#"))

    def test_frontend_react_developer_suffix_variant(self) -> None:
        family, level, _ = normalize_title("Junior Frontend React Developer")
        self.assertEqual(family, "web_frontend")
        self.assertEqual(level, "junior")

    def test_fullstack_engineer_senior(self) -> None:
        family, level, _ = normalize_title("Senior Fullstack Engineer")
        self.assertEqual(family, "web_frontend")
        self.assertEqual(level, "senior")

    def test_web_frontend_negative_backend_title(self) -> None:
        family, _, _ = normalize_title("Backend Engineer")
        self.assertNotEqual(family, "web_frontend")


class TestBackendFamily(unittest.TestCase):
    def test_backend_engineer_basic(self) -> None:
        family, level, rule = normalize_title("Backend Engineer")
        self.assertEqual(family, "backend")
        self.assertEqual(level, "unspecified")
        self.assertTrue(rule.startswith("backend#"))

    def test_senior_backend_engineer(self) -> None:
        family, level, _ = normalize_title("Senior Backend Engineer")
        self.assertEqual(family, "backend")
        self.assertEqual(level, "senior")

    def test_backend_reversed_word_order_with_comma(self) -> None:
        family, level, _ = normalize_title("Senior Software Engineer, Backend")
        self.assertEqual(family, "backend")
        self.assertEqual(level, "senior")

    def test_backend_engineer_intern_level(self) -> None:
        family, level, _ = normalize_title("Backend Engineer Intern")
        self.assertEqual(family, "backend")
        self.assertEqual(level, "intern")

    def test_staff_backend_engineer_level(self) -> None:
        family, level, _ = normalize_title("Staff Backend Engineer")
        self.assertEqual(family, "backend")
        self.assertEqual(level, "staff")

    def test_backend_negative_frontend_title(self) -> None:
        family, _, _ = normalize_title("Frontend Engineer")
        self.assertNotEqual(family, "backend")


class TestDevopsPlatformFamily(unittest.TestCase):
    def test_devops_engineer_basic(self) -> None:
        family, level, rule = normalize_title("Lead DevOps Engineer")
        self.assertEqual(family, "devops_platform")
        self.assertEqual(level, "senior")
        self.assertTrue(rule.startswith("devops_platform#"))

    def test_systems_engineer_variant(self) -> None:
        family, level, _ = normalize_title("Systems Engineer - Cloudflare Workers")
        self.assertEqual(family, "devops_platform")
        self.assertEqual(level, "unspecified")

    def test_systems_architect_senior(self) -> None:
        family, level, _ = normalize_title("Senior Systems Architect")
        self.assertEqual(family, "devops_platform")
        self.assertEqual(level, "senior")

    def test_platform_engineer_staff(self) -> None:
        family, level, _ = normalize_title("Staff Platform Engineer")
        self.assertEqual(family, "devops_platform")
        self.assertEqual(level, "staff")

    def test_devops_negative_cloud_security_assessment(self) -> None:
        family, _, _ = normalize_title("Cloud Security Assessment")
        self.assertNotEqual(family, "devops_platform")


class TestProductFamily(unittest.TestCase):
    def test_product_manager_basic(self) -> None:
        family, level, rule = normalize_title("Senior Product Manager")
        self.assertEqual(family, "product")
        self.assertEqual(level, "senior")
        self.assertTrue(rule.startswith("product#"))

    def test_product_owner_variant(self) -> None:
        family, _, _ = normalize_title("Product Owner - Payments")
        self.assertEqual(family, "product")

    def test_product_vs_program_manager_no_collision(self) -> None:
        product_family, _, _ = normalize_title("Product Manager")
        program_family, _, _ = normalize_title("Program Manager")
        self.assertEqual(product_family, "product")
        self.assertEqual(program_family, "project_program_management")
        self.assertNotEqual(product_family, program_family)


class TestProjectProgramManagementFamily(unittest.TestCase):
    def test_program_manager_basic(self) -> None:
        family, level, rule = normalize_title("Senior Localization Program Manager")
        self.assertEqual(family, "project_program_management")
        self.assertEqual(level, "senior")
        self.assertTrue(rule.startswith("project_program_management#"))

    def test_program_coordinator_variant(self) -> None:
        family, level, _ = normalize_title("Youth Skills Program Coordinator")
        self.assertEqual(family, "project_program_management")
        self.assertEqual(level, "unspecified")

    def test_program_management_negative_product_title(self) -> None:
        family, _, _ = normalize_title("Product Manager")
        self.assertNotEqual(family, "project_program_management")


class TestOtherFallback(unittest.TestCase):
    def test_regional_partnerships_contractor(self) -> None:
        family, level, rule = normalize_title("Regional Partnerships Contractor")
        self.assertEqual(family, "other")
        self.assertEqual(level, "unspecified")
        self.assertEqual(rule, "other#no_match")

    def test_compliance_monitoring_consultant(self) -> None:
        family, _, _ = normalize_title("Compliance Monitoring Consultant")
        self.assertEqual(family, "other")

    def test_empty_title_resolves_other(self) -> None:
        family, level, rule = normalize_title("")
        self.assertEqual(family, "other")
        self.assertEqual(level, "unspecified")
        self.assertEqual(rule, "other#no_match")


class TestLevelDetection(unittest.TestCase):
    def test_level_mid(self) -> None:
        _, level, _ = normalize_title("Mid-Level Data Engineer")
        self.assertEqual(level, "mid")

    def test_level_principal(self) -> None:
        _, level, _ = normalize_title("Principal Backend Architect")
        self.assertEqual(level, "principal")

    def test_level_senior_abbreviation(self) -> None:
        _, level, _ = normalize_title("Sr Data Engineer")
        self.assertEqual(level, "senior")

    def test_level_unspecified_default(self) -> None:
        _, level, _ = normalize_title("Data Engineer")
        self.assertEqual(level, "unspecified")


class TestPurityAndDeterminism(unittest.TestCase):
    def test_case_insensitivity(self) -> None:
        family, _, _ = normalize_title("DATA ENGINEER")
        self.assertEqual(family, "data_engineering")

    def test_determinism_same_input_same_output(self) -> None:
        first = normalize_title("Senior Data Engineer, Platform (Remote — EU)")
        second = normalize_title("Senior Data Engineer, Platform (Remote — EU)")
        self.assertEqual(first, second)

    def test_every_result_family_is_a_known_family(self) -> None:
        titles = [
            "Data Engineer", "Customer Engineer", "ML Engineer", "Sales Engineer",
            "Data Scientist", "Data Migration Specialist", "Data Analyst",
            "Mathematics Tutor", "Junior Frontend Developer", "Backend Engineer",
            "Lead DevOps Engineer", "Senior Product Manager", "Program Manager",
            "Regional Partnerships Contractor",
        ]
        for title in titles:
            family, _, _ = normalize_title(title)
            self.assertIn(family, _KNOWN_FAMILIES, f"unknown family for {title!r}: {family!r}")


if __name__ == "__main__":
    unittest.main()
