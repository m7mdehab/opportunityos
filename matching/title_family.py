"""B3 (BRIEF-FR-006) -- target-role family and title normalization.

`normalize_title(title) -> (family_id, level, matched_rule)` maps a raw
posting title onto one of the committed families in
`matching/title_families.yaml` (or `other`) plus a seniority `level`, and
names the exact alias/regex rule responsible so evidence can say *why* a
title landed where it did.

Deterministic and pure: depends only on the input `title` string and the
committed YAML file (loaded once and cached); never on Python's dict/hash
iteration order. Family precedence comes from the YAML file's explicit list
order, not from dict iteration; level precedence comes from an explicit rank
table, not from first-seen-token order.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

_FAMILIES_PATH = Path(__file__).resolve().parent / "title_families.yaml"

Level = Literal["intern", "junior", "mid", "senior", "staff", "principal", "unspecified"]

# Higher rank wins when a title contains more than one level token (e.g.
# "Senior Staff Engineer" resolves to staff, not senior). Assumption, named:
# "lead" is treated as a senior-level synonym, not its own rank, because the
# fixture/test titles in this repo use "Lead X Engineer" the way industry
# job boards commonly do (senior individual contributor), not as a distinct
# managerial band.
_LEVEL_TOKEN_RANK: dict[str, int] = {
    "intern": 0, "internship": 0, "trainee": 0,
    "junior": 1, "jr": 1, "entry": 1, "graduate": 1, "associate": 1,
    "mid": 2, "ii": 2,
    "senior": 3, "sr": 3, "lead": 3,
    "staff": 4,
    "principal": 5, "distinguished": 5, "chief": 5,
}
_LEVEL_BY_RANK: dict[int, Level] = {
    0: "intern", 1: "junior", 2: "mid", 3: "senior", 4: "staff", 5: "principal",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_for_matching(title: str) -> str:
    """Casefold and collapse every run of non-alphanumeric characters to a
    single space, so punctuation, dashes, commas, and parentheses never break
    a phrase match: 'Senior Data Engineer, Platform (Remote — EU)' reads
    as 'senior data engineer platform remote eu'."""
    return _NON_ALNUM_RE.sub(" ", title.casefold()).strip()


def _alias_to_pattern(alias: str) -> re.Pattern[str]:
    words = alias.casefold().split()
    escaped = r"\s+".join(re.escape(w) for w in words)
    return re.compile(rf"\b{escaped}\b")


@dataclass(frozen=True, slots=True)
class _CompiledRule:
    rule_id: str
    pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class _CompiledFamily:
    family_id: str
    display_name: str
    rules: tuple[_CompiledRule, ...]
    negative_patterns: tuple[re.Pattern[str], ...]


def _compile_families(raw: dict) -> tuple[_CompiledFamily, ...]:
    compiled: list[_CompiledFamily] = []
    for family in raw["families"]:
        family_id = family["id"]
        rules: list[_CompiledRule] = []
        for idx, alias in enumerate(family.get("aliases") or ()):
            rules.append(_CompiledRule(
                rule_id=f"{family_id}#alias:{idx}:{alias}",
                pattern=_alias_to_pattern(alias),
            ))
        for idx, pattern in enumerate(family.get("patterns") or ()):
            rules.append(_CompiledRule(
                rule_id=f"{family_id}#pattern:{idx}",
                pattern=re.compile(pattern),
            ))
        negatives = tuple(re.compile(p) for p in (family.get("negative_patterns") or ()))
        compiled.append(_CompiledFamily(
            family_id=family_id,
            display_name=family.get("display_name", family_id),
            rules=tuple(rules),
            negative_patterns=negatives,
        ))
    return tuple(compiled)


@lru_cache(maxsize=1)
def _load_families() -> tuple[_CompiledFamily, ...]:
    with _FAMILIES_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return _compile_families(raw)


def _detect_level(normalized_title: str) -> Level:
    best_rank: int | None = None
    for token in _TOKEN_RE.findall(normalized_title):
        rank = _LEVEL_TOKEN_RANK.get(token)
        if rank is not None and (best_rank is None or rank > best_rank):
            best_rank = rank
    if best_rank is None:
        return "unspecified"
    return _LEVEL_BY_RANK[best_rank]


def normalize_title(title: str) -> tuple[str, Level, str]:
    """Map a raw posting title to (family_id, level, matched_rule).

    Families are evaluated in the committed YAML's list order (specific
    families first, `other` last). Within a family, a `negative_patterns`
    match disqualifies the *whole family* for this title (not just one
    rule), then evaluation continues to the next family. The first family
    whose alias/pattern rules match -- and whose negative patterns do not --
    wins; its first matching rule's id is returned as `matched_rule`.

    Every title resolves: an unmatched title returns `("other", level,
    "other#no_match")` rather than raising or returning `None`.
    """
    normalized = _normalize_for_matching(title or "")
    level = _detect_level(normalized)

    for family in _load_families():
        if family.family_id == "other":
            continue
        if any(neg.search(normalized) for neg in family.negative_patterns):
            continue
        for rule in family.rules:
            if rule.pattern.search(normalized):
                return family.family_id, level, rule.rule_id

    return "other", level, "other#no_match"
