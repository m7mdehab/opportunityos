"""Proficiency-aware, requirement-aware skill matching (BRIEF-FR-006 B2).

Fixes a defect where the scorer told the founder "Verified core skill:
Javascript" for a skill their own CV records as *basic* proficiency, and
where a posting's nice-to-have skill list inflated the founder's apparent
match to the same strength as a genuinely required skill. Both are the same
defect class: the product being optimistic about the founder on the founder's
behalf. See `reports/evidence/FR-006/orders/B2-skills.md`.

Two independent primitives live here:

1. A **proficiency tier model** (`PROFICIENCY_TIERS`) with an explicit
   ordering and the rule that `basic`/`foundations` are the *partial* tier
   and an absent or unrecognised proficiency string is *also* partial --
   never a strength.
2. A **required-vs-nice-to-have splitter** (`split_required_and_nice_to_have`)
   that reads headed-list detection rules from
   `opportunity/inference_rules.yaml`'s `skill_requirement_rules` section
   (Greenhouse/Lever descriptions use headed lists such as "Requirements:"
   and "Nice to have:"). When no header is found, every skill is
   nice-to-have -- the conservative direction, because inflating "required"
   inflates the founder's apparent match.

`matching/scorer.py`'s skills dimension is the only caller; it owns wiring
these primitives to the truth graph and the opportunity payload.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import unicodedata
from typing import TypeAlias

import yaml
from truth import predicates
from truth.models import AtomicAssertion, Polarity, VerificationStatus

_RULES_PATH = Path(__file__).resolve().parent.parent / "opportunity" / "inference_rules.yaml"

# ---------------------------------------------------------------------------
# Proficiency tier model. Committed as data, thresholds visible in one place,
# not scattered constants. Ordered lowest -> highest.
# ---------------------------------------------------------------------------
PROFICIENCY_TIERS: tuple[str, ...] = ("basic", "foundations", "working", "advanced", "expert")

# The minimum tier that can ever support a core-skill strength (Required
# behaviour #3 in the work order): `working` and above. `basic` and
# `foundations` sit below this floor and are always partial.
_MIN_STRENGTH_TIER = "working"

_TIER_RANK: dict[str, int] = {tier: idx for idx, tier in enumerate(PROFICIENCY_TIERS)}
_MIN_STRENGTH_RANK = _TIER_RANK[_MIN_STRENGTH_TIER]

PARTIAL_TIERS: frozenset[str] = frozenset(
    tier for tier, rank in _TIER_RANK.items() if rank < _MIN_STRENGTH_RANK
)


def normalize_proficiency(raw: str | None) -> str | None:
    """Casefold/strip a proficiency string and return it only if it belongs
    to the closed vocabulary; otherwise return None, meaning *unknown*."""
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().casefold()
    return candidate if candidate in _TIER_RANK else None


def is_partial_proficiency(raw: str | None) -> bool:
    """True for `basic`, `foundations`, and any unknown/unrecognised/absent
    proficiency. False only for `working` and above.

    Unknown must not be optimistic -- the whole defect being fixed is
    optimism -- so an unrecognised or missing proficiency string is treated
    the same as `basic`: partial, never a strength.
    """
    tier = normalize_proficiency(raw)
    if tier is None:
        return True
    return _TIER_RANK[tier] < _MIN_STRENGTH_RANK


def meets_strength_floor(raw: str | None) -> bool:
    """True only for `working`, `advanced`, `expert`."""
    return not is_partial_proficiency(raw)


def normalize_skill_label(raw: str | None) -> str:
    """Return the literal skill label normalized for exact matching.

    The only transformations are canonical Unicode composition, whitespace
    collapse, and case-folding. This deliberately does not expand aliases or
    infer related skills (for example, ``JS`` is not ``JavaScript``).
    """
    if not isinstance(raw, str):
        return ""
    normalized = unicodedata.normalize("NFC", raw)
    collapsed = " ".join(normalized.split())
    return unicodedata.normalize("NFC", collapsed.casefold())


SkillIndexEntry: TypeAlias = tuple[str | None, tuple[str, ...]]


def build_verified_skill_index(
    assertions: Iterable[AtomicAssertion],
) -> dict[str, SkillIndexEntry]:
    """Index verified career skill names and their safely joined evidence.

    Skill names are grouped by exact normalized label. Proficiency is joined
    only through the same assertion subject and only from verified
    ``skill.proficiency`` assertions. Conflicting (or unrecognized) verified
    tiers keep proficiency unknown. References from verified name assertions
    are always retained; proficiency references are included only when one
    unambiguous accepted tier exists.
    """
    name_rows: list[tuple[str, str, tuple[str, ...]]] = []
    proficiency_by_subject: dict[str, list[tuple[str | None, tuple[str, ...]]]] = defaultdict(list)

    for assertion in assertions:
        if (
            assertion.verification_status is not VerificationStatus.VERIFIED
            or assertion.polarity is not Polarity.POSITIVE
        ):
            continue
        if assertion.predicate == predicates.SKILL_NAME:
            key = normalize_skill_label(assertion.value)
            if key:
                name_rows.append((key, assertion.subject_id, assertion.evidence_ids))
        elif assertion.predicate == predicates.SKILL_PROFICIENCY:
            tier = normalize_proficiency(assertion.value)
            proficiency_by_subject[assertion.subject_id].append((tier, assertion.evidence_ids))

    names_by_key: dict[str, list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
    for key, subject_id, evidence_refs in name_rows:
        names_by_key[key].append((subject_id, evidence_refs))

    result: dict[str, SkillIndexEntry] = {}
    for key, skill_names in names_by_key.items():
        name_refs = [ref for _, refs in skill_names for ref in refs]
        subject_ids = dict.fromkeys(subject for subject, _ in skill_names)
        observed = [
            tier_ref
            for subject_id in subject_ids
            for tier_ref in proficiency_by_subject.get(subject_id, ())
        ]
        observed_tiers = {tier for tier, _ in observed}
        accepted_tier = None
        proficiency_refs: list[str] = []
        if len(observed_tiers) == 1 and None not in observed_tiers:
            accepted_tier = next(iter(observed_tiers))
            proficiency_refs = [
                ref for tier, refs in observed if tier == accepted_tier for ref in refs
            ]

        evidence_refs = tuple(dict.fromkeys((*name_refs, *proficiency_refs)))
        result[key] = (accepted_tier, evidence_refs)

    return result


# ---------------------------------------------------------------------------
# Required vs nice-to-have splitting, driven by opportunity/inference_rules.yaml
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _HeaderRule:
    id: str
    pattern: re.Pattern[str]


@lru_cache(maxsize=1)
def _load_skill_requirement_rules() -> tuple[tuple[_HeaderRule, ...], tuple[_HeaderRule, ...]]:
    with _RULES_PATH.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    section = (doc or {}).get("skill_requirement_rules") or {}
    required = tuple(
        _HeaderRule(r["id"], re.compile(r["pattern"])) for r in section.get("required_headers", ())
    )
    nice_to_have = tuple(
        _HeaderRule(r["id"], re.compile(r["pattern"])) for r in section.get("nice_to_have_headers", ())
    )
    return required, nice_to_have


_BLOCK_BREAK_RE = re.compile(r"</(?:li|p|h[1-6]|div|br)\s*>|<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _description_to_lines(description: str) -> list[str]:
    """Turn a plain-text or lightly-HTML posting description (Greenhouse and
    Lever both ship `<h3>`/`<li>`/`<p>` headed lists) into a flat list of
    lines, so headed-list detection works regardless of whether the adapter
    already stripped tags."""
    text = _BLOCK_BREAK_RE.sub("\n", description or "")
    text = _TAG_RE.sub("", text)
    return text.splitlines()


def split_required_and_nice_to_have(
    description: str, skills: tuple[str, ...],
) -> tuple[frozenset[str], frozenset[str]]:
    """Split `skills` (returned casefolded) into (required, nice_to_have)
    using headed-list rules from `opportunity/inference_rules.yaml`.

    Conservative by construction: a skill only ever lands in `required`
    while a `required_headers` rule is the most recently seen header in the
    description; every other skill -- including all of them when no header
    matches at all -- is `nice_to_have`.
    """
    required_rules, nice_rules = _load_skill_requirement_rules()
    skill_pool = {
        normalized for raw in skills
        if (normalized := normalize_skill_label(raw))
    }
    if not skill_pool:
        return frozenset(), frozenset()

    required: set[str] = set()
    state = "nice_to_have"  # conservative default before any header is seen
    for raw_line in _description_to_lines(description):
        line = normalize_skill_label(raw_line)
        if not line:
            continue
        if any(rule.pattern.search(line) for rule in required_rules):
            state = "required"
            continue
        if any(rule.pattern.search(line) for rule in nice_rules):
            state = "nice_to_have"
            continue
        if state == "required":
            for skill in skill_pool:
                if re.search(rf"(?<![\w-]){re.escape(skill)}(?![\w-])", line, re.IGNORECASE):
                    required.add(skill)

    nice_to_have = skill_pool - required
    return frozenset(required), frozenset(nice_to_have)


# ---------------------------------------------------------------------------
# Per-skill evaluation and the specific, generated reason text.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SkillMatch:
    """One opportunity skill's outcome against the founder truth graph."""

    name: str  # casefolded
    required: bool
    has_founder_match: bool
    proficiency: str | None  # normalized tier, or None if unknown/unset
    evidence_count: int
    evidence_refs: tuple[str, ...]

    @property
    def is_strength(self) -> bool:
        """Core-skill strength requires a *required* match at >= working
        proficiency (Required behaviour #3). A `basic` skill -- or an
        unknown-proficiency skill -- never produces a strength."""
        return self.required and self.has_founder_match and meets_strength_floor(self.proficiency)

    @property
    def is_gap(self) -> bool:
        return not self.has_founder_match

    @property
    def is_partial(self) -> bool:
        return self.has_founder_match and not self.is_strength


