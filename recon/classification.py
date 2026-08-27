"""Pure, deterministic eligibility rules for normalized source records."""
from __future__ import annotations

import re

from recon.models import Classification, Record


RESTRICTIONS = (
    r"\b(?:must (?:be )?(?:authorized|eligible)|(?:work )?authorization (?:is )?required|right to work)\b[^.]{0,50}\b(?:united states|u\.?s\.?|usa|canada|canadian)\b",
    r"\b(?:united states|u\.?s\.?|usa|canada|canadian)\b[^.]{0,35}\b(?:work )?(?:authorization|residen\w*|citizen\w*)\b",
    r"\b(?:must be |applicants must be |candidates must )(?:based|located|resident|reside|live) (?:in )?(?:the )?(?:united states|u\.?s\.?|usa|canada|australia|germany|france|japan|brazil|india|uk|united kingdom)\b",
    r"\b(?:based|located|resident|reside|live) in (?:france|japan|brazil|germany|australia)\b",
    r"\b(?:australian|canadian|german|french|japanese|brazilian) residents? only\b",
    r"\b(?:us|u\.?s\.?|usa|united states|canada|eu|india|latam)\s*(?:-| )?only\b",
    r"\b(?:us|u\.?s\.?|usa)[ -]based\b",
    r"\b(?:green card|citizenship|citizen(?:ship)?|right to work)\b",
    r"\b(?:no visa sponsorship|sponsorship is not available|no sponsorship available)\b",
    r"\beligible countries\s*:\s*(?![^.]*\begypt\b)[^.]+",
)
ELIGIBLE = (
    r"\b(?:egypt|egyptian|mena|middle east(?: and north africa)?|emea|africa)\b",
    r"\b(?:worldwide|anywhere(?: in the world)?|global|work from anywhere|any country)\b",
    r"\bremote\s*[-(]\s*(?:global|worldwide)\b",
)


def _combined(record: Record) -> str:
    return " ".join((record.title, record.location_text, record.description))


def _match(patterns: tuple[str, ...], text: str) -> str | None:
    for pattern in patterns:
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            return found.group(0)
    return None


def classify(record: Record) -> Classification:
    """Return a deterministic result with the actual matched signal or restriction."""
    text = _combined(record)
    restriction = _match(RESTRICTIONS, text)
    individual, individual_reason = _individual(text, record.track)
    if restriction:
        return Classification("excluded", restriction, individual, individual_reason)
    eligible = _match(ELIGIBLE, record.location_text)
    if not eligible:
        eligible = _match((ELIGIBLE[0].replace("|emea|", "|"), *ELIGIBLE[1:]), record.description)
    if eligible:
        return Classification("eligible", eligible, individual, individual_reason)
    if re.search(r"\bremote\b", text, re.IGNORECASE):
        return Classification("unclear", "remote without an eligibility geography", individual, individual_reason)
    return Classification("unclear", "no geography signal", individual, individual_reason)


def _individual(text: str, track: str) -> tuple[str, str]:
    if track != "independent":
        return "unclear", "not an independent-track record"
    entity = _match((r"\b(?:commercial registration|registered (?:company|legal entit\w*)|legal entities only|bid bond|minimum annual turnover)\b",), text)
    if entity:
        return "entity_required", entity
    individual = _match((r"\b(?:individual consultants?|individual contractors?|natural persons?)\b",), text)
    if individual:
        return "individual_ok", individual
    return "unclear", "no individual or entity signal"
