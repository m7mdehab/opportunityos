"""Small, deterministic opportunity-side signals for the BC recommendation path.

These classifications stay separate: title relevance does not imply eligibility,
and eligibility does not imply application accessibility. Unknown evidence stays
unknown so later recommendation logic can route it to review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from matching.title_family import normalize_title
from recon.geography import PLACE_ALIASES
from recon.regions import includes


@dataclass(frozen=True, slots=True)
class RoleRelevance:
    classification: str  # core | adjacent | non_target | unknown
    title_family: str
    title_level: str
    reason: str


@dataclass(frozen=True, slots=True)
class ApplicationAccess:
    route: str  # employer | ats | intermediary | source | email | dm | unknown
    access: str  # direct_free | free_intermediary | free_account_required | premium_or_gated | manual_only | unknown
    application_url: str
    reason: str


_CORE_FAMILIES = frozenset({
    "data_engineering", "data_science", "ml_ai_engineering",
    "data_quality_management", "data_migration",
})
_KNOWN_NON_TARGET = frozenset({
    "tutoring", "web_frontend", "project_program_management",
    "sales_account_management", "marketing", "support_success",
    "operations_logistics", "finance_accounting", "legal",
    "people_recruiting", "design_ux", "healthcare_clinical",
    "education", "hardware_embedded",
})
_CORE_TITLE = re.compile(
    r"\b(?:data\s+analyst|analytics\s+(?:engineer|analyst)|"
    r"business\s+intelligence|bi\s+(?:analyst|engineer|developer)|"
    r"data\s+(?:platform|infrastructure|pipeline|quality|governance|management|steward|migration)|"
    r"data\s+engineer|data\s+scientist|machine\s+learning|mlops|"
    r"(?:ai|ml|llm)\s+engineer|ai\s+research)\b", re.I,
)
_DATA_AI_EVIDENCE = re.compile(
    r"\b(?:data\s+(?:engineering|platform|pipeline|analytics|science|quality|governance|management)|"
    r"machine\s+learning|\bmlops\b|\bAI\b|\bLLM\b|\bSQL\b|\bETL\b|"
    r"data warehouse|dbt|lakehouse|feature store|vector database)\b", re.I,
)
_US_CANDIDATE_RESTRICTION = re.compile(
    r"\b(?:US|U\.S\.|USA|United States)(?:[- ]based)?\s+"
    r"(?:applicants?|candidates?|residents?|employees?)\s+only\b|"
    r"\b(?:must|only)\s+(?:be\s+)?(?:located|reside|live)\s+in\s+"
    r"(?:the\s+)?(?:US|U\.S\.|USA|United States)\b|"
    r"\b(?:must|only)\s+be\s+based\s+in\s+(?:the\s+)?"
    r"(?:US|U\.S\.|USA|United States)\b(?!\s+(?:(?:eastern|central|mountain|pacific)\s+)?time\s*zone|\s+hours?)|"
    r"\bUS\s+work\s+authorization\s+(?:is\s+)?required\b", re.I,
)
_EGYPT_RESTRICTION = re.compile(
    r"\b(?:must|only)\s+(?:be\s+)?(?:located|reside|live)\s+in\s+"
    r"(?:the\s+)?([A-Z][A-Za-z ]+)\b|"
    r"\b(?:residents?|applicants?|candidates?)\s+of\s+([A-Z][A-Za-z ]+)\s+only\b", re.I,
)
_EXPLICIT_COUNTRY_LIST = re.compile(
    r"\b(?:eligible countries|location restrictions|hiring in|applicants?\s+(?:from|in)|"
    r"open to candidates? from|restricted to residents? of|residents? of)\s*:?[ \t]*"
    r"([^.!?;\r\n]{1,140})", re.I,
)


def classify_role_relevance(title: str, description: str = "") -> RoleRelevance:
    """Classify from the existing canonical title-family taxonomy and evidence."""
    family, level, rule = normalize_title(title)
    text = f"{title or ''} {description or ''}"
    if family in (_CORE_FAMILIES - {"data_migration"}) or (
        family == "data_migration" and re.search(r"\bdata\b", title or "", re.I)
    ) or (family == "analytics_bi" and _CORE_TITLE.search(title or "")):
        classification, reason = "core", f"target title family ({family})"
    elif family == "analytics_bi" and _DATA_AI_EVIDENCE.search(text):
        classification, reason = "core", "business-analysis title with data/AI evidence"
    elif family in _KNOWN_NON_TARGET:
        classification, reason = "non_target", f"non-target title family ({family})"
    elif family in {"backend", "devops_platform", "software_engineering", "security", "product", "customer_solutions_engineering"}:
        if _DATA_AI_EVIDENCE.search(text):
            classification, reason = "adjacent", f"adjacent title with data/AI evidence ({family})"
        else:
            classification, reason = "non_target", f"adjacent family lacks data/AI evidence ({family})"
    elif family == "other":
        classification, reason = "unknown", "title did not match a known family"
    else:
        classification, reason = "unknown", f"family needs review ({family})"
    return RoleRelevance(classification, family, level, reason[:160])


_ATS_SUFFIXES = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com",
    "personio.com", "teamtailor.com",
)


def classify_application_access(
    source_id: str,
    listing_url: str,
    application_url: str | None = None,
) -> ApplicationAccess:
    """Recognize public ATS destinations; leave unverified routes unknown."""
    target = (application_url or "").strip() or (listing_url or "").strip()
    host = (urlparse(target).hostname or "").casefold().removeprefix("www.")
    if host and any(host == suffix or host.endswith("." + suffix) for suffix in _ATS_SUFFIXES):
        return ApplicationAccess("ats", "direct_free", target, "recognized public ATS destination")
    source_host = (urlparse(listing_url or "").hostname or "").casefold()
    source = (source_id or "").casefold()
    if target and host and source_host and host == source_host:
        return ApplicationAccess("source", "unknown", target, "listing and application route are not independently verified")
    if target:
        return ApplicationAccess("unknown", "unknown", target, "application destination needs verification")
    return ApplicationAccess("unknown", "unknown", "", f"no application destination for {source or 'source'}")


def classify_founder_geography(
    *,
    description: str = "",
    location_country: str | None = None,
    location_region: str | None = None,
    work_mode: str = "unspecified",
    remote_scope: str = "unspecified",
    remote_scope_regions: tuple[str, ...] | list[str] = (),
) -> tuple[str, str]:
    """Conservative Egypt-specific remote eligibility; employer location alone is not a restriction."""
    text = f"{description or ''} {location_region or ''} {' '.join(remote_scope_regions or ())}"
    if _US_CANDIDATE_RESTRICTION.search(text):
        return "ineligible", "explicit US applicant/residency/work-authorization restriction"

    allow_match = _EGYPT_RESTRICTION.search(text)
    if allow_match:
        restricted_to = (allow_match.group(1) or allow_match.group(2) or "").strip().casefold()
        if "egypt" in restricted_to:
            return "eligible", "explicit applicant residence includes Egypt"
        if restricted_to and "worldwide" not in restricted_to:
            return "ineligible", "explicit applicant residence restriction excludes Egypt"

    # Source-native region restrictions are stronger than a generic location
    # field. Respect an explicit allow-list while leaving unrecognized values
    # unresolved rather than treating them as a negative.
    if remote_scope == "region_restricted" and remote_scope_regions:
        recognized = False
        includes_egypt = False
        for value in remote_scope_regions:
            item = str(value).strip()
            for token, pattern in PLACE_ALIASES:
                if pattern.search(item):
                    recognized = True
                    includes_egypt = includes_egypt or includes(token, "EG")
        if recognized and includes_egypt:
            return "likely_eligible", "source-native allowed regions include Egypt"
        if recognized:
            return "ineligible", "source-native allowed regions exclude Egypt"

    explicit_list = _EXPLICIT_COUNTRY_LIST.search(text)
    if explicit_list:
        tokens = explicit_list.group(1)
        recognized = [
            token for token, pattern in PLACE_ALIASES if pattern.search(tokens)
        ]
        if any(includes(token, "EG") for token in recognized):
            return "likely_eligible", "explicit applicant allow-list includes Egypt"
        if recognized:
            return "ineligible", "explicit applicant allow-list excludes Egypt"

    location = (location_country or "").strip().upper()
    regions = " ".join(str(item) for item in remote_scope_regions or ()).casefold()
    region_text = f"{text} {regions}".casefold()
    if location in {"EG", "EGY", "EGYPT"}:
        return "eligible", "Egypt is an explicit job location"
    if remote_scope == "worldwide" or re.search(r"\b(?:worldwide|global|anywhere)\b", region_text):
        return "likely_eligible", "source explicitly permits worldwide applicants"
    if re.search(r"\b(?:mena|middle east|africa|emea)\b", region_text) and not re.search(
        r"\b(?:mena|africa|emea)\s+(?:excluding|except)\s+egypt\b", region_text
    ):
        return "likely_eligible", "source region includes Egypt (MENA/Africa/EMEA)"
    if work_mode in {"onsite", "on_site"} and location and location not in {"EG", "EGY", "EGYPT"}:
        return "ineligible", "on-site role is outside Egypt"
    # An American employer or office location does not imply a candidate-side
    # restriction; remote jobs with that evidence remain Review.
    return "review", "no explicit Egypt-compatible applicant scope was found"
