import json
import unittest
from dataclasses import replace
from pathlib import Path

from matching.candidate_admission import admit_new_ats_candidates
from opportunity.adapters.himalayas import HimalayasAdapter


class CandidateAdmissionTests(unittest.TestCase):
    def setUp(self):
        fixture = Path(__file__).resolve().parents[1] / "opportunity" / "fixtures" / "himalayas.json"
        source = json.loads(fixture.read_text(encoding="utf-8"))["jobs"][0]
        self.opportunity = HimalayasAdapter().parse_payload(
            json.dumps({"jobs": [source]}), raw_pointer="test", fetched_at="2026-09-28"
        ).opportunities[0]

    def test_broad_ats_gate_excludes_only_clearly_non_target_roles(self):
        core = replace(self.opportunity, title="Senior Data Engineer")
        unknown = replace(self.opportunity, title="Special Projects Specialist")
        admitted, excluded = admit_new_ats_candidates(
            "greenhouse:example", (self.opportunity, core, unknown)
        )
        self.assertEqual(1, excluded)
        self.assertEqual((core, unknown), admitted)

    def test_non_ats_lanes_keep_existing_admission_behavior(self):
        admitted, excluded = admit_new_ats_candidates("himalayas", (self.opportunity,))
        self.assertEqual((self.opportunity,), admitted)
        self.assertEqual(0, excluded)


if __name__ == "__main__":
    unittest.main()
