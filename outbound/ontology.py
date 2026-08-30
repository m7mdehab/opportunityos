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
        step_index: int = 0,
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
        elif any(k in text_to_match for k in ("email", "e mail", "phone", "mobile", "telephone", "phone number", "contact number")):
            ont = FieldOntologyType.CONTACT
            sens = AnswerClass.GREEN

        # 4. ADDRESS_LOCATION
        elif any(k in text_to_match for k in ("street address", "address line", "current location", "where are you located", "city", "postal code", "zip code", "zipcode", "country of residence", "residence address")):
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
        elif any(k in text_to_match for k in ("current company", "recent employer", "current title", "years of experience", "work experience")):
            ont = FieldOntologyType.EMPLOYMENT
            sens = AnswerClass.GREEN

        # 8. WORK_AUTHORIZATION (Yellow / Green)
        elif any(k in text_to_match for k in ("authorized to work", "legally authorized", "work permit", "right to work", "work authorization", "eligible to work in")):
            ont = FieldOntologyType.WORK_AUTHORIZATION
            sens = AnswerClass.YELLOW

        # 9. SPONSORSHIP (Yellow)
        elif any(k in text_to_match for k in ("sponsorship", "visa sponsorship", "require sponsorship", "need sponsorship", "h1b")):
            ont = FieldOntologyType.SPONSORSHIP
            sens = AnswerClass.YELLOW

        # 10. COMPENSATION (Yellow)
        elif any(k in text_to_match for k in ("salary expectation", "expected compensation", "desired salary", "hourly rate expectation", "expected rate", "compensation expectations")):
            ont = FieldOntologyType.COMPENSATION
            sens = AnswerClass.YELLOW

        # 11. AVAILABILITY (Yellow)
        elif any(k in text_to_match for k in ("notice period", "start date", "how soon can you start", "availability")):
            ont = FieldOntologyType.AVAILABILITY
            sens = AnswerClass.YELLOW

        # 12. TRAVEL (Yellow)
        elif any(k in text_to_match for k in ("willing to travel", "travel percentage", "business travel")):
            ont = FieldOntologyType.TRAVEL
            sens = AnswerClass.YELLOW

        # 13. RELOCATION (Yellow)
        elif any(k in text_to_match for k in ("willing to relocate", "relocation")):
            ont = FieldOntologyType.RELOCATION
            sens = AnswerClass.YELLOW

        # 14. DEMOGRAPHIC_VOLUNTARY (Red - sensitive EEO)
        elif any(k in text_to_match for k in ("gender", "race", "ethnicity", "veteran", "disability", "equal opportunity", "voluntary disclosure", "eeo")):
            ont = FieldOntologyType.DEMOGRAPHIC_VOLUNTARY
            sens = AnswerClass.RED

        # 15. CUSTOM_NARRATIVE (Red - creative / unique text)
        elif any(k in text_to_match for k in ("why do you want to work", "why us", "cover letter text", "additional information", "describe your experience", "tell us about a project", "motivation")):
            ont = FieldOntologyType.CUSTOM_NARRATIVE
            sens = AnswerClass.RED

        # 16. LEGAL_DECLARATION (Red - binding legal commitments)
        elif any(k in text_to_match for k in ("agree to terms", "non compete", "binding declaration", "background check consent", "certify that the information", "under penalty of perjury", "signature", "electronic signature", "legal declaration", "binding agreement", "acknowledge and agree")):
            ont = FieldOntologyType.LEGAL_DECLARATION
            sens = AnswerClass.RED

        # 17. SECURITY_CLEARANCE (Red - governmental clearance)
        elif any(k in text_to_match for k in ("security clearance", "clearance level", "top secret", "polygraph", "active clearance")):
            ont = FieldOntologyType.SECURITY_CLEARANCE
            sens = AnswerClass.RED

        # 18. CONFLICT_OF_INTEREST (Red - ethical declarations)
        elif any(k in text_to_match for k in ("conflict of interest", "relatives working", "governmental official", "sanctions declaration")):
            ont = FieldOntologyType.CONFLICT_OF_INTEREST
            sens = AnswerClass.RED

        # 19. OTHER_UNKNOWN (Red - fail closed)
        else:
            ont = FieldOntologyType.OTHER_UNKNOWN
            sens = AnswerClass.RED

        return DetectedFormField(
            field_id=field_id or name or label,
            name=name,
            field_type=field_type,
            label=label,
            normalized_label=norm_label,
            ontology_type=ont,
            required=required,
            options=options,
            step_index=step_index,
            sensitivity_class=sens,
        )
