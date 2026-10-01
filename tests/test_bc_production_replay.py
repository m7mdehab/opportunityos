from __future__ import annotations

import sys
import unittest
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from matching.recommendation_engine import RecommendationCandidate, build_behavior_profile, recommend
from matching.recommendation_foundation import (
    classify_application_access,
    classify_founder_geography,
    classify_required_credentials,
    classify_role_relevance,
)
from scripts.replay_bc_production import replay
from scripts.replay_bc_production import replay_candidate_files


class ProductionEvidenceReplayTests(unittest.TestCase):
    def test_frozen_production_replay_is_deterministic_and_deduplicated(self) -> None:
        result = replay()
        self.assertEqual(result["candidate_count"], 30)
        self.assertEqual(result["deduplicated_count"], 30)
        self.assertEqual(result["recommendation_counts"], {
            "for_you": 0,
            "review": 21,
            "excluded": 9,
        })

    def test_known_clearance_false_positive_is_blocked_from_for_you(self) -> None:
        result = replay()
        clearance = next(row for row in result["candidates"] if row["sample_group"] == "known_clearance")
        self.assertEqual(clearance["credential_state"], "review")
        self.assertEqual(clearance["credential_reason"], "required_clearance_unverified")
        self.assertNotEqual(clearance["recommendation"], "for_you")

    def test_company_global_language_does_not_override_job_location(self) -> None:
        result = replay()
        candidates = [row for row in result["candidates"] if row["geography"] == "ineligible"]
        self.assertTrue(candidates)
        self.assertTrue(all(row["recommendation"] != "for_you" for row in candidates))

    def test_clean_egypt_compatible_target_role_remains_recommendable(self) -> None:
        title = "Senior Data Engineer"
        description = "Build data pipelines for a distributed team. Applicants in EMEA, including Egypt, may work fully remotely."
        role = classify_role_relevance(title, description)
        credential_state, credential_reason = classify_required_credentials(description)
        geography, _ = classify_founder_geography(
            title=title,
            description=description,
            location_region="EMEA Remote",
            work_mode="remote",
        )
        access = classify_application_access(
            "greenhouse:example",
            "https://boards.greenhouse.io/example/jobs/123",
            "https://boards.greenhouse.io/example/jobs/123",
        )
        recommendation = recommend(RecommendationCandidate(
            opportunity_id="greenhouse:example:123",
            role_relevance=role.classification,
            geography=geography,
            application_access=access.access,
            application_url=access.application_url,
            decision="uncertain",
            fit_score=None,
            confidence_score=None,
            eligibility_state=credential_state,
            eligibility_reason=credential_reason,
        ), behavior=build_behavior_profile(()))
        self.assertEqual(role.classification, "core")
        self.assertIsNone(credential_state)
        self.assertEqual(geography, "likely_eligible")
        self.assertEqual(access.access, "direct_free")
        self.assertEqual(recommendation.state, "for_you")

    def test_full_hot_protected_target_family_replay_has_no_clean_survivor(self) -> None:
        result = replay(Path("tests/fixtures/bc_production_target_candidates_2026-10-01.json"))
        self.assertEqual(result["candidate_count"], 241)
        self.assertEqual(result["deduplicated_count"], 241)
        self.assertEqual(result["gate_counts"], {
            "role_core_or_adjacent": 208,
            "Egypt_compatible": 3,
            "credential_clean": 175,
            "actionable_access": 218,
            "For_You": 0,
        })
        compatible = [row for row in result["candidates"] if row["geography_compatible"]]
        self.assertEqual({row["title"] for row in compatible}, {
            "AI Engineer Data APIs",
            "Data Analyst Assistant",
            "Software Developer Security Analytics",
        })
        self.assertTrue(all(row["application_access"] == "unknown" for row in compatible))

    def test_combined_live_for_you_and_target_replays_deduplicate_canonical_ids(self) -> None:
        root = Path("tests/fixtures")
        result = replay_candidate_files((
            root / "bc_production_replay_2026-10-01.json",
            root / "bc_production_replay_expanded_2026-10-01.json",
            root / "bc_production_target_candidates_2026-10-01.json",
        ))
        self.assertEqual(result["candidate_count"], result["deduplicated_count"])
        self.assertEqual(result["gate_counts"]["For_You"], 0)

    def test_expanded_geographic_corpus_has_five_candidates_before_founder_state(self) -> None:
        result = replay(Path("tests/fixtures/bc_production_geo_candidates_2026-10-01.json"))
        self.assertEqual(result["candidate_count"], 69)
        self.assertEqual(result["deduplicated_count"], 69)
        self.assertEqual(result["gate_counts"], {
            "role_core_or_adjacent": 47,
            "Egypt_compatible": 22,
            "credential_clean": 69,
            "actionable_access": 55,
            "For_You": 5,
        })
        # This offline public-posting fixture intentionally contains no Founder
        # state. Live feedback/action checks are performed separately.
        self.assertEqual({row["opportunity_id"] for row in result["candidates"]
                          if row["recommendation"] == "for_you"}, {
            "greenhouse:canonical:4810491",
            "greenhouse:canonical:5667860",
            "greenhouse:canonical:5703396",
            "greenhouse:canonical:6394147",
            "greenhouse:canonical:6783943",
        })

    def test_individually_audited_candidates_preserve_founder_actions(self) -> None:
        result = replay(Path("tests/fixtures/bc_clean_candidate_replay_2026-10-01.json"))
        fixture = json.loads(
            Path("tests/fixtures/bc_clean_candidate_replay_2026-10-01.json").read_text(encoding="utf-8")
        )
        self.assertEqual(result["candidate_count"], 6)
        self.assertEqual(result["gate_counts"], {
            "role_core_or_adjacent": 6,
            "Egypt_compatible": 6,
            "credential_clean": 6,
            "actionable_access": 6,
            "For_You": 6,
        })
        self.assertEqual(set(result["for_you_employers"]), {"Canonical", "Vrchat", "LiveKit"})
        self.assertEqual(
            {row["source_id"].split(":", 1)[0] for row in result["candidates"]},
            {"greenhouse", "lever", "hacker_news_who_is_hiring"},
        )
        surviving_ids = {row["opportunity_id"] for row in result["candidates"]}
        excluded_ids = {row["opportunity_id"] for row in fixture["founder_state_exclusions"]}
        self.assertTrue(surviving_ids.isdisjoint(excluded_ids))
        self.assertEqual(
            {row["title"] for row in result["candidates"]},
            {
                "Engineering Manager - Data Platform",
                "Lead Data Governance Engineer",
                "MLOps Field Engineer",
                "Senior Data Scientist",
                "Staff Engineer - Recommendations",
                "Software Engineer, Agents",
            },
        )
        self.assertIn("Public Ashby page", fixture["provenance"]["hacker_news_candidate"])


if __name__ == "__main__":
    unittest.main()
