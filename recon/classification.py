"""Pure, deterministic eligibility rules for normalized source records."""
from __future__ import annotations

import re

from recon.geography import eligibility_for, extract
from recon.models import Classification, Record


def _combined(record: Record) -> str:
    return " ".join((record.title, record.location_text, record.description))


def classify(record: Record) -> Classification:
    """Return a deterministic result with the actual matched signal or restriction."""
    text = _combined(record)
    extracted = extract(record)
    individual, individual_reason = _individual(text, record.track)
    eligibility, reason = eligibility_for(extracted)
    return Classification(eligibility, reason, individual, individual_reason)


def _individual(text: str, track: str) -> tuple[str, str]:
    if track != "independent":
        return "unclear", "not an independent-track record"
    entity_match = re.search(r"\b(?:commercial registration|registered (?:company|legal entit\w*)|legal entities only|bid bond|minimum annual turnover)\b", text, re.IGNORECASE)
    entity = entity_match.group(0) if entity_match else None
    if entity:
        return "entity_required", entity
    individual_match = re.search(r"\b(?:individual consultants?|individual contractors?|natural persons?)\b", text, re.IGNORECASE)
    individual = individual_match.group(0) if individual_match else None
    if individual:
        return "individual_ok", individual
    return "unclear", "no individual or entity signal"
