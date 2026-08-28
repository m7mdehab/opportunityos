"""Evidence-backed geographic rule extraction and pure derivation."""
from __future__ import annotations

import re
from dataclasses import replace

from recon.models import Record
from recon.regions import includes

NAMES = {"egypt": "EG", "cairo": "EG", "united states": "US", "u.s.": "US", "us": "US", "usa": "US", "canada": "CA", "united kingdom": "GB", "uk": "GB", "germany": "DE", "australia": "AU", "india": "IN", "france": "FR", "japan": "JP", "brazil": "BR", "latam": "LATAM", "uae": "AE", "saudi arabia": "SA", "eea": "EEA", "eu": "EU", "emea": "EMEA", "mena": "MENA", "middle east": "MENA", "africa": "AFRICA", "worldwide": "WORLDWIDE", "global": "WORLDWIDE", "anywhere": "WORLDWIDE", "any country": "WORLDWIDE"}


IGNORE_WORDS = {
    "remote", "hybrid", "onsite", "on-site", "office", "work from home", "wfh",
    "full-time", "part-time", "contract", "freelance", "n/a", "any", "unstated",
    "anywhere", "flexible", "multiple locations", "various", "worldwide", "global",
}


def _extract_unmapped(location_text: str, description: str, allow: list[tuple[str, str]], deny: list[tuple[str, str]]) -> tuple[str, ...]:
    candidates: list[str] = []
    if location_text:
        segments = re.split(r"[,/|;•·]|\s+[-–—]\s+|\band\b|\bor\b", location_text)
        candidates.extend(segments)
    if not allow:
        explicit = re.search(r"\b(?:hiring in|candidates from|open to candidates in|restricted to residents of)\s+([A-Za-z\s,]+)", description, re.I)
        if explicit:
            desc_segments = re.split(r"[,/|;•·]|\band\b|\bor\b", explicit.group(1))
            candidates.extend(desc_segments)
    unmapped: list[str] = []
    for seg in candidates:
        clean = re.sub(r"^[\s()\[\]{}:\"'.,-]+|[\s()\[\]{}:\"'.,-]+$", "", seg).strip()
        if not clean or len(clean) < 2:
            continue
        if clean.lower() in IGNORE_WORDS:
            continue
        matched_allow = any(re.search(rf"\b{re.escape(name)}\b", clean, re.I) for name in NAMES)
        matched_deny = any(re.search(re.escape(evidence), clean, re.I) for _, evidence in deny)
        if not matched_allow and not matched_deny:
            if re.search(r"[a-zA-Z]", clean):
                unmapped.append(clean)
    return tuple(dict.fromkeys(unmapped))


def extract(record: Record) -> Record:
    location_text = record.location_text
    text = " ".join((location_text, record.description))
    allow: list[tuple[str, str]] = []
    deny: list[tuple[str, str]] = []
    restricted_place = re.search(r"\b(?:restricted to residents? of|residents? (?:of|in)|reside|located) (?:in |of )?the EEA\b", text, re.I)
    explicit_listing = re.search(r"\b(?:eligible countries|hiring in|restricted to residents? of)\s*:?.*", record.description, re.I)
    for name, token in NAMES.items():
        if token == "WORLDWIDE" and restricted_place:
            continue
        if name == "emea" and re.search(r"\bemea hours?\b", text, re.I):
            continue
        found = re.search(rf"\b{re.escape(name)}\b", location_text, re.I)
        if not found:
            found = re.search(rf"\b(?:open to candidates |candidates? from |we hire from |hiring in |applicants? from )[^.]*\b{re.escape(name)}\b", record.description, re.I)
        if not found and explicit_listing:
            found = re.search(rf"\b{re.escape(name)}\b", explicit_listing.group(0), re.I)
        if found:
            allow.append((token, found.group(0)))
    for pattern, token in ((r"no (?:visa )?sponsorship[^.]*|sponsorship (?:is )?not available", "NO_SPONSORSHIP"), (r"(?:work authorization|authorized to work|right to work)[^.]*\b(?:united states|u\.s\.?|us|usa|canada)\b|\b(?:us|usa|united states|canadian) work authorization", "WORK_AUTH_REQUIRED:US"), (r"(?:residents? (?:of|in)|reside|located) (?:in |of )?the EEA", "RESIDENCY_REQUIRED:EEA"), (r"schengen visa", "RESIDENCY_REQUIRED:EU"), (r"\bgreen card\b|\b(?:(?:u\.s\.?|us|usa|united states) )?citizenship (?:is )?required\b|\b(?:must\s+(?:possess|hold|have)|needs?(?:\s+to\s+(?:possess|hold|have))?)\s+(?:(?:u\.s\.?|us|usa|united states)\s+)?citizenship\b|\bproof of (?:(?:u\.s\.?|us|usa|united states) )?citizenship\b", "WORK_AUTH_REQUIRED:US"), (r"\b(?:us|usa|united states)\s+only\b|\bus-based\b", "RESIDENCY_REQUIRED:US"), (r"\bfrance\s+only\b", "RESIDENCY_REQUIRED:FR"), (r"\bjapan\s+only\b", "RESIDENCY_REQUIRED:JP"), (r"\bbrazil\s+only\b", "RESIDENCY_REQUIRED:BR"), (r"\bindia\s+only\b", "RESIDENCY_REQUIRED:IN"), (r"\bcanada\s+only\b", "RESIDENCY_REQUIRED:CA"), (r"\blatam\s+only\b", "RESIDENCY_REQUIRED:LATAM"), (r"\beu\s+only\b", "RESIDENCY_REQUIRED:EU"), (r"\b(?:australian) residents? only\b", "RESIDENCY_REQUIRED:AU"), (r"\b(?:candidates?|applicants?) must (?:reside|be located|live) in germany\b", "RESIDENCY_REQUIRED:DE"), (r"\bapplicants? must live in japan\b", "RESIDENCY_REQUIRED:JP"), (r"\bmust be located in brazil\b", "RESIDENCY_REQUIRED:BR"), (r"\b(?:applicants?) must be located in australia\b", "RESIDENCY_REQUIRED:AU"), (r"\bmust be based in (?:the )?united kingdom\b", "RESIDENCY_REQUIRED:GB"), (r"\bemea hours?\b", "TIMEZONE_ONLY")):
        found = re.search(pattern, text, re.I)
        if found:
            deny.append((token, found.group(0)))
    mode = ("onsite", "on-site") if re.search(r"\bon[- ]site\b", text, re.I) else ("hybrid", "hybrid") if re.search(r"\bhybrid\b", text, re.I) else ("remote", "remote") if re.search(r"\bremote\b", text, re.I) else ("unstated", "")
    unmapped = _extract_unmapped(location_text, record.description, allow, deny)
    return replace(record, geo_allow=tuple(dict.fromkeys(allow)), geo_deny=tuple(dict.fromkeys(deny)), work_mode=mode, unmapped=unmapped)


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
