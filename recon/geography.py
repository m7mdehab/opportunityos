"""Evidence-backed geographic rule extraction and pure derivation."""
from __future__ import annotations

import re
from dataclasses import replace

from recon.models import Record
from recon.regions import includes


# Description prose is searched only inside candidate/location clauses;
# structured location fields can use this full country and region table.
PLACE_ALIASES = (
    ("EG", re.compile(r"(?<!\w)egypt(?!\w)", re.I)),
    ("US", re.compile(r"(?<!\w)united states(?!\w)", re.I)),
    ("US", re.compile(r"(?<!\w)u\.s\.?(?!\w)", re.I)),
    ("US", re.compile(r"(?<!\w)usa(?!\w)", re.I)),
    # Case-sensitive so the pronoun "us" cannot become a country token.
    ("US", re.compile(r"(?<!\w)US(?!\w)")),
    ("CA", re.compile(r"(?<!\w)canada(?!\w)", re.I)),
    ("GB", re.compile(r"(?<!\w)(?:united kingdom|england|scotland|wales)(?!\w)", re.I)),
    ("GB", re.compile(r"(?<!\w)UK(?!\w)")),
    ("DE", re.compile(r"(?<!\w)germany(?!\w)", re.I)),
    ("AU", re.compile(r"(?<!\w)australia(?!\w)", re.I)),
    ("IN", re.compile(r"(?<!\w)india(?!\w)", re.I)),
    ("FR", re.compile(r"(?<!\w)france(?!\w)", re.I)),
    ("IE", re.compile(r"(?<!\w)ireland(?!\w)", re.I)),
    ("JP", re.compile(r"(?<!\w)japan(?!\w)", re.I)),
    ("ES", re.compile(r"(?<!\w)spain(?!\w)", re.I)),
    ("KR", re.compile(r"(?<!\w)south korea(?!\w)", re.I)),
    ("MX", re.compile(r"(?<!\w)mexico(?!\w)", re.I)),
    ("BR", re.compile(r"(?<!\w)brazil(?!\w)", re.I)),
    ("NL", re.compile(r"(?<!\w)(?:netherlands|holland)(?!\w)", re.I)),
    ("PT", re.compile(r"(?<!\w)portugal(?!\w)", re.I)),
    ("SE", re.compile(r"(?<!\w)sweden(?!\w)", re.I)),
    ("PL", re.compile(r"(?<!\w)poland(?!\w)", re.I)),
    ("AE", re.compile(r"(?<!\w)(?:uae|united arab emirates)(?!\w)", re.I)),
    ("SA", re.compile(r"(?<!\w)saudi arabia(?!\w)", re.I)),
    ("QA", re.compile(r"(?<!\w)qatar(?!\w)", re.I)),
    ("LATAM", re.compile(r"(?<!\w)latam(?!\w)", re.I)),
    ("EEA", re.compile(r"(?<!\w)eea(?!\w)", re.I)),
    ("EU", re.compile(r"(?<!\w)eu(?!\w)", re.I)),
    ("EMEA", re.compile(r"(?<!\w)emea(?!\w)", re.I)),
    ("MENA", re.compile(r"(?<!\w)(?:mena|middle east)(?!\w)", re.I)),
    ("AFRICA", re.compile(r"(?<!\w)africa(?!\w)", re.I)),
)


# Only sufficiently distinctive cities belong here. Ambiguous names such as
# Cambridge and Springfield intentionally require more context and are absent.
CITIES = {
    "cairo": "EG", "alexandria": "EG",
    "seattle": "US", "washington dc": "US", "washington, dc": "US",
    "new york": "US", "san francisco": "US", "austin": "US",
    "dublin": "IE", "paris": "FR", "berlin": "DE", "munich": "DE",
    "amsterdam": "NL", "lisbon": "PT", "stockholm": "SE", "warsaw": "PL",
    "madrid": "ES", "barcelona": "ES",
    "bengaluru": "IN", "bangalore": "IN", "hyderabad": "IN",
    "mumbai": "IN", "new delhi": "IN",
    "tokyo": "JP", "osaka": "JP", "seoul": "KR",
    "alice springs": "AU", "sydney": "AU", "melbourne": "AU",
    "toronto": "CA", "vancouver": "CA",
    "dubai": "AE", "abu dhabi": "AE", "riyadh": "SA", "jeddah": "SA",
    "doha": "QA",
}


