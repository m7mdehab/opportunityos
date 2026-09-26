"""Requirement priority classification for matching and qualification inputs."""
from __future__ import annotations

import re
from enum import Enum


class RequirementPriority(str, Enum):
    MANDATORY = "mandatory"
    STRONGLY_PREFERRED = "strongly_preferred"
    NICE_TO_HAVE = "nice_to_have"
    CONTEXTUAL = "contextual"
    UNKNOWN = "unknown"


_STRONGLY_PREFERRED_RE = re.compile(
    r"\b(?:strongly|highly|particularly)\s+preferred\b", re.IGNORECASE,
)
_NICE_TO_HAVE_RE = re.compile(
    r"\b(?:nice[-\s]+to[-\s]+have|good\s+to\s+have|bonus(?:\s+points?)?|preferred)\b",
    re.IGNORECASE,
)
_NOT_MANDATORY_RE = re.compile(
    r"\b(?:not\s+required|not\s+necessary|not\s+mandatory|optional)\b", re.IGNORECASE,
)
_DIRECT_MANDATORY_RE = re.compile(
    r"\b(?:must[-\s]+have|must\s+(?:be|have|possess|speak|hold|demonstrate)|"
    r"candidate\s+must|you\s+(?:must|need\s+to)|required\s+(?:skill|qualification|experience|certification|language)"
    r"|minimum\s+(?:qualification|requirement|experience)|experience\s+required)\b"
    r"|\brequired\s*:",
    re.IGNORECASE,
)
_GENERIC_REQUIRED_RE = re.compile(r"\brequired\b", re.IGNORECASE)
_COMPANY_CONTEXT_RE = re.compile(
    r"\b(?:our\s+(?:company|product|platform|business|technology|tech\s+stack|engineering\s+team)"
    r"|we\s+(?:use|build|develop|maintain|operate|work\s+with)|"
    r"built\s+with|powered\s+by|technology\s+stack)\b",
    re.IGNORECASE,
)


def classify_requirement_text(
    text: str,
    *,
    source_section: str | RequirementPriority | None = None,
) -> RequirementPriority:
    """Classify the posting-side priority signaled by wording and section.

    Direct applicant-facing language wins over a broad section hint. A general
    company/product technology statement remains contextual even if it uses
    ``required`` to describe how the business operates.
    """
    if not isinstance(text, str) or not text.strip():
        return RequirementPriority.UNKNOWN

    value = " ".join(text.split())
    lower = value.casefold()
    if _NOT_MANDATORY_RE.search(value):
        return RequirementPriority.NICE_TO_HAVE
    if _STRONGLY_PREFERRED_RE.search(value):
        return RequirementPriority.STRONGLY_PREFERRED
    if _NICE_TO_HAVE_RE.search(value):
        return RequirementPriority.NICE_TO_HAVE

    company_context = bool(_COMPANY_CONTEXT_RE.search(value))
    if _DIRECT_MANDATORY_RE.search(value):
        return RequirementPriority.MANDATORY
    if company_context:
        return RequirementPriority.CONTEXTUAL
    if _GENERIC_REQUIRED_RE.search(value):
        return RequirementPriority.MANDATORY

    if isinstance(source_section, RequirementPriority):
        return source_section
    section = (source_section or "").strip().casefold().replace("-", "_")
    if section in {"requirement", "requirements", "required", "mandatory", "minimum_qualifications"}:
        return RequirementPriority.MANDATORY
    if section in {"strongly_preferred", "highly_preferred"}:
        return RequirementPriority.STRONGLY_PREFERRED
    if section in {"preferred", "nice_to_have", "bonus"}:
        return RequirementPriority.NICE_TO_HAVE
    if section in {"responsibility", "responsibilities", "about", "company", "contextual"}:
        return RequirementPriority.CONTEXTUAL
    if lower.startswith(("must have", "must be", "required:", "required ")):
        return RequirementPriority.MANDATORY
    return RequirementPriority.UNKNOWN
