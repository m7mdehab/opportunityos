"""Cheap pre-persistence admission for broad ATS boards.

Historical opportunity rows are not touched. For new Greenhouse/Lever batches,
reuse the canonical FR-008 role classifier before heavyweight persistence and
evaluation so clearly non-target job families do not create evaluation history.
Unknown roles remain available for review instead of being guessed away.
"""
from __future__ import annotations

from matching.recommendation_foundation import classify_role_relevance
from opportunity.models import Opportunity


_BROAD_ATS_PREFIXES = ("greenhouse:", "lever:")
# These title families are rejected by the canonical classifier regardless of
# description evidence. Adjacent software/platform families are deliberately
# absent: their description can establish that the work is data/AI-related.
_DESCRIPTION_DEPENDENT_FAMILIES = frozenset({
    "backend", "devops_platform", "software_engineering", "security",
    "product", "customer_solutions_engineering",
})


def is_unambiguously_non_target_title(title: str) -> bool:
    """Cheap pre-parse gate; preserve families whose relevance needs a body."""
    result = classify_role_relevance(title, "")
    return result.classification == "non_target" and result.title_family not in _DESCRIPTION_DEPENDENT_FAMILIES


def admit_new_ats_candidates(
    source_id: str, opportunities: tuple[Opportunity, ...]
) -> tuple[tuple[Opportunity, ...], int]:
    """Return candidates to persist and the count excluded as clearly non-target.

    This is intentionally limited to broad company ATS sources. Aggregator and
    discovery lanes retain their existing behavior until their own canaries are
    evaluated; a `review`/unknown role also remains persisted for human review.
    """
    if not source_id.startswith(_BROAD_ATS_PREFIXES):
        return opportunities, 0
    admitted: list[Opportunity] = []
    excluded = 0
    for opportunity in opportunities:
        relevance = classify_role_relevance(opportunity.title, opportunity.description)
        if relevance.classification == "non_target":
            excluded += 1
        else:
            admitted.append(opportunity)
    return tuple(admitted), excluded
