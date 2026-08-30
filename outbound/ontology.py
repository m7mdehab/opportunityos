"""Canonical Field Ontology and Classification for Outbound Forms."""
from __future__ import annotations

import re
from .models import AnswerClass, DetectedFormField, FieldOntologyType


class FieldClassifier:
    """Classifies detected form fields into the canonical 19-type ontology."""

    @classmethod
    def normalize_label(cls, label: str) -> str:
        norm = re.sub(r"[^a-zA-Z0-9\s]", " ", label.lower())
        return " ".join(norm.split())

    @classmethod
    def classify_field(
        cls,
        label: str,
        name: str = "",
        field_type: str = "text",
        options: tuple[str, ...] = (),
        required: bool = False,
        field_id: str = "",
    ) -> DetectedFormField:
        norm_label = cls.normalize_label(label)
        norm_name = cls.normalize_label(name)
        text_to_match = f"{norm_label} {norm_name}"

        # 1. ATTACHMENT
        if field_type == "file" or any(k in text_to_match for k in ("resume", "cv", "curriculum vitae", "cover letter file", "portfolio upload", "attachment", "upload your")):
            ont = FieldOntologyType.ATTACHMENT
            sens = AnswerClass.GREEN

        # 2. IDENTITY
        elif any(k in text_to_match for k in ("first name", "given name", "forename", "last name", "family name", "surname", "full name", "legal name", "preferred name", "your name")):
            ont = FieldOntologyType.IDENTITY
            sens = AnswerClass.GREEN

        # 3. CONTACT
        elif any(k in text_to_match for k in ("email", "e mail", "phone", "mobile", "telephone", "phone number", "contact number", "postal code", "zip code", "zipcode", "city", "country of residence")):
            ont = FieldOntologyType.CONTACT
            sens = AnswerClass.GREEN

        # 4. ADDRESS_LOCATION
        elif any(k in text_to_match for k in ("street address", "address line", "current location", "where are you located", "state province", "residence address")):
            ont = FieldOntologyType.ADDRESS_LOCATION
            sens = AnswerClass.GREEN

        # 5. LINKS
        elif any(k in text_to_match for k in ("linkedin", "github", "portfolio url", "website", "personal site", "twitter", "blog url", "online profile")):
            ont = FieldOntologyType.LINKS
            sens = AnswerClass.GREEN

        # 6. EDUCATION
        elif any(k in text_to_match for k in ("university", "college", "school", "degree", "field of study", "major", "gpa", "graduation year", "education level")):
            ont = FieldOntologyType.EDUCATION
            sens = AnswerClass.GREEN

        # 7. EMPLOYMENT
        elif any(k in text_to_match for k in ("current company", "current employer", "current title", "job title", "work history", "recent employer", "years of experience")):
            ont = FieldOntologyType.EMPLOYMENT
            sens = AnswerClass.GREEN

        # 8. WORK_AUTHORIZATION
        elif any(k in text_to_match for k in ("authorized to work", "work authorization", "legal right to work", "legally authorized", "right to work in", "work permit", "eligible to work")):
            ont = FieldOntologyType.WORK_AUTHORIZATION
            sens = AnswerClass.YELLOW

        # 9. SPONSORSHIP
        elif any(k in text_to_match for k in ("require sponsorship", "require visa sponsorship", "need visa sponsorship", "sponsorship now or in the future", "visa sponsorship")):
            ont = FieldOntologyType.SPONSORSHIP
            sens = AnswerClass.YELLOW

        # 10. COMPENSATION
        elif any(k in text_to_match for k in ("salary expectation", "desired salary", "compensation expectation", "target pay", "hourly rate", "daily rate", "expected compensation", "salary requirements")):
            ont = FieldOntologyType.COMPENSATION
            sens = AnswerClass.YELLOW

        # 11. AVAILABILITY
        elif any(k in text_to_match for k in ("start date", "notice period", "availability", "when can you start", "earliest start", "how soon can you start", "hours per week")):
            ont = FieldOntologyType.AVAILABILITY
            sens = AnswerClass.YELLOW

        # 12. TRAVEL
        elif any(k in text_to_match for k in ("willing to travel", "travel percentage", "travel requirement", "ability to travel", "business travel")):
            ont = FieldOntologyType.TRAVEL
            sens = AnswerClass.YELLOW

        # 13. RELOCATION
        elif any(k in text_to_match for k in ("willing to relocate", "relocation assistance", "open to relocation", "able to relocate")):
            ont = FieldOntologyType.RELOCATION
            sens = AnswerClass.YELLOW

        # 14. DEMOGRAPHIC_VOLUNTARY
        elif any(k in text_to_match for k in ("gender", "race", "ethnicity", "veteran status", "disability status", "voluntary self identification", "equal opportunity", "demographic")):
            ont = FieldOntologyType.DEMOGRAPHIC_VOLUNTARY
            sens = AnswerClass.RED

        # 15. LEGAL_DECLARATION
        elif any(k in text_to_match for k in ("certify", "terms and conditions", "non compete", "binding declaration", "agree to terms", "privacy policy", "acknowledge and agree", "consent to", "declaration")):
            ont = FieldOntologyType.LEGAL_DECLARATION
            sens = AnswerClass.RED

        # 16. SECURITY_CLEARANCE
        elif any(k in text_to_match for k in ("security clearance", "clearance level", "top secret", "active clearance", "government clearance")):
            ont = FieldOntologyType.SECURITY_CLEARANCE
            sens = AnswerClass.RED

        # 17. CONFLICT_OF_INTEREST
        elif any(k in text_to_match for k in ("conflict of interest", "relative employed", "family member working", "relationship with employee", "financial interest")):
            ont = FieldOntologyType.CONFLICT_OF_INTEREST
            sens = AnswerClass.RED

        # 18. CUSTOM_NARRATIVE
        elif field_type == "textarea" or any(k in text_to_match for k in ("why do you want", "tell us about", "cover letter", "describe a project", "additional information", "personal statement", "why should we hire", "motivation")):
            ont = FieldOntologyType.CUSTOM_NARRATIVE
            sens = AnswerClass.RED

        # 19. OTHER_UNKNOWN
        else:
            ont = FieldOntologyType.OTHER_UNKNOWN
            sens = AnswerClass.RED

        return DetectedFormField(
            field_id=field_id or name or norm_label[:30],
            name=name,
            field_type=field_type,
            label=label,
            normalized_label=norm_label,
            ontology_type=ont,
            required=required,
            options=options,
            sensitivity_class=sens,
        )
