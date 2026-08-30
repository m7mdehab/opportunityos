"""Deterministic Normalization Engine for OpportunityOS.

Transforms raw feed records into normalized Opportunity representations without
fabrication. All derived fields preserve provenance and fail closed to UNSPECIFIED.
"""
from __future__ import annotations

import datetime
import html
import re
from typing import Any

from recon.classification import classify
from recon.models import Record as ReconRecord
from truth.ingest import CANONICAL_SKILL_ALIASES

from .models import (
    Compensation,
    CompensationInterval,
    EmploymentType,
    GeographicEligibility,
    RemotePolicy,
    SeniorityLevel,
    Track,
)


def clean_text(text: Any) -> str:
    """Strip HTML tags, unescape entities, and normalize whitespace."""
    if text is None:
        return ""
    if isinstance(text, dict):
        values = text.get("eng") or text.get("ENG") or next(iter(text.values()), [])
        text = values[0] if isinstance(values, list) and values else values
    val_str = str(text)
    # Strip HTML tags
    val_no_html = re.sub(r"<[^>]+>", " ", val_str)
    # Unescape HTML entities
    unescaped = html.unescape(val_no_html)
    # Collapse multiple whitespace
    collapsed = re.sub(r"\s+", " ", unescaped).strip()
    return collapsed


_SENIORITY_PATTERNS: tuple[tuple[SeniorityLevel, re.Pattern[str]], ...] = (
    (
        SeniorityLevel.EXECUTIVE,
        re.compile(
            r"\b(?:chief\s+\w+\s+officer|cxo|cto|ceo|cfo|cio|cpo|vice\s+president|vp\b|head\s+of|director\b|managing\s+director)\b",
            re.IGNORECASE,
        ),
    ),
    (
        SeniorityLevel.PRINCIPAL,
        re.compile(r"\b(?:principal|staff|distinguished)\b", re.IGNORECASE),
    ),
    (
        SeniorityLevel.LEAD,
        re.compile(r"\b(?:lead|team\s+lead|tech\s+lead|technical\s+lead)\b", re.IGNORECASE),
    ),
    (
        SeniorityLevel.SENIOR,
        re.compile(r"\b(?:senior|sr\.?)\b", re.IGNORECASE),
    ),
    (
        SeniorityLevel.ENTRY,
        re.compile(r"\b(?:junior|jr\.?|associate|entry\s*level|intern|internship|trainee|graduate)\b", re.IGNORECASE),
    ),
    (
        SeniorityLevel.MID,
        re.compile(r"\b(?:mid\s*level|intermediate|mid-senior)\b", re.IGNORECASE),
    ),
)


def extract_seniority(title: str, text: str = "") -> SeniorityLevel:
    """Deterministically extract seniority from title first, falling back to clean text.
    
    Never guesses; returns UNSPECIFIED if no clear match.
    """
    for level, pattern in _SENIORITY_PATTERNS:
        if pattern.search(title):
            return level
    if text:
        first_paragraph = text[:300]
        for level, pattern in _SENIORITY_PATTERNS:
            if pattern.search(first_paragraph):
                return level
    return SeniorityLevel.UNSPECIFIED


_EMPLOYMENT_TYPE_PATTERNS: tuple[tuple[EmploymentType, re.Pattern[str]], ...] = (
    (
        EmploymentType.FULL_TIME,
        re.compile(r"\b(?:full[-_ ]?time|permanent|fte)\b", re.IGNORECASE),
    ),
    (
        EmploymentType.PART_TIME,
        re.compile(r"\b(?:part[-_ ]?time)\b", re.IGNORECASE),
    ),
    (
        EmploymentType.CONTRACT,
        re.compile(r"\b(?:contract|contractor|fixed[-_ ]?term|c2c|1099)\b", re.IGNORECASE),
    ),
    (
        EmploymentType.FREELANCE,
        re.compile(r"\b(?:freelance|freelancer)\b", re.IGNORECASE),
    ),
    (
        EmploymentType.INTERNSHIP,
        re.compile(r"\b(?:internship|intern)\b", re.IGNORECASE),
    ),
    (
        EmploymentType.TEMPORARY,
        re.compile(r"\b(?:temporary|temp)\b", re.IGNORECASE),
    ),
)


