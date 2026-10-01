"""Offline replay of a sanitized production evidence envelope through BC gates.

This intentionally consumes only public opportunity evidence. Founder feedback,
actions, identity, CV selections, and scoring details are absent from the fixture.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from matching.recommendation_engine import (
    RecommendationCandidate,
    build_behavior_profile,
    recommend,
)
from matching.recommendation_foundation import (
    classify_application_access,
    classify_founder_geography,
    classify_required_credentials,
    classify_role_relevance,
)
from opportunity.normalization import clean_text
from opportunity.unicode_safety import normalize_unicode


DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "bc_production_replay_2026-10-01.json"


def _regions(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if item)
    text = str(value).strip()
    if text.startswith("["):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return tuple(str(item) for item in decoded if item)
    return tuple(part.strip() for part in text.split(",") if part.strip())


def replay_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Replay canonical source evidence through the deterministic BC gates."""
    row = normalize_unicode(candidate)
    title = str(row.get("title") or "")
    description = clean_text(row.get("evidence_text"))
    role = classify_role_relevance(title, description)
    credential_state, credential_reason = classify_required_credentials(description)
    geography, geography_reason = classify_founder_geography(
        title=title,
        description=description,
        location_country=row.get("location_country"),
        location_city=row.get("location_city"),
        location_region=row.get("location_region"),
        work_mode=str(row.get("work_mode") or "unspecified"),
        remote_scope=str(row.get("remote_scope") or "unspecified"),
        remote_scope_regions=_regions(row.get("remote_scope_regions")),
    )
    access = classify_application_access(
        str(row.get("source_id") or ""),
        str(row.get("source_url") or ""),
        str(row.get("application_url") or ""),
    )
    result = recommend(RecommendationCandidate(
        opportunity_id=str(row["opportunity_id"]),
        role_relevance=role.classification,
        geography=geography,
        application_access=access.access,
        application_url=access.application_url,
        decision=None,
        fit_score=None,
        confidence_score=None,
        role_family=role.title_family,
        source_family=str(row.get("source_id") or "").split(":", 1)[0],
        is_stale=False,
        family_key=str(row.get("opportunity_id") or ""),
        organization=str(row.get("organization") or ""),
        eligibility_state=credential_state,
        eligibility_reason=credential_reason,
    ), behavior=build_behavior_profile(()))
    return {
        "opportunity_id": row["opportunity_id"],
        "title": title,
        "organization": row.get("organization"),
        "source_id": row.get("source_id"),
        "sample_group": row.get("sample_group"),
        "role_relevance": role.classification,
        "role_relevant": role.classification in {"core", "adjacent"},
        "role_family": role.title_family,
        "role_reason": role.reason,
        "geography": geography,
        "geography_compatible": geography in {"eligible", "likely_eligible"},
        "geography_reason": geography_reason,
        "credential_state": credential_state or "clean",
        "credential_clean": credential_state is None,
        "credential_reason": credential_reason,
        "application_access": access.access,
        "application_actionable": access.access in {"direct_free", "free_intermediary", "free_account_required"} and bool(access.application_url),
        "application_route": access.route,
        "application_reason": access.reason,
        "recommendation": result.state,
        "recommendation_reasons": list(result.reasons),
    }


def replay_candidate_files(fixture_paths: tuple[Path, ...]) -> dict[str, Any]:
    """Replay one or more frozen canonical evidence envelopes, deduping IDs."""
    if not fixture_paths:
        raise ValueError("at least one frozen replay fixture is required")
    fixtures = [json.loads(path.read_text(encoding="utf-8")) for path in fixture_paths]
    grouped: dict[str, dict[str, Any]] = {}
    for fixture in fixtures:
        for candidate in fixture["candidates"]:
            opportunity_id = str(candidate["opportunity_id"])
            prior = grouped.get(opportunity_id)
            if prior is None or len(str(candidate.get("evidence_text") or "")) > len(str(prior.get("evidence_text") or "")):
                grouped[opportunity_id] = dict(candidate)
            elif prior is not None:
                groups = {str(prior.get("sample_group") or ""), str(candidate.get("sample_group") or "")}
                groups.discard("")
                prior["sample_group"] = ",".join(sorted(groups))
    candidates = list(grouped.values())
    rows = [replay_candidate(row) for row in candidates]
    unique = {row["opportunity_id"] for row in rows}
    return {
        "fixtures": [fixture.get("fixture") for fixture in fixtures],
        "captured_at": max(str(fixture.get("captured_at") or "") for fixture in fixtures),
        "candidate_count": len(rows),
        "deduplicated_count": len(unique),
        "gate_counts": {
            "role_core_or_adjacent": sum(row["role_relevant"] for row in rows),
            "Egypt_compatible": sum(row["geography_compatible"] for row in rows),
            "credential_clean": sum(row["credential_clean"] for row in rows),
            "actionable_access": sum(row["application_actionable"] for row in rows),
            "For_You": sum(row["recommendation"] == "for_you" for row in rows),
        },
        "recommendation_counts": {
            state: sum(row["recommendation"] == state for row in rows)
            for state in ("for_you", "review", "excluded")
        },
        "for_you_employers": sorted({row["organization"] for row in rows if row["recommendation"] == "for_you"}),
        "candidates": rows,
    }


def replay(fixture_path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    return replay_candidate_files((fixture_path,))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, action="append", dest="fixtures")
    arguments = parser.parse_args()
    print(json.dumps(replay_candidate_files(tuple(arguments.fixtures or (DEFAULT_FIXTURE,))), indent=2, sort_keys=True))