def evaluate_skill_matches(
    opp_skills: tuple[str, ...],
    required: frozenset[str],
    founder_skills_by_name: dict[str, tuple[str | None, tuple[str, ...]]],
) -> tuple[SkillMatch, ...]:
    """Evaluate each (deduplicated, order-preserving) opportunity skill.

    `founder_skills_by_name` maps a casefolded skill name to
    `(normalized_proficiency_or_None, evidence_ids)` for the founder's
    verified skill of that name.
    """
    seen: set[str] = set()
    matches: list[SkillMatch] = []
    for raw in opp_skills:
        name = normalize_skill_label(raw)
        if not name or name in seen:
            continue
        seen.add(name)
        founder_entry = founder_skills_by_name.get(name)
        if founder_entry is None:
            matches.append(SkillMatch(name, name in required, False, None, 0, ()))
        else:
            proficiency, evidence_refs = founder_entry
            matches.append(SkillMatch(name, name in required, True, proficiency, len(evidence_refs), evidence_refs))
    return tuple(matches)


def _evidence_phrase(match: SkillMatch) -> str:
    tier_label = match.proficiency or "unknown-proficiency"
    plural = "" if match.evidence_count == 1 else "s"
    if match.proficiency == "expert":
        return f"expert-evidence: {match.evidence_count} record{plural}"
    return f"{tier_label}, {match.evidence_count} record{plural}"


