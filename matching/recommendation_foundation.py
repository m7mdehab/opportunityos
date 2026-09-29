"""Small, deterministic opportunity-side signals for the BC recommendation path.

These classifications stay separate: title relevance does not imply eligibility,
and eligibility does not imply application accessibility. Unknown evidence stays
unknown so later recommendation logic can route it to review.
"""
from __future__ import annotations

import re
from html import unescape
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
_TARGET_ROLE_EVIDENCE = re.compile(
    r"\b(?:data\s+(?:engineering|platform|pipeline|analytics|science|quality|governance|management|warehouse|infrastructure|migration)|"
    r"analytics\s+engineering|machine\s+learning|mlops|artificial\s+intelligence|"
    r"(?:ai|ml|llm)\s+(?:engineering|engineer|platform|infrastructure)|"
    r"etl|dbt|lakehouse|feature\s+store|vector\s+database)\b", re.I,
)
_TARGET_TITLE_EVIDENCE = re.compile(
    r"(?:" + _TARGET_ROLE_EVIDENCE.pattern[:-2] + r"|\b(?:ai|ml|llm)\b)", re.I,
)
_CONSUMER_AI_APP_TITLE = re.compile(r"\bAI\s+Neobank\s+App\b", re.I)
_TECHNICAL_PRODUCT_SCOPE = re.compile(
    r"\b(?:data|analytics|machine\s+learning|ml|ai)\s+"
    r"(?:platform|infrastructure|engineering)\b",
    re.I,
)
_NON_TARGET_DOMAIN_TITLE = re.compile(
    r"\b(?:electrical|mechanical|structural|civil|chemical|industrial|manufacturing|"
    r"process|aerospace|automotive|BESS|EPC|payroll|recruit(?:er|ing|ment)|"
    r"account\s+executive|customer\s+service|risk\s+analyst|IT\s+operations|"
    r"field\s+service|construction|gardener|marketing|sales)\b", re.I,
)
_COMPANY_SECTION = re.compile(
    r"\b(?:about\s+(?:us|the\s+company|our\s+company)|who\s+we\s+are|"
    r"company\s+overview|equal\s+opportunity|eeo\s+statement)\b", re.I,
)
_GEOGRAPHY_COMPANY_SECTION_HEADING = re.compile(
    r"(?im)(?:^|\n)\s*(?:about\s+us|about\s+(?:the|our)\s+company|who\s+we\s+are|"
    r"company\s+overview|equal\s+opportunity(?:\s+employer)?|eeo(?:\s+statement)?|"
    r"benefits|our\s+culture)\s*:?\s*(?:\n|$)"
)


