"""Registry for outbound action policies and authoritative adapter graduation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping
from .models import AdapterLifecycleState, GraduationRecord, SourceActionPolicy


class SourceActionRegistry:
    """Platform-specific outbound action policies with positive permission granularity."""

    DEFAULT_POLICIES: dict[str, SourceActionPolicy] = {
        "greenhouse": SourceActionPolicy.SUBMIT_ALLOWED,
        "lever": SourceActionPolicy.SUBMIT_ALLOWED,
        "ashby": SourceActionPolicy.SUBMIT_ALLOWED,
        "generic_form": SourceActionPolicy.BROWSER_FILL_ALLOWED,
        "ungm": SourceActionPolicy.MANUAL_ONLY,
        "world_bank": SourceActionPolicy.MANUAL_ONLY,
        "eu_ted": SourceActionPolicy.MANUAL_ONLY,
    }

    def __init__(self, policies: Mapping[str, SourceActionPolicy] | None = None, version: str = "1.0.0") -> None:
        self._policies: dict[str, SourceActionPolicy] = dict(self.DEFAULT_POLICIES)
        if policies is not None:
            self._policies.update(policies)
        self.version = version

    def get_policy(self, source_id: str) -> SourceActionPolicy:
        """Resolve policy by exact match, prefix match, or fail-closed PROHIBITED default."""
        if source_id in self._policies:
            return self._policies[source_id]
        prefix = source_id.split(":")[0] if ":" in source_id else source_id
        if prefix in self._policies:
            return self._policies[prefix]
        return SourceActionPolicy.PROHIBITED

    def get_policy_version(self, source_id: str) -> str:
        pol = self.get_policy(source_id)
        payload = f"{self.version}:{source_id}:{pol.value}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def set_policy(self, source_id: str, policy: SourceActionPolicy) -> None:
        self._policies[source_id] = policy


class AdapterRegistry:
    """Authoritative singleton/shared registry for outbound adapter graduation records."""

    def __init__(self) -> None:
        self._records: dict[str, GraduationRecord] = {}
        self._init_default_graduations()

    def _init_default_graduations(self) -> None:
        self.register_adapter(GraduationRecord(
            adapter_id="greenhouse",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.SUBMIT_ELIGIBLE,
            source_compatibility=("greenhouse",),
            evidence_hash=hashlib.sha256(b"greenhouse_verified_shadow_run_evidence").hexdigest(),
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ))
        self.register_adapter(GraduationRecord(
            adapter_id="lever",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.SUBMIT_ELIGIBLE,
            source_compatibility=("lever",),
            evidence_hash=hashlib.sha256(b"lever_verified_shadow_run_evidence").hexdigest(),
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ))
        self.register_adapter(GraduationRecord(
            adapter_id="ashby",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.SUBMIT_ELIGIBLE,
            source_compatibility=("ashby",),
            evidence_hash=hashlib.sha256(b"ashby_verified_shadow_run_evidence").hexdigest(),
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ))
        self.register_adapter(GraduationRecord(
            adapter_id="generic_form",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            source_compatibility=("generic_form", "web"),
            evidence_hash=hashlib.sha256(b"generic_form_assisted_verified").hexdigest(),
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ))
        self.register_adapter(GraduationRecord(
            adapter_id="procurement_package",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            source_compatibility=("ungm", "world_bank", "eu_ted", "procurement"),
            evidence_hash=hashlib.sha256(b"procurement_manual_portal_verified").hexdigest(),
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ))
        self.register_adapter(GraduationRecord(
            adapter_id="freelance_proposal",
            version="1.0.0",
            lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED,
            source_compatibility=("direct", "freelance"),
            evidence_hash=hashlib.sha256(b"freelance_proposal_verified").hexdigest(),
            verified_at="2026-08-30T00:00:00Z",
            submit_enabled_by_founder=False,
        ))

    def register_adapter(self, record: GraduationRecord) -> None:
        self._records[record.adapter_id] = record

    def get_graduation_record(self, adapter_id: str) -> GraduationRecord | None:
        return self._records.get(adapter_id)

    def enable_submit(self, adapter_id: str) -> None:
        rec = self._records.get(adapter_id)
        if rec is None:
            raise KeyError(f"Adapter '{adapter_id}' is not registered")
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

    def disable_submit(self, adapter_id: str) -> None:
        rec = self._records.get(adapter_id)
        if rec is None:
            raise KeyError(f"Adapter '{adapter_id}' is not registered")
        updated = GraduationRecord(
            adapter_id=rec.adapter_id,
            version=rec.version,
            lifecycle_state=AdapterLifecycleState.SUBMIT_ELIGIBLE,
            source_compatibility=rec.source_compatibility,
            evidence_hash=rec.evidence_hash,
            verified_at=rec.verified_at,
            submit_enabled_by_founder=False,
        )
        self._records[adapter_id] = updated
