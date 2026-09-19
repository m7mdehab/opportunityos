"""Regression tests for Founder-locked CV portfolio selection."""
import unittest

from matching.cv_selector import portfolio_hashes, select_cv_for_opportunity
from opportunity.models import Opportunity, Track


def opp(title: str, description: str = "", skills: tuple[str, ...] = ()) -> Opportunity:
    return Opportunity(
        id="opp-test",
        track=Track.EMPLOYMENT,
        source="fixture",
        source_url="https://example.test/job",
        source_id="job-1",
        organization="Example",
        title=title,
        description=description or title,
        skills=skills,
    )


class FixedCVSelectorTests(unittest.TestCase):
    def test_data_engineer(self) -> None:
        selected = select_cv_for_opportunity(
            opp("Data Engineer", "Build ETL data pipelines and data integration on Databricks.", ("SQL", "Databricks"))
        )
        self.assertEqual(selected.selected.variant, "data_engineer")

    def test_data_scientist(self) -> None:
        selected = select_cv_for_opportunity(
            opp("Data Scientist", "Own forecasting, statistical modeling, experimentation and model calibration.", ("Python", "scikit-learn"))
        )
        self.assertEqual(selected.selected.variant, "data_scientist")

    def test_data_analyst(self) -> None:
        selected = select_cv_for_opportunity(
            opp("Data Analyst", "Build Power BI dashboards, KPI reporting and Excel analysis.", ("Power BI", "SQL"))
        )
        self.assertEqual(selected.selected.variant, "data_analyst")

    def test_business_analyst(self) -> None:
        selected = select_cv_for_opportunity(
            opp("Business Analyst", "Gather business requirements, coordinate stakeholders and support UAT.", ("Requirements Gathering",))
        )
        self.assertEqual(selected.selected.variant, "business_analyst")

    def test_ai_engineer(self) -> None:
        selected = select_cv_for_opportunity(
            opp("Generative AI Engineer", "Build LLM RAG agents with tool calling and FastAPI.", ("LLM", "RAG"))
        )
        self.assertEqual(selected.selected.variant, "ai_engineer")

    def test_ml_engineer_llm_goes_ai(self) -> None:
        selected = select_cv_for_opportunity(
            opp("Machine Learning Engineer", "Production LLM and RAG agents, embeddings and tool calling.", ("Generative AI",))
        )
        self.assertEqual(selected.selected.variant, "ai_engineer")

    def test_ml_engineer_modeling_goes_data_scientist(self) -> None:
        selected = select_cv_for_opportunity(
            opp("Machine Learning Engineer", "Predictive modeling, experimentation, statistics, calibration.", ("scikit-learn",))
        )
        self.assertEqual(selected.selected.variant, "data_scientist")

    def test_ml_engineer_platform_goes_data_engineer(self) -> None:
        selected = select_cv_for_opportunity(
            opp("Machine Learning Engineer", "Own training pipelines, feature store, Databricks and orchestration.", ("Databricks",))
        )
        self.assertEqual(selected.selected.variant, "data_engineer")

    def test_ambiguous_hybrid_uses_master(self) -> None:
        selected = select_cv_for_opportunity(
            opp("Technology Associate", "Support a cross-functional technical team.")
        )
        self.assertEqual(selected.selected.variant, "master")

    def test_portfolio_has_exactly_six_locked_hashes(self) -> None:
        hashes = portfolio_hashes()
        self.assertEqual(len(hashes), 6)
        self.assertEqual(
            hashes["Mohammed_Ehab_Master_CV_2026.pdf"],
            "4b52a32e58008afd59a93ebdf9edc5b165a624a7e4f2cd13eefadf009a44b7d5",
        )

    def test_non_employment_rejected(self) -> None:
        opportunity = Opportunity(
            id="opp-contract",
            track=Track.CONTRACT,
            source="fixture",
            source_url="https://example.test/contract",
            source_id="contract-1",
            organization="Example",
            title="Data Consultant",
            description="Consulting scope",
        )
        with self.assertRaises(ValueError):
            select_cv_for_opportunity(opportunity)


if __name__ == "__main__":
    unittest.main()
