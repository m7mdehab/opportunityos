"""Regression tests for Founder-locked nine-CV portfolio selection."""
import unittest
from pathlib import Path

import yaml

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
            opp(
                "Data Integration Engineer",
                "Build ETL data pipelines, source-to-target mappings and reconciliation on Databricks.",
                ("SQL", "Databricks"),
            )
        )
        self.assertEqual(selected.selected.variant, "data_engineer")

    def test_data_analyst(self) -> None:
        selected = select_cv_for_opportunity(
            opp(
                "BI Developer",
                "Build Power BI dashboards, KPI reporting and Excel analysis.",
                ("Power BI", "SQL"),
            )
        )
        self.assertEqual(selected.selected.variant, "data_analyst")

    def test_data_scientist(self) -> None:
        selected = select_cv_for_opportunity(
            opp(
                "Decision Scientist",
                "Own forecasting, statistical modeling, experimentation and model calibration.",
                ("Python", "scikit-learn"),
            )
        )
        self.assertEqual(selected.selected.variant, "data_scientist")

    def test_machine_learning_engineer_is_dedicated_variant(self) -> None:
        selected = select_cv_for_opportunity(
            opp(
                "Machine Learning Engineer",
                "Train and serve deep-learning computer-vision models with ONNX, MLflow and FastAPI.",
                ("PyTorch", "Docker"),
            )
        )
        self.assertEqual(selected.selected.variant, "ml_engineer")

    def test_ai_engineer(self) -> None:
        selected = select_cv_for_opportunity(
            opp(
                "Generative AI Engineer",
                "Build LLM RAG agents with embeddings, tool calling and FastAPI.",
                ("LLM", "RAG"),
            )
        )
        self.assertEqual(selected.selected.variant, "ai_engineer")

    def test_business_analyst(self) -> None:
        selected = select_cv_for_opportunity(
            opp(
                "Technical Business Analyst",
                "Gather business requirements, coordinate stakeholders and translate requirements into delivery specifications.",
                ("Requirements Gathering",),
            )
        )
        self.assertEqual(selected.selected.variant, "business_analyst")

    def test_solutions_engineer(self) -> None:
        selected = select_cv_for_opportunity(
            opp(
                "AI Solutions Engineer",
                "Lead technical discovery, solution design, API integration and implementation planning.",
                ("FastAPI", "PostgreSQL"),
            )
        )
        self.assertEqual(selected.selected.variant, "solutions_engineer")

    def test_fullstack_product_engineer(self) -> None:
        selected = select_cv_for_opportunity(
            opp(
                "Product Engineer",
                "Build a React and TypeScript frontend with a FastAPI backend, PostgreSQL and Docker.",
                ("React", "TypeScript", "FastAPI"),
            )
        )
        self.assertEqual(selected.selected.variant, "fullstack_product")

    def test_generic_software_engineer_uses_product_cv_when_stack_is_clear(self) -> None:
        selected = select_cv_for_opportunity(
            opp(
                "Software Engineer",
                "Own Next.js React TypeScript frontend, REST APIs, PostgreSQL and Docker deployment.",
                ("Next.js", "React", "TypeScript"),
            )
        )
        self.assertEqual(selected.selected.variant, "fullstack_product")

    def test_ambiguous_hybrid_uses_master(self) -> None:
        selected = select_cv_for_opportunity(
            opp("Technology Associate", "Support a cross-functional technical team.")
        )
        self.assertEqual(selected.selected.variant, "master")

    def test_portfolio_has_exactly_nine_locked_hashes(self) -> None:
        hashes = portfolio_hashes()
        self.assertEqual(len(hashes), 9)
        self.assertEqual(
            hashes["Mohammed_Ehab_Master_Comprehensive_CV_2026.pdf"],
            "f20ceec79d450f66d241640f36fbcbac74ee2d365da7e29e4d11883c352e5407",
        )
        self.assertEqual(
            hashes["Mohammed_Ehab_Machine_Learning_Engineer_CV_2026.pdf"],
            "b705a4cc85ad7aca72de8f2832b250e579bdb5e92a5c0f77b87e6971471058e3",
        )

    def test_committed_catalog_matches_runtime_portfolio_exactly(self) -> None:
        catalog = yaml.safe_load(Path("founder/cv_portfolio.yaml").read_text(encoding="utf-8"))
        rows = catalog["variants"]
        self.assertEqual(catalog["portfolio_version"], "2026-09-21-final-9cv")
        self.assertEqual(len(rows), 9)

        runtime = {
            item.variant: (item.filename, item.object_path, item.sha256)
            for item in __import__("matching.cv_selector", fromlist=["PORTFOLIO"]).PORTFOLIO
        }
        committed = {
            row["variant"]: (row["filename"], row["object_path"], row["sha256"])
            for row in rows
        }
        self.assertEqual(committed, runtime)
        self.assertEqual(
            {row["pages"] for row in rows if row["variant"] != "master"},
            {2},
        )
        self.assertEqual(
            next(row["pages"] for row in rows if row["variant"] == "master"),
            3,
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
