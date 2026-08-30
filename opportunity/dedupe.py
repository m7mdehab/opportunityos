"""Two-Layer Deduplication Engine for OpportunityOS.

Implements exact content-hash matching and deterministic opportunity-level clustering
with strictly conservative false-merge behavior.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from .models import (
    Opportunity,
    OpportunityCluster,
    SeniorityLevel,
    Track,
)


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    unique_opportunities: tuple[Opportunity, ...]
    clusters: tuple[OpportunityCluster, ...]
    exact_duplicates_count: int
    cross_source_duplicates_count: int


def _normalize_token_bag(text: str) -> frozenset[str]:
    cleaned = re.sub(r"[^\w\s]", " ", text.casefold())
    tokens = [t for t in cleaned.split() if len(t) > 2]
    return frozenset(tokens)


def _can_merge_cross_source(opp_a: Opportunity, opp_b: Opportunity) -> bool:
    """Evaluate whether two opportunities represent the exact same real-world posting across sources.
    
    Fail-closed: returns False if there is any material mismatch in organization,
    seniority, track, or geographic scope.
    """
    # 1. Must have identical track
    if opp_a.track != opp_b.track:
        return False

    # 2. Must have compatible organization
    org_a = re.sub(r"[^\w]", "", opp_a.organization.casefold())
    org_b = re.sub(r"[^\w]", "", opp_b.organization.casefold())
    if org_a != org_b:
        # Check if one is a clean prefix/suffix or exact match
        if not (org_a.startswith(org_b) or org_b.startswith(org_a)):
            return False

    # 3. Must have compatible seniority
    if opp_a.seniority != SeniorityLevel.UNSPECIFIED and opp_b.seniority != SeniorityLevel.UNSPECIFIED:
        if opp_a.seniority != opp_b.seniority:
            return False

    # 4. Must have compatible title tokens
    title_a_tokens = _normalize_token_bag(opp_a.title)
    title_b_tokens = _normalize_token_bag(opp_b.title)
    if not title_a_tokens or not title_b_tokens:
        return False
    # Significant token intersection required
    intersection = title_a_tokens & title_b_tokens
    if len(intersection) < min(len(title_a_tokens), len(title_b_tokens)) * 0.7:
        return False

    # 5. Geographic scope compatibility
    if opp_a.geographic_eligibility and opp_b.geographic_eligibility:
        # If one is eligible and one is ineligible, they MUST NOT merge
        if opp_a.geographic_eligibility.status != opp_b.geographic_eligibility.status:
            return False

    return True


def deduplicate_opportunities(
    opportunities: Iterable[Opportunity],
) -> DeduplicationResult:
    """Execute two-layer deduplication over an iterable of Opportunity records."""
    opp_list = list(opportunities)
    if not opp_list:
        return DeduplicationResult((), (), 0, 0)

    # -------------------------------------------------------------
    # Layer 1: Exact Content-Hash Deduplication
    # -------------------------------------------------------------
    exact_hash_map: dict[str, list[Opportunity]] = {}
    for opp in opp_list:
        exact_hash_map.setdefault(opp.content_hash, []).append(opp)

    layer1_uniques: list[Opportunity] = []
    exact_clusters: list[OpportunityCluster] = []
    exact_dupe_count = 0

    for chash, group in exact_hash_map.items():
        primary = group[0]
        duplicates = tuple(group[1:])
        exact_dupe_count += len(duplicates)
        layer1_uniques.append(primary)
        if duplicates:
            cluster = OpportunityCluster(
                canonical_id=primary.id,
                primary_opportunity=primary,
                duplicate_opportunities=duplicates,
                dedup_layer="exact",
            )
            exact_clusters.append(cluster)

    # -------------------------------------------------------------
    # Layer 2: Deterministic Opportunity-Level Deduplication
    # -------------------------------------------------------------
    # Group by dedup_key first, then apply conservative cross-source merge verification
    key_groups: dict[str, list[Opportunity]] = {}
    for opp in layer1_uniques:
        key_groups.setdefault(opp.dedup_key, []).append(opp)

    final_uniques: list[Opportunity] = []
    final_clusters: list[OpportunityCluster] = list(exact_clusters)
    cross_source_dupe_count = 0

    for dedup_k, group in key_groups.items():
        if len(group) == 1:
            final_uniques.append(group[0])
            continue

        # In groups with multiple items sharing dedup_key, verify pairwise compatibility
        merged_indices: set[int] = set()
        for i in range(len(group)):
            if i in merged_indices:
                continue
            primary = group[i]
            dupes: list[Opportunity] = []
            for j in range(i + 1, len(group)):
                if j in merged_indices:
                    continue
                candidate = group[j]
                if _can_merge_cross_source(primary, candidate):
                    dupes.append(candidate)
                    merged_indices.add(j)

            merged_indices.add(i)
            final_uniques.append(primary)
            if dupes:
                cross_source_dupe_count += len(dupes)
                cluster = OpportunityCluster(
                    canonical_id=primary.id,
                    primary_opportunity=primary,
                    duplicate_opportunities=tuple(dupes),
                    dedup_layer="cross_source",
                )
                final_clusters.append(cluster)

    return DeduplicationResult(
        unique_opportunities=tuple(final_uniques),
        clusters=tuple(final_clusters),
        exact_duplicates_count=exact_dupe_count,
        cross_source_duplicates_count=cross_source_dupe_count,
    )
