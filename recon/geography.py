"""Evidence-backed geographic rule extraction and pure derivation."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from recon.models import Record
from recon.regions import REGIONS, includes


def _alias(token: str, expression: str, flags: int = re.I) -> tuple[str, re.Pattern[str]]:
    return token, re.compile(rf"(?<!\w)(?:{expression})(?!\w)", flags)


# Description prose is searched only inside hiring/location clauses. Structured
# location fields may use this complete country and region alias table.
PLACE_ALIASES = (
    _alias("EG", "egypt"),
    _alias("US", r"united states|u\.s\.?|usa"),
    _alias("US", "US", 0),  # Case-sensitive: the pronoun "us" is not a country.
    _alias("CA", "canada"),
    _alias("GB", "united kingdom|england|scotland|wales"),
    _alias("GB", "UK", 0),
    _alias("DE", "germany"), _alias("AU", "australia"), _alias("IN", "india"),
    _alias("FR", "france"), _alias("IE", "ireland"), _alias("JP", "japan"),
    _alias("ES", "spain"), _alias("KR", "south korea"), _alias("MX", "mexico"),
    _alias("BR", "brazil"), _alias("NL", "netherlands|holland"),
    _alias("PT", "portugal"), _alias("SE", "sweden"), _alias("PL", "poland"),
    _alias("AE", "uae|united arab emirates"), _alias("SA", "saudi arabia"),
    _alias("QA", "qatar"), _alias("CY", "cyprus"), _alias("CO", "colombia"),
    _alias("IL", "israel"), _alias("SG", "singapore"), _alias("NZ", "new zealand"),
    _alias("AR", "argentina"), _alias("CL", "chile"), _alias("PE", "peru"),
    _alias("ZA", "south africa"),
    _alias("CN", "china"),
    _alias("HK", "hong kong"),
    _alias("IT", "italy"),
    _alias("KH", "cambodia"),
    _alias("TT", "trinidad and tobago|trinidad|tobago"),
    _alias("LATAM", "latam"),
    _alias("AMERICAS", "americas|north america|south america"),
    _alias("EEA", "eea"), _alias("EU", "eu"), _alias("EMEA", "emea"),
    _alias("MENA", "mena|middle east"),
    _alias("AFRICA", r"(?<!south\s)africa"),
)


# Ambiguous city names such as Cambridge and Springfield intentionally require
# more context and are absent.
CITIES = {
    "cairo": "EG", "alexandria": "EG", "giza": "EG",
    "dubai": "AE", "abu dhabi": "AE", "riyadh": "SA", "jeddah": "SA", "doha": "QA",
    "sf": "US", "nyc": "US", "new york city": "US", "new york": "US",
    "san francisco": "US", "chicago": "US", "boston": "US", "atlanta": "US",
    "denver": "US", "seattle": "US", "austin": "US", "washington dc": "US",
    "washington, dc": "US", "dallas": "US", "dallas warehouse": "US",
    "london": "GB", "sherborne": "GB", "glasgow": "GB", "newcastle upon tyne": "GB",
    "manchester": "GB", "edinburgh": "GB", "bristol": "GB",
    "bengaluru": "IN", "bangalore": "IN", "hyderabad": "IN", "mumbai": "IN",
    "new delhi": "IN", "chennai": "IN", "greater chennai area": "IN", "pune": "IN",
    "gurugram": "IN",
    "toronto": "CA", "vancouver": "CA", "montreal": "CA", "quebec": "CA",
    "grand falls-windsor": "CA", "ottawa": "CA", "calgary": "CA",
    "sao paulo": "BR", "rio de janeiro": "BR", "tel aviv": "IL", "jerusalem": "IL",
    "sydney": "AU", "melbourne": "AU", "alice springs": "AU", "brisbane": "AU", "perth": "AU",
    "parramatta": "AU", "rozelle": "AU",
    "tokyo": "JP", "osaka": "JP", "kyoto": "JP", "singapore": "SG", "seoul": "KR",
    "beijing": "CN", "hong kong": "HK", "phnom penh": "KH", "milan": "IT",
    "piarco": "TT", "limassol": "CY",
    "berlin": "DE", "munich": "DE", "frankfurt": "DE", "paris": "FR",
    "amsterdam": "NL", "dublin": "IE", "madrid": "ES", "barcelona": "ES",
    "lisbon": "PT", "stockholm": "SE", "warsaw": "PL",
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
    "PE": "prince edward island", "QC": "quebec", "SK": "saskatchewan", "YT": "yukon",
}

IGNORE_WORDS = {
    "remote", "hybrid", "onsite", "on-site", "office", "work from home", "wfh",
    "full-time", "part-time", "contract", "freelance", "n/a", "any", "unstated",
    "anywhere", "flexible", "multiple locations", "various", "worldwide", "global",
}

WORLDWIDE_LOCATION = re.compile(r"(?<!\w)(?:worldwide|global|anywhere)(?!\w)", re.I)
TIMEZONE_BOUNDARY = r"(?:eastern|central|mountain|pacific)\s+time\s*zone"
WITHIN_RESTRICTION = r"(?:\s+within\s+(?:the\s+)?(?:united states|u\.s\.?|usa|US|canada|uk|europe|america|[a-z ]+time\s*zone))"
WORLDWIDE_DESCRIPTION_PATTERNS = (
    re.compile(
        rf"\b(?:open to|available to|accepting)\s+(?:qualified\s+)?(?:candidates?|applicants?)\b"
        rf"[^.!?;\r\n]{{0,120}}\b(?:anywhere(?!{WITHIN_RESTRICTION})(?!\s+(?:within|in)\s+(?:the\s+)?{TIMEZONE_BOUNDARY})"
        r"(?:\s+in\s+the\s+world)?|worldwide|globally|any country)\b", re.I,
    ),
    re.compile(r"\b(?:candidates?|applicants?)\s+from\s+(?:any country|anywhere(?: in the world)?|worldwide)\b", re.I),
    re.compile(r"\bwe\s+(?:hire|recruit|employ)\s+from\s+(?:any country|anywhere(?: in the world)?|worldwide)\b", re.I),
    re.compile(
        rf"\b(?:candidates?|applicants?|employees?|you)\b[^.!?;\r\n]{{0,80}}\b"
        rf"(?:work|be based|be located)\s+(?:from\s+)?(?:anywhere(?!{WITHIN_RESTRICTION})(?!\s+(?:within|in)\s+(?:the\s+)?{TIMEZONE_BOUNDARY})"
        r"(?:\s+(?:globally|in the world))?|worldwide)\b", re.I,
    ),
    re.compile(rf"\bwork from anywhere(?!{WITHIN_RESTRICTION})(?:\s+(?:globally|in the world))?\b", re.I),
    re.compile(r"\b(?:this|the)\s+(?:role|position|job)\s+is\s+(?:open|available)\s+(?:to\s+applicants?\s+)?(?:anywhere(?: in the world)?|worldwide|globally)\b", re.I),
)
PRODUCT_BOILERPLATE = re.compile(r"\b(?:products?|platform|software|users?|customers?|teams?|collaborat\w*|real[ -]time|empowers?)\b", re.I)
HIRING_CONTEXT = re.compile(r"\b(?:applicants?|candidates?|employees?|role|position|job|we hire|you)\b", re.I)


def _normalize_location(value: str) -> str:
    """Repair common UTF-8-as-Latin-1 mojibake and fold accents for matching."""
    normalized = value
    if any(marker in normalized for marker in ("Ã", "Â", "â")):
        try:
            normalized = normalized.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return "".join(
        char for char in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(char)
    )


def _add_rule(rules: list[tuple[str, str]], token: str, evidence: str) -> None:
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
    if not restricted_place and (worldwide := WORLDWIDE_LOCATION.search(value)):
        _add_rule(allow, "WORLDWIDE", worldwide.group(0))
    for token, pattern in PLACE_ALIASES:
        if found := pattern.search(value):
            _add_rule(allow, token, found.group(0))
    if subdivision := _subdivision_match(value):
        _add_rule(allow, *subdivision)
    lowered = value.lower()
    for city, token in CITIES.items():
        if found := re.search(rf"(?<!\w){re.escape(city)}(?!\w)", lowered):
            _add_rule(allow, token, value[found.start():found.end()])


def _description_location_clauses(description: str) -> tuple[str, ...]:
    patterns = (
        re.compile(r"\b(?:eligible countries|hiring in|restricted to residents? of)\s*:?[ \t]*([^\r\n.!?;]+)", re.I),
        re.compile(r"\b(?:open to candidates?|candidates? from|we hire from|applicants? from)\s*:?[ \t]*([^\r\n.!?;]+)", re.I),
        re.compile(r"\b(?:work|located|based)\s+(?:from\s+)?anywhere\s+within\s*:?[ \t]*([^\r\n.!?;]+)", re.I),
    )
    clauses = [match.group(0) for pattern in patterns for match in pattern.finditer(description)]
    return tuple(dict.fromkeys(clauses))


def _structured_description_locations(description: str) -> tuple[str, ...]:
    pattern = re.compile(r"(?im)^\s*(?:job |work )?location\s*:\s*([^\r\n]+)")
    return tuple(_normalize_location(match.group(1).strip()) for match in pattern.finditer(description))


def _worldwide_description_match(description: str) -> re.Match[str] | None:
    for pattern in WORLDWIDE_DESCRIPTION_PATTERNS:
        for found in pattern.finditer(description):
            start = max(description.rfind(mark, 0, found.start()) for mark in ".!?;\n") + 1
            ends = [index for mark in ".!?;\n" if (index := description.find(mark, found.end())) >= 0]
            sentence = description[start:min(ends, default=len(description))]
            if PRODUCT_BOILERPLATE.search(sentence) and not HIRING_CONTEXT.search(sentence):
                continue
            return found
    return None


def _segment_is_known_place(segment: str) -> bool:
    return bool(
        WORLDWIDE_LOCATION.fullmatch(segment)
        or segment.lower() in CITIES
        or any(pattern.search(segment) for _, pattern in PLACE_ALIASES)
    )


def _extract_unmapped(location_text: str, description: str, allow: list[tuple[str, str]], deny: list[tuple[str, str]]) -> tuple[str, ...]:
    candidates = re.split(r"[,/|;•·]|\s+[-–—]\s+|\band\b|\bor\b", location_text, flags=re.I) if location_text else []
    if not allow:
        for clause in _description_location_clauses(description):
            candidates.extend(re.split(r"[,/|;•·]|\band\b|\bor\b", clause, flags=re.I))
    unmapped: list[str] = []
    for segment in candidates:
        clean = re.sub(r"^[\s()\[\]{}:\"'.,-]+|[\s()\[\]{}:\"'.,-]+$", "", segment).strip()
        matched_deny = any(re.search(re.escape(evidence), clean, re.I) for _, evidence in deny)
        if clean and len(clean) >= 2 and clean.lower() not in IGNORE_WORDS and not _segment_is_known_place(clean) and not matched_deny and re.search(r"[a-zA-Z]", clean):
            unmapped.append(clean)
    return tuple(dict.fromkeys(unmapped))


US_COUNTRY = r"(?:united states|u\.s\.?|usa|US)"
CA_PROVINCE = r"(?:alberta|british columbia|manitoba|new brunswick|newfoundland(?: and labrador)?|nova scotia|ontario|prince edward island|quebec|saskatchewan)"
DENY_PATTERNS = (
    (re.compile(r"\b(?:no (?:visa )?sponsorship|sponsorship (?:is )?not available|without sponsorship for an employment visa|will not sponsor)\b[^.\r\n]*", re.I), "NO_SPONSORSHIP"),
    (re.compile(rf"\b(?:verify\s+(?:your|their)\s+eligibility\s+to\s+work\s+in|authorized\s+to\s+work\s+in|work\s+authorization\s+in|right\s+to\s+work\s+in)\s+(?:the\s+)?{US_COUNTRY}\b", re.I), "WORK_AUTH_REQUIRED:US"),
    (re.compile(rf"\b{US_COUNTRY}\s+work\s+authorization\b|\bwork\s+authorization\s+(?:is\s+)?required[^.\r\n]{{0,40}}\b{US_COUNTRY}\b", re.I), "WORK_AUTH_REQUIRED:US"),
    (re.compile(r"\bcanadian work authorization\b|\bauthorized to work in canada\b", re.I), "WORK_AUTH_REQUIRED:CA"),
    (re.compile(r"\bgreen card\b|\b(?:(?:u\.s\.?|US|usa|united states) )?citizenship (?:is )?required\b|\b(?:applicants?|candidates?)\s+(?:must|needs?|need to)(?:\s+(?:possess|hold|have))?\s+(?:(?:u\.s\.?|US|usa|united states)\s+)?citizenship\b|\bproof of (?:(?:u\.s\.?|US|usa|united states) )?citizenship(?: is)? required\b", re.I), "WORK_AUTH_REQUIRED:US"),
    (re.compile(r"\b(?:residents? (?:of|in)|reside|located) (?:in |of )?the EEA\b", re.I), "RESIDENCY_REQUIRED:EEA"),
    (re.compile(r"\bschengen visa\b", re.I), "RESIDENCY_REQUIRED:EU"),
    (re.compile(rf"\b(?:candidates?|applicants?)\s+(?:residing|who reside|must reside)\s+in\s+[^.\r\n]{{0,180}}\b{CA_PROVINCE}\b", re.I), "RESIDENCY_REQUIRED:CA"),
    (re.compile(r"\bmust live in a state where\b[^.\r\n]{0,160}\bhas a registered entity\b", re.I), "RESIDENCY_REQUIRED:US"),
    (re.compile(rf"\b{US_COUNTRY}\s+only\b|\bus-based\s+(?:role|position|job|candidate|applicant|employee)\b", re.I), "RESIDENCY_REQUIRED:US"),
    (re.compile(r"\bfrance\s+only\b", re.I), "RESIDENCY_REQUIRED:FR"),
    (re.compile(r"\bjapan\s+only\b", re.I), "RESIDENCY_REQUIRED:JP"),
    (re.compile(r"\bbrazil\s+only\b", re.I), "RESIDENCY_REQUIRED:BR"),
    (re.compile(r"\bindia\s+only\b", re.I), "RESIDENCY_REQUIRED:IN"),
    (re.compile(r"\bcanada\s+only\b", re.I), "RESIDENCY_REQUIRED:CA"),
    (re.compile(r"\blatam\s+only\b", re.I), "RESIDENCY_REQUIRED:LATAM"),
    (re.compile(r"\beu\s+only\b", re.I), "RESIDENCY_REQUIRED:EU"),
    (re.compile(r"\baustralian residents? only\b", re.I), "RESIDENCY_REQUIRED:AU"),
    (re.compile(r"\b(?:candidates?|applicants?) must (?:reside|be located|live) in germany\b", re.I), "RESIDENCY_REQUIRED:DE"),
    (re.compile(r"\bapplicants? must live in japan\b", re.I), "RESIDENCY_REQUIRED:JP"),
    (re.compile(r"\bmust be located in brazil\b", re.I), "RESIDENCY_REQUIRED:BR"),
    (re.compile(r"\bapplicants? must be located in australia\b", re.I), "RESIDENCY_REQUIRED:AU"),
    (re.compile(r"\bmust be based in (?:the )?united kingdom\b", re.I), "RESIDENCY_REQUIRED:GB"),
)

TIMEZONE_PATTERNS = (
    re.compile(r"\b(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|CET|CEST|EET|EEST|UTC|GMT)\b"),
    re.compile(r"\b(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|CET|CEST|EET|EEST|GMT)\s+time\s*zone\b", re.I),
    re.compile(r"\b(?:US\s+)?(?:Eastern|Central|Mountain|Pacific)\s+Time\b", re.I),
    re.compile(r"\b(?:eastern|central|mountain|pacific|greenwich mean|central european)\s+time\s*(?:zone|time)\b", re.I),
    re.compile(r"\b(?:overlap|availability|working hours?|schedule)[^.\r\n]{0,80}\b(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|CET|CEST|EET|EEST|UTC|GMT)\b", re.I),
    re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:AM|PM)\s*[-–—]\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM)\s*(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|CET|CEST|EET|EEST|UTC|GMT)\b", re.I),
    re.compile(r"\b(?:EMEA|APAC|Americas|European|US)\s+hours?\b", re.I),
    re.compile(r"\bUTC\s*[+-]\s*\d{1,2}(?::?\d{2})?(?:\s*(?:or|to|[-–—])\s*(?:UTC\s*)?[+-]\s*\d{1,2}(?::?\d{2})?)?(?:\s+time\s*zone(?:\s+range)?)?", re.I),
)


def extract(record: Record) -> Record:
    location_text = _normalize_location(record.location_text)
    text = " ".join((location_text, record.description))
    allow: list[tuple[str, str]] = []
    deny: list[tuple[str, str]] = []
    restricted_place = bool(re.search(r"\b(?:restricted to residents? of|residents? (?:of|in)|reside|located) (?:in |of )?the EEA\b", text, re.I))

    _extract_structured_place(location_text, allow, restricted_place)
    for structured_location in _structured_description_locations(record.description):
        _extract_structured_place(structured_location, allow, restricted_place)
    for clause in _description_location_clauses(record.description):
        normalized_clause = _normalize_location(clause)
        for token, pattern in PLACE_ALIASES:
            if token != "EMEA" or not re.search(r"\bemea hours?\b", normalized_clause, re.I):
                if found := pattern.search(normalized_clause):
                    _add_rule(allow, token, found.group(0))

    if not restricted_place and (worldwide := _worldwide_description_match(record.description)):
        _add_rule(allow, "WORLDWIDE", worldwide.group(0))

    timezone_boundary = re.search(
        rf"\b(?:candidates?|applicants?)\b[^.!?;\r\n]{{0,80}}\blocated\s+anywhere\s+within\s+(?:the\s+)?{TIMEZONE_BOUNDARY}\b",
        record.description, re.I,
    )
    if timezone_boundary:
        _add_rule(allow, "US", timezone_boundary.group(0))

    for pattern, token in DENY_PATTERNS:
        if found := pattern.search(text):
            _add_rule(deny, token, found.group(0))
    for pattern in TIMEZONE_PATTERNS:
        if found := pattern.search(text):
            _add_rule(deny, "TIMEZONE_ONLY", found.group(0))
            break

    mode = (
        ("onsite", "on-site") if re.search(r"\bon[- ]site\b", text, re.I)
        else ("hybrid", "hybrid") if re.search(r"\bhybrid\b", text, re.I)
        else ("remote", "remote") if re.search(r"\bremote\b", text, re.I)
        else ("unstated", "")
    )
    unmapped = _extract_unmapped(location_text, record.description, allow, deny)
    return replace(record, location_text=location_text, geo_allow=tuple(allow), geo_deny=tuple(deny), work_mode=mode, unmapped=unmapped)


def eligibility_for(record: Record, country: str = "EG") -> tuple[str, str]:
    """Derive eligibility from stored rules; restrictions always win."""
    country = country.upper()
    timezone_evidence: str | None = None
    for token, evidence in record.geo_deny:
        if token == "NO_SPONSORSHIP":
            return "excluded", evidence
        if token == "TIMEZONE_ONLY":
            timezone_evidence = evidence
            continue
        condition, separator, target = token.partition(":")
        if separator and condition in {"WORK_AUTH_REQUIRED", "RESIDENCY_REQUIRED", "ENTITY_REQUIRED"} and not includes(target, country):
            return "excluded", evidence

    specific_allows = [(token, evidence) for token, evidence in record.geo_allow if token not in REGIONS]
    if timezone_evidence is not None:
        if specific_allows and not any(includes(token, country) for token, _ in specific_allows):
            return "excluded", specific_allows[0][1]
        return "unclear", timezone_evidence

    if any(token == "WORLDWIDE" for token, _ in record.geo_allow) and specific_allows:
        for token, evidence in specific_allows:
            if includes(token, country):
                return "eligible", evidence
        return "excluded", specific_allows[0][1]

    for token, evidence in record.geo_allow:
        if includes(token, country):
            return "eligible", evidence
    if record.geo_allow:
        return "excluded", record.geo_allow[0][1]
    return "unclear", "no mapped geographic rule"
