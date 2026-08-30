"""Conservative Two-Layer Deduplication Engine for OpportunityOS.

Implements exact content-hash matching and deterministic opportunity-level clustering
with strict identity-provenance constraints and zero destructive false merges.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from typing import Iterable, Sequence

from opportunity.models import (
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
    ambiguous_duplicates_count: int


def _normalize_token_bag(text: str) -> frozenset[str]:
    cleaned = re.sub(r"[^\w\s]", " ", text.casefold())
    tokens = [t for t in cleaned.split() if len(t) > 2]
    return frozenset(tokens)


def _canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        # Strip tracking params
        clean_query = urllib.parse.parse_qs(parsed.query)
        filtered_query = {k: v for k, v in clean_query.items() if not k.startswith("utm_") and k not in {"ref", "source"}}
        encoded_query = urllib.parse.urlencode(filtered_query, doseq=True)
        return urllib.parse.urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/").lower(),
            parsed.params,
            encoded_query,
            "",
        ))
    except Exception:
        return url.strip().rstrip("/").casefold()


def _have_identical_outbound_identity(opp_a: Opportunity, opp_b: Opportunity) -> bool:
    """Check if both opportunities point to the same outbound requisition or ATS URL."""
    urls_a = {
        _canonicalize_url(opp_a.canonical_outbound_url),
        _canonicalize_url(opp_a.source_url),
    } - {""}
    urls_b = {
        _canonicalize_url(opp_b.canonical_outbound_url),
        _canonicalize_url(opp_b.source_url),
    } - {""}
    common = urls_a & urls_b
    if common:
        return True

    # Check if one URL contains greenhouse/lever path with the other's source_id
    if opp_a.source_id and opp_b.source_url and opp_a.source_id in opp_b.source_url:
        return True
    if opp_b.source_id and opp_a.source_url and opp_b.source_id in opp_a.source_url:
        return True

    return False


def _evaluate_deduplication(opp_a: Opportunity, opp_b: Opportunity) -> tuple[bool, bool]:
    """Evaluate whether two opportunities should merge or be flagged as possible duplicates.
    
    Returns: (can_merge, is_ambiguous)
    - (True, False): Definitively same real-world opportunity. Safe to merge into cluster.
    - (False, True): Plausible similarity but unproven identity. Preserve both; link as possible duplicate.
    - (False, False): Distinct opportunities. Never merge.
    """
    # Invariant 1: Must have identical track
    if opp_a.track != opp_b.track:
        return False, False

    # Invariant 2: Same source with distinct stable requisition IDs MUST NOT merge
    if opp_a.source == opp_b.source and opp_a.source_id and opp_b.source_id:
        if opp_a.source_id != opp_b.source_id:
            return False, False

    # Strong Identity Proof A: Common canonical outbound ATS URL
    if _have_identical_outbound_identity(opp_a, opp_b):
        return True, False

    # Invariant 3: Organization compatibility (non-empty orgs must match)
    org_a = re.sub(r"[^\w]", "", opp_a.organization.casefold())
    org_b = re.sub(r"[^\w]", "", opp_b.organization.casefold())
    if not org_a or not org_b:
        return False, False
    if org_a != org_b and not (org_a.startswith(org_b) or org_b.startswith(org_a)):
        return False, False

    # Invariant 4: Seniority compatibility (Senior != Junior/Lead/Executive)
    if opp_a.seniority != SeniorityLevel.UNSPECIFIED and opp_b.seniority != SeniorityLevel.UNSPECIFIED:
        if opp_a.seniority != opp_b.seniority:
            return False, False

    # Invariant 5: Geographic eligibility status compatibility
    if opp_a.geographic_eligibility and opp_b.geographic_eligibility:
        if opp_a.geographic_eligibility.status != opp_b.geographic_eligibility.status:
            return False, False

    # Invariant 6: Title token intersection
    title_a_tokens = _normalize_token_bag(opp_a.title)
    title_b_tokens = _normalize_token_bag(opp_b.title)
    if not title_a_tokens or not title_b_tokens:
        return False, False
    intersection = title_a_tokens & title_b_tokens
    overlap_ratio = len(intersection) / max(len(title_a_tokens), len(title_b_tokens))

    if overlap_ratio >= 0.85:
        # Check description similarity / divergence
        desc_a_tokens = _normalize_token_bag(opp_a.description)
        desc_b_tokens = _normalize_token_bag(opp_b.description)
        if desc_a_tokens and desc_b_tokens:
            desc_intersection = desc_a_tokens & desc_b_tokens
            desc_overlap = len(desc_intersection) / min(len(desc_a_tokens), len(desc_b_tokens))
            if desc_overlap < 0.25 and opp_a.source_id != opp_b.source_id:
                # Same title and org, but materially different descriptions without identity proof
                return False, True
        return True, False
    elif overlap_ratio >= 0.6:
        # Plausible but unproven
        return False, True

    return False, False


def deduplicate_opportunities(
    opportunities: Iterable[Opportunity],
) -> DeduplicationResult:
    """Execute conservative two-layer deduplication over an iterable of Opportunity records."""
    opp_list = list(opportunities)
    if not opp_list:
        return DeduplicationResult((), (), 0, 0, 0)

    # -------------------------------------------------------------
    # Layer 1: Exact Content-Hash Deduplication (within same source/content)
    # -------------------------------------------------------------
    exact_hash_map: dict[str, list[Opportunity]] = {}
    for opp in opp_list:
        exact_hash_map.setdefault(opp.content_hash, []).append(opp)

    layer1_uniques: list[Opportunity] = []
    exact_clusters: list[OpportunityCluster] = []
    exact_dupe_count = 0

    for chash, group in exact_hash_map.items():
        # Check if items in group share same source with distinct requisition IDs
        split_groups: dict[str, list[Opportunity]] = {}
        for item in group:
            key = f"{item.source}:{item.source_id}" if item.source_id else f"{item.source}:auto"
            split_groups.setdefault(key, []).append(item)

        for subkey, subgroup in split_groups.items():
            primary = subgroup[0]
            duplicates = tuple(subgroup[1:])
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
    # Layer 2: Deterministic Cross-Source Opportunity-Level Clustering
    # -------------------------------------------------------------
    final_uniques: list[Opportunity] = []
    final_clusters: list[OpportunityCluster] = list(exact_clusters)
    cross_source_dupe_count = 0
    ambiguous_dupe_count = 0

    merged_indices: set[int] = set()
    for i in range(len(layer1_uniques)):
        if i in merged_indices:
            continue
        primary = layer1_uniques[i]
        confirmed_dupes: list[Opportunity] = []
        possible_dupes: list[Opportunity] = []

        for j in range(i + 1, len(layer1_uniques)):
            if j in merged_indices:
                continue
            candidate = layer1_uniques[j]
            can_merge, is_ambiguous = _evaluate_deduplication(primary, candidate)
            if can_merge:
                confirmed_dupes.append(candidate)
                merged_indices.add(j)
            elif is_ambiguous:
                possible_dupes.append(candidate)

        merged_indices.add(i)
        final_uniques.append(primary)

        if confirmed_dupes or possible_dupes:
            cross_source_dupe_count += len(confirmed_dupes)
            ambiguous_dupe_count += len(possible_dupes)
            cluster = OpportunityCluster(
                canonical_id=primary.id,
                primary_opportunity=primary,
                duplicate_opportunities=tuple(confirmed_dupes),
                possible_duplicates=tuple(possible_dupes),
                dedup_layer="cross_source" if confirmed_dupes else "ambiguous",
                is_ambiguous=bool(possible_dupes),
            )
            final_clusters.append(cluster)

    return DeduplicationResult(
        unique_opportunities=tuple(final_uniques),
        clusters=tuple(final_clusters),
        exact_duplicates_count=exact_dupe_count,
        cross_source_duplicates_count=cross_source_dupe_count,
        ambiguous_duplicates_count=ambiguous_dupe_count,
    )
