from __future__ import annotations

import unittest

from matching.recommendation_foundation import (
    classify_application_access,
    classify_founder_geography,
    classify_required_credentials,
    classify_role_relevance,
)
from scripts.bc_candidate_canary import NEW_CANDIDATE_IDS, _canonical_candidates


class BCCandidateCanaryTests(unittest.TestCase):
    def test_canonical_pipeline_reproduces_only_the_three_audited_new_candidates(self) -> None:
        batch, candidates = _canonical_candidates()

        self.assertEqual(set(candidates), set(NEW_CANDIDATE_IDS))
        self.assertEqual(len(batch.opportunities), 3)
        self.assertEqual(batch.total_unique_opportunities, 3)
        self.assertEqual(
            {candidate.organization for candidate in candidates.values()},
            {"Vrchat", "LiveKit"},
        )

        for opportunity_id, candidate in candidates.items():
            with self.subTest(opportunity_id=opportunity_id):
                role = classify_role_relevance(candidate.title, candidate.description)
                geography, _ = classify_founder_geography(
                    title=candidate.title,
                    description=candidate.description,
                    location_country=candidate.location_country,
                    location_city=candidate.location_city,
                    location_region=candidate.location_region,
                    work_mode=candidate.work_mode.value,
                    remote_scope=candidate.remote_scope.value,
                    remote_scope_regions=candidate.remote_scope_regions,
                )
                credential_state, _ = classify_required_credentials(
                    f"{candidate.title}\n{candidate.description}"
                )
                access = classify_application_access(
                    candidate.source,
                    candidate.source_url,
                    candidate.canonical_outbound_url or candidate.source_url,
                )
                self.assertIn(role.classification, {"core", "adjacent"})
                self.assertIn(geography, {"eligible", "likely_eligible"})
                self.assertIsNone(credential_state)
                self.assertIn(access.access, {"direct_free", "free_intermediary"})
                self.assertTrue(access.application_url)


if __name__ == "__main__":
    unittest.main()
