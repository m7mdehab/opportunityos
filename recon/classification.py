"""Pure, deterministic eligibility rules for normalized source records."""
from __future__ import annotations

import re

from recon.models import Classification, Record


def _text(record: Record) -> str:
    return " ".join((record.title, record.location_text, record.description)).lower()


def classify(record: Record) -> Classification:
    """Classify one record without I/O, configuration, fixtures, or network access."""
    text = _text(record)
    excluded = (
        (r"\b(us|u\.s\.|united states) (work )?(authorization|residen|citizen)", "US work authorization or residence required"),
        (r"\bmust be (based|located|resident) in (the )?(us|u\.s\.|united states)\b", "US-only residence requirement"),
        (r"\b(canada|canadian) (work )?(authorization|residen|citizen)", "Canada work authorization or residence required"),
        (r"\bmust be (based|located|resident) in (canada|australia|uk|united kingdom)\b", "country-only residence requirement"),
        (r"\b(no visa sponsorship|sponsorship is not available)\b", "no sponsorship stated"),
    )
    for pattern, reason in excluded:
        if re.search(pattern, text):
            return Classification("excluded", reason, *_individual(text, record.track))

    if re.search(r"\b(egypt|egyptian)\b", text):
        return Classification("eligible", "Egypt explicitly included", *_individual(text, record.track))
    if re.search(r"\b(mena|middle east and north africa)\b", text):
        return Classification("eligible", "MENA explicitly included", *_individual(text, record.track))
    if re.search(r"\b(emea|europe,? middle east (and|&) africa)\b", text):
        return Classification("eligible", "EMEA explicitly included", *_individual(text, record.track))
    if re.search(r"\b(worldwide|work from anywhere|anywhere in the world|global remote)\b", text):
        return Classification("eligible", "worldwide eligibility stated", *_individual(text, record.track))
    if re.search(r"\bremote\b", text):
        return Classification("unclear", "remote stated without an eligible geography", *_individual(text, record.track))
    return Classification("unclear", "no geography stated", *_individual(text, record.track))


def _individual(text: str, track: str) -> tuple[str, str]:
    if track != "independent":
        return "unclear", "not an independent-track record"
    entity_patterns = (
        r"\b(registered (company|legal entity|vendor|supplier)|incorporated (company|entity))\b",
        r"\b(company registration|commercial registration|trade license)\b",
        r"\b(minimum annual turnover|bid bond|performance bond)\b",
        r"\b(only (companies|firms|organizations)|legal entities only)\b",
    )
    if any(re.search(pattern, text) for pattern in entity_patterns):
        return "entity_required", "legal-entity, registration, turnover, or bond requirement stated"
    if re.search(r"\b(individual consultant|individual contractor|sole consultant|natural person)\b", text):
        return "individual_ok", "individual participation explicitly stated"
    return "unclear", "individual or entity requirement not stated"
