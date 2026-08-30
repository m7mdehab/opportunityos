"""Deterministic Application Answer Engine with Atomic Provenance and Non-Closed-World Work Auth."""
from __future__ import annotations

import re
from typing import Any
from matching.models import TailoringPolicy
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import AtomicAssertion, Modality, Polarity, VerificationStatus
from .models import AnswerClass, ApplicationAnswer, BoundArtifact, DetectedFormField, FieldOntologyType


class ApplicationAnswerEngine:
    """Derives answers strictly from verified TruthGraph assertions, versioned policy, and artifacts."""

    def __init__(self, truth_graph: TruthGraph, policy: TailoringPolicy) -> None:
        self.truth_graph = truth_graph
        self.policy = policy

    def _extract_target_jurisdiction(self, label: str) -> str | None:
        """Deterministically extract the question's target jurisdiction."""
        norm = label.lower()
        if any(w in norm for w in ("united states", "usa", "u.s.", "us citizen", "us work")):
            return "United States"
        if any(w in norm for w in ("egypt", "egyptian")):
            return "Egypt"
        if any(w in norm for w in ("united kingdom", "uk", "great britain")):
            return "United Kingdom"
        if any(w in norm for w in ("canada", "canadian")):
            return "Canada"
        if any(w in norm for w in ("germany", "german")):
            return "Germany"
        if any(w in norm for w in ("european union", "eu citizen", "eu work")):
            return "European Union"
        if any(w in norm for w in ("saudi", "ksa", "saudi arabia")):
            return "Saudi Arabia"
        if any(w in norm for w in ("uae", "emirates", "dubai", "abu dhabi")):
            return "United Arab Emirates"
        return None

    def answer_field(
        self,
        field: DetectedFormField,
        opportunity: Opportunity,
        action_id: str = "act-default",
        artifact: BoundArtifact | None = None,
    ) -> ApplicationAnswer:
        """Derive an atomic answer for a single detected form field."""
        norm_label = field.normalized_label

        # 1. ATTACHMENT / RESUME
        if field.ontology_type == FieldOntologyType.ATTACHMENT:
            if artifact is not None:
                compiled_artifact = artifact.artifact
                assertion_ids = tuple(
                    aid for claim in compiled_artifact.generated_claims for aid in claim.assertion_ids
                )
                if compiled_artifact.artifact_id:
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
                        assertion_ids=assertion_ids,
                        policy_source=f"TailoringPolicy.{self.policy.version}",
                        artifact_ids=(compiled_artifact.artifact_id,),
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
                if a.predicate in ("identity.name", "identity.full_name", "founder.name")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            if not name_assertions:
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=None,
                    answer_class=AnswerClass.RED,
                    answer_source="unasserted_identity",
                    disposition="pause",
                )

            full_name = str(name_assertions[0].value)
            first_name = full_name.split()[0] if full_name else ""
            last_name = " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else ""

            ans_val = full_name
            if any(k in norm_label for k in ("first", "given")):
                ans_val = first_name
            elif any(k in norm_label for k in ("last", "family", "surname")):
                ans_val = last_name

            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=ans_val,
                answer_class=AnswerClass.GREEN,
                answer_source=f"truth_graph:{name_assertions[0].id}",
                assertion_ids=(name_assertions[0].id,),
                disposition="auto_fill",
            )

        # 3. CONTACT (Email & Phone)
        if field.ontology_type == FieldOntologyType.CONTACT:
            if any(k in norm_label for k in ("email", "mail")):
                email_assertions = [
                    a for a in self.truth_graph.assertions.values()
                    if a.predicate in ("identity.email", "contact.email")
                    and a.verification_status == VerificationStatus.VERIFIED
                ]
                if not email_assertions:
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer=None,
                        answer_class=AnswerClass.RED,
                        answer_source="unasserted_email",
                        disposition="pause",
                    )
                val = str(email_assertions[0].value)
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=val,
                    answer_class=AnswerClass.GREEN,
                    answer_source=f"truth_graph:{email_assertions[0].id}",
                    assertion_ids=(email_assertions[0].id,),
                    disposition="auto_fill",
                )

            if any(k in norm_label for k in ("phone", "mobile", "telephone")):
                phone_assertions = [
                    a for a in self.truth_graph.assertions.values()
                    if a.predicate in ("identity.phone", "contact.phone")
                    and a.verification_status == VerificationStatus.VERIFIED
                ]
                if not phone_assertions:
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer=None,
                        answer_class=AnswerClass.RED,
                        answer_source="unasserted_phone",
                        disposition="pause",
                    )
                val = str(phone_assertions[0].value)
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=val,
                    answer_class=AnswerClass.GREEN,
                    answer_source=f"truth_graph:{phone_assertions[0].id}",
                    assertion_ids=(phone_assertions[0].id,),
                    disposition="auto_fill",
                )

        # 4. ADDRESS_LOCATION
        if field.ontology_type == FieldOntologyType.ADDRESS_LOCATION:
            loc_assertions = [
                a for a in self.truth_graph.assertions.values()
                if a.predicate in ("identity.country", "identity.location", "contact.country", "contact.city")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            if not loc_assertions:
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=None,
                    answer_class=AnswerClass.RED,
                    answer_source="unasserted_location",
                    disposition="pause",
                )
            val = str(loc_assertions[0].value)
            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=val,
                answer_class=AnswerClass.GREEN,
                answer_source=f"truth_graph:{loc_assertions[0].id}",
                assertion_ids=(loc_assertions[0].id,),
                disposition="auto_fill",
            )

        # 5. LINKS
        if field.ontology_type == FieldOntologyType.LINKS:
            link_assertions = [
                a for a in self.truth_graph.assertions.values()
                if a.predicate in ("link.linkedin", "profile.linkedin", "link.github", "link.portfolio")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            if not link_assertions:
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=None,
                    answer_class=AnswerClass.RED,
                    answer_source="unasserted_links",
                    disposition="pause",
                )
            val = str(link_assertions[0].value)
            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=val,
                answer_class=AnswerClass.GREEN,
                answer_source=f"truth_graph:{link_assertions[0].id}",
                assertion_ids=(link_assertions[0].id,),
                disposition="auto_fill",
            )

        # 6. WORK_AUTHORIZATION (Strict Open-World / UNKNOWN != FALSE)
        if field.ontology_type == FieldOntologyType.WORK_AUTHORIZATION:
            target_jurisdiction = self._extract_target_jurisdiction(field.label)
            auth_assertions = [
                a for a in self.truth_graph.assertions.values()
                if a.predicate in ("authorization.jurisdiction", "identity.work_authorization")
                and a.verification_status == VerificationStatus.VERIFIED
            ]

            if target_jurisdiction is not None:
                matching_pos = [
                    a for a in auth_assertions
                    if a.polarity == Polarity.POSITIVE and str(a.value).strip().lower() == target_jurisdiction.lower()
                ]
                if matching_pos:
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer="Yes",
                        answer_class=AnswerClass.GREEN,
                        answer_source=f"truth_graph:{matching_pos[0].id}",
                        assertion_ids=(matching_pos[0].id,),
                        disposition="auto_fill",
                    )

                matching_neg = [
                    a for a in auth_assertions
                    if a.polarity == Polarity.NEGATIVE and str(a.value).strip().lower() == target_jurisdiction.lower()
                ]
                if matching_neg:
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer="No",
                        answer_class=AnswerClass.GREEN,
                        answer_source=f"truth_graph:{matching_neg[0].id}",
                        assertion_ids=(matching_neg[0].id,),
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
                    answer_source="unresolved_work_authorization",
                    disposition="pause",
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
                answer_source="unresolved_work_authorization_jurisdiction",
                disposition="pause",
            )

        # 7. SPONSORSHIP (Yellow Answer ONLY if explicitly configured in TailoringPolicy)
        if field.ontology_type == FieldOntologyType.SPONSORSHIP:
            if self.policy.default_sponsorship_required is not None:
                ans = "Yes" if self.policy.default_sponsorship_required else "No"
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=ans,
                    answer_class=AnswerClass.YELLOW,
                    answer_source="tailoring_policy:sponsorship",
                    policy_source=f"TailoringPolicy.{self.policy.version}.default_sponsorship_required",
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
                answer_source="unconfigured_sponsorship_policy",
                disposition="pause",
            )

        # 8. AVAILABILITY & NOTICE PERIOD (Yellow Answer ONLY if explicitly configured)
        if field.ontology_type == FieldOntologyType.AVAILABILITY:
            if self.policy.default_notice_period_days is not None:
                ans = f"{self.policy.default_notice_period_days} days"
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=ans,
                    answer_class=AnswerClass.YELLOW,
                    answer_source="tailoring_policy:notice_period",
                    policy_source=f"TailoringPolicy.{self.policy.version}.default_notice_period_days",
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
                answer_source="unconfigured_notice_period_policy",
                disposition="pause",
            )

        # 9. COMPENSATION (Yellow Answer ONLY if rate AND currency explicitly configured)
        if field.ontology_type == FieldOntologyType.COMPENSATION:
            rate = self.policy.default_hourly_rate or self.policy.default_daily_rate
            currency = self.policy.default_currency
            if rate is not None and currency:
                ans = f"{currency} {rate}"
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=ans,
                    answer_class=AnswerClass.YELLOW,
                    answer_source="tailoring_policy:compensation",
                    policy_source=f"TailoringPolicy.{self.policy.version}.default_rate",
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
                answer_source="unconfigured_compensation_policy",
                disposition="pause",
            )

        # 10. RED QUESTIONS (Legal, Demographics, Clearance, Conflict, Narrative, or Unknown)
        return ApplicationAnswer(
            opportunity_id=opportunity.id,
            opportunity_content_hash=opportunity.content_hash,
            action_id=action_id,
            field_type=field.ontology_type,
            original_label=field.label,
            normalized_question=field.normalized_label,
            answer=None,
            answer_class=AnswerClass.RED,
            answer_source="red_question_policy",
            disposition="pause",
        )
