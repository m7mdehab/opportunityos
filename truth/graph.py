"""Deterministic in-memory graph for truth, capability, and provenance nodes."""

from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType
from typing import TypeAlias

from .models import (
    AssertionType,
    BusinessCapacity,
    CapabilityProfile,
    CareerProfile,
    EvidenceRecord,
)


Profile: TypeAlias = CareerProfile | CapabilityProfile


class TruthGraph:
    """Owns atomic evidence and immutable profiles linked to that evidence.

    Mutation is explicit and transactional: profile validation finishes before any
    graph index is changed. Returned mappings and records are immutable.
    """

    def __init__(self, evidence: Iterable[EvidenceRecord] = ()) -> None:
        self._evidence: dict[str, EvidenceRecord] = {}
        self._profiles: dict[str, Profile] = {}
        self._entities: dict[str, object] = {}
        self._entity_evidence: dict[str, tuple[str, ...]] = {}
        self._evidence_entities: dict[str, list[str]] = {}
        for record in evidence:
            self.add_evidence(record)

    @property
    def evidence_records(self):
        return MappingProxyType(self._evidence)

    @property
    def profiles(self):
        return MappingProxyType(self._profiles)

    def add_evidence(self, record: EvidenceRecord) -> None:
        if record.id in self._evidence or record.id in self._entities:
            raise ValueError(f"duplicate graph node id: {record.id}")
        self._evidence[record.id] = record
        self._evidence_entities.setdefault(record.id, [])

    def add_career_profile(self, profile: CareerProfile) -> None:
        self._add_profile(profile)

    def add_capability_profile(self, profile: CapabilityProfile) -> None:
        self._add_profile(profile)

    def _add_profile(self, profile: Profile) -> None:
        nodes = tuple(self._walk_profile(profile))
        node_ids = [node.id for node in nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("profile contains duplicate entity ids")
        collisions = set(node_ids) & (set(self._entities) | set(self._evidence))
        if collisions:
            raise ValueError(f"duplicate graph node id: {sorted(collisions)[0]}")

        links: dict[str, tuple[str, ...]] = {}
        for node in nodes:
            evidence_ids = self._direct_evidence_ids(node)
            missing = sorted(set(evidence_ids) - set(self._evidence))
            if missing:
                raise ValueError(f"node {node.id} references unknown evidence: {', '.join(missing)}")
            links[node.id] = evidence_ids

        # Commit only after every node and link is valid.
        self._profiles[profile.id] = profile
        for node in nodes:
            self._entities[node.id] = node
            self._entity_evidence[node.id] = links[node.id]
            for ev_id in links[node.id]:
                self._evidence_entities.setdefault(ev_id, []).append(node.id)

    def entities_for_evidence(self, evidence_id: str) -> tuple[object, ...]:
        """Return all entity nodes supported by a given evidence record."""
        if evidence_id not in self._evidence:
            raise KeyError(f"unknown evidence id: {evidence_id}")
        entity_ids = tuple(dict.fromkeys(self._evidence_entities.get(evidence_id, [])))
        return tuple(self._entities[entity_id] for entity_id in entity_ids if entity_id in self._entities)

    def entity_ids_for_evidence(self, evidence_id: str) -> tuple[str, ...]:
        """Return all entity node IDs supported by a given evidence record."""
        if evidence_id not in self._evidence:
            raise KeyError(f"unknown evidence id: {evidence_id}")
        return tuple(dict.fromkeys(self._evidence_entities.get(evidence_id, [])))

    def are_relationally_linked(self, evidence_ids: tuple[str, ...] | list[str] | set[str]) -> bool:
        """Determine whether multiple evidence IDs share a common relational entity node in the graph.

        Cross-evidence relationship laundering is prevented by requiring that any conjunction of
        distinct evidence records must be explicitly grounded in a structured graph entity (such as
        an EmploymentRecord with its sub-achievements, a PortfolioItem, ServiceRecord, etc.).
        Root profile objects (CareerProfile, CapabilityProfile) represent the whole person/business
        and do NOT establish relational link between independent sub-entities.
        """
        unique_ids = tuple(dict.fromkeys(evidence_ids))
        if len(unique_ids) <= 1:
            return True

        target_set = set(unique_ids)
        for entity_id, entity in self._entities.items():
            if isinstance(entity, (CareerProfile, CapabilityProfile)):
                continue

            linked_ev_ids = set(self._entity_evidence.get(entity_id, ()))
            if hasattr(entity, "achievements"):
                for ach in getattr(entity, "achievements", ()):
                    linked_ev_ids.update(self._entity_evidence.get(ach.id, ()))

            if target_set.issubset(linked_ev_ids):
                return True

        return False

    @staticmethod
    def _direct_evidence_ids(node: object) -> tuple[str, ...]:
        value = getattr(node, "evidence_ids", ())
        return tuple(value)

    @staticmethod
    def _walk_profile(profile: Profile):
        yield profile
        if isinstance(profile, CareerProfile):
            for employment in profile.employment:
                yield employment
                yield from employment.achievements
            yield from profile.education
            yield from profile.certifications
            yield from profile.skills
            yield from profile.languages
            yield from profile.work_authorizations
            yield from profile.red_lines
            yield from profile.never_claims
        else:
            yield from profile.services
            yield from profile.portfolio
            if profile.capacity is not None:
                yield profile.capacity
            yield from profile.tools
            yield from profile.red_lines
            yield from profile.never_claims

    def evidence(self, evidence_id: str) -> EvidenceRecord:
        try:
            return self._evidence[evidence_id]
        except KeyError as error:
            raise KeyError(f"unknown evidence id: {evidence_id}") from error

    def entity(self, entity_id: str) -> object:
        try:
            return self._entities[entity_id]
        except KeyError as error:
            raise KeyError(f"unknown entity id: {entity_id}") from error

    def evidence_for(self, entity_id: str, *, recursive: bool = False) -> tuple[EvidenceRecord, ...]:
        """Return direct, or stable recursively collected, provenance records."""
        entity = self.entity(entity_id)
        evidence_ids = list(self._entity_evidence[entity_id])
        if recursive and isinstance(entity, (CareerProfile, CapabilityProfile)):
            for node in self._walk_profile(entity):
                evidence_ids.extend(self._entity_evidence[node.id])
        unique_ids = tuple(dict.fromkeys(evidence_ids))
        return tuple(self._evidence[evidence_id] for evidence_id in unique_ids)

    def provenance(self, entity_id: str) -> tuple[tuple[str, EvidenceRecord], ...]:
        """Return a stable edge list from a profile/entity to its recursive evidence."""
        entity = self.entity(entity_id)
        nodes = (
            tuple(self._walk_profile(entity))
            if isinstance(entity, (CareerProfile, CapabilityProfile))
            else (entity,)
        )
        return tuple(
            (node.id, self._evidence[evidence_id])
            for node in nodes
            for evidence_id in self._entity_evidence[node.id]
        )

    def records_by_assertion(self, assertion_type: AssertionType) -> tuple[EvidenceRecord, ...]:
        return tuple(
            record
            for record in self._evidence.values()
            if record.assertion_type is assertion_type
        )

    def facts(self) -> tuple[EvidenceRecord, ...]:
        fact_types = {AssertionType.DIRECT_FACT, AssertionType.NORMALIZED_FACT}
        return tuple(record for record in self._evidence.values() if record.assertion_type in fact_types)

    def inferences(self) -> tuple[EvidenceRecord, ...]:
        inference_types = {AssertionType.DERIVED_CAPABILITY, AssertionType.USER_ASSERTION}
        return tuple(
            record for record in self._evidence.values() if record.assertion_type in inference_types
        )

    def metric_status_for_evidence(self, evidence_id: str):
        """Find metric statuses of achievements/portfolio items linked to evidence."""
        statuses = []
        for node_id, evidence_ids in self._entity_evidence.items():
            if evidence_id in evidence_ids:
                node = self._entities[node_id]
                status = getattr(node, "metric_verification", None)
                if status is not None:
                    statuses.append(status)
        return tuple(statuses)

    def certification_records(self):
        return tuple(
            certification
            for profile in self._profiles.values()
            if isinstance(profile, CareerProfile)
            for certification in profile.certifications
        )

    def rules(self):
        red_lines = []
        never_claims = []
        for profile in self._profiles.values():
            red_lines.extend(profile.red_lines)
            never_claims.extend(profile.never_claims)
        return tuple(red_lines), tuple(never_claims)

