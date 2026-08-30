"""Zero-Fabrication Application Answer Engine with strict TruthGraph and Policy Authority."""
from __future__ import annotations

import re
from typing import Any
from matching.models import TailoringPolicy
from opportunity.models import Opportunity
from truth.graph import TruthGraph
from truth.models import Modality, Polarity, VerificationStatus
from .models import AnswerClass, ApplicationAnswer, BoundArtifact, DetectedFormField, FieldOntologyType


class ApplicationAnswerEngine:
    """Answers detected form fields strictly from verified TruthGraph assertions or explicit policy."""

    def __init__(self, truth_graph: TruthGraph, policy: TailoringPolicy | None = None) -> None:
        self.truth_graph = truth_graph
        self.policy = policy or TailoringPolicy()

    def answer_field(
        self,
        field: DetectedFormField,
        opportunity: Opportunity,
        action_id: str = "act-default",
        artifact: BoundArtifact | None = None,
    ) -> ApplicationAnswer:
        """Derive answer for a detected form field with fail-closed provenance."""
        norm_label = field.normalized_label

        # 1. ATTACHMENTS (Resume, CV, Cover Letter)
        if field.ontology_type in (FieldOntologyType.RESUME_CV, FieldOntologyType.COVER_LETTER, FieldOntologyType.ATTACHMENT):
            if artifact is not None:
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer=artifact.artifact_id,
                    answer_class=AnswerClass.GREEN,
                    answer_source="matching_artifact",
                    artifact_ids=(artifact.artifact_id,),
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
                answer_source="unattached_artifact",
                disposition="pause",
            )

        # 2. IDENTITY (Name, First Name, Last Name) - ZERO FABRICATION
        if field.ontology_type == FieldOntologyType.IDENTITY:
            name_assertions = [
                a for a in self.truth_graph.assertions.values()
                if a.predicate in ("identity.name", "identity.full_name")
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
            parts = full_name.split()

            if any(k in norm_label for k in ("first name", "given name")):
                val = parts[0] if parts else full_name
            elif any(k in norm_label for k in ("last name", "family name", "surname")):
                val = parts[-1] if len(parts) > 1 else ""
            else:
                val = full_name

            return ApplicationAnswer(
                opportunity_id=opportunity.id,
                opportunity_content_hash=opportunity.content_hash,
                action_id=action_id,
                field_type=field.ontology_type,
                original_label=field.label,
                normalized_question=field.normalized_label,
                answer=val,
                answer_class=AnswerClass.GREEN,
                answer_source=f"truth_graph:{name_assertions[0].id}",
                assertion_ids=(name_assertions[0].id,),
                disposition="auto_fill",
            )

        # 3. CONTACT (Email, Phone, Country, City) - ZERO FABRICATION
        if field.ontology_type == FieldOntologyType.CONTACT:
            if any(k in norm_label for k in ("email", "e-mail")):
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

            if "country" in norm_label:
                country_assertions = [
                    a for a in self.truth_graph.assertions.values()
                    if a.predicate in ("identity.country", "location.country")
                    and a.verification_status == VerificationStatus.VERIFIED
                ]
                if country_assertions:
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer=str(country_assertions[0].value),
                        answer_class=AnswerClass.GREEN,
                        answer_source=f"truth_graph:{country_assertions[0].id}",
                        assertion_ids=(country_assertions[0].id,),
                        disposition="auto_fill",
                    )

            if "city" in norm_label:
                city_assertions = [
                    a for a in self.truth_graph.assertions.values()
                    if a.predicate in ("identity.city", "location.city")
                    and a.verification_status == VerificationStatus.VERIFIED
                ]
                if city_assertions:
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer=str(city_assertions[0].value),
                        answer_class=AnswerClass.GREEN,
                        answer_source=f"truth_graph:{city_assertions[0].id}",
                        assertion_ids=(city_assertions[0].id,),
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
                answer_source="unasserted_contact",
                disposition="pause",
            )

        # 4. LINKS (LinkedIn, GitHub, Portfolio) - ZERO FABRICATION
        if field.ontology_type == FieldOntologyType.LINKS:
            if "linkedin" in norm_label:
                li_assertions = [
                    a for a in self.truth_graph.assertions.values()
                    if a.predicate in ("link.linkedin", "profile.linkedin")
                    and a.verification_status == VerificationStatus.VERIFIED
                ]
                if li_assertions:
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer=str(li_assertions[0].value),
                        answer_class=AnswerClass.GREEN,
                        answer_source=f"truth_graph:{li_assertions[0].id}",
                        assertion_ids=(li_assertions[0].id,),
                        disposition="auto_fill",
                    )

            if "github" in norm_label:
                gh_assertions = [
                    a for a in self.truth_graph.assertions.values()
                    if a.predicate in ("link.github", "profile.github")
                    and a.verification_status == VerificationStatus.VERIFIED
                ]
                if gh_assertions:
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer=str(gh_assertions[0].value),
                        answer_class=AnswerClass.GREEN,
                        answer_source=f"truth_graph:{gh_assertions[0].id}",
                        assertion_ids=(gh_assertions[0].id,),
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
                answer_source="unasserted_links",
                disposition="pause",
            )

        # 5. LOCATION PREFERENCE
        if field.ontology_type == FieldOntologyType.LOCATION_PREFERENCE:
            remote_assertions = [
                a for a in self.truth_graph.assertions.values()
                if a.predicate in ("preference.remote", "location.remote_ok")
                and a.verification_status == VerificationStatus.VERIFIED
            ]
            if remote_assertions:
                return ApplicationAnswer(
                    opportunity_id=opportunity.id,
                    opportunity_content_hash=opportunity.content_hash,
                    action_id=action_id,
                    field_type=field.ontology_type,
                    original_label=field.label,
                    normalized_question=field.normalized_label,
                    answer="Remote / Worldwide",
                    answer_class=AnswerClass.GREEN,
                    answer_source=f"truth_graph:{remote_assertions[0].id}",
                    assertion_ids=(remote_assertions[0].id,),
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
                answer_source="unasserted_location_preference",
                disposition="pause",
            )

        # 6. WORK AUTHORIZATION (Deterministic Open-World Semantics: UNKNOWN != FALSE)
        if field.ontology_type == FieldOntologyType.WORK_AUTHORIZATION:
            jurisdictions = {
                "united states": "United States", "usa": "United States", "us": "United States",
                "egypt": "Egypt", "germany": "Germany", "united kingdom": "United Kingdom", "uk": "United Kingdom",
                "canada": "Canada", "france": "France", "uae": "United Arab Emirates",
            }
            target_jurisdiction = None
            for key, canon in jurisdictions.items():
                if re.search(r"\b" + re.escape(key) + r"\b", norm_label):
                    target_jurisdiction = canon
                    break

            all_auth_assertions = [
                a for a in self.truth_graph.assertions.values()
                if a.predicate.startswith("authorization.")
                and a.verification_status == VerificationStatus.VERIFIED
            ]

            if target_jurisdiction:
                target_positive = [
                    a for a in all_auth_assertions
                    if str(a.value).lower() == target_jurisdiction.lower()
                    and a.polarity == Polarity.POSITIVE
                ]
                if target_positive:
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer="Yes",
                        answer_class=AnswerClass.GREEN,
                        answer_source=f"truth_graph:{target_positive[0].id}",
                        assertion_ids=(target_positive[0].id,),
                        disposition="auto_fill",
                    )

                target_negative = [
                    a for a in all_auth_assertions
                    if str(a.value).lower() == target_jurisdiction.lower()
                    and a.polarity == Polarity.NEGATIVE
                ]
                if target_negative:
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer="No",
                        answer_class=AnswerClass.GREEN,
                        answer_source=f"truth_graph:{target_negative[0].id}",
                        assertion_ids=(target_negative[0].id,),
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
                answer_source="unresolved_work_authorization",
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

        # 9. COMPENSATION (Yellow Answer ONLY if rate, currency, AND interval are all explicitly configured)
        if field.ontology_type == FieldOntologyType.COMPENSATION:
            currency = self.policy.default_currency
            if currency:
                if self.policy.default_hourly_rate is not None:
                    ans = f"{currency} {self.policy.default_hourly_rate}/hr"
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer=ans,
                        answer_class=AnswerClass.YELLOW,
                        answer_source="tailoring_policy:compensation_hourly",
                        policy_source=f"TailoringPolicy.{self.policy.version}.default_hourly_rate",
                        disposition="auto_fill",
                    )
                elif self.policy.default_daily_rate is not None:
                    ans = f"{currency} {self.policy.default_daily_rate}/day"
                    return ApplicationAnswer(
                        opportunity_id=opportunity.id,
                        opportunity_content_hash=opportunity.content_hash,
                        action_id=action_id,
                        field_type=field.ontology_type,
                        original_label=field.label,
                        normalized_question=field.normalized_label,
                        answer=ans,
                        answer_class=AnswerClass.YELLOW,
                        answer_source="tailoring_policy:compensation_daily",
                        policy_source=f"TailoringPolicy.{self.policy.version}.default_daily_rate",
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
