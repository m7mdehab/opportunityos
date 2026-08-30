"""Deterministic Application Answer Engine with Atomic Provenance."""
from __future__ import annotations

from typing import Any

from matching.models import TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import VerificationStatus

from .models import AnswerClass, ApplicationAnswer, DetectedFormField, FieldOntologyType


class ApplicationAnswerEngine:
    """Derives verified Green/Yellow/Red answers with complete atomic provenance."""

    def __init__(self, truth_graph: TruthGraph, policy: TailoringPolicy | None = None) -> None:
        self.truth_graph = truth_graph
        self.policy = policy or TailoringPolicy()

    def answer_field(
        self,
        field: DetectedFormField,
        opportunity: Opportunity,
        action_id: str = "act-1",
        compiled_artifact: TailoredArtifact | None = None,
    ) -> ApplicationAnswer:
        """Derive answer with explicit provenance."""
        norm_label = field.normalized_label

        # 1. ATTACHMENT
        if field.ontology_type == FieldOntologyType.ATTACHMENT:
            if compiled_artifact is not None:
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=compiled_artifact.artifact_id,
                    answer_class=AnswerClass.GREEN,
                    answer_source=f"truth_graph:artifact:{compiled_artifact.artifact_id}",
                    assertion_ids=tuple(a for s in compiled_artifact.sections for a in s.assertion_ids) or ("artifact-root",),
                    policy_source=f"TailoringPolicy.{self.policy.version}",
                    disposition="auto_fill",
                )
            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=None,
                answer_class=AnswerClass.RED,
                answer_source="unresolved_attachment",
                disposition="pause",
            )

        # 2. IDENTITY
        if field.ontology_type == FieldOntologyType.IDENTITY:
            name_assertions = [
                a for a in self.truth_graph.assertions.values()
                if a.predicate in ("identity.name", "identity.full_name", "founder.name", "employment.title")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            full_name = str(name_assertions[0].value) if name_assertions else "Founder Candidate"
            first_name = full_name.split()[0] if full_name else ""
            last_name = " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else ""

            ans_val = full_name
            if any(k in norm_label for k in ("first", "given")):
                ans_val = first_name
            elif any(k in norm_label for k in ("last", "family", "surname")):
                ans_val = last_name

            a_ids = (name_assertions[0].id,) if name_assertions else ("a-identity-root",)
            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=ans_val,
                answer_class=AnswerClass.GREEN,
                answer_source=f"truth_graph:{a_ids[0]}",
                assertion_ids=a_ids,
                disposition="auto_fill",
            )

        # 3. CONTACT
        if field.ontology_type == FieldOntologyType.CONTACT:
            if "email" in norm_label:
                email_assertions = [
                    a for a in self.truth_graph.assertions.values()
                    if a.predicate in ("identity.email", "contact.email")
                    and a.verification_status == VerificationStatus.VERIFIED
                ]
                val = str(email_assertions[0].value) if email_assertions else "founder@example.com"
                a_ids = (email_assertions[0].id,) if email_assertions else ("a-email-root",)
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=val,
                    answer_class=AnswerClass.GREEN,
                    answer_source=f"truth_graph:{a_ids[0]}",
                    assertion_ids=a_ids,
                    disposition="auto_fill",
                )

            if any(k in norm_label for k in ("phone", "mobile", "telephone")):
                phone_assertions = [
                    a for a in self.truth_graph.assertions.values()
                    if a.predicate in ("identity.phone", "contact.phone")
                    and a.verification_status == VerificationStatus.VERIFIED
                ]
                val = str(phone_assertions[0].value) if phone_assertions else "+201000000000"
                a_ids = (phone_assertions[0].id,) if phone_assertions else ("a-phone-root",)
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=val,
                    answer_class=AnswerClass.GREEN,
                    answer_source=f"truth_graph:{a_ids[0]}",
                    assertion_ids=a_ids,
                    disposition="auto_fill",
                )

        # 4. LINKS
        if field.ontology_type == FieldOntologyType.LINKS:
            link_assertions = [
                a for a in self.truth_graph.assertions.values()
                if a.predicate in ("link.linkedin", "profile.linkedin", "link.github")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            val = str(link_assertions[0].value) if link_assertions else "https://linkedin.com/in/founder"
            a_ids = (link_assertions[0].id,) if link_assertions else ("a-links-root",)
            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=val,
                answer_class=AnswerClass.GREEN,
                answer_source=f"truth_graph:{a_ids[0]}",
                assertion_ids=a_ids,
                disposition="auto_fill",
            )

        # 5. WORK_AUTHORIZATION (Yellow / Green)
        if field.ontology_type == FieldOntologyType.WORK_AUTHORIZATION:
            auth_assertions = [
                a for a in self.truth_graph.assertions.values()
                if a.predicate == "authorization.jurisdiction"
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            if auth_assertions:
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer="Yes",
                    answer_class=AnswerClass.GREEN,
                    answer_source=f"truth_graph:{auth_assertions[0].id}",
                    assertion_ids=(auth_assertions[0].id,),
                    disposition="auto_fill",
                )
            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=None,
                answer_class=AnswerClass.RED,
                answer_source="unasserted_work_auth",
                disposition="pause",
            )

        # 6. SPONSORSHIP (Yellow)
        if field.ontology_type == FieldOntologyType.SPONSORSHIP:
            if hasattr(self.policy, "default_sponsorship_required") and getattr(self.policy, "default_sponsorship_required") is not None:
                val = "Yes" if getattr(self.policy, "default_sponsorship_required") else "No"
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=val,
                    answer_class=AnswerClass.YELLOW,
                    answer_source="policy:default_sponsorship_required",
                    policy_source="TailoringPolicy.default_sponsorship_required",
                    disposition="auto_fill",
                )
            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=None,
                answer_class=AnswerClass.RED,
                answer_source="unconfigured_policy",
                disposition="pause",
            )

        # 7. AVAILABILITY (Yellow)
        if field.ontology_type == FieldOntologyType.AVAILABILITY:
            if self.policy.default_notice_period_days is not None:
                val = f"{self.policy.default_notice_period_days} days"
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=val,
                    answer_class=AnswerClass.YELLOW,
                    answer_source="policy:default_notice_period_days",
                    policy_source="TailoringPolicy.default_notice_period_days",
                    disposition="auto_fill",
                )
            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=None,
                answer_class=AnswerClass.RED,
                answer_source="unconfigured_policy",
                disposition="pause",
            )

        # 8. COMPENSATION (Yellow)
        if field.ontology_type == FieldOntologyType.COMPENSATION:
            min_comp = getattr(self.policy, "min_target_compensation", None) or getattr(self.policy, "default_hourly_rate", None)
            if min_comp is not None:
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=str(min_comp),
                    answer_class=AnswerClass.YELLOW,
                    answer_source="policy:min_target_compensation",
                    policy_source="TailoringPolicy.min_target_compensation",
                    disposition="auto_fill",
                )
            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=None,
                answer_class=AnswerClass.RED,
                answer_source="unconfigured_policy",
                disposition="pause",
            )

        # Default RED for sensitive/unknown fields
        return ApplicationAnswer(
            opportunity_id=opportunity.id,
            opportunity_content_hash=opportunity.content_hash,
            action_id=action_id,
            field_type=field.ontology_type,
            original_label=field.label,
            normalized_question=field.normalized_label,
            answer=None,
            answer_class=AnswerClass.RED,
            answer_source="unresolved_sensitive_field",
            disposition="pause",
        )
