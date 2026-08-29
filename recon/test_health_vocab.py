import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile

import recon.__main__ as recon_main


def make_source(method: str = "POST") -> SimpleNamespace:
    return SimpleNamespace(
        source_id="src:example",
        track="employment",
        url="http://example.com/foo",
        method=method,
        action_classification="create",
        request_body=None,
        parser=lambda payload, fixture: [],
        policy_url="http://policy",
    )


class HealthVocabTest(unittest.TestCase):
    def test_permits_false_raises_systemexit_not_health_status(self) -> None:
        """A non-GET source that fails permits() is a configuration error.

        BRIEF-001 §5.2 closed vocabulary has no policy-block slot (extension
        requires an ADR per §12), so a misconfigured source definition must
        raise rather than emit a mislabeled health status.
        """
        src = make_source(method="POST")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            with (
                patch.object(recon_main, "robots_allow", return_value="allowed"),
                patch.object(recon_main, "permits", return_value=False),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    recon_main.fetch(src, out, {})
        self.assertIn("SOURCE DEFINITION ERROR", str(ctx.exception))
        self.assertNotIn("policy_denied", str(ctx.exception))

    def test_get_source_returns_closed_vocabulary_status(self) -> None:
        """A GET source that reaches HTTP returns an allowed_ok health status."""
        src = make_source(method="GET")
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.status = 200
        mock_response.read.return_value = b"[]"
        mock_response.headers.get_content_charset.return_value = "utf-8"
        src.parser = lambda payload, fixture: []
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            with (
                patch.object(recon_main, "robots_allow", return_value="allowed"),
                patch("urllib.request.urlopen", return_value=mock_response),
            ):
                _records, health = recon_main.fetch(src, out, {})
        valid = {
            "allowed_ok", "disallowed_by_robots", "robots_unreachable",
            "network_error", "parse_error", "parse_empty", "not_found",
        }
        self.assertTrue(
            health.status in valid or health.status.startswith("http_"),
            f"Status {health.status!r} not in closed vocabulary",
        )


if __name__ == "__main__":
    unittest.main()