US_SUBDIVISIONS = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york",
    "NC": "north carolina", "ND": "north dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island", "SC": "south carolina",
    "SD": "south dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia",
}

CA_SUBDIVISIONS = {
    "AB": "alberta", "BC": "british columbia", "MB": "manitoba",
    "NB": "new brunswick", "NL": "newfoundland and labrador", "NS": "nova scotia",
    "NT": "northwest territories", "NU": "nunavut", "ON": "ontario",
    "PE": "prince edward island", "QC": "quebec", "SK": "saskatchewan",
    "YT": "yukon",
}


IGNORE_WORDS = {
    "remote", "hybrid", "onsite", "on-site", "office", "work from home", "wfh",
    "full-time", "part-time", "contract", "freelance", "n/a", "any", "unstated",
    "anywhere", "flexible", "multiple locations", "various", "worldwide", "global",
}

WORLDWIDE_LOCATION = re.compile(r"(?<!\w)(?:worldwide|global|anywhere)(?!\w)", re.I)
WORLDWIDE_DESCRIPTION_PATTERNS = (
    re.compile(r"\b(?:open to candidates?|candidates?)\b[^.!?;\r\n]{0,120}\b(?:anywhere(?: in the world)?|worldwide|globally|any country)\b", re.I),
    re.compile(r"\bwe hire from any country\b", re.I),
    re.compile(r"\b(?:work|working) from anywhere(?: globally| in the world)?\b", re.I),
    re.compile(r"\banywhere in the world\b", re.I),
)


def _add_rule(rules: list[tuple[str, str]], token: str, evidence: str) -> None:
    """Keep one clear evidence string per extracted token."""
    if not any(existing == token for existing, _ in rules):
        rules.append((token, evidence.strip()))


def _subdivision_match(value: str) -> tuple[str, str] | None:
    """Resolve a subdivision only when paired with a preceding city-like value."""
    match = re.search(r"(?P<city>[A-Za-z][A-Za-z .'-]{1,60}),\s*(?P<sub>[A-Za-z ]+)\s*$", value)
    if not match or match.group("city").strip().lower() in IGNORE_WORDS:
        return None
    subdivision = match.group("sub").strip()
    for token, names in (("US", US_SUBDIVISIONS), ("CA", CA_SUBDIVISIONS)):
        if subdivision in names or subdivision.lower() in names.values():
            return token, match.group(0)
    return None


def _extract_structured_place(value: str, allow: list[tuple[str, str]], restricted_place: bool = False) -> None:
    if not restricted_place:
        worldwide = WORLDWIDE_LOCATION.search(value)
        if worldwide:
            _add_rule(allow, "WORLDWIDE", worldwide.group(0))

    contextual_tokens: set[str] = set()
    for token, pattern in PLACE_ALIASES:
        found = pattern.search(value)
        if found:
            contextual_tokens.add(token)
            _add_rule(allow, token, found.group(0))

    subdivision = _subdivision_match(value)
    if subdivision:
        contextual_tokens.add(subdivision[0])
        _add_rule(allow, *subdivision)

    lowered = value.lower()
    for city, token in CITIES.items():
        found = re.search(rf"(?<!\w){re.escape(city)}(?!\w)", lowered)
        if found and (not contextual_tokens or token in contextual_tokens):
            _add_rule(allow, token, value[found.start():found.end()])


