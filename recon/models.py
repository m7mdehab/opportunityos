from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Record:
    source: str
    track: str
    title: str
    organization: str
    location_text: str
    url: str
    posted_date: str
    description: str
    raw_payload_pointer: str

    def flat(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class Classification:
    eligibility: str
    eligibility_reason: str
    individual_eligibility: str
    individual_reason: str
