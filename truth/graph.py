"""Deterministic in-memory graph for truth, capability, and provenance nodes."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
import re
from types import MappingProxyType
from typing import Any, TypeAlias

from .models import (
    Achievement,
    AssertionType,
    AtomicAssertion,
    BusinessCapacity,
    CapabilityProfile,
    CareerProfile,
    CertificationRecord,
    CertificationState,
    EducationRecord,
    EmploymentRecord,
    EvidenceRecord,
    LanguageRecord,
    MetricAssertion,
    MetricVerification,
    Modality,
    Polarity,
    PortfolioItem,
    RelationType,
    ServiceRecord,
    SkillRecord,
    TypedRelation,
    VerificationStatus,
    WorkAuthorization,
)


Profile: TypeAlias = CareerProfile | CapabilityProfile


class TruthGraph:
    """Owns atomic evidence, assertions, typed relations, and immutable profiles.

    Mutation is explicit and transactional: profile validation finishes before any
    graph index is changed. Returned mappings and records are immutable.
    """

    def __init__(
        self,
        evidence: Iterable[EvidenceRecord] = (),
        assertions: Iterable[AtomicAssertion] = (),
        relations: Iterable[TypedRelation] = (),
        metrics: Iterable[MetricAssertion] = (),
    ) -> None:
        self._evidence: dict[str, EvidenceRecord] = {}
        self._assertions: dict[str, AtomicAssertion] = {}
        self._relations: dict[str, TypedRelation] = {}
        self._metrics: dict[str, MetricAssertion] = {}
        self._profiles: dict[str, Profile] = {}
        self._entities: dict[str, object] = {}
        self._entity_evidence: dict[str, tuple[str, ...]] = {}
        self._evidence_entities: dict[str, list[str]] = {}

        for record in evidence:
            self.add_evidence(record)
        for assertion in assertions:
            self.add_assertion(assertion)
        for relation in relations:
            self.add_relation(relation)
        for metric in metrics:
            self.add_metric_assertion(metric)

    @property
    def evidence_records(self):
        return MappingProxyType(self._evidence)

    @property
    def assertions(self):
        return MappingProxyType(self._assertions)

    @property
    def relations(self):
        return MappingProxyType(self._relations)

    @property
    def metrics(self):
        return MappingProxyType(self._metrics)

    @property
    def profiles(self):
        return MappingProxyType(self._profiles)

    def add_evidence(self, record: EvidenceRecord) -> None:
        if record.id in self._evidence or record.id in self._entities:
            raise ValueError(f"duplicate graph node id: {record.id}")
        self._evidence[record.id] = record
        self._evidence_entities.setdefault(record.id, [])

    def add_assertion(self, assertion: AtomicAssertion) -> None:
        if assertion.id in self._assertions:
            raise ValueError(f"duplicate assertion id: {assertion.id}")
        for ev_id in assertion.evidence_ids:
            if ev_id not in self._evidence:
                raise ValueError(f"assertion {assertion.id} references unknown evidence: {ev_id}")
        self._assertions[assertion.id] = assertion

    def add_relation(self, relation: TypedRelation) -> None:
        if relation.id in self._relations:
            raise ValueError(f"duplicate relation id: {relation.id}")
        for ev_id in relation.evidence_ids:
            if ev_id not in self._evidence:
                raise ValueError(f"relation {relation.id} references unknown evidence: {ev_id}")
        self._relations[relation.id] = relation

    def add_metric_assertion(self, metric: MetricAssertion) -> None:
        if metric.id in self._metrics:
            raise ValueError(f"duplicate metric assertion id: {metric.id}")
        for ev_id in metric.evidence_ids:
            if ev_id not in self._evidence:
                raise ValueError(f"metric assertion {metric.id} references unknown evidence: {ev_id}")
        self._metrics[metric.id] = metric

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

        # Auto-project field assertions and typed relations for profile entities
        self._project_profile_assertions(profile)

    def _project_profile_assertions(self, profile: Profile) -> None:
        if isinstance(profile, CareerProfile):
            for emp in profile.employment:
                self._create_field_assertion(emp.id, "employment.organization", emp.organization, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)
                self._create_field_assertion(emp.id, "employment.title", emp.title, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)
                self._create_field_assertion(emp.id, "employment.start_date", emp.start_date, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)
                if emp.end_date:
                    self._create_field_assertion(emp.id, "employment.end_date", emp.end_date, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)
                for idx, resp in enumerate(emp.responsibilities):
                    self._create_field_assertion(f"{emp.id}.resp.{idx}", "employment.responsibility", resp, emp.evidence_ids, effective_from=emp.start_date, effective_to=emp.end_date)

                for ach in emp.achievements:
                    self._create_field_assertion(ach.id, "achievement.statement", ach.statement, ach.evidence_ids)
                    rel_id = f"rel_{emp.id}_{ach.id}"
                    if rel_id not in self._relations:
                        self._relations[rel_id] = TypedRelation(
                            id=rel_id,
                            source_id=emp.id,
                            relation_type=RelationType.ACHIEVED_DURING,
                            target_id=ach.id,
                            evidence_ids=ach.evidence_ids,
                            effective_from=emp.start_date,
                            effective_to=emp.end_date,
                        )
                    # Extract numeric metric assertions from achievement
                    self._extract_metrics_from_text(ach.id, ach.statement, ach.evidence_ids, ach.metric_verification)

            for edu in profile.education:
                self._create_field_assertion(edu.id, "education.institution", edu.institution, edu.evidence_ids, effective_from=edu.start_date, effective_to=edu.end_date)
                self._create_field_assertion(edu.id, "education.qualification", edu.qualification, edu.evidence_ids, effective_from=edu.start_date, effective_to=edu.end_date)

            for cert in profile.certifications:
                modality = Modality.PLANNED if cert.state is CertificationState.PLANNED else Modality.DEFINITE
                self._create_field_assertion(cert.id, "certification.name", cert.name, cert.evidence_ids, modality=modality, effective_from=cert.issued_date, effective_to=cert.expiry_date)
                self._create_field_assertion(cert.id, "certification.state", cert.state.value, cert.evidence_ids, modality=modality, effective_from=cert.issued_date, effective_to=cert.expiry_date)

            for skill in profile.skills:
                self._create_field_assertion(skill.id, "skill.name", skill.name, skill.evidence_ids)
                if skill.proficiency:
                    self._create_field_assertion(skill.id, "skill.proficiency", skill.proficiency, skill.evidence_ids)

            for lang in profile.languages:
                self._create_field_assertion(lang.id, "language.language", lang.language, lang.evidence_ids)
                self._create_field_assertion(lang.id, "language.proficiency", lang.proficiency, lang.evidence_ids)

            for auth in profile.work_authorizations:
                self._create_field_assertion(auth.id, "work_authorization.jurisdiction", auth.jurisdiction, auth.evidence_ids, effective_to=auth.expiry_date)
                self._create_field_assertion(auth.id, "work_authorization.status", auth.status, auth.evidence_ids, effective_to=auth.expiry_date)
        else:
            for srv in profile.services:
                self._create_field_assertion(srv.id, "service.name", srv.name, srv.evidence_ids, assertion_type=AssertionType.DERIVED_CAPABILITY)
                self._create_field_assertion(srv.id, "service.description", srv.description, srv.evidence_ids, assertion_type=AssertionType.DERIVED_CAPABILITY)

            for port in profile.portfolio:
                self._create_field_assertion(port.id, "portfolio.title", port.title, port.evidence_ids)
                self._create_field_assertion(port.id, "portfolio.summary", port.summary, port.evidence_ids)
                if port.outcome:
                    self._create_field_assertion(port.id, "portfolio.outcome", port.outcome, port.evidence_ids)
                    self._extract_metrics_from_text(port.id, port.outcome, port.evidence_ids, port.metric_verification)

            if profile.capacity:
                cap = profile.capacity
                if cap.hours_per_week is not None:
                    self._create_field_assertion(cap.id, "capacity.hours_per_week", cap.hours_per_week, cap.evidence_ids, effective_from=cap.available_from)
                if cap.annual_turnover_usd is not None:
                    self._create_field_assertion(cap.id, "capacity.annual_turnover_usd", cap.annual_turnover_usd, cap.evidence_ids, effective_from=cap.available_from)
                if cap.bid_bond_capacity_usd is not None:
                    self._create_field_assertion(cap.id, "capacity.bid_bond_capacity_usd", cap.bid_bond_capacity_usd, cap.evidence_ids, effective_from=cap.available_from)
                if cap.legal_capacity is not None:
                    self._create_field_assertion(cap.id, "capacity.legal_capacity", cap.legal_capacity, cap.evidence_ids, effective_from=cap.available_from)

    def _create_field_assertion(
        self,
        subject_id: str,
        predicate: str,
        value: Any,
        evidence_ids: tuple[str, ...],
        *,
        assertion_type: AssertionType = AssertionType.DIRECT_FACT,
        verification_status: VerificationStatus = VerificationStatus.VERIFIED,
        polarity: Polarity = Polarity.POSITIVE,
        modality: Modality = Modality.DEFINITE,
        effective_from: date | None = None,
        effective_to: date | None = None,
    ) -> None:
        assertion_id = f"as_{subject_id}_{predicate.replace('.', '_')}"
        if assertion_id not in self._assertions:
            self._assertions[assertion_id] = AtomicAssertion(
                id=assertion_id,
                subject_id=subject_id,
                predicate=predicate,
                value=value,
                assertion_type=assertion_type,
                verification_status=verification_status,
                evidence_ids=evidence_ids,
                polarity=polarity,
                modality=modality,
                effective_from=effective_from,
                effective_to=effective_to,
            )

    def _extract_metrics_from_text(
        self,
        subject_id: str,
        text: str,
        evidence_ids: tuple[str, ...],
        verification: MetricVerification,
    ) -> None:
        metric_pattern = re.compile(
            r"(?<![\w-])(?:(?P<curr>[$€£])\s*)?(?P<val>\d+(?:[.,]\d+)?)(?:\s*(?P<unit>%|[xX]\b|hours?|days?|weeks?|months?|users?|clients?|projects?|requests?|seconds?|minutes?|USD|EUR|GBP))?",
            re.IGNORECASE,
        )
        for idx, match in enumerate(metric_pattern.finditer(text)):
            curr = match.group("curr") or ""
            val_str = match.group("val").replace(",", "")
            unit = match.group("unit") or curr or "count"
            try:
                num_val = float(val_str) if "." in val_str else int(val_str)
            except ValueError:
                continue

            metric_id = f"metric_{subject_id}_{idx}"
            if metric_id not in self._metrics:
                self._metrics[metric_id] = MetricAssertion(
                    id=metric_id,
                    subject_id=subject_id,
                    numeric_value=num_val,
                    unit=unit.strip(),
                    context=text[:100],
                    verification_status=verification,
                    evidence_ids=evidence_ids,
                )

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

    def assertions_for_subject(self, subject_id: str) -> tuple[AtomicAssertion, ...]:
        return tuple(a for a in self._assertions.values() if a.subject_id == subject_id)

    def assertion_for_field(self, subject_id: str, predicate: str) -> AtomicAssertion | None:
        for a in self._assertions.values():
            if a.subject_id == subject_id and a.predicate == predicate:
                return a
        return None

    def relations_for_source(self, source_id: str) -> tuple[TypedRelation, ...]:
        return tuple(r for r in self._relations.values() if r.source_id == source_id)

    def relations_between(self, source_id: str, target_id: str) -> tuple[TypedRelation, ...]:
        return tuple(r for r in self._relations.values() if r.source_id == source_id and r.target_id == target_id)

    def has_relation(
        self,
        source_id: str,
        relation_type: str,
        target_id: str,
        *,
        as_of: date | None = None,
    ) -> bool:
        for r in self._relations.values():
            if r.source_id == source_id and r.relation_type == relation_type and r.target_id == target_id:
                if as_of is not None:
                    if r.effective_from and as_of < r.effective_from:
                        continue
                    if r.effective_to and as_of > r.effective_to:
                        continue
                return True
        return False

    def metric_assertions_for_evidence(self, evidence_id: str) -> tuple[MetricAssertion, ...]:
        return tuple(m for m in self._metrics.values() if evidence_id in m.evidence_ids)

    def metric_assertions_for_subject(self, subject_id: str) -> tuple[MetricAssertion, ...]:
        return tuple(m for m in self._metrics.values() if m.subject_id == subject_id)

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

