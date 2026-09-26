"""Privacy-safe sampling and review-label contracts for the FR-008 gold set.

This module deliberately has no database, network, or profile dependencies. The
sampler receives opaque opportunity identifiers and caller-supplied categorical
strata; the label serializer emits only the fields declared by the versioned
review contract. Reviewer rationales should describe the judgment without
copying job text or Founder profile content.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, TypeVar


SCHEMA_VERSION = 1
MAX_OPPORTUNITY_ID_LENGTH = 256
MAX_STRATUM_VALUE_LENGTH = 80
MAX_SEED_LENGTH = 256
MAX_RATIONALE_LENGTH = 500

Stratum = tuple[str, ...]


class ActionabilityChoice(str, Enum):
    DEFINITELY_APPLY = "definitely_apply"
    LIKELY_APPLY = "likely_apply"
    MAYBE_REVIEW = "maybe_review"
    PROBABLY_SKIP = "probably_skip"
    DEFINITELY_INELIGIBLE = "definitely_ineligible"


class CapabilityFitBand(str, Enum):
    EXCEPTIONAL_DIRECT = "exceptional_direct"
    STRONG = "strong"
    GOOD_REALISTIC = "good_realistic"
    PLAUSIBLE_MATERIAL_GAPS = "plausible_material_gaps"
    STRETCH = "stretch"
    WEAK = "weak"


class TargetFamilyTier(str, Enum):
    PRIMARY = "primary"
    ADJACENT = "adjacent"
    STRETCH = "stretch"
    NOT_TARGET = "not_target"
    UNMAPPED = "unmapped"


def _validate_opaque_id(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value != value.strip() or len(value) > MAX_OPPORTUNITY_ID_LENGTH:
        raise ValueError(f"{field_name} must be a non-empty opaque identifier of at most {MAX_OPPORTUNITY_ID_LENGTH} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{field_name} must not contain control characters")
    return value


def _normalize_stratum(value: object, *, field_name: str = "stratum") -> Stratum:
    if not isinstance(value, tuple) or not value:
        raise TypeError(f"{field_name} must be a non-empty tuple of categorical strings")
    if any(
        not isinstance(part, str)
        or not part
        or part != part.strip()
        or len(part) > MAX_STRATUM_VALUE_LENGTH
        or any(ord(char) < 32 or ord(char) == 127 for char in part)
        for part in value
    ):
        raise ValueError(f"{field_name} values must be non-empty categorical strings of at most {MAX_STRATUM_VALUE_LENGTH} characters")
    return value


@dataclass(frozen=True, slots=True)
class SamplingCandidate:
    """An opaque ID paired only with categorical values used for sampling."""

    opportunity_id: str
    stratum: Stratum

    def __post_init__(self) -> None:
        _validate_opaque_id(self.opportunity_id, field_name="opportunity_id")
        _normalize_stratum(self.stratum)


@dataclass(frozen=True, slots=True)
class ReviewSelection:
    """A selected opaque ID and its categorical stratum, with no source text."""

    opportunity_id: str
    stratum: Stratum

    def __post_init__(self) -> None:
        _validate_opaque_id(self.opportunity_id, field_name="opportunity_id")
        _normalize_stratum(self.stratum)


@dataclass(frozen=True, slots=True)
class QuotaDeficit:
    stratum: Stratum
    available: int
    required: int


class InsufficientStratumError(ValueError):
    """Raised when any requested stratum cannot meet its minimum sample size."""

    def __init__(self, deficits: tuple[QuotaDeficit, ...]) -> None:
        self.deficits = deficits
        detail = "; ".join(
            f"{deficit.stratum!r}: available={deficit.available}, required={deficit.required}"
            for deficit in deficits
        )
        super().__init__(f"insufficient candidates for requested strata ({detail})")


def select_stratified(
    candidates: Iterable[SamplingCandidate],
    *,
    seed: str,
    minimums: Mapping[Stratum, int],
) -> tuple[ReviewSelection, ...]:
    """Select the requested minimum from each stratum deterministically.

    Within a stratum, candidates are ordered by a SHA-256 digest of the supplied
    seed, categorical stratum, and opaque ID. Input order therefore has no
    effect. Every requested stratum must meet its quota or the function raises
    :class:`InsufficientStratumError` without returning a partial selection.
    """
    if not isinstance(seed, str) or not seed or len(seed) > MAX_SEED_LENGTH:
        raise ValueError(f"seed must be a non-empty string of at most {MAX_SEED_LENGTH} characters")
    if not isinstance(minimums, Mapping) or not minimums:
        raise ValueError("minimums must be a non-empty mapping of strata to positive counts")

    normalized_minimums: dict[Stratum, int] = {}
    for stratum, minimum in minimums.items():
        normalized_stratum = _normalize_stratum(stratum, field_name="minimums key")
        if type(minimum) is not int or minimum < 1:
            raise ValueError("each stratum minimum must be a positive integer")
        normalized_minimums[normalized_stratum] = minimum

    grouped: dict[Stratum, list[SamplingCandidate]] = {key: [] for key in normalized_minimums}
    seen_ids: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, SamplingCandidate):
            raise TypeError("candidates must contain SamplingCandidate values")
        if candidate.opportunity_id in seen_ids:
            raise ValueError("candidate opportunity IDs must be unique")
        seen_ids.add(candidate.opportunity_id)
        if candidate.stratum in grouped:
            grouped[candidate.stratum].append(candidate)

    deficits = tuple(
        QuotaDeficit(stratum=stratum, available=len(grouped[stratum]), required=minimum)
        for stratum, minimum in sorted(normalized_minimums.items())
        if len(grouped[stratum]) < minimum
    )
    if deficits:
        raise InsufficientStratumError(deficits)

    selected: list[ReviewSelection] = []
    for stratum in sorted(normalized_minimums):
        ranked = sorted(
            grouped[stratum],
            key=lambda candidate: (
                _selection_digest(seed, stratum, candidate.opportunity_id),
                candidate.opportunity_id,
            ),
        )
        selected.extend(
            ReviewSelection(candidate.opportunity_id, candidate.stratum)
            for candidate in ranked[: normalized_minimums[stratum]]
        )
    return tuple(selected)


def _selection_digest(seed: str, stratum: Stratum, opportunity_id: str) -> bytes:
    material = json.dumps(
        [seed, stratum, opportunity_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).digest()


EnumT = TypeVar("EnumT", bound=Enum)


def _enum_value(enum_type: type[EnumT], value: object, *, field_name: str) -> EnumT:
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a recognized string choice")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not an allowed choice") from exc


@dataclass(frozen=True, slots=True)
class GoldReviewLabel:
    """One human review label; it contains no job or Founder source content."""

    opportunity_id: str
    actionability: ActionabilityChoice | str
    capability_fit: CapabilityFitBand | str
    geography_correctness: bool | None
    seniority_correctness: bool | None
    required_skill_correctness: bool | None
    expected_target_family_tier: TargetFamilyTier | str | None
    reviewer_rationale: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_opaque_id(self.opportunity_id, field_name="opportunity_id")
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        object.__setattr__(
            self,
            "actionability",
            _enum_value(ActionabilityChoice, self.actionability, field_name="actionability"),
        )
        object.__setattr__(
            self,
            "capability_fit",
            _enum_value(CapabilityFitBand, self.capability_fit, field_name="capability_fit"),
        )
        if self.expected_target_family_tier is not None:
            object.__setattr__(
                self,
                "expected_target_family_tier",
                _enum_value(
                    TargetFamilyTier,
                    self.expected_target_family_tier,
                    field_name="expected_target_family_tier",
                ),
            )
        for field_name in (
            "geography_correctness",
            "seniority_correctness",
            "required_skill_correctness",
        ):
            value = getattr(self, field_name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"{field_name} must be true, false, or null")
        if not isinstance(self.reviewer_rationale, str):
            raise TypeError("reviewer_rationale must be a string")
        rationale = self.reviewer_rationale.strip()
        if not rationale or len(rationale) > MAX_RATIONALE_LENGTH:
            raise ValueError(
                f"reviewer_rationale must contain 1 to {MAX_RATIONALE_LENGTH} characters"
            )
        if any(ord(char) < 32 and char not in "\t\n\r" for char in rationale):
            raise ValueError("reviewer_rationale must not contain control characters")
        object.__setattr__(self, "reviewer_rationale", rationale)

    def to_dict(self) -> dict[str, object]:
        """Return exactly the version-1 allowlisted fields."""
        return {
            "schema_version": self.schema_version,
            "opportunity_id": self.opportunity_id,
            "actionability": self.actionability.value,
            "capability_fit": self.capability_fit.value,
            "geography_correctness": self.geography_correctness,
            "seniority_correctness": self.seniority_correctness,
            "required_skill_correctness": self.required_skill_correctness,
            "expected_target_family_tier": (
                self.expected_target_family_tier.value
                if self.expected_target_family_tier is not None
                else None
            ),
            "reviewer_rationale": self.reviewer_rationale,
        }


_LABEL_FIELDS = frozenset(
    {
        "schema_version",
        "opportunity_id",
        "actionability",
        "capability_fit",
        "geography_correctness",
        "seniority_correctness",
        "required_skill_correctness",
        "expected_target_family_tier",
        "reviewer_rationale",
    }
)


def serialize_review_label(label: GoldReviewLabel) -> str:
    """Serialize a validated label using its strict, versioned field set."""
    if not isinstance(label, GoldReviewLabel):
        raise TypeError("label must be a GoldReviewLabel")
    return json.dumps(
        label.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("serialized review label contains a duplicate field")
        result[key] = value
    return result


def deserialize_review_label(serialized: str) -> GoldReviewLabel:
    """Parse only strict version-1 JSON; reject duplicate and unlisted fields."""
    if not isinstance(serialized, str):
        raise TypeError("serialized review label must be a string")
    payload = json.loads(serialized, object_pairs_hook=_unique_object)
    if not isinstance(payload, dict):
        raise ValueError("serialized review label must be a JSON object")
    keys = frozenset(payload)
    if keys != _LABEL_FIELDS:
        raise ValueError("serialized review label has missing or unlisted fields")
    version = payload["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version; expected {SCHEMA_VERSION}")
    return GoldReviewLabel(
        opportunity_id=payload["opportunity_id"],
        actionability=payload["actionability"],
        capability_fit=payload["capability_fit"],
        geography_correctness=payload["geography_correctness"],
        seniority_correctness=payload["seniority_correctness"],
        required_skill_correctness=payload["required_skill_correctness"],
        expected_target_family_tier=payload["expected_target_family_tier"],
        reviewer_rationale=payload["reviewer_rationale"],
        schema_version=version,
    )
