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


# Minimum default required variables for each role when unconfigured.
# For single-founder FR-007 operation (ADR-0012), PostgreSQL + injected secrets
# enables autonomous operation without external brokers or JWKS services.
BLOCKERS = {
    "web": ("NEXT_PUBLIC_DATA_API_URL", "NEXT_PUBLIC_DATA_ANON_KEY"),
    "api": ("OPPORTUNITYOS_FOUNDER_PASSWORD", "OPPORTUNITYOS_SESSION_SECRET"),
    "worker": ("OPPORTUNITYOS_TRUTH_PACK_URI",),
    "scheduler": (),
    "backup": ("BACKUP_DESTINATION_URL", "BACKUP_ACCESS_KEY",
               "BACKUP_ENCRYPTION_KEY"),
    "migrate": (),
    "readiness": (),
    "liveness": (),
}


def _truth_is_cloud(source: Mapping[str, str]) -> bool:
    return source.get("OPPORTUNITYOS_ENVIRONMENT", "").lower() in {"cloud", "prod", "production"} or source.get("MODE", "").lower() == "cloud"


def plan_runtime_environment(role: str, source: Mapping[str, str]) -> BridgePlan:
    """Validate W0 inputs and return safe aliases, never an implicit fallback.

    ``source`` is an explicit mapping, not the process environment. Optional
    variables with no consumer remain named blockers when required for cloud
    correctness; they are not copied to the child process.
    """
    if role not in ROLES:
        raise CompatibilityError("Unsupported role; expected " + ", ".join(ROLES))
    
    from scripts.validate_cloud_config import validate
    missing = validate(role, dict(source))
    if missing:
        raise CompatibilityError("Missing or invalid required variables: " + ", ".join(missing))

    aliases: dict[str, str] = {}
    if role not in ("web", "liveness"):
        cloud = source.get("CLOUD_DATABASE_URL") or source.get("OPPORTUNITYOS_DB_URL")
        if not cloud:
            raise CompatibilityError("Missing or invalid required variables: CLOUD_DATABASE_URL")
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
        is_cloud_mode = (
            source.get("OPPORTUNITYOS_ENVIRONMENT", "").lower() in {"production", "prod", "cloud"}
            or source.get("MODE", "").lower() == "cloud"
            or "QUEUE_NAMESPACE" in source
            or "AUTH_JWKS_URL" in source
        )
        if local and is_cloud_mode:
            raise CompatibilityError("Invalid cloud database endpoint: CLOUD_DATABASE_URL")
        legacy = source.get("OPPORTUNITYOS_DB_URL")
        cloud_raw = source.get("CLOUD_DATABASE_URL")
        if legacy is not None and cloud_raw is not None and legacy != cloud_raw:
            raise CompatibilityError("Conflicting variables: CLOUD_DATABASE_URL, OPPORTUNITYOS_DB_URL")
        aliases["OPPORTUNITYOS_DB_URL"] = cloud

    # Fail on known production mock/local switches, even if the role's own
    # code currently ignores them. Do not propagate any unknown input keys.
    if source.get("NEXT_PUBLIC_USE_MOCK_API") not in (None, "", "0"):
        raise CompatibilityError("Forbidden production setting: NEXT_PUBLIC_USE_MOCK_API")
    
    truth_path = source.get("OPPORTUNITYOS_TRUTH_PACK_PATH") or source.get("OPPORTUNITYOS_TRUTH_PACK_URI")
    truth_hash = source.get("OPPORTUNITYOS_TRUTH_PACK_HASH") or source.get("OPPORTUNITYOS_TRUTH_PACK_SHA256")
    truth_auth = source.get("OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN")
    truth_api_key = source.get("OPPORTUNITYOS_TRUTH_PACK_API_KEY")
    truth_is_supabase = False

    if truth_path:
        truth_lower = truth_path.lower()
        if (
            truth_path.startswith("private/")
            or "c:\\" in truth_lower
            or "/users/" in truth_lower
            or invalid("OPPORTUNITYOS_TRUTH_PACK_PATH", truth_path)
        ):
            raise CompatibilityError("Forbidden local path: OPPORTUNITYOS_TRUTH_PACK_PATH")

        try:
            truth_uri = urlsplit(truth_path)
        except ValueError as exc:
            raise CompatibilityError("Invalid Truth Pack URI") from exc

        if role in ("api", "worker"):
            if _truth_is_cloud(source):
                host = truth_uri.hostname
                local = truth_uri.scheme != "https" or host is None
                if host:
                    lowered = host.lower()
                    local = local or lowered in {"localhost", "host.docker.internal"} or lowered.endswith(".localhost")
                    try:
                        local = local or ipaddress.ip_address(host).is_loopback
                    except ValueError:
                        pass
                if local:
                    raise CompatibilityError("Invalid cloud Truth Pack endpoint")
                if truth_uri.username or truth_uri.password or truth_uri.query or truth_uri.fragment:
                    raise CompatibilityError("Credential-bearing Truth Pack URI is forbidden")
                if "/object/public/" in truth_uri.path.lower():
                    raise CompatibilityError("Public Truth Pack object endpoint is forbidden")
                truth_is_supabase = (
                    (host or "").lower().endswith("supabase.co")
                    or "/storage/v1/object/" in truth_uri.path.lower()
                )
                aliases["OPPORTUNITYOS_TRUTH_PACK_URI"] = truth_path
                if truth_hash:
                    aliases["OPPORTUNITYOS_TRUTH_PACK_HASH"] = truth_hash
            else:
                # Preserve the existing local/non-cloud compatibility bridge.
                aliases["OPPORTUNITYOS_TRUTH_PACK_PATH"] = truth_path
                aliases["OPPORTUNITYOS_TRUTH_PACK_URI"] = truth_path
                if truth_hash:
                    aliases["OPPORTUNITYOS_TRUTH_PACK_HASH"] = truth_hash
    if truth_auth and invalid("OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN", truth_auth):
        raise CompatibilityError("Invalid or placeholder credential: OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN")
    if truth_api_key and invalid("OPPORTUNITYOS_TRUTH_PACK_API_KEY", truth_api_key):
        raise CompatibilityError("Invalid or placeholder credential: OPPORTUNITYOS_TRUTH_PACK_API_KEY")
    if role in ("api", "worker") and _truth_is_cloud(source):
        if truth_auth:
            aliases["OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN"] = truth_auth
        if truth_api_key:
            aliases["OPPORTUNITYOS_TRUTH_PACK_API_KEY"] = truth_api_key

    # Single-founder authentication: safe secrets propagated when valid
    founder_pw = source.get("OPPORTUNITYOS_FOUNDER_PASSWORD")
    founder_hash = source.get("OPPORTUNITYOS_FOUNDER_PASSWORD_HASH")
    if founder_pw:
        if invalid("OPPORTUNITYOS_FOUNDER_PASSWORD", founder_pw):
            raise CompatibilityError("Invalid or placeholder credential: OPPORTUNITYOS_FOUNDER_PASSWORD")
        aliases["OPPORTUNITYOS_FOUNDER_PASSWORD"] = founder_pw
    if founder_hash:
        if invalid("OPPORTUNITYOS_FOUNDER_PASSWORD_HASH", founder_hash) or not founder_hash.startswith("scrypt$v1$"):
            raise CompatibilityError("Invalid or malformed credential: OPPORTUNITYOS_FOUNDER_PASSWORD_HASH")
        if role == "api" and _truth_is_cloud(source):
            aliases["OPPORTUNITYOS_FOUNDER_PASSWORD_HASH"] = founder_hash

    session_sec = source.get("OPPORTUNITYOS_SESSION_SECRET")
    if session_sec:
        if invalid("OPPORTUNITYOS_SESSION_SECRET", session_sec):
            raise CompatibilityError("Invalid or placeholder credential: OPPORTUNITYOS_SESSION_SECRET")
        aliases["OPPORTUNITYOS_SESSION_SECRET"] = session_sec

    # Dynamic blocker calculation:
    if role == "web":
        blockers = list(BLOCKERS["web"])
    elif role == "backup":
        blockers = list(BLOCKERS["backup"])
    elif role == "api":
        has_founder = bool(
            ((founder_hash and not invalid("OPPORTUNITYOS_FOUNDER_PASSWORD_HASH", founder_hash)) or
             (not _truth_is_cloud(source) and founder_pw and not invalid("OPPORTUNITYOS_FOUNDER_PASSWORD", founder_pw)))
            and session_sec and not invalid("OPPORTUNITYOS_SESSION_SECRET", session_sec)
        )
        if _truth_is_cloud(source):
            blockers = []
            if not founder_hash: blockers.append("OPPORTUNITYOS_FOUNDER_PASSWORD_HASH")
            if source.get("OPPORTUNITYOS_FOUNDER_PASSWORD"): blockers.append("OPPORTUNITYOS_FOUNDER_PASSWORD")
            if not source.get("OPPORTUNITYOS_PUBLIC_ORIGIN"): blockers.append("OPPORTUNITYOS_PUBLIC_ORIGIN")
        elif not has_founder:
            blockers = list(BLOCKERS["api"])
        else:
            blockers = []
    elif role == "worker":
        blockers = []
        if not truth_path or not truth_path.startswith("https://"):
            blockers.append("OPPORTUNITYOS_TRUTH_PACK_URI")
        elif not truth_hash:
            blockers.append("OPPORTUNITYOS_TRUTH_PACK_HASH")
        if _truth_is_cloud(source) and not truth_auth:
            blockers.append("OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN")
        if _truth_is_cloud(source) and truth_is_supabase and not truth_api_key:
            blockers.append("OPPORTUNITYOS_TRUTH_PACK_API_KEY")

    if role == "api" and _truth_is_cloud(source):
        if not truth_path or not truth_path.startswith("https://"):
            blockers.append("OPPORTUNITYOS_TRUTH_PACK_URI")
        if not truth_hash:
            blockers.append("OPPORTUNITYOS_TRUTH_PACK_HASH")
        if not truth_auth:
            blockers.append("OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN")
        if truth_is_supabase and not truth_api_key:
            blockers.append("OPPORTUNITYOS_TRUTH_PACK_API_KEY")

    elif role in ("scheduler", "migrate", "readiness", "liveness"):
        # Autonomous against PostgreSQL! Zero external broker or queue blockers.
        blockers = []
    elif role in ("web", "backup"):
        # Preserve the role's static blockers calculated above.
        pass

    return BridgePlan(role, aliases, tuple(blockers))


def build_runtime_environment(role: str, source: Mapping[str, str]) -> dict[str, str]:
    """Only produce a launchable env once all current-runtime blockers clear."""
    plan = plan_runtime_environment(role, source)
    if plan.blockers:
        raise CompatibilityError("Unwired cloud runtime dependencies: " + ", ".join(plan.blockers))
    return dict(plan.aliases)