def _description_location_clauses(description: str) -> tuple[str, ...]:
    clauses: list[str] = []
    # The terminator is intentional: a listing must never consume later
    # sentences or the rest of a job-description document.
    explicit_listing = re.compile(
        r"\b(?:eligible countries|hiring in|restricted to residents? of)\s*:?[ \t]*([^\r\n.!?;]+)", re.I,
    )
    candidate_clause = re.compile(
        r"\b(?:open to candidates?|candidates? from|we hire from|applicants? from)\s*:?[ \t]*([^\r\n.!?;]+)", re.I,
    )
    for pattern in (explicit_listing, candidate_clause):
        clauses.extend(match.group(0) for match in pattern.finditer(description))
    return tuple(dict.fromkeys(clauses))


def _structured_description_locations(description: str) -> tuple[str, ...]:
    pattern = re.compile(r"(?im)^\s*(?:job |work )?location\s*:\s*([^\r\n]+)")
    return tuple(match.group(1).strip() for match in pattern.finditer(description))


def _segment_is_known_place(segment: str) -> bool:
    if WORLDWIDE_LOCATION.fullmatch(segment) or segment.lower() in CITIES:
        return True
    return any(pattern.search(segment) for _, pattern in PLACE_ALIASES)


def _extract_unmapped(location_text: str, description: str, allow: list[tuple[str, str]], deny: list[tuple[str, str]]) -> tuple[str, ...]:
    candidates: list[str] = []
    if location_text:
        candidates.extend(re.split(r"[,/|;•·]|\s+[-–—]\s+|\band\b|\bor\b", location_text, flags=re.I))
    if not allow:
        for clause in _description_location_clauses(description):
            candidates.extend(re.split(r"[,/|;•·]|\band\b|\bor\b", clause, flags=re.I))
    unmapped: list[str] = []
    for seg in candidates:
        clean = re.sub(r"^[\s()\[\]{}:\"'.,-]+|[\s()\[\]{}:\"'.,-]+$", "", seg).strip()
        if not clean or len(clean) < 2 or clean.lower() in IGNORE_WORDS:
            continue
        matched_allow = _segment_is_known_place(clean)
        matched_deny = any(re.search(re.escape(evidence), clean, re.I) for _, evidence in deny)
        if not matched_allow and not matched_deny and re.search(r"[a-zA-Z]", clean):
            unmapped.append(clean)
    return tuple(dict.fromkeys(unmapped))


