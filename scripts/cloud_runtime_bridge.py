"""FR-007 role-scoped config adaptation for the current (not future) runtime.

Planning returns only safe current aliases and explicit integration blockers.
No current role is deployment-ready until its blockers are resolved by later
application/container lanes. This module never reads or changes os.environ.
"""

from dataclasses import dataclass
import ipaddress
from typing import Mapping
from urllib.parse import urlsplit

from scripts.validate_cloud_config import REQUIRED, ROLES, invalid


class CompatibilityError(ValueError):
    """Names only: safe to display without disclosing supplied values."""


@dataclass(frozen=True)
class BridgePlan:
    role: str
    aliases: dict[str, str]
    blockers: tuple[str, ...]


# These are requirements, not automatic aliases. They must be implemented in
# their owning lanes before the indicated role may be called cloud-ready.
BLOCKERS = {
    "web": ("NEXT_PUBLIC_DATA_API_URL", "NEXT_PUBLIC_DATA_ANON_KEY",
            "OPPORTUNITYOS_API_PORT", "NEXT_PUBLIC_USE_MOCK_API"),
    "api": ("AUTH_JWKS_URL", "AUTH_ISSUER", "AUTH_AUDIENCE",
            "AUTH_SERVICE_KEY", "STORAGE_SERVICE_KEY", "STORAGE_PRIVATE_BUCKET",
            "OPPORTUNITYOS_FOUNDER_PASSWORD", "OPPORTUNITYOS_SESSION_SECRET",
            "OPPORTUNITYOS_TRUTH_PACK_PATH"),
    "worker": ("QUEUE_NAMESPACE", "STORAGE_SERVICE_KEY",
               "STORAGE_PRIVATE_BUCKET", "OPPORTUNITYOS_TRUTH_PACK_PATH"),
    "scheduler": ("QUEUE_NAMESPACE", "SCHEDULER_DISPATCH_TOKEN"),
    "backup": ("BACKUP_DESTINATION_URL", "BACKUP_ACCESS_KEY",
               "BACKUP_ENCRYPTION_KEY"),
}


def plan_runtime_environment(role: str, source: Mapping[str, str]) -> BridgePlan:
    """Validate W0 inputs and return safe aliases, never an implicit fallback.

    ``source`` is an explicit mapping, not the process environment. Optional
    variables with no consumer remain named blockers when required for cloud
    correctness; they are not copied to the child process.
    """
    if role not in ROLES:
        raise CompatibilityError("Unsupported role; expected web, api, worker, scheduler, or backup")
    missing = [name for name in REQUIRED[role] if invalid(name, source.get(name, ""))]
    if missing:
        raise CompatibilityError("Missing or invalid required variables: " + ", ".join(missing))

    aliases: dict[str, str] = {}
    if role != "web":
        cloud = source["CLOUD_DATABASE_URL"]
        # The current SQLAlchemy engine accepts these dialects. Never route
        # SQLite or a local host/file through a cloud production role.
        try:
            parsed = urlsplit(cloud)
            host = parsed.hostname
            local = host is None or host.lower() in {"localhost", "host.docker.internal"} or host.lower().endswith(".localhost")
            if host:
                try:
                    local = local or ipaddress.ip_address(host).is_loopback
                except ValueError:
                    pass
        except ValueError:
            local = True
        if local:
            raise CompatibilityError("Invalid cloud database endpoint: CLOUD_DATABASE_URL")
        legacy = source.get("OPPORTUNITYOS_DB_URL")
        if legacy is not None and legacy != cloud:
            raise CompatibilityError("Conflicting variables: CLOUD_DATABASE_URL, OPPORTUNITYOS_DB_URL")
        aliases["OPPORTUNITYOS_DB_URL"] = cloud

    # Fail on known production mock/local switches, even if the role's own
    # code currently ignores them. Do not propagate any unknown input keys.
    if source.get("NEXT_PUBLIC_USE_MOCK_API") not in (None, "", "0"):
        raise CompatibilityError("Forbidden production setting: NEXT_PUBLIC_USE_MOCK_API")
    if source.get("OPPORTUNITYOS_TRUTH_PACK_PATH"):
        raise CompatibilityError("Forbidden local path: OPPORTUNITYOS_TRUTH_PACK_PATH")
    if source.get("OPPORTUNITYOS_FOUNDER_PASSWORD") or source.get("OPPORTUNITYOS_SESSION_SECRET"):
        raise CompatibilityError(
            "Unsupported local auth variables: OPPORTUNITYOS_FOUNDER_PASSWORD, OPPORTUNITYOS_SESSION_SECRET"
        )
    return BridgePlan(role, aliases, BLOCKERS[role])


def build_runtime_environment(role: str, source: Mapping[str, str]) -> dict[str, str]:
    """Only produce a launchable env once all current-runtime blockers clear."""
    plan = plan_runtime_environment(role, source)
    if plan.blockers:
        raise CompatibilityError("Unwired cloud runtime dependencies: " + ", ".join(plan.blockers))
    return dict(plan.aliases)
