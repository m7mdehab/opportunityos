"""Deterministic Normalization and Atomic Lineage Engine for OpportunityOS.

Transforms raw feed records into normalized Opportunity representations without
data fabrication. Material fields preserve atomic field-level provenance.
"""
from __future__ import annotations

import datetime
import functools
import hashlib
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from recon.classification import classify
from recon.models import Record as ReconRecord
from truth.ingest import CANONICAL_SKILL_ALIASES

from .models import (
    Compensation,
    CompensationInterval,
    DerivationType,
    EmploymentType,
    FieldProvenance,
    GeographicEligibility,
    RemotePolicy,
    RemoteScope,
    SeniorityLevel,
    Track,
    WorkMode,
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


def compute_record_checksum(raw_item: Any) -> str:
    """Compute deterministic SHA-256 checksum for a single raw item payload."""
    if isinstance(raw_item, str):
        payload = raw_item.encode("utf-8")
    else:
        import json
        try:
            payload = json.dumps(raw_item, sort_keys=True).encode("utf-8")
        except Exception:
            payload = str(raw_item).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def create_field_provenance(
    field_name: str,
    raw_val: Any,
    norm_val: Any,
    derivation_type: DerivationType | str,
    raw_pointer: str,
    record_checksum: str,
    rule_id: str,
) -> FieldProvenance:
    """Construct an immutable FieldProvenance record."""
    dtype = derivation_type.value if isinstance(derivation_type, DerivationType) else str(derivation_type)
    return FieldProvenance(
        field_name=field_name,
        raw_value=str(raw_val) if raw_val is not None else "",
        normalized_value=str(norm_val) if norm_val is not None else "",
        derivation_type=dtype,
        raw_pointer=raw_pointer,
        record_checksum=record_checksum,
        rule_id=rule_id,
    )


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
        re.compile(r"\b(?:mid[-_ ]?level|intermediate|mid[-_ ]?senior)\b", re.IGNORECASE),
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


def extract_track(
    default_track: Track,
    raw_type: str = "",
    title: str = "",
    text: str = "",
) -> Track:
    """Determine real track without collapsing contract or freelance into employment."""
    if default_track == Track.PROCUREMENT:
        return Track.PROCUREMENT

    combined = f"{raw_type} {title} {text[:200]}".casefold()
    if re.search(r"\b(?:freelance|freelancer)\b", combined):
        return Track.FREELANCE
    if re.search(r"\b(?:contract|contractor|c2c|1099|fixed[-_ ]?term)\b", combined):
        return Track.CONTRACT
    if re.search(r"\b(?:tender|procurement|rfp|eoi|rfq)\b", combined):
        return Track.PROCUREMENT

    return default_track


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


# ---------------------------------------------------------------------------
# BRIEF-FR-006 A1: work_mode / location / remote_scope text-inference engine.
#
# ``opportunity/inference_rules.yaml`` is the committed, ordered rule table
# (id, regex pattern, and the fields it sets). Rules run ONLY over fields an
# adapter did not already map from a native source field -- adapter-native
# mapping always wins (see ``extract_work_location``'s ``native_*`` kwargs).
# Rules are data, not code: a new rule can be added to the YAML file without
# touching this module.
# ---------------------------------------------------------------------------

_INFERENCE_RULES_PATH = Path(__file__).resolve().parent / "inference_rules.yaml"

# ISO-3166-1 alpha-2 country code aliases (name/abbreviation -> code, all keys
# casefolded) used both to resolve a captured "(<country/region> only)" group
# and, indirectly, to keep the generated ``country_*`` rules in
# ``inference_rules.yaml`` consistent with this table (see the codegen script
# referenced in the FR-006 A1 report; this table is the hand-committed
# artifact, not a runtime import of that script).
COUNTRY_ALIASES: dict[str, str] = {
    'algeria': 'DZ', 'argentina': 'AR', 'australia': 'AU', 'austria': 'AT',
    'bahrain': 'BH', 'bangladesh': 'BD', 'belgium': 'BE', 'brazil': 'BR',
    'canada': 'CA', 'chile': 'CL', 'china': 'CN', 'colombia': 'CO',
    'czech republic': 'CZ', 'czechia': 'CZ', 'denmark': 'DK', 'egypt': 'EG',
    'egy': 'EG', 'finland': 'FI', 'france': 'FR', 'germany': 'DE',
    'ghana': 'GH', 'greece': 'GR', 'hungary': 'HU', 'india': 'IN',
    'indonesia': 'ID', 'ireland': 'IE', 'israel': 'IL', 'italy': 'IT',
    'japan': 'JP', 'jordan': 'JO', 'kenya': 'KE', 'kuwait': 'KW',
    'lebanon': 'LB', 'malaysia': 'MY', 'mexico': 'MX', 'morocco': 'MA',
    'netherlands': 'NL', 'the netherlands': 'NL', 'holland': 'NL',
    'new zealand': 'NZ', 'nigeria': 'NG', 'norway': 'NO', 'oman': 'OM',
    'pakistan': 'PK', 'peru': 'PE', 'philippines': 'PH', 'poland': 'PL',
    'portugal': 'PT', 'qatar': 'QA', 'romania': 'RO', 'saudi arabia': 'SA',
    'singapore': 'SG', 'south africa': 'ZA', 'south korea': 'KR', 'korea': 'KR',
    'spain': 'ES', 'sweden': 'SE', 'switzerland': 'CH', 'thailand': 'TH',
    'tunisia': 'TN', 'turkey': 'TR', 'ukraine': 'UA',
    'united arab emirates': 'AE', 'uae': 'AE',
    'united kingdom': 'GB', 'uk': 'GB', 'u.k.': 'GB', 'great britain': 'GB',
    'united states': 'US', 'usa': 'US', 'united states of america': 'US',
    'u.s.': 'US', 'u.s.a.': 'US', 'vietnam': 'VN',
}

# Recognised region codes (as used by remote_scope_regions) that are not a
# single ISO-3166 country.
REGION_ALIASES: dict[str, str] = {
    'apac': 'APAC', 'canada': 'CA', 'emea': 'EMEA', 'eu': 'EU',
    'europe': 'EU', 'european union': 'EU', 'latam': 'LATAM',
    'u.k.': 'GB', 'u.s.': 'US', 'uk': 'GB', 'united kingdom': 'GB',
    'united states': 'US', 'us': 'US', 'usa': 'US',
}


def country_code_to_name(iso2_or_region: str) -> str:
    """Best-effort reverse lookup: ISO-2/region code -> a human-readable name.

    Falls back to the code itself when unrecognised (never fabricates a name).
    """
    if not iso2_or_region:
        return ""
    code = iso2_or_region.strip().upper()
    for name, mapped in COUNTRY_ALIASES.items():
        if mapped == code and " " not in name and len(name) > 2:
            # Prefer a canonical multi-letter alias (e.g. "egypt" over "egy").
            return name.title()
    for name, mapped in COUNTRY_ALIASES.items():
        if mapped == code:
            return name.title()
    return code


@functools.lru_cache(maxsize=1)
def _load_inference_rules() -> tuple[dict[str, Any], ...]:
    """Load and compile ``inference_rules.yaml`` once per process."""
    if not _INFERENCE_RULES_PATH.exists():
        return ()
    with open(_INFERENCE_RULES_PATH, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    raw_rules = doc.get("rules", []) if isinstance(doc, dict) else []
    compiled: list[dict[str, Any]] = []
    for raw_rule in raw_rules:
        rule_id = raw_rule["id"]
        channel = raw_rule.get("channel", "location")
        compiled.append(
            {
                "id": rule_id,
                "regex": re.compile(raw_rule["pattern"]),
                "sets": dict(raw_rule.get("sets") or {}),
                "region_from_group": raw_rule.get("region_from_group"),
                "location_from_group": raw_rule.get("location_from_group"),
                "channel": channel,
            }
        )
    return tuple(compiled)


def _resolve_location_string(location_text: str) -> dict[str, tuple[Any, str]]:
    """Resolve an explicit location string against location-channel rules."""
    cleaned = clean_text(location_text).strip(" ,;.-")
    if not cleaned:
        return {}
    res: dict[str, tuple[Any, str]] = {}
    for r in _load_inference_rules():
        if r["channel"] not in ("location", "both"):
            continue
        m = r["regex"].search(cleaned)
        if not m:
            continue
        for f, v in r["sets"].items():
            if f not in res:
                res[f] = (v, r["id"])
    return res


def _resolve_region_tokens(raw_group: str) -> tuple[str, ...]:
    """Split a captured '<country/region list>' group and resolve each token."""
    tokens = re.split(r",|&|/|\band\b|\bor\b", raw_group, flags=re.IGNORECASE)
    codes: list[str] = []
    for tok in tokens:
        key = clean_text(tok).casefold().strip()
        if not key:
            continue
        code = COUNTRY_ALIASES.get(key) or REGION_ALIASES.get(key)
        if code and code not in codes:
            codes.append(code)
    return tuple(codes)


_WORK_MODE_BY_VALUE: dict[str, WorkMode] = {m.value: m for m in WorkMode}
_REMOTE_SCOPE_BY_VALUE: dict[str, RemoteScope] = {s.value: s for s in RemoteScope}


@dataclass(frozen=True, slots=True)
class WorkLocationExtraction:
    """Result of :func:`extract_work_location`."""
    work_mode: WorkMode = WorkMode.UNSPECIFIED
    work_mode_source: str = "none"  # "adapter" | "inference" | "none"
    work_mode_rule_id: str = ""
    location_country: str = ""
    location_city: str = ""
    location_region: str = ""
    remote_scope: RemoteScope = RemoteScope.UNSPECIFIED
    remote_scope_regions: tuple[str, ...] = ()


def extract_work_mode(location_raw: str, text: str = "") -> WorkMode:
    """Standalone work-mode-only extraction (brief vocabulary: remote | hybrid |
    onsite | unspecified). Convenience wrapper around
    :func:`extract_work_location` for callers that only need the mode."""
    return extract_work_location(location_raw, text).work_mode


def extract_work_location(
    location_raw: str,
    text: str = "",
    *,
    native_work_mode: WorkMode | None = None,
    native_country: str = "",
    native_city: str = "",
    native_region: str = "",
) -> WorkLocationExtraction:
    """Adapter-native mapping first, text inference second (BRIEF-FR-006 A1).

    Segregates inference into deterministic evidence channels:
    - Channel A (Location Channel): bare geographic/location tokens operate on
      raw_location, explicit source location field, or equivalent typed metadata.
    - Channel B (Description Channel): description text infers work mode or
      location strictly from explicit role/candidate semantics (e.g. 'this role is
      remote', 'work from anywhere', 'role location: Cairo', 'must be based in...').
      Generic employer/customer prose ('global company', 'customers in California',
      'teams anywhere') never creates unsupported job facts.
    """
    resolved: dict[str, Any] = {}
    rule_ids: dict[str, str] = {}

    if native_work_mode is not None and native_work_mode != WorkMode.UNSPECIFIED:
        resolved["work_mode"] = native_work_mode.value
        rule_ids["work_mode"] = "adapter_native"
    if native_country:
        norm_country = native_country.strip().upper()
        if len(norm_country) != 2:
            norm_country = COUNTRY_ALIASES.get(native_country.strip().casefold(), "")
        if norm_country:
            resolved["location_country"] = norm_country
            rule_ids["location_country"] = "adapter_native"
    if native_city:
        resolved["location_city"] = native_city.strip()
        rule_ids["location_city"] = "adapter_native"
    if native_region:
        resolved["location_region"] = native_region.strip()
        rule_ids["location_region"] = "adapter_native"

    rules = _load_inference_rules()

    # Channel A: Location-channel rules (evaluate raw_location)
    loc_clean = location_raw.strip()
    if loc_clean:
        for rule in rules:
            if rule["channel"] not in ("location", "both"):
                continue
            match = rule["regex"].search(loc_clean)
            if not match:
                continue

            region_group = rule.get("region_from_group")
            if region_group is not None and "remote_scope_regions" not in resolved:
                try:
                    captured = match.group(region_group)
                except IndexError:  # pragma: no cover - defensive
                    captured = ""
                codes = _resolve_region_tokens(captured) if captured else ()
                if not codes:
                    continue
                resolved["remote_scope_regions"] = list(codes)
                rule_ids["remote_scope_regions"] = rule["id"]

            loc_group = rule.get("location_from_group")
            if loc_group is not None:
                try:
                    captured_loc = match.group(loc_group)
                except IndexError:  # pragma: no cover - defensive
                    captured_loc = ""
                loc_res = _resolve_location_string(captured_loc)
                for f, (v, rid) in loc_res.items():
                    if f not in resolved:
                        resolved[f] = v
                        rule_ids[f] = rid

            for field, value in rule["sets"].items():
                if field in resolved:
                    continue
                resolved[field] = value
                rule_ids[field] = rule["id"]

    # Channel B: Description-channel rules (explicit role/candidate semantics ONLY)
    # Scan the complete committed description.  Source adapters retain the
    # full payload text, and some ATS-native role tags (for example Greenhouse
    # ``#LI-Hybrid``/``#LI-Onsite`` markers) are appended after the body.  A
    # prefix-only scan silently discarded those explicit posting signals.
    desc_clean = text.strip()
    if desc_clean:
        for rule in rules:
            if rule["channel"] not in ("description", "both"):
                continue
            match = rule["regex"].search(desc_clean)
            if not match:
                continue

            loc_group = rule.get("location_from_group")
            if loc_group is not None:
                try:
                    captured_loc = match.group(loc_group)
                except IndexError:  # pragma: no cover - defensive
                    captured_loc = ""
                loc_res = _resolve_location_string(captured_loc)
                for f, (v, rid) in loc_res.items():
                    if f not in resolved:
                        resolved[f] = v
                        rule_ids[f] = rid

            region_group = rule.get("region_from_group")
            if region_group is not None and "remote_scope_regions" not in resolved:
                try:
                    captured = match.group(region_group)
                except IndexError:  # pragma: no cover - defensive
                    captured = ""
                codes = _resolve_region_tokens(captured) if captured else ()
                if not codes:
                    continue
                resolved["remote_scope_regions"] = list(codes)
                rule_ids["remote_scope_regions"] = rule["id"]

            for field, value in rule["sets"].items():
                if field in resolved:
                    continue
                resolved[field] = value
                rule_ids[field] = rule["id"]

    work_mode_value = resolved.get("work_mode", WorkMode.UNSPECIFIED.value)
    work_mode = _WORK_MODE_BY_VALUE.get(work_mode_value, WorkMode.UNSPECIFIED)
    if rule_ids.get("work_mode") == "adapter_native":
        work_mode_source = "adapter"
    elif "work_mode" in resolved:
        work_mode_source = "inference"
    else:
        work_mode_source = "none"

    remote_scope_value = resolved.get("remote_scope", RemoteScope.UNSPECIFIED.value)
    remote_scope = _REMOTE_SCOPE_BY_VALUE.get(remote_scope_value, RemoteScope.UNSPECIFIED)
    remote_scope_regions = tuple(resolved.get("remote_scope_regions", ()))

    return WorkLocationExtraction(
        work_mode=work_mode,
        work_mode_source=work_mode_source,
        work_mode_rule_id=rule_ids.get("work_mode", ""),
        location_country=resolved.get("location_country", ""),
        location_city=resolved.get("location_city", ""),
        location_region=resolved.get("location_region", ""),
        remote_scope=remote_scope,
        remote_scope_regions=remote_scope_regions,
    )


_CURRENCY_MAP: dict[str, str] = {
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
    r"(?:(?P<label>\b(?:salary|pay|rate|compensation|remuneration|stipend)\b[\s:]*)?"
    r"(?P<curr>USD|EUR|GBP|CAD|AUD|CHF|AED|SAR|EGP|[\$€£])?\s*"
    r"(?P<min>\d{1,3}(?:,\d{3})*(?:\.\d+)?k?|\d+k?)\s*"
    r"(?:-|–|—|to)\s*"
    r"(?P<curr2>USD|EUR|GBP|CAD|AUD|CHF|AED|SAR|EGP|[\$€£])?\s*"
    r"(?P<max>\d{1,3}(?:,\d{3})*(?:\.\d+)?k?|\d+k?)\s*"
    r"(?P<curr3>USD|EUR|GBP|CAD|AUD|CHF|AED|SAR|EGP|[\$€£])?\s*"
    r"(?:(?:per|\/|\ba\b)\s*(?P<interval_per>hour|hr|day|week|month|year|yr)\b|(?P<interval_adv>\b(?:hourly|daily|weekly|monthly|yearly|annual|annually)\b))?)"
    r"(?:\s*(?P<follower>years?(?:\s+(?:of\s+)?experience)?|yrs?(?:\s+(?:of\s+)?experience)?|engineers?|people|members?|developers?|clients?|customers?|tickets?|points?)\b)?",
    re.IGNORECASE,
)


def _parse_num(val_str: str) -> float:
    cleaned = val_str.replace(",", "").strip().casefold()
    if cleaned.endswith("k"):
        return float(cleaned[:-1]) * 1000.0
    return float(cleaned)


def extract_compensation(text: str) -> Compensation | None:
    """Extract explicit compensation range from text. Never defaults currency or interval."""
    if not text:
        return None

    for match in _COMPENSATION_PATTERN.finditer(text):
        follower = (match.group("follower") or "").casefold()
        if follower and any(w in follower for w in ("year", "yr", "engineer", "people", "member", "developer", "client", "customer", "ticket", "point")):
            continue

        label = match.group("label")
        curr_token = match.group("curr") or match.group("curr2") or match.group("curr3")
        interval_per = (match.group("interval_per") or "").casefold()
        interval_adv = (match.group("interval_adv") or "").casefold()

        # Must have at least a currency token, a compensation label, or a clear rate interval
        if not curr_token and not label and not interval_per and not interval_adv:
            continue

        currency = _CURRENCY_MAP.get(curr_token.strip().casefold()) if curr_token else None

        try:
            min_val = _parse_num(match.group("min"))
            max_val = _parse_num(match.group("max"))
        except (ValueError, AttributeError):
            continue

        interval = CompensationInterval.UNSPECIFIED
        interval_token = interval_per or interval_adv
        if interval_token in {"hour", "hr", "hourly"}:
            interval = CompensationInterval.HOURLY
        elif interval_token in {"day", "daily"}:
            interval = CompensationInterval.DAILY
        elif interval_token in {"week", "weekly"}:
            interval = CompensationInterval.WEEKLY
        elif interval_token in {"month", "monthly"}:
            interval = CompensationInterval.MONTHLY
        elif interval_token in {"year", "yr", "yearly", "annual", "annually"}:
            interval = CompensationInterval.YEARLY

        if min_val > max_val:
            min_val, max_val = max_val, min_val

        return Compensation(
            min_amount=min_val,
            max_amount=max_val,
            currency=currency,
            interval=interval,
        )

    return None


def parse_iso_date(raw_date: Any) -> str | None:
    """Deterministically parse dates into ISO 8601 calendar date YYYY-MM-DD or None."""
    if raw_date is None:
        return None
    if isinstance(raw_date, (int, float)):
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
    next_header = re.search(r"<h[1-6][^>]*>|^(?:#{1,6}\s|[A-Z][A-Za-z\s]{3,20}:)", subtext, re.MULTILINE)
    if next_header:
        subtext = subtext[:next_header.start()]

    li_items = re.findall(r"<li[^>]*>(.*?)</li>", subtext, re.IGNORECASE | re.DOTALL)
    if li_items:
        return tuple(clean_text(item) for item in li_items if clean_text(item))

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
