"""Fail-closed, value-redacting preflight for the FR-007 cloud runtime contract.

This checks deployment inputs, not provider connectivity, grants, RLS, or a
successful backup restore. Application wiring is deliberately outside W0.3.
"""

import argparse
import os
import re
from urllib.parse import urlsplit


ROLES = ("web", "api", "worker", "scheduler", "backup")

# Required for startup of each role. Optional values are documented in the
# contract; a role must not inherit another role's secret requirements.
REQUIRED = {
    "web": ("NEXT_PUBLIC_DATA_API_URL", "NEXT_PUBLIC_DATA_ANON_KEY"),
    "api": ("CLOUD_DATABASE_URL", "AUTH_JWKS_URL", "AUTH_ISSUER",
            "AUTH_AUDIENCE", "AUTH_SERVICE_KEY", "STORAGE_SERVICE_KEY",
            "STORAGE_PRIVATE_BUCKET"),
    "worker": ("CLOUD_DATABASE_URL", "QUEUE_NAMESPACE",
               "STORAGE_SERVICE_KEY", "STORAGE_PRIVATE_BUCKET"),
    "scheduler": ("CLOUD_DATABASE_URL", "QUEUE_NAMESPACE"),
    "backup": ("CLOUD_DATABASE_URL", "BACKUP_DESTINATION_URL",
               "BACKUP_ACCESS_KEY", "BACKUP_ENCRYPTION_KEY"),
}

URL_SCHEMES = {
    "CLOUD_DATABASE_URL": {"postgresql", "postgresql+psycopg2"},
    "NEXT_PUBLIC_DATA_API_URL": {"https"},
    "AUTH_JWKS_URL": {"https"},
    "BACKUP_DESTINATION_URL": {"https", "s3"},
}
PLACEHOLDER = re.compile(r"(?i)(replace[_ -]?me|placeholder|your[_ -]|<[^>]+>|\$\{|example\.)")


def invalid(name: str, value: str) -> bool:
    """Reject missing/template/obviously malformed input; never return values."""
    if not value or value != value.strip() or PLACEHOLDER.search(value):
        return True
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return True
    if name in URL_SCHEMES:
        try:
            parsed = urlsplit(value)
            return (parsed.scheme not in URL_SCHEMES[name] or not parsed.hostname
                    or bool(parsed.fragment) or bool(parsed.username and
                    name != "CLOUD_DATABASE_URL"))
        except ValueError:
            return True
    return not bool(value.strip())


def validate(role: str, environ: dict[str, str]) -> list[str]:
    return [name for name in REQUIRED[role] if invalid(name, environ.get(name, ""))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate FR-007 cloud config without exposing values")
    parser.add_argument("--role", choices=ROLES, required=True, help="deployment role to preflight")
    args = parser.parse_args(argv)
    failures = validate(args.role, os.environ)
    if failures:
        print("Missing or invalid required variables: " + ", ".join(failures))
        return 1
    print("Cloud configuration valid for role: " + args.role)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
