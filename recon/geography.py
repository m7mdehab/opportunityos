"""Evidence-backed geographic rule extraction and pure derivation."""
from __future__ import annotations

import re
from dataclasses import replace

from recon.models import Record
from recon.regions import includes

NAMES = {"egypt": "EG", "cairo": "EG", "united states": "US", "us": "US", "usa": "US", "united kingdom": "GB", "uk": "GB", "germany": "DE", "uae": "AE", "saudi arabia": "SA", "europe": "EUROPE", "eea": "EEA", "emea": "EMEA", "mena": "MENA", "africa": "AFRICA", "worldwide": "WORLDWIDE", "global": "WORLDWIDE", "anywhere": "WORLDWIDE"}


def extract(record: Record) -> Record:
    text = " ".join((record.location_text, record.description))
    allow: list[tuple[str, str]] = []
    deny: list[tuple[str, str]] = []
    for name, token in NAMES.items():
        found = re.search(rf"\b{re.escape(name)}\b", text, re.I)
        if found:
            allow.append((token, found.group(0)))
    for pattern, token in ((r"no sponsorship[^.]*|sponsorship not available", "NO_SPONSORSHIP"), (r"(?:work authorization|authorized to work)[^.]*\b(?:united states|us|usa)\b", "WORK_AUTH_REQUIRED:US"), (r"(?:residents?|reside|located) in the EEA", "RESIDENCY_REQUIRED:EEA"), (r"schengen visa", "RESIDENCY_REQUIRED:EU")):
        found = re.search(pattern, text, re.I)
        if found:
            deny.append((token, found.group(0)))
    mode = ("onsite", "on-site") if re.search(r"\bon[- ]site\b", text, re.I) else ("hybrid", "hybrid") if re.search(r"\bhybrid\b", text, re.I) else ("remote", "remote") if re.search(r"\bremote\b", text, re.I) else ("unstated", "")
    return replace(record, geo_allow=tuple(dict.fromkeys(allow)), geo_deny=tuple(dict.fromkeys(deny)), work_mode=mode)


def eligibility_for(record: Record, country: str = "EG") -> tuple[str, str]:
    country = country.upper()
    for token, evidence in record.geo_deny:
        target = token.split(":", 1)[-1] if ":" in token else ""
        if token == "NO_SPONSORSHIP" or includes(target, country):
            return "excluded", evidence
    if any(includes(token, country) for token, _ in record.geo_allow):
        return "eligible", next(evidence for token, evidence in record.geo_allow if includes(token, country))
    if record.geo_allow:
        return "excluded", record.geo_allow[0][1]
    return "unclear", "no mapped geographic rule"
