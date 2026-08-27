from __future__ import annotations

import re
from collections import defaultdict

from recon.models import Record


SENIORITY = re.compile(r"\b(junior|jr\.?|senior|sr\.?|lead|principal|staff|intern)\b", re.I)
NON_WORD = re.compile(r"[^a-z0-9]+")


def fingerprint(record: Record) -> str:
    def normalize(value: str) -> str:
        value = SENIORITY.sub("", value.lower())
        return NON_WORD.sub(" ", value).strip()

    return f"{normalize(record.organization)}|{normalize(record.title)}"


def deduplicate(records: list[Record]) -> tuple[list[Record], int, int]:
    grouped: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        grouped[fingerprint(record)].append(record)
    unique = [group[0] for group in grouped.values()]
    duplicates = len(records) - len(unique)
    overlaps = sum(1 for group in grouped.values() if len({item.source for item in group}) > 1)
    return unique, duplicates, overlaps
