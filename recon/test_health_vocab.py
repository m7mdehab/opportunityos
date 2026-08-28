import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import tempfile

import recon.__main__ as recon_main


def make_source():
    return SimpleNamespace(
        source_id="src:example",
        track="employment",
        url="http://example.com/foo",
        method="POST",
        action_classification="create",
        request_body=None,
        parser=lambda payload, fixture: [],
        policy_url="http://policy",
    )


class HealthVocabTest(unittest.TestCase):
    def test_permits_false_returns_disallowed_by_robots(self):
        src = make_source()
        # robots_allow returns allowed so fetch reaches permits() check
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            with patch.object(recon_main, "robots_allow", return_value="allowed"), patch.object(recon_main, "permits", return_value=False):
                records, health = recon_main.fetch(src, out, {})
        # Ensure old incorrect vocabulary is not used
        self.assertNotEqual(health.status, "policy_denied")
        # Ensure closed vocabulary term is used instead
        self.assertEqual(health.status, "disallowed_by_robots")


if __name__ == "__main__":
    unittest.main()
