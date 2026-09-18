from pathlib import Path
import unittest

from scripts import validate_cloudflare_deployment as validator


class CloudflareDeploymentValidatorTests(unittest.TestCase):
    def test_repository_package_passes(self):
        root = Path(__file__).parents[1]
        errors = validator.validate_cloudflare_package(root)
        self.assertEqual(errors, [], f"Expected zero errors, got: {errors}")


if __name__ == "__main__":
    unittest.main()