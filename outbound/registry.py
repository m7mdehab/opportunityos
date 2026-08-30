"""Authoritative Source Action Policy and Adapter Graduation Registries."""
from __future__ import annotations

from .models import AdapterLifecycleState, GraduationRecord, SourceActionPolicy


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


class AdapterRegistry:
    """Authoritative adapter graduation and lifecycle state registry."""

    DEFAULT_GRADUATIONS: dict[str, GraduationRecord] = {
        "greenhouse": GraduationRecord(
            adapter_id="greenhouse",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            source_compatibility=("greenhouse", "boards.greenhouse.io"),
            evidence_hash="grad-ev-greenhouse-001",
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ),
        "lever": GraduationRecord(
            adapter_id="lever",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            source_compatibility=("lever", "jobs.lever.co"),
            evidence_hash="grad-ev-lever-001",
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ),
        "ashby": GraduationRecord(
            adapter_id="ashby",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            source_compatibility=("ashby", "jobs.ashbyhq.com"),
            evidence_hash="grad-ev-ashby-001",
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ),
        "generic_form": GraduationRecord(
            adapter_id="generic_form",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.EXPERIMENTAL,
            source_compatibility=("generic", "web"),
            evidence_hash="grad-ev-generic-001",
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ),
        "procurement_package": GraduationRecord(
            adapter_id="procurement_package",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            source_compatibility=("eu_ted", "ungm", "world_bank"),
            evidence_hash="grad-ev-procurement-001",
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ),
        "freelance_proposal": GraduationRecord(
            adapter_id="freelance_proposal",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            source_compatibility=("freelance", "direct"),
            evidence_hash="grad-ev-freelance-001",
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ),
    }

    def __init__(self, overrides: dict[str, GraduationRecord] | None = None) -> None:
        self._records = dict(self.DEFAULT_GRADUATIONS)
        if overrides:
            self._records.update(overrides)

    def get_graduation_record(self, adapter_id: str) -> GraduationRecord | None:
        return self._records.get(adapter_id)

    def register_graduation(self, record: GraduationRecord) -> None:
        self._records[record.adapter_id] = record

    def enable_submit(self, adapter_id: str) -> None:
        rec = self._records.get(adapter_id)
        if rec is None:
            raise KeyError(f"Adapter '{adapter_id}' not registered")
        updated = GraduationRecord(
            adapter_id=rec.adapter_id,
            version=rec.version,
            lifecycle_state=AdapterLifecycleState.SUBMIT_ENABLED,
            source_compatibility=rec.source_compatibility,
            evidence_hash=rec.evidence_hash,
            verified_at=rec.verified_at,
            submit_enabled_by_founder=True,
        )
        self._records[adapter_id] = updated
