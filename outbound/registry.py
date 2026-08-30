"""Registry for outbound action policies and authoritative adapter graduation."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from .models import AdapterLifecycleState, GraduationRecord, SourceActionPolicy

DEFAULT_GRADUATION_DIR = Path(__file__).parent / "fixtures" / "graduation"


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
    """Authoritative singleton/shared registry for outbound adapter graduation records with dynamic evidence validation."""

    def __init__(self, evidence_dir: Path | None = None) -> None:
        self._records: dict[str, GraduationRecord] = {}
        self.evidence_dir = evidence_dir or DEFAULT_GRADUATION_DIR
        self._init_default_graduations()

    def _compute_evidence_hash(self, adapter_id: str) -> tuple[str, bool]:
        """Load real persisted evidence file and compute SHA-256 digest."""
        evidence_file = self.evidence_dir / f"{adapter_id}_graduation_evidence.json"
        if not evidence_file.exists():
            return "", False
        try:
            content = evidence_file.read_bytes()
            if not content:
                return "", False
            # Validate JSON parseable
            parsed = json.loads(content.decode("utf-8"))
            if not isinstance(parsed, dict) or not parsed:
                return "", False
            digest = hashlib.sha256(content).hexdigest()
            return digest, True
        except Exception:
            return "", False

    def _init_default_graduations(self) -> None:
        # Default production state is ASSISTED_VERIFIED unless concrete persisted evidence exists
        for adapter_id, comp in [
            ("greenhouse", ("greenhouse",)),
            ("lever", ("lever",)),
            ("ashby", ("ashby",)),
            ("generic_form", ("generic_form", "web")),
            ("procurement_package", ("ungm", "world_bank", "eu_ted", "procurement")),
            ("freelance_proposal", ("direct", "freelance")),
        ]:
            ev_hash, ev_valid = self._compute_evidence_hash(adapter_id)
            state = AdapterLifecycleState.SUBMIT_ELIGIBLE if ev_valid else AdapterLifecycleState.ASSISTED_VERIFIED
            self.register_adapter(GraduationRecord(
                adapter_id=adapter_id,
                version="1.0.0",
                lifecycle_state=state,
                source_compatibility=comp,
                evidence_hash=ev_hash,
                verified_at="2026-08-30T00:00:00Z" if ev_valid else "",
                submit_enabled_by_founder=False,
            ))

    def register_adapter(self, record: GraduationRecord) -> None:
        self._records[record.adapter_id] = record

    def get_graduation_record(self, adapter_id: str) -> GraduationRecord | None:
        rec = self._records.get(adapter_id)
        if rec is None:
            return None

        # Dynamic runtime evidence check: if record claims SUBMIT_ELIGIBLE or SUBMIT_ENABLED,
        # re-verify that the backing evidence file exists, is valid, and matches the recorded evidence_hash
        if rec.lifecycle_state in (AdapterLifecycleState.SUBMIT_ELIGIBLE, AdapterLifecycleState.SUBMIT_ENABLED):
            current_hash, valid = self._compute_evidence_hash(adapter_id)
            if not valid or not rec.evidence_hash or current_hash != rec.evidence_hash:
                # Dynamically downgrade to ASSISTED_VERIFIED
                downgraded = GraduationRecord(
                    adapter_id=rec.adapter_id,
                    version=rec.version,
                    lifecycle_state=AdapterLifecycleState.ASSISTED_VERIFIED,
                    source_compatibility=rec.source_compatibility,
                    evidence_hash="",
                    verified_at="",
                    submit_enabled_by_founder=False,
                )
                self._records[adapter_id] = downgraded
                return downgraded

        return rec

    def enable_submit(self, adapter_id: str) -> None:
        rec = self.get_graduation_record(adapter_id)
        if rec is None:
            raise KeyError(f"Adapter '{adapter_id}' is not registered")
        current_hash, valid = self._compute_evidence_hash(adapter_id)
        if rec.lifecycle_state != AdapterLifecycleState.SUBMIT_ELIGIBLE or not valid or not rec.evidence_hash or current_hash != rec.evidence_hash:
            raise ValueError(f"Adapter '{adapter_id}' is not SUBMIT_ELIGIBLE with valid graduation evidence")
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
        rec = self.get_graduation_record(adapter_id)
        if rec is None:
            raise KeyError(f"Adapter '{adapter_id}' is not registered")
        current_hash, valid = self._compute_evidence_hash(adapter_id)
        updated = GraduationRecord(
            adapter_id=rec.adapter_id,
            version=rec.version,
            lifecycle_state=AdapterLifecycleState.SUBMIT_ELIGIBLE if (valid and rec.evidence_hash) else AdapterLifecycleState.ASSISTED_VERIFIED,
            source_compatibility=rec.source_compatibility,
            evidence_hash=rec.evidence_hash if valid else "",
            verified_at=rec.verified_at if valid else "",
            submit_enabled_by_founder=False,
        )
        self._records[adapter_id] = updated