def extract_employment_type(raw_type: str, title: str = "", text: str = "") -> EmploymentType:
    """Deterministically extract employment type."""
    search_space = f"{raw_type} {title} {text[:200]}"
    for emp_type, pattern in _EMPLOYMENT_TYPE_PATTERNS:
        if pattern.search(search_space):
            return emp_type
    return EmploymentType.UNSPECIFIED


_REMOTE_PATTERNS: tuple[tuple[RemotePolicy, re.Pattern[str]], ...] = (
    (
        RemotePolicy.HYBRID,
        re.compile(r"\b(?:hybrid)\b", re.IGNORECASE),
    ),
    (
        RemotePolicy.ON_SITE,
        re.compile(r"\b(?:on[-_ ]?site|in[-_ ]?office|onsite)\b", re.IGNORECASE),
    ),
    (
        RemotePolicy.REMOTE,
        re.compile(r"\b(?:remote|anywhere|work\s+from\s+home|wfh|telecommute|virtual)\b", re.IGNORECASE),
    ),
)


def extract_remote_policy(location_raw: str, text: str = "") -> RemotePolicy:
    """Deterministically extract remote policy."""
    search_space = f"{location_raw} {text[:200]}"
    for policy, pattern in _REMOTE_PATTERNS:
        if pattern.search(search_space):
            return policy
    return RemotePolicy.UNSPECIFIED


_CURRENCY_MAP: dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "usd": "USD",
    "eur": "EUR",
    "gbp": "GBP",
    "cad": "CAD",
    "aud": "AUD",
    "chf": "CHF",
    "aed": "AED",
    "sar": "SAR",
    "egp": "EGP",
}

_COMPENSATION_PATTERN = re.compile(
    r"(?P<curr>[\$€£]|USD|EUR|GBP|CAD|AUD|CHF|AED|SAR|EGP)?\s*"
    r"(?P<min>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+k?)\s*"
    r"(?:-|–|—|to)\s*"
    r"(?P<curr2>[\$€£]|USD|EUR|GBP|CAD|AUD|CHF|AED|SAR|EGP)?\s*"
    r"(?P<max>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+k?)\s*"
    r"(?P<curr3>[\$€£]|USD|EUR|GBP|CAD|AUD|CHF|AED|SAR|EGP)?\s*"
    r"(?:per|\/|\ba\b)?\s*"
    r"(?P<interval>hour|hr|hourly|day|daily|week|weekly|month|monthly|year|yr|yearly|annual|annually)?",
    re.IGNORECASE,
)


def _parse_num(val_str: str) -> float:
    cleaned = val_str.replace(",", "").strip().casefold()
    if cleaned.endswith("k"):
        return float(cleaned[:-1]) * 1000.0
    return float(cleaned)


def extract_compensation(text: str) -> Compensation | None:
    """Extract explicit compensation range from structured text."""
    if not text:
        return None
    match = _COMPENSATION_PATTERN.search(text)
    if not match:
        return None

    curr_token = match.group("curr") or match.group("curr2") or match.group("curr3")
    currency = _CURRENCY_MAP.get(curr_token.strip().casefold()) if curr_token else None

    try:
        min_val = _parse_num(match.group("min"))
        max_val = _parse_num(match.group("max"))
    except (ValueError, AttributeError):
        return None

    interval_str = (match.group("interval") or "").casefold()
    interval = CompensationInterval.UNSPECIFIED
    if interval_str in {"hour", "hr", "hourly"}:
        interval = CompensationInterval.HOURLY
    elif interval_str in {"day", "daily"}:
        interval = CompensationInterval.DAILY
    elif interval_str in {"week", "weekly"}:
        interval = CompensationInterval.WEEKLY
    elif interval_str in {"month", "monthly"}:
        interval = CompensationInterval.MONTHLY
    elif interval_str in {"year", "yr", "yearly", "annual", "annually"}:
        interval = CompensationInterval.YEARLY

    if min_val > max_val:
        min_val, max_val = max_val, min_val

    return Compensation(
        min_amount=min_val,
        max_amount=max_val,
        currency=currency,
        interval=interval,
    )


