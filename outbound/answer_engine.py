"""Deterministic Application Answer Engine with Atomic Provenance."""
from __future__ import annotations

import re
from typing import Any

from matching.models import TailoredArtifact, TailoringPolicy
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import VerificationStatus

from .models import AnswerClass, ApplicationAnswer, DetectedFormField, FieldOntologyType


def _extract_target_jurisdiction(text: str) -> str | None:
    """Deterministically extract country / jurisdiction from question text."""
    clean = text.lower()
    mapping = {
        "united states": "United States",
        "u.s.": "United States",
        "u.s": "United States",
        "usa": "United States",
        "us ": "United States",
        " in the us": "United States",
        "egypt": "Egypt",
        "germany": "Germany",
        "united kingdom": "United Kingdom",
        "uk": "United Kingdom",
        "canada": "Canada",
        "european union": "European Union",
        "eu": "European Union",
        "saudi arabia": "Saudi Arabia",
        "uae": "United Arab Emirates",
        "united arab emirates": "United Arab Emirates",
    }
    for pattern, target in mapping.items():
        if re.search(rf"\b{re.escape(pattern)}\b", clean):
            return target
    return None


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
        """Derive answer with explicit provenance. Never fabricates answers."""
        norm_label = field.normalized_label

        # 1. ATTACHMENT
        if field.ontology_type == FieldOntologyType.ATTACHMENT:
            if compiled_artifact is not None:
                assertion_ids = tuple(a for s in compiled_artifact.sections for a in s.assertion_ids) or tuple(c.assertion_ids[0] for c in compiled_artifact.generated_claims if c.assertion_ids)
                if assertion_ids:
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

        # 3. CONTACT
        if field.ontology_type == FieldOntologyType.CONTACT:
            if "email" in norm_label:
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

        # 6. WORK_AUTHORIZATION (Determined by deterministic jurisdiction matching)
        if field.ontology_type == FieldOntologyType.WORK_AUTHORIZATION:
            target_jurisdiction = _extract_target_jurisdiction(field.label) or _extract_target_jurisdiction(field.name)
            if not target_jurisdiction:
                # If jurisdiction cannot be resolved from question: RED / PAUSE
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=None,
                    answer_class=AnswerClass.RED,
                    answer_source="unresolved_jurisdiction_in_question",
                    disposition="pause",
                )

            auth_assertions = [
                a for a in self.truth_graph.assertions.values()
                if a.predicate in ("authorization.jurisdiction", "work_auth.jurisdiction")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            if not auth_assertions:
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

            # Match target jurisdiction against verified assertions
            matching = [
                a for a in auth_assertions
                if str(a.value).casefold() == target_jurisdiction.casefold()
                or (target_jurisdiction == "United States" and str(a.value).casefold() in ("us", "usa", "united states"))
                or (target_jurisdiction == "United Kingdom" and str(a.value).casefold() in ("uk", "united kingdom"))
            ]
            if matching:
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer="Yes",
                    answer_class=AnswerClass.GREEN,
                    answer_source=f"truth_graph:{matching[0].id}",
                    assertion_ids=(matching[0].id,),
                    disposition="auto_fill",
                )
            else:
                # Founder has authorizations but NOT for the target jurisdiction: NOT YES!
                # If explicit policy or binary choice, answer No or pause
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer="No",
                    answer_class=AnswerClass.YELLOW,
                    answer_source=f"derived:no_auth_for_{target_jurisdiction}",
                    policy_source=f"TailoringPolicy.{self.policy.version}",
                    disposition="auto_fill",
                )

        # 7. SPONSORSHIP (Yellow)
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

        # 8. AVAILABILITY (Yellow)
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

        # 9. COMPENSATION (Yellow)
        if field.ontology_type == FieldOntologyType.COMPENSATION:
            target_comp = getattr(self.policy, "min_target_yearly_compensation", None) or getattr(self.policy, "min_target_compensation", None)
            if target_comp is not None:
                val = f"{self.policy.default_currency} {target_comp:,.0f}"
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=val,
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

        # 10. RED QUESTIONS (Sensitive / Legal / Narrative / Unknown)
        return ApplicationAnswer(
            opportunity_id=opportunity.id,
            opportunity_content_hash=opportunity.content_hash,
            action_id=action_id,
            field_type=field.ontology_type,
            original_label=field.label,
            normalized_question=field.normalized_label,
            answer=None,
            answer_class=AnswerClass.RED,
            answer_source="sensitive_declaration_requires_human_review",
            disposition="pause",
        )
