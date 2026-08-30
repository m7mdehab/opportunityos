"""Authoritative Source Registry Policy Engine for OpportunityOS.

Loads docs/SOURCE_REGISTRY.yaml and enforces strict pre-flight authorization
binding SOURCE_ID + METHOD + EXACT ALLOWED HOST + EXACT BOARD/SITE TOKEN + ALLOWED PATH.
Refuses unregistered, disabled, mutating, or unallowlisted endpoints before transport.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Default path to SOURCE_REGISTRY.yaml relative to repository root
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "docs" / "SOURCE_REGISTRY.yaml"


@dataclass(frozen=True, slots=True)
class EndpointRule:
    allowed_hosts: frozenset[str]
    allowed_path_prefix: str
    allowed_methods: frozenset[str]
    require_https: bool = True


# Exact endpoint templates binding source to allowed host, path, and method
SOURCE_ENDPOINT_RULES: dict[str, EndpointRule] = {
    "himalayas": EndpointRule(
        allowed_hosts=frozenset({"himalayas.app"}),
        allowed_path_prefix="/jobs/api",
        allowed_methods=frozenset({"GET"}),
        require_https=True,
    ),
    "remotive": EndpointRule(
        allowed_hosts=frozenset({"remotive.com", "remotive.io"}),
        allowed_path_prefix="/api/remote-jobs",
        allowed_methods=frozenset({"GET"}),
        require_https=True,
    ),
    "remote_ok": EndpointRule(
        allowed_hosts=frozenset({"remoteok.com", "remoteok.io"}),
        allowed_path_prefix="/api",
        allowed_methods=frozenset({"GET"}),
        require_https=True,
    ),
    "we_work_remotely": EndpointRule(
        allowed_hosts=frozenset({"weworkremotely.com"}),
        allowed_path_prefix="/remote-jobs.rss",
        allowed_methods=frozenset({"GET"}),
        require_https=True,
    ),
    "ungm": EndpointRule(
        allowed_hosts=frozenset({"www.ungm.org", "ungm.org"}),
        allowed_path_prefix="/Public/Notice",
        allowed_methods=frozenset({"GET"}),
        require_https=True,
    ),
    "world_bank": EndpointRule(
        allowed_hosts=frozenset({"projects.worldbank.org", "www.worldbank.org"}),
        allowed_path_prefix="/",
        allowed_methods=frozenset({"GET"}),
        require_https=True,
    ),
    "eu_ted": EndpointRule(
        allowed_hosts=frozenset({"api.ted.europa.eu"}),
        allowed_path_prefix="/v3/notices/search",
        allowed_methods=frozenset({"POST"}),
        require_https=True,
    ),
}


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    source_id: str
    name: str
    category: str
    read_allowed: bool
    allowed_methods: tuple[str, ...]
    policy_status: str
    observed_status: str
    policy_evidence: tuple[str, ...]
    request_metadata: str = ""


class SourceRegistry:
    """Authoritative loader and pre-flight policy validator for data sources."""

    def __init__(self, registry_path: Path | str | None = None) -> None:
        self.path = Path(registry_path or DEFAULT_REGISTRY_PATH)
        self._sources: dict[str, SourcePolicy] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        content = self.path.read_text(encoding="utf-8")
        self._sources = self._parse_yaml_sources(content)

    def _parse_yaml_sources(self, content: str) -> dict[str, SourcePolicy]:
        """Simple, robust YAML parser for SOURCE_REGISTRY.yaml without external dependencies."""
        sources: dict[str, SourcePolicy] = {}
        chunks = re.split(r"(?m)^\s*-\s+source_id:\s*", content)
        for chunk in chunks[1:]:
            lines = chunk.strip().splitlines()
            if not lines:
                continue
            first_line = lines[0].strip().strip('"\'')
            source_id = first_line

            name_m = re.search(r'(?m)^\s*name:\s*["\']?([^"\']+)["\']?', chunk)
            category_m = re.search(r'(?m)^\s*category:\s*(\w+)', chunk)
            read_m = re.search(r'(?m)^\s*read:\s*(\w+)', chunk)
            status_m = re.search(r'(?m)^\s*status:\s*(\w+)', chunk)
            policy_status_m = re.search(r'(?m)^\s*policy_status:\s*(\w+)', chunk)
            req_meta_m = re.search(r'(?m)^\s*request_metadata:\s*["\']?([^"\']*)["\']?', chunk)
            
            read_allowed = bool(read_m and read_m.group(1).lower() == "allowed")
            category = category_m.group(1) if category_m else "unknown"
            name = name_m.group(1) if name_m else source_id
            observed_status = status_m.group(1) if status_m else "unknown"
            policy_status = policy_status_m.group(1) if policy_status_m else "unknown"
            req_meta = req_meta_m.group(1) if req_meta_m else ""

            # Method authorization: GET only, except eu_ted which has ADR-0005 POST search
            if source_id == "eu_ted":
                allowed_methods = ("POST",)
            else:
                allowed_methods = ("GET",)

            policy = SourcePolicy(
                source_id=source_id,
                name=name,
                category=category,
                read_allowed=read_allowed,
                allowed_methods=allowed_methods,
                policy_status=policy_status,
                observed_status=observed_status,
                policy_evidence=(),
                request_metadata=req_meta,
            )
            sources[source_id] = policy
        return sources

    def get_policy(self, source_id: str) -> SourcePolicy | None:
        return self._sources.get(source_id)

    def is_source_registered(self, source_id: str) -> bool:
        return source_id in self._sources

    def is_read_allowed(self, source_id: str) -> bool:
        policy = self.get_policy(source_id)
        return bool(policy and policy.read_allowed)

    def validate_preflight(
        self, source_id: str, url: str, method: str = "GET"
    ) -> tuple[bool, str]:
        """Validate request authorization binding SOURCE_ID + METHOD + EXACT HOST + TOKEN + ALLOWED PATH."""
        policy = self.get_policy(source_id)
        if not policy:
            return False, f"Refused: Source '{source_id}' is not registered in docs/SOURCE_REGISTRY.yaml"

        if not policy.read_allowed:
            return False, f"Refused: Source '{source_id}' read automation is disabled by policy (status: {policy.policy_status})"

        method_upper = method.upper()
        if method_upper in {"PUT", "PATCH", "DELETE"}:
            return False, f"Refused: Mutating HTTP method '{method_upper}' is strictly forbidden by Product Constitution"

        if method_upper not in policy.allowed_methods:
            return False, f"Refused: Method '{method_upper}' is forbidden for source '{source_id}' (allowed: {policy.allowed_methods})"

        # Parse URL components
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception:
            return False, f"Refused: Malformed URL '{url}'"

        scheme = parsed.scheme.lower()
        host = parsed.netloc.lower().split(":")[0]  # remove port
        path = parsed.path or "/"

        # Greenhouse dynamic rule: HTTPS + exact host + exact board token prefix
        if source_id.startswith("greenhouse:"):
            if scheme != "https":
                return False, f"Refused: Greenhouse source '{source_id}' requires https scheme, got '{scheme}'"
            if host not in {"boards-api.greenhouse.io", "boards.greenhouse.io"}:
                return False, f"Refused: Host '{host}' is unauthorized for Greenhouse source '{source_id}'"
            board_token = source_id.partition(":")[2].lower()
            expected_prefix = f"/v1/boards/{board_token}"
            if not path.startswith(expected_prefix):
                return False, f"Refused: Path '{path}' is unauthorized for Greenhouse board '{board_token}' (expected prefix: '{expected_prefix}')"
            return True, "Authorized"

        # Lever dynamic rule: HTTPS + exact host + exact site token prefix
        if source_id.startswith("lever:"):
            if scheme != "https":
                return False, f"Refused: Lever source '{source_id}' requires https scheme, got '{scheme}'"
            if host not in {"api.lever.co", "jobs.lever.co"}:
                return False, f"Refused: Host '{host}' is unauthorized for Lever source '{source_id}'"
            site_token = source_id.partition(":")[2].lower()
            expected_prefix = f"/v0/postings/{site_token}"
            if not path.startswith(expected_prefix):
                return False, f"Refused: Path '{path}' is unauthorized for Lever site '{site_token}' (expected prefix: '{expected_prefix}')"
            return True, "Authorized"

        rule = SOURCE_ENDPOINT_RULES.get(source_id)
        if not rule:
            return False, f"Refused: No endpoint rule defined for source '{source_id}'"

        if rule.require_https and scheme != "https":
            return False, f"Refused: Source '{source_id}' requires https scheme, got '{scheme}'"

        if host not in rule.allowed_hosts:
            return False, f"Refused: Host '{host}' is unauthorized for source '{source_id}' (allowed: {sorted(rule.allowed_hosts)})"

        if not path.startswith(rule.allowed_path_prefix) and not (rule.allowed_path_prefix.endswith(".rss") and path.endswith(".rss")):
            return False, f"Refused: Path '{path}' does not match allowed prefix '{rule.allowed_path_prefix}' for source '{source_id}'"

        if method_upper not in rule.allowed_methods:
            return False, f"Refused: Method '{method_upper}' not allowed by endpoint rule for '{source_id}'"

        # Strict ADR-0005 check for TED
        if source_id == "eu_ted":
            if scheme != "https" or host != "api.ted.europa.eu" or path != "/v3/notices/search" or method_upper != "POST":
                return False, f"Refused: EU TED query must strictly be HTTPS POST to https://api.ted.europa.eu/v3/notices/search"

        return True, "Authorized"
