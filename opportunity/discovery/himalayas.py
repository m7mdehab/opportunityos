"""Bounded, target-role Himalayas search plan for the public jobs API.

The API's browse route is cursor-paginated at 20 records and refreshes daily.
For the Founder feed, use the documented search route once per role family and
location scope instead of repeatedly ingesting the arbitrary first page.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode


HIMALAYAS_SEARCH_ENDPOINT = "https://himalayas.app/jobs/api/search"
HIMALAYAS_TARGET_QUERIES = (
    "data engineer",
    "analytics engineer",
    "data analyst",
    "business intelligence",
    "data scientist",
    "machine learning engineer",
    "AI engineer",
    "MLOps",
    "data platform",
    "data governance",
)


def targeted_search_urls(
    *,
    queries: tuple[str, ...] = HIMALAYAS_TARGET_QUERIES,
    page: int = 1,
    seniority: tuple[str, ...] = ("Mid-level", "Senior", "Manager", "Director"),
    employment_type: tuple[str, ...] = ("Full Time", "Contractor"),
) -> tuple[str, ...]:
    """Build deterministic Egypt + worldwide recent-search URLs.

    Search pagination is page-based. The production poll deliberately requests
    only the first recent page for each target query to bound daily work; callers
    can request a later page explicitly when a controlled canary needs it.
    """
    if page < 1:
        raise ValueError("Himalayas search pages are 1-based")
    return tuple(
        f"{HIMALAYAS_SEARCH_ENDPOINT}?{urlencode({'q': query, 'country': 'Egypt', 'worldwide': 'true', 'seniority': ','.join(seniority), 'employment_type': ','.join(employment_type), 'sort': 'recent', 'page': page})}"
        for query in queries
    )


def merge_search_payloads(payloads: tuple[str, ...] | list[str]) -> tuple[str, int]:
    """Combine successful search pages and remove overlaps by source identity.

    A malformed page fails the entire bounded source poll rather than silently
    presenting a partial result as a complete successful search.
    """
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_count = 0
    for page_number, payload in enumerate(payloads, start=1):
        data = json.loads(payload)
        page_jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(page_jobs, list):
            raise ValueError(f"Himalayas search page {page_number} did not contain a jobs list")
        raw_count += len(page_jobs)
        for job in page_jobs:
            if not isinstance(job, dict):
                continue
            key = next(
                (str(job.get(field)).strip() for field in ("guid", "id", "slug", "applicationLink", "url") if job.get(field)),
                "",
            )
            if not key:
                key = "|".join((str(job.get("companyName") or "").strip().casefold(), str(job.get("title") or "").strip().casefold()))
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            jobs.append(job)
    return json.dumps({"jobs": jobs}, ensure_ascii=False), raw_count