def render_reason(matches: tuple[SkillMatch, ...]) -> str:
    """Build the brief's specific reason text: the required list, what the
    founder has (with tier and evidence strength), and what is missing by
    name. Generated from the computed match, never a fixed string.

    Shape (verbatim example from the work order): "Required: Python, SQL,
    Airflow -> you have Python (expert-evidence: 3 roles), SQL (3 roles);
    Airflow not in your pack." This implementation reports evidence strength
    as verified evidence *record* counts rather than "roles": the truth
    graph does not establish a skill-to-employment-role linkage today, and
    AGENTS.md forbids fabricating a claim the graph does not support.
    """
    required_matches = [m for m in matches if m.required]
    nice_matches = [m for m in matches if not m.required]

    parts: list[str] = []
    if required_matches:
        req_names = ", ".join(m.name.title() for m in required_matches)
        have = [m for m in required_matches if m.has_founder_match]
        missing = [m for m in required_matches if not m.has_founder_match]
        have_str = "; ".join(f"{m.name.title()} ({_evidence_phrase(m)})" for m in have) or "none"
        clause = f"Required: {req_names} -> you have {have_str}"
        if missing:
            clause += "; " + ", ".join(m.name.title() for m in missing) + " not in your pack"
        clause += "."
        parts.append(clause)

    if nice_matches:
        nice_have = [m for m in nice_matches if m.has_founder_match]
        nice_missing = [m for m in nice_matches if not m.has_founder_match]
        nice_bits = []
        if nice_have:
            nice_bits.append(
                "you have " + "; ".join(f"{m.name.title()} ({_evidence_phrase(m)})" for m in nice_have)
            )
        if nice_missing:
            nice_bits.append(", ".join(m.name.title() for m in nice_missing) + " not in your pack")
        if nice_bits:
            parts.append("Nice-to-have: " + "; ".join(nice_bits) + ".")

    if not parts:
        return "No explicit skills specified in posting."
    return " ".join(parts)