def extract(record: Record) -> Record:
    location_text = record.location_text
    text = " ".join((location_text, record.description))
    allow: list[tuple[str, str]] = []
    deny: list[tuple[str, str]] = []

    restricted_place = bool(re.search(r"\b(?:restricted to residents? of|residents? (?:of|in)|reside|located) (?:in |of )?the EEA\b", text, re.I))

    _extract_structured_place(location_text, allow, restricted_place=restricted_place)
    for structured_location in _structured_description_locations(record.description):
        _extract_structured_place(structured_location, allow, restricted_place=restricted_place)
    for clause in _description_location_clauses(record.description):
        for token, pattern in PLACE_ALIASES:
            if token == "EMEA" and re.search(r"\bemea hours?\b", clause, re.I):
                continue
            found = pattern.search(clause)
            if found:
                _add_rule(allow, token, found.group(0))

    if not restricted_place:
        for pattern in WORLDWIDE_DESCRIPTION_PATTERNS:
            found = pattern.search(record.description)
            if found:
                _add_rule(allow, "WORLDWIDE", found.group(0))
                break

    deny_patterns = (
        (r"no (?:visa )?sponsorship[^.]*|sponsorship (?:is )?not available", "NO_SPONSORSHIP"),
        (r"(?:work authorization|authorized to work|right to work)[^.]*\b(?:united states|u\.s\.?|US|usa|canada)\b|\b(?:US|usa|united states|canadian) work authorization", "WORK_AUTH_REQUIRED:US"),
        (r"(?:residents? (?:of|in)|reside|located) (?:in |of )?the EEA", "RESIDENCY_REQUIRED:EEA"),
        (r"schengen visa", "RESIDENCY_REQUIRED:EU"),
        (r"\bgreen card\b|\b(?:(?:u\.s\.?|US|usa|united states) )?citizenship (?:is )?required\b|\b(?:must\s+(?:possess|hold|have)|needs?(?:\s+to\s+(?:possess|hold|have))?)\s+(?:(?:u\.s\.?|US|usa|united states)\s+)?citizenship\b|\bproof of (?:(?:u\.s\.?|US|usa|united states) )?citizenship\b", "WORK_AUTH_REQUIRED:US"),
        (r"\b(?:US|usa|united states)\s+only\b|\bus-based\b", "RESIDENCY_REQUIRED:US"),
        (r"\bfrance\s+only\b", "RESIDENCY_REQUIRED:FR"),
        (r"\bjapan\s+only\b", "RESIDENCY_REQUIRED:JP"),
        (r"\bbrazil\s+only\b", "RESIDENCY_REQUIRED:BR"),
        (r"\bindia\s+only\b", "RESIDENCY_REQUIRED:IN"),
        (r"\bcanada\s+only\b", "RESIDENCY_REQUIRED:CA"),
        (r"\blatam\s+only\b", "RESIDENCY_REQUIRED:LATAM"),
        (r"\beu\s+only\b", "RESIDENCY_REQUIRED:EU"),
        (r"\b(?:australian) residents? only\b", "RESIDENCY_REQUIRED:AU"),
        (r"\b(?:candidates?|applicants?) must (?:reside|be located|live) in germany\b", "RESIDENCY_REQUIRED:DE"),
        (r"\bapplicants? must live in japan\b", "RESIDENCY_REQUIRED:JP"),
        (r"\bmust be located in brazil\b", "RESIDENCY_REQUIRED:BR"),
        (r"\b(?:applicants?) must be located in australia\b", "RESIDENCY_REQUIRED:AU"),
        (r"\bmust be based in (?:the )?united kingdom\b", "RESIDENCY_REQUIRED:GB"),
    )
    for pattern, token in deny_patterns:
        found = re.search(pattern, text, re.I)
        if found:
            _add_rule(deny, token, found.group(0))

    timezone_patterns = (
        r"\b(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|CET|CEST|EET|EEST|GMT)\s+time\s*zone\b",
        r"\b(?:overlap|availability)[^.\r\n]{0,50}\b(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|CET|CEST|EET|EEST|GMT)\b",
        r"\b\d{1,2}(?::\d{2})?\s*(?:AM|PM)\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM)\s*(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|CET|CEST|EET|EEST|GMT)\b",
        r"\b(?:EMEA|APAC|Americas|European|US)\s+hours?\b",
        r"\bUTC\s*[+-]\s*\d{1,2}(?::?\d{2})?(?:\s*(?:or|to|[-–—])\s*(?:UTC\s*)?[+-]\s*\d{1,2}(?::?\d{2})?)?(?:\s+time\s*zone(?:\s+range)?)?",
    )
    for pattern in timezone_patterns:
        found = re.search(pattern, text, re.I)
        if found:
            _add_rule(deny, "TIMEZONE_ONLY", found.group(0))
            break

    mode = ("onsite", "on-site") if re.search(r"\bon[- ]site\b", text, re.I) else ("hybrid", "hybrid") if re.search(r"\bhybrid\b", text, re.I) else ("remote", "remote") if re.search(r"\bremote\b", text, re.I) else ("unstated", "")
    unmapped = _extract_unmapped(location_text, record.description, allow, deny)
    return replace(record, geo_allow=tuple(allow), geo_deny=tuple(deny), work_mode=mode, unmapped=unmapped)


def eligibility_for(record: Record, country: str = "EG") -> tuple[str, str]:
    country = country.upper()
    for token, evidence in record.geo_deny:
        target = token.split(":", 1)[-1] if ":" in token else ""
        if token == "NO_SPONSORSHIP" or (token != "TIMEZONE_ONLY" and ":" in token and not includes(target, country)):
            return "excluded", evidence
    if any(includes(token, country) for token, _ in record.geo_allow):
        return "eligible", next(evidence for token, evidence in record.geo_allow if includes(token, country))
    if record.geo_allow:
        return "excluded", record.geo_allow[0][1]
    return "unclear", "no mapped geographic rule"