def _role_description(title: str, description: str) -> str:
    """Remove markup and company boilerplate before checking role evidence."""
    plain = unescape(re.sub(r"<[^>]*>", " ", description or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    company_section = _COMPANY_SECTION.search(plain)
    if company_section:
        plain = plain[:company_section.start()]
    return f"{title or ''} {plain[:6000]}"
_US_CANDIDATE_RESTRICTION = re.compile(
    r"\b(?:US|U\.S\.|USA|United States)(?:[- ]based)?\s+"
    r"(?:applicants?|candidates?|residents?|employees?)\s+only\b|"
    r"\b(?:must|only)\s+(?:be\s+)?(?:located|reside|live|based)\s+in\s+"
    r"(?:the\s+)?(?:US|U\.S\.|USA|United States)\b|"
    r"\bremote\s*(?:[-–—(:]\s*)?(?:US|U\.S\.|USA|United States)\b"
    r"(?!\s+(?:(?:business|working)\s+)?hours?\b|\s+time\s*zones?\b)|"
    r"\|\s*(?:US|U\.S\.|USA|United States)\s*\|\s*remote\b|"
    r"\b(?:must|only)\s+be\s+based\s+in\s+(?:the\s+)?"
    r"(?:US|U\.S\.|USA|United States)\b(?!\s+(?:(?:eastern|central|mountain|pacific)\s+)?time\s*zone|\s+hours?)|"
    r"\b(?:US|U\.S\.|USA|United States)\s+work\s+authorization\s+(?:is\s+)?required\b|"
    r"\bmust\s+be\s+authorized\s+to\s+work\s+in\s+(?:the\s+)?(?:US|U\.S\.|USA|United States)\b|"
    r"\b(?:US|U\.S\.|USA|United States)\s+citizenship\s+required\b|"
    r"\bmust\s+be\s+(?:a\s+)?U\.?S\.?\s+citizen\b", re.I,
)
_US_RESIDENCY_RESTRICTION = re.compile(
    r"\b(?:US|U\.S\.|USA|United States)(?:[- ]based)?\s+(?:applicants?|candidates?|residents?)\s+only\b|"
    r"\b(?:must|only)\s+(?:be\s+)?(?:located|reside|live)\s+in\s+(?:the\s+)?"
    r"(?:US|U\.S\.|USA|United States)\b|"
    r"\bremote\s*(?:(?:[-–—(:]\s*)|(?:within|in)\s+)?(?:US|U\.S\.|USA|United States)\b"
    r"(?!\s+(?:(?:business|working)\s+)?hours?\b|\s+time\s*zones?\b)|"
    r"\b(?:US|U\.S\.|USA|United States)\s*(?:\|\s*)?(?:\(\s*)?remote\b|"
    r"\|\s*(?:US|U\.S\.|USA|United States)\s*\|\s*remote\b|"
    r"\b(?:must|only)\s+be\s+based\s+in\s+(?:the\s+)?(?:US|U\.S\.|USA|United States)\b"
    r"(?!\s+(?:(?:eastern|central|mountain|pacific)\s+)?time\s*zone|\s+hours?)", re.I,
)
_US_WORK_AUTH_REQUIREMENT = re.compile(
    r"\b(?:US|U\.S\.|USA|United States)\s+work\s+authorization\s+(?:is\s+)?required\b|"
    r"\bmust\s+be\s+authorized\s+to\s+work\s+in\s+(?:the\s+)?(?:US|U\.S\.|USA|United States)\b", re.I,
)
_US_CITIZENSHIP_REQUIREMENT = re.compile(
    r"\b(?:US|U\.S\.|USA|United States)\s+citizenship\s+required\b|"
    r"\bmust\s+be\s+(?:a\s+)?U\.?S\.?\s+citizen\b", re.I,
)
_EGYPT_RESTRICTION = re.compile(
    r"\b(?:must|only)\s+(?:be\s+)?(?:located|reside|live|based)\s+in\s+"
    r"(?:the\s+)?([A-Z][A-Za-z ]+)\b|"
    r"\b(?:residents?|applicants?|candidates?)\s+of\s+([A-Z][A-Za-z ]+)\s+only\b", re.I,
)
_EXPLICIT_COUNTRY_LIST = re.compile(
    r"\b(?:eligible countries|location restrictions|hiring in|applicants?\s+(?:from|in)|"
    r"open to candidates? from|restricted to residents? of|residents? of)\s*:?[ \t]*"
    r"([^.!?;\r\n]{1,140})", re.I,
)
_EXPLICIT_REMOTE_SCOPE = re.compile(
    r"\bremote(?:\s+(?:role|position|work))?\s*(?:from|in|within|across|[-:])\s*"
    r"(?:anywhere|worldwide|globally|the\s+world|MENA|Middle\s+East|Africa|EMEA)\b|"
    r"\b(?:globally|worldwide|anywhere(?:\s+in\s+the\s+world)?)\s+remote\b|"
    r"\b(?:remote|work[- ]from[- ]home|home[- ]based)\s+(?:roles?|positions?|work)\s+"
    r"(?:are\s+)?(?:available|open)\s+(?:to\s+(?:applicants?|candidates?)\s+)?"
    r"(?:anywhere(?:\s+in\s+the\s+world)?|worldwide|globally)\b|"
    r"\bwork[- ]from[- ]home\s+(?:roles?|positions?)\s+(?:are\s+)?available\s+worldwide\b|"
    r"\bremote\s+(?:roles?|positions?)\s+(?:(?:with|has|have)\s+)?(?:globally\s+distributed\s+)?teams?\s+"
    r"in\s+all\s+time\s+zones\b|"
    r"\bremote\s+(?:roles?|positions?)?\s*based\s+(?:remotely\s+)?in\s+"
    r"(?:MENA|Middle\s+East|Africa|EMEA)\b|"
    r"\bbased\s+remotely\s+in\s+(?:the\s+)?(?:MENA|Middle\s+East|Africa|EMEA)\b|"
    r"\bwork\s+from\s+anywhere(?:\s+in\s+the\s+world)?\b|"
    r"\bremote\b.{0,100}\bteams?\s+in\s+all\s+time\s+zones\b|"
    r"\b(?:globally\s+distributed\s+)?teams?\s+in\s+all\s+time\s+zones\b.{0,80}\bremote\b|"
    r"\b(?:open|available|accepting)\s+(?:to\s+)?(?:remote\s+)?(?:applications?|candidates?|applicants?)\s+"
    r"(?:(?:from|in|across)\s+)?(?:anywhere|worldwide|globally|MENA|Middle\s+East|Africa|EMEA)\b|"
    r"\bwe\s+hire\s+(?:from\s+)?(?:anywhere|worldwide|globally)\b|"
    r"\bwe\s+are\s+hiring\s+(?:from\s+)?(?:anywhere|worldwide|globally)\b|"
    r"\b(?:worldwide|global|MENA|Middle\s+East|Africa|EMEA)\s+remote\s+"
    r"(?:applicants?|candidates?|positions?|roles?)\b", re.I,
)
_US_PLACE = re.compile(
    r"\b(?:US|U\.S\.|USA|United States|AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|"
    r"MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|"
    r"DC)\b", re.I,
)
_REQUIRED_CREDENTIAL = re.compile(
    r"\b(?:(?:active|current|valid)\s+)?(?:top\s+secret|secret|TS\s*/\s*SCI(?:\s+with\s+polygraph)?|"
    r"security\s+clearance|professional\s+(?:license|licence|certification)|"
    r"(?:license|licence|certification)\s+in\s+[A-Z][\w.+/# -]{1,50})\b", re.I,
)
_REQUIRED_CONTEXT = re.compile(
    r"\b(?:required|must\s+(?:have|hold|maintain|possess)|need\s+to\s+(?:have|hold)|"
    r"eligib(?:le|ility)\s+to\s+obtain|ability\s+to\s+obtain)\b|"
    r"\bsecurity\s+clearance\s*[:\-]", re.I,
)
_PHYSICAL_LOCATION_LINE = re.compile(
    r"(?im)(?:^\s*(?:job\s+)?(?:work\s+)?location\s*:\s*([^\n]{1,240})$|"
    r"^\s*(?:work\s+mode|work\s+arrangement|schedule)\s*:\s*([^\n]{1,180})$)"
)
_PHYSICAL_MODE = re.compile(r"\b(?:on[- ]?site|in[- ]office|hybrid)\b", re.I)
_REMOTE_MODE = re.compile(r"\bremote\b", re.I)
_REQUIRED_OFFICE_ATTENDANCE = re.compile(
    r"\b(?:requires?|must|expected)\b.{0,100}\b\d+\s*[-–—]\s*\d+\s+days?\s+"
    r"(?:per|a)\s+(?:week|wk)\b.{0,100}\b(?:in|at)\s+(?:the\s+)?office\b",
    re.I,
)
_UTC_RANGE = re.compile(
    r"\b(?:UTC|GMT)\s*([+-])\s*(\d{1,2})\s*(?:hours?|hrs?)?\s*(?:to|through|[–—])\s*"
    r"(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})\b", re.I,
)
_CET_TOLERANCE = re.compile(r"\bCET\s*(?:±|\+\s*/\s*-|plus\s*/\s*minus)\s*(\d{1,2})\s*[- ]?\s*(?:hours?|hrs?)\b", re.I)


def _plain_job_text(value: str) -> str:
    """Decode source HTML while keeping block boundaries for evidence matching."""
    plain = unescape(value or "")
    # Descriptions from some ATS payloads are HTML-escaped twice.
    plain = unescape(plain)
    plain = re.sub(r"(?i)<br\s*/?>|</(?:p|li|h[1-6]|div|section|tr)>|</?ul\b[^>]*>", "\n", plain)
    plain = re.sub(r"<[^>]*>", " ", plain)
    plain = re.sub(r"&nbsp;|\u00a0", " ", plain, flags=re.I)
    return re.sub(r"[ \t]+", " ", plain)


def _geography_job_text(value: str) -> str:
    """Keep role-specific geography and drop trailing employer boilerplate."""
    text = _plain_job_text(value)
    heading = _GEOGRAPHY_COMPANY_SECTION_HEADING.search(text)
    if heading:
        text = text[:heading.start()]
    return text


def _description_physical_mode(text: str) -> tuple[str | None, str | None]:
    """Return a physical mode only when a job-specific location/mode line states it."""
    for match in _PHYSICAL_LOCATION_LINE.finditer(text):
        line = next((group for group in match.groups() if group), "")
        modes = _PHYSICAL_MODE.findall(line)
        if not modes:
            continue
        if _REMOTE_MODE.search(line):
            return "ambiguous", line.strip()
        mode = "hybrid" if any(item.casefold() == "hybrid" for item in modes) else "onsite"
        return mode, line.strip()
    return None, None


def _remote_time_window_includes_egypt(text: str) -> bool:
    normalized = text.replace("−", "-").replace("﹣", "-")
    for match in _UTC_RANGE.finditer(normalized):
        start = int(match.group(2)) * (1 if match.group(1) == "+" else -1)
        end = int(match.group(4)) * (1 if match.group(3) == "+" else -1)
        low, high = sorted((start, end))
        if low <= 2 and high >= 3:
            return True
    for match in _CET_TOLERANCE.finditer(normalized):
        tolerance = int(match.group(1))
        if 1 - tolerance <= 2 and 1 + tolerance >= 3:
            return True
    return False


def _remote_country_tokens(text: str) -> set[str]:
    if not _REMOTE_MODE.search(text or ""):
        return set()
    country_tokens = {
        "EG", "US", "CA", "GB", "DE", "AU", "IN", "FR", "IE", "JP", "ES", "KR", "MX", "BR",
        "NL", "PT", "SE", "PL", "AE", "SA", "QA", "CY", "CO", "IL", "SG", "NZ", "AR", "CL",
        "PE", "ZA", "CN", "HK", "IT", "KH", "TT",
    }
    return {
        token for token, pattern in PLACE_ALIASES
        if token in country_tokens and pattern.search(text or "")
    }


def _verified_us_work_authorization(truth_graph) -> str:
    """Return verified, contradicted, or unknown using linked Truth Graph facts."""
    if truth_graph is None:
        return "unknown"
    from truth import predicates
    from truth.models import Polarity, VerificationStatus

    assertions = tuple(getattr(truth_graph, "assertions", {}).values())
    jurisdictions = [
        item for item in assertions
        if item.predicate == predicates.WORK_AUTHORIZATION_JURISDICTION
        and item.verification_status == VerificationStatus.VERIFIED
        and re.search(r"\b(?:US|U\.S\.|USA|United States)\b", str(item.value), re.I)
    ]
    if not jurisdictions:
        return "unknown"
    for jurisdiction in jurisdictions:
        statuses = [
            item for item in assertions
            if item.subject_id == jurisdiction.subject_id
            and item.predicate == predicates.WORK_AUTHORIZATION_STATUS
            and item.verification_status == VerificationStatus.VERIFIED
        ]
        for status in statuses:
            if status.polarity == Polarity.NEGATIVE or re.search(
                r"\b(?:unauthorized|not authorized|ineligible|expired|denied)\b",
                str(status.value), re.I,
            ):
                return "contradicted"
            if status.polarity == Polarity.POSITIVE and re.search(
                r"\b(?:authorized|eligible|permitted|citizen|permanent resident)\b",
                str(status.value), re.I,
            ):
                return "verified"
    return "unknown"


def _founder_permits_relocation(location_evidence: str, truth_graph) -> bool:
    """Honor only verified Founder relocation preferences naming this place."""
    if truth_graph is None:
        return False
    from truth import predicates
    from truth.models import Modality, Polarity, VerificationStatus

    assertions = tuple(getattr(truth_graph, "assertions", {}).values())
    for assertion in assertions:
        if (
            assertion.predicate != predicates.PREFERENCE_RELOCATION
            or assertion.verification_status != VerificationStatus.VERIFIED
            or assertion.modality == Modality.PLANNED
            or assertion.polarity != Polarity.POSITIVE
        ):
            continue
        preference = str(assertion.value)
        if re.search(r"\b(?:anywhere|worldwide|any country|global(?:ly)?)\b", preference, re.I):
            return True
        destination_tokens = {
            token for token, pattern in PLACE_ALIASES if pattern.search(location_evidence)
        }
        preference_tokens = {
            token for token, pattern in PLACE_ALIASES if pattern.search(preference)
        }
        if destination_tokens.intersection(preference_tokens):
            return True
    return False


def _credential_name_matches(requirement: str, credential_name: str) -> bool:
    requirement = re.sub(r"\b(?:active|current|valid|required)\b", " ", requirement.casefold())
    requirement = re.sub(r"\s+", " ", requirement).strip()
    credential_name = re.sub(r"\s+", " ", credential_name.casefold()).strip()
    if "top secret" in requirement:
        return "top secret" in credential_name or "ts/sci" in credential_name
    if "ts/sci" in requirement:
        return "ts/sci" in credential_name
    if re.search(r"\bsecret\b", requirement):
        return bool(re.search(r"\bsecret\b|ts/sci", credential_name))
    if "security clearance" in requirement:
        return bool(re.search(r"\b(?:clearance|secret|ts/sci)\b", credential_name))
    requirement = re.sub(r"\b(?:professional|license|licence|certification)\b", " ", requirement)
    requirement = re.sub(r"\s+", " ", requirement).strip()
    return bool(requirement and requirement in credential_name)


def classify_required_credentials(
    description: str, truth_graph=None,
) -> tuple[str | None, str | None]:
    """Require verified Truth Graph evidence for material applicant credentials.

    Returns ``(None, None)`` when the posting has no material credential gate,
    ``("review", reason)`` when possession is not verified, and
    ``("ineligible", reason)`` only for a verified contradiction.
    """
    text = _plain_job_text(description)
    required_spans: list[str] = []
    for match in _REQUIRED_CREDENTIAL.finditer(text):
        window = text[max(0, match.start() - 120): min(len(text), match.end() + 100)]
        if _REQUIRED_CONTEXT.search(window):
            required_spans.append(match.group(0).casefold())
    if not required_spans:
        return None, None

    from truth import predicates
    from truth.models import Modality, Polarity, VerificationStatus

    assertions = tuple(getattr(truth_graph, "assertions", {}).values()) if truth_graph is not None else ()
    names = [
        assertion for assertion in assertions
        if assertion.predicate == predicates.CERTIFICATION_NAME
        and assertion.verification_status == VerificationStatus.VERIFIED
        and assertion.modality != Modality.PLANNED
        and any(_credential_name_matches(term, str(assertion.value)) for term in required_spans)
    ]
    if any(assertion.polarity == Polarity.NEGATIVE for assertion in names):
        return "ineligible", "founder_lacks_required_credential"
    positive = [assertion for assertion in names if assertion.polarity == Polarity.POSITIVE]
    if positive:
        subjects = {assertion.subject_id for assertion in positive}
        states = [
            assertion for assertion in assertions
            if assertion.subject_id in subjects
            and assertion.predicate == predicates.CERTIFICATION_STATE
            and assertion.verification_status == VerificationStatus.VERIFIED
            and assertion.modality != Modality.PLANNED
        ]
        if states and all(str(assertion.value).casefold() != "expired" for assertion in states):
            return None, None
    requires_clearance = any(
        re.search(r"\b(?:top\s+secret|secret|TS\s*/\s*SCI|security\s+clearance)\b", item, re.I)
        for item in required_spans
    )
    reason = "required_clearance_unverified" if requires_clearance else "required_credential_unverified"
    return "review", reason


def classify_role_relevance(title: str, description: str = "") -> RoleRelevance:
    """Classify from the existing canonical title-family taxonomy and evidence."""
    family, level, rule = normalize_title(title)
    text = _role_description(title, description)
    title_text = title or ""
    # AI can name the product being built rather than the role's technical
    # domain. Do not turn consumer-product titles into AI engineering roles.
    title_target = bool(
        _TARGET_TITLE_EVIDENCE.search(title_text)
        and not _CONSUMER_AI_APP_TITLE.search(title_text)
    )
    role_target = bool(_TARGET_ROLE_EVIDENCE.search(text))
    if _NON_TARGET_DOMAIN_TITLE.search(title or ""):
        return RoleRelevance("non_target", family, level, "non-target domain named in title")
    if family in (_CORE_FAMILIES - {"data_migration"}) or (
        family == "data_migration" and re.search(r"\bdata\b", title or "", re.I)
    ) or (family == "analytics_bi" and _CORE_TITLE.search(title or "")):
        classification, reason = "core", f"target title family ({family})"
    elif family == "analytics_bi" and role_target:
        classification, reason = "core", "business-analysis title with data/AI evidence"
    elif family in _KNOWN_NON_TARGET:
        classification, reason = "non_target", f"non-target title family ({family})"
    elif family == "product":
        if _TECHNICAL_PRODUCT_SCOPE.search(title_text):
            classification, reason = "adjacent", "product role explicitly scoped to a data/AI platform or infrastructure"
        else:
            classification, reason = "non_target", "product role is not a target technical discipline"
    elif family in {"backend", "devops_platform", "software_engineering", "security", "customer_solutions_engineering"}:
        # Broad software/backend/security/solutions titles are adjacent only
        # when the role itself names a data/AI domain. Description keywords
        # alone are too easily inherited from company boilerplate.
        if title_target:
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
    title: str = "",
    description: str = "",
    location_country: str | None = None,
    location_city: str | None = None,
    location_region: str | None = None,
    work_mode: str = "unspecified",
    remote_scope: str = "unspecified",
    remote_scope_regions: tuple[str, ...] | list[str] = (),
    truth_graph=None,
) -> tuple[str, str]:
    """Resolve Egypt eligibility with job-specific evidence above company boilerplate.

    Structural work mode/location, applicant restrictions and source-native
    eligibility data take precedence over generic remote/global phrasing.
    Employer location by itself does not disqualify a remote role.
    """
    title_text = title or ""
    job_text = _geography_job_text(description)
    applicant_text = f"{title_text}\n{job_text}"
    title_remote_countries = _remote_country_tokens(title_text)
    source_remote_countries = _remote_country_tokens(str(location_region or ""))
    if title_remote_countries and source_remote_countries and not title_remote_countries.intersection(source_remote_countries):
        return "review", "title and source remote-country labels conflict"
    residency_text = f"{applicant_text}\n{location_region or ''}"
    residency_match = _US_RESIDENCY_RESTRICTION.search(residency_text)
    if residency_match:
        prior = residency_text[max(0, residency_match.start() - 180):residency_match.start()]
        prior_sentence = re.split(r"[.!?\n]", prior)[-1]
        salary_scoped = re.search(r"\b(?:salary|compensation|pay|pay\s+range|base\s+range)\b", prior_sentence, re.I)
    else:
        salary_scoped = None
    if residency_match and not salary_scoped:
        return "ineligible", "explicit US applicant/residency restriction"
    explicitly_includes_egypt = False
    allow_match = _EGYPT_RESTRICTION.search(job_text)
    if allow_match:
        restricted_to = (allow_match.group(1) or allow_match.group(2) or "").strip().casefold()
        if re.fullmatch(
            r"(?:the\s+)?(?:us|u\.s\.|usa|united states)\s+"
            r"(?:(?:eastern|central|mountain|pacific)\s+)?time\s*zone",
            restricted_to, re.I,
        ):
            restricted_to = ""
        if "egypt" in restricted_to:
            explicitly_includes_egypt = True
        if restricted_to and "worldwide" not in restricted_to:
            if "egypt" not in restricted_to:
                return "ineligible", "explicit applicant residence restriction excludes Egypt"

    explicit_list = _EXPLICIT_COUNTRY_LIST.search(job_text)
    if explicit_list:
        tokens = explicit_list.group(1)
        recognized = [token for token, pattern in PLACE_ALIASES if pattern.search(tokens)]
        if recognized and not any(includes(token, "EG") for token in recognized):
            return "ineligible", "explicit applicant allow-list excludes Egypt"
        explicitly_includes_egypt = explicitly_includes_egypt or any(
            includes(token, "EG") for token in recognized
        )

    location = (location_country or "").strip().upper()
    outside_egypt = bool(location and location not in {"EG", "EGY", "EGYPT"})
    location_evidence = f"{location_region or ''} {location_country or ''} {location_city or ''}"
    described_mode, described_location = _description_physical_mode(job_text)
    effective_mode = work_mode
    if work_mode in {"unspecified", "remote", ""} and described_mode:
        effective_mode = described_mode
        location_evidence = f"{location_evidence} {described_location or ''}"
    if work_mode == "remote" and not described_mode:
        attendance = _REQUIRED_OFFICE_ATTENDANCE.search(job_text)
        if attendance:
            effective_mode = "onsite"
            location_evidence = f"{location_evidence} {attendance.group(0)}"
    if effective_mode == "ambiguous":
        return "review", "job description mixes remote and physical attendance requirements"
    if effective_mode in {"onsite", "on_site", "hybrid"}:
        if location in {"EG", "EGY", "EGYPT"}:
            return "eligible", "required workplace is in Egypt"
        described_places = [
            token for token, pattern in PLACE_ALIASES if described_location and pattern.search(described_location)
        ]
        evidence_places = [
            token for token, pattern in PLACE_ALIASES if pattern.search(location_evidence)
        ]
        if location in {"EG", "EGY", "EGYPT"}:
            return "eligible", "required workplace is in Egypt"
        if outside_egypt and described_places and any(includes(token, "EG") for token in described_places):
            if not any(not includes(token, "EG") for token in described_places):
                return "review", "structured and job-description workplace locations conflict"
        if not outside_egypt and described_places and all(includes(token, "EG") for token in described_places):
            return "eligible", "required workplace is in Egypt"
        if outside_egypt or evidence_places or described_places or _US_PLACE.search(location_evidence):
            if _founder_permits_relocation(location_evidence, truth_graph):
                return "review", "Founder permits relocation but destination work authorization is unresolved"
            return "ineligible", "required onsite/hybrid workplace is outside Egypt"
        return "review", "required onsite/hybrid workplace location is unresolved"

    # A physical worksite outside Egypt is decisive before checking separate
    # citizenship/export-control clauses that may be scoped to another office.
    if _US_CITIZENSHIP_REQUIREMENT.search(applicant_text):
        return "review", "required_us_citizenship_unverified"
    if _US_WORK_AUTH_REQUIREMENT.search(applicant_text):
        authorization = _verified_us_work_authorization(truth_graph)
        if authorization == "contradicted":
            return "ineligible", "required_us_work_authorization_contradicted"
        if authorization != "verified":
            return "review", "required_us_work_authorization_unverified"

    if explicitly_includes_egypt:
        return "likely_eligible", "explicit applicant scope includes Egypt"

    # Some source-native remote listings encode their hiring region in the
    # location label (for example, "Brazil & Latin America / Remote") while
    # an older generic inference has also populated remote_scope=worldwide.
    # Treat a remote-tagged, recognized region label as the narrower scope;
    # company prose and a broad inferred flag cannot override it.
    region_label = str(location_region or "")
    if work_mode == "remote" and re.search(r"\b(?:MENA|Middle\s+East|Africa|EMEA)\b", region_label, re.I):
        if not re.search(r"\b(?:MENA|Middle\s+East|Africa|EMEA)\s+(?:excluding|except)\s+Egypt\b", region_label, re.I):
            return "likely_eligible", "source remote region includes Egypt"
    if re.search(r"\bremote\b", region_label, re.I):
        recognized_regions = [
            token for token, pattern in PLACE_ALIASES if pattern.search(region_label)
        ]
        if recognized_regions and not any(includes(token, "EG") for token in recognized_regions):
            return "ineligible", "remote location label restricts applicants outside Egypt"
        if any(includes(token, "EG") for token in recognized_regions):
            return "likely_eligible", "remote location label includes Egypt"

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

    regions = " ".join(str(item) for item in remote_scope_regions or ()).casefold()
    region_text = f"{regions}".casefold()
    if location in {"EG", "EGY", "EGYPT"}:
        return "eligible", "Egypt is an explicit job location"
    if remote_scope == "worldwide" or re.search(r"\b(?:worldwide|anywhere)\b", region_text):
        return "likely_eligible", "source explicitly permits worldwide applicants"
    if re.search(r"\b(?:mena|middle east|africa|emea)\b", region_text) and not re.search(
        r"\b(?:mena|africa|emea)\s+(?:excluding|except)\s+egypt\b", region_text
    ):
        return "likely_eligible", "source region includes Egypt (MENA/Africa/EMEA)"
    if _EXPLICIT_REMOTE_SCOPE.search(f"{title_text}\n{job_text}"):
        return "likely_eligible", "job-specific remote scope includes Egypt"
    if (work_mode == "remote" or _REMOTE_MODE.search(title_text)) and _remote_time_window_includes_egypt(job_text):
        return "likely_eligible", "remote time-zone window includes Egypt"
    # Global employer descriptions, benefits, offices, and company geography
    # do not prove that a candidate based in Egypt may apply.
    return "review", "no explicit Egypt-compatible applicant scope was found"
