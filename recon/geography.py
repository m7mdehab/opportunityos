"""Evidence-backed geographic rule extraction and pure derivation."""
from __future__ import annotations

import re
from dataclasses import replace

from recon.models import Record
from recon.regions import includes

NAMES = {"egypt": "EG", "cairo": "EG", "united states": "US", "u.s.": "US", "us": "US", "usa": "US", "canada": "CA", "united kingdom": "GB", "uk": "GB", "germany": "DE", "australia": "AU", "india": "IN", "france": "FR", "japan": "JP", "brazil": "BR", "latam": "LATAM", "uae": "AE", "saudi arabia": "SA", "eea": "EEA", "eu": "EU", "emea": "EMEA", "mena": "MENA", "middle east": "MENA", "africa": "AFRICA", "worldwide": "WORLDWIDE", "global": "WORLDWIDE", "anywhere": "WORLDWIDE", "any country": "WORLDWIDE"}


def extract(record: Record) -> Record:
    text = " ".join((record.location_text, record.description))
    allow: list[tuple[str, str]] = []
    deny: list[tuple[str, str]] = []
    for name, token in NAMES.items():
        if name == "emea" and re.search(r"\bemea hours?\b", text, re.I):
            continue
        found = re.search(rf"\b{re.escape(name)}\b", text, re.I)
        if found:
            allow.append((token, found.group(0)))
    for pattern, token in ((r"no (?:visa )?sponsorship[^.]*|sponsorship (?:is )?not available", "NO_SPONSORSHIP"), (r"(?:work authorization|authorized to work|right to work)[^.]*\b(?:united states|u\.s\.?|us|usa)\b|\b(?:us|usa|united states) work authorization", "WORK_AUTH_REQUIRED:US"), (r"(?:residents? (?:of|in)|reside|located) (?:in |of )?the EEA", "RESIDENCY_REQUIRED:EEA"), (r"schengen visa", "RESIDENCY_REQUIRED:EU"), (r"green card|citizenship", "WORK_AUTH_REQUIRED:US"), (r"\b(?:us|usa|united states|france|japan)\s+only\b|\bus-based\b", "RESIDENCY_REQUIRED:US"), (r"\b(?:australian) residents? only\b", "RESIDENCY_REQUIRED:AU"), (r"\b(?:candidates?|applicants?) must (?:reside|be located|live) in germany\b", "RESIDENCY_REQUIRED:DE"), (r"\bapplicants? must live in japan\b", "RESIDENCY_REQUIRED:JP"), (r"\bmust be located in brazil\b", "RESIDENCY_REQUIRED:BR"), (r"\b(?:applicants?) must be located in australia\b", "RESIDENCY_REQUIRED:AU"), (r"\bmust be based in (?:the )?united kingdom\b", "RESIDENCY_REQUIRED:GB"), (r"\bemea hours?\b", "TIMEZONE_ONLY")):
        found = re.search(pattern, text, re.I)
        if found:
            deny.append((token, found.group(0)))
    mode = ("onsite", "on-site") if re.search(r"\bon[- ]site\b", text, re.I) else ("hybrid", "hybrid") if re.search(r"\bhybrid\b", text, re.I) else ("remote", "remote") if re.search(r"\bremote\b", text, re.I) else ("unstated", "")
    return replace(record, geo_allow=tuple(dict.fromkeys(allow)), geo_deny=tuple(dict.fromkeys(deny)), work_mode=mode)


def eligibility_for(record: Record, country: str = "EG") -> tuple[str, str]:
    country = country.upper()
    for token, evidence in record.geo_deny:
        target = token.split(":", 1)[-1] if ":" in token else ""
        if token == "NO_SPONSORSHIP" or (":" in token and not includes(target, country)) or (":" not in token and includes(target, country)):
            return "excluded", evidence
    if any(includes(token, country) for token, _ in record.geo_allow):
        return "eligible", next(evidence for token, evidence in record.geo_allow if includes(token, country))
    if record.geo_allow:
        return "excluded", record.geo_allow[0][1]
    return "unclear", "no mapped geographic rule"