def parse_iso_date(raw_date: Any) -> str | None:
    """Deterministically parse dates into ISO 8601 calendar date YYYY-MM-DD or full UTC string."""
    if raw_date is None:
        return None
    if isinstance(raw_date, (int, float)):
        # Timestamp (seconds or milliseconds)
        ts = raw_date if raw_date < 1e11 else raw_date / 1000.0
        try:
            dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return None

    s = str(raw_date).strip()
    if not s:
        return None

    # Try ISO calendar date YYYY-MM-DD
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if iso_match:
        return iso_match.group(1)

    # Try standard string date formats (e.g. RSS / RFC 2822: Sun, 30 Aug 2026 12:00:00 GMT)
    formats = (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    )
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


OPPORTUNITY_SKILL_CATALOG: dict[str, str] = {
    **CANONICAL_SKILL_ALIASES,
    "terraform": "Terraform",
    "rust": "Rust",
    "golang": "Go",
    "go": "Go",
    "fastapi": "FastAPI",
    "graphql": "GraphQL",
    "kafka": "Kafka",
    "redis": "Redis",
    "linux": "Linux",
    "pytorch": "PyTorch",
    "django": "Django",
    "flask": "Flask",
}


def extract_skills_from_text(text: str) -> tuple[str, ...]:
    """Extract recognized normalized skill aliases from text."""
    if not text:
        return ()
    text_lower = text.casefold()
    found: set[str] = set()
    for alias, canonical in OPPORTUNITY_SKILL_CATALOG.items():
        # Match whole words (handling C#, Go, etc.)
        if alias in {"c#", "go", "c"}:
            pattern = rf"(?<!\w){re.escape(alias)}(?!\w)"
        else:
            pattern = rf"\b{re.escape(alias)}\b"
        if re.search(pattern, text_lower):
            found.add(canonical)
    return tuple(sorted(found))


def extract_list_sections(html_or_markdown: str, header_regex: str) -> tuple[str, ...]:
    """Extract bulleted or numbered items following a section header."""
    if not html_or_markdown:
        return ()
    match = re.search(header_regex, html_or_markdown, re.IGNORECASE)
    if not match:
        return ()
    subtext = html_or_markdown[match.end():]
    # Stop at the next major heading
    next_header = re.search(r"<h[1-6][^>]*>|^(?:#{1,6}\s|[A-Z][A-Za-z\s]{3,20}:)", subtext, re.MULTILINE)
    if next_header:
        subtext = subtext[:next_header.start()]

    # Extract <li> items
    li_items = re.findall(r"<li[^>]*>(.*?)</li>", subtext, re.IGNORECASE | re.DOTALL)
    if li_items:
        return tuple(clean_text(item) for item in li_items if clean_text(item))

    # Extract lines starting with - or * or numbers
    bullets = re.findall(r"^\s*[-*•\d+.]\s+(.+)$", subtext, re.MULTILINE)
    if bullets:
        return tuple(clean_text(b) for b in bullets if clean_text(b))

    return ()


def derive_geographic_eligibility(
    title: str,
    location_raw: str,
    description: str,
    track: Track = Track.EMPLOYMENT,
    source: str = "",
    url: str = "",
) -> GeographicEligibility:
    """Integrate with recon.classification.classify() to compute conservative geographic eligibility."""
    recon_rec = ReconRecord(
        source=source,
        track=track.value,
        title=title,
        organization="",
        location_text=location_raw,
        url=url,
        posted_date="",
        description=description,
        raw_payload_pointer="",
    )
    classification = classify(recon_rec)
    return GeographicEligibility(
        status=classification.eligibility,
        reason=classification.eligibility_reason,
        individual_eligibility=classification.individual_eligibility,
        individual_reason=classification.individual_reason,
    )
