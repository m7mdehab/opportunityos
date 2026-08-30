"""Source Action Policy Registry."""
from __future__ import annotations

from .models import SourceActionPolicy


class SourceActionRegistry:
    """Authoritative registry mapping sources/platforms to permitted action policies."""

    DEFAULT_POLICIES: dict[str, SourceActionPolicy] = {
        # Employment ATS platforms
        "greenhouse": SourceActionPolicy.BROWSER_FILL_ALLOWED,
        "lever": SourceActionPolicy.BROWSER_FILL_ALLOWED,
        "ashby": SourceActionPolicy.BROWSER_FILL_ALLOWED,
        "greenhouse:cloudflare": SourceActionPolicy.BROWSER_FILL_ALLOWED,
        "lever:shyftlabs": SourceActionPolicy.BROWSER_FILL_ALLOWED,
        # Job boards / aggregation feeds (read only discovery feeds)
        "himalayas": SourceActionPolicy.MANUAL_ONLY,
        "remotive": SourceActionPolicy.MANUAL_ONLY,
        "remote_ok": SourceActionPolicy.MANUAL_ONLY,
        "we_work_remotely": SourceActionPolicy.MANUAL_ONLY,
        # Multilateral procurement platforms (package prep + deep-link only)
        "eu_ted": SourceActionPolicy.MANUAL_ONLY,
        "ungm": SourceActionPolicy.MANUAL_ONLY,
        "world_bank": SourceActionPolicy.MANUAL_ONLY,
    }

    def __init__(self, overrides: dict[str, SourceActionPolicy] | None = None) -> None:
        self._policies = dict(self.DEFAULT_POLICIES)
        if overrides:
            self._policies.update(overrides)

    def get_policy(self, source_id: str) -> SourceActionPolicy:
        """Retrieve action policy for source. Unknown sources default to PROHIBITED."""
        if source_id in self._policies:
            return self._policies[source_id]

        prefix = source_id.split(":")[0] if ":" in source_id else source_id
        if prefix in self._policies:
            return self._policies[prefix]

        return SourceActionPolicy.PROHIBITED

    def set_policy(self, source_id: str, policy: SourceActionPolicy) -> None:
        self._policies[source_id] = policy
