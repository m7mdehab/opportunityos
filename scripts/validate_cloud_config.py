"""Fail-closed, value-redacting preflight for the FR-007 cloud runtime contract.

This checks deployment inputs, not provider connectivity, grants, RLS, or a
successful backup restore. Application wiring is deliberately outside W0.3.
"""

import argparse
import os
import re
from urllib.parse import urlsplit


ROLES = ("web", "api", "worker", "scheduler", "backup", "migrate", "readiness", "liveness")

# Minimum required variables for startup of each role in FR-007.
# For single-founder cloud operation (ADR-0012), PostgreSQL + injected secrets
# provides autonomous execution without external message broker or JWKS service.
REQUIRED = {
    "web": ("NEXT_PUBLIC_DATA_API_URL", "NEXT_PUBLIC_DATA_ANON_KEY"),
    "api": ("CLOUD_DATABASE_URL", "OPPORTUNITYOS_FOUNDER_PASSWORD", "OPPORTUNITYOS_SESSION_SECRET"),
    "worker": ("CLOUD_DATABASE_URL",),
    "scheduler": ("CLOUD_DATABASE_URL",),
    "backup": ("CLOUD_DATABASE_URL", "BACKUP_DESTINATION_URL",
               "BACKUP_ACCESS_KEY", "BACKUP_ENCRYPTION_KEY"),
    "migrate": ("CLOUD_DATABASE_URL",),
    "readiness": ("CLOUD_DATABASE_URL",),
    "liveness": (),
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
    if role not in REQUIRED:
        return [f"unsupported role: {role}"]
    if role == "api":
        cloud = environ.get("OPPORTUNITYOS_ENVIRONMENT", "").lower() in {"cloud", "prod", "production"} or environ.get("MODE", "").lower() == "cloud"
        auth_name = "OPPORTUNITYOS_FOUNDER_PASSWORD_HASH" if cloud else "OPPORTUNITYOS_FOUNDER_PASSWORD"
        req = ("CLOUD_DATABASE_URL", auth_name, "OPPORTUNITYOS_SESSION_SECRET")
        failures = [name for name in req if invalid(name, environ.get(name, ""))]
        if cloud:
            if environ.get("OPPORTUNITYOS_FOUNDER_PASSWORD"):
                failures.append("OPPORTUNITYOS_FOUNDER_PASSWORD")
            origin = environ.get("OPPORTUNITYOS_PUBLIC_ORIGIN", "")
            try:
                parsed = urlsplit(origin)
                if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
                    failures.append("OPPORTUNITYOS_PUBLIC_ORIGIN")
            except ValueError:
                failures.append("OPPORTUNITYOS_PUBLIC_ORIGIN")
        return failures

    if role in ("worker", "scheduler"):
        req = ("CLOUD_DATABASE_URL",)
        failures = [name for name in req if invalid(name, environ.get(name, ""))]
        for opt in ("QUEUE_NAMESPACE", "STORAGE_SERVICE_KEY", "STORAGE_PRIVATE_BUCKET"):
            if opt in environ and invalid(opt, environ.get(opt, "")):
                failures.append(opt)
        return failures
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
