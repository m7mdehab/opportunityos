"""Offline-only Reddit hiring-post classifier/canonicalizer.

This module accepts a post payload only after a caller has obtained it through
authorized Reddit access. It performs no network I/O, scraping, retries, or
model-training work; the repository keeps Reddit sources disabled until access
and usage permission are approved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


_URL = re.compile(r"https?://[^\s<>\])}]+", re.IGNORECASE)
_HIRING_TAG = re.compile(r"\[(?:hiring|we'?re hiring)\]", re.IGNORECASE)
_FOR_HIRE_TAG = re.compile(r"\[(?:for\s*hire|forhire)\]", re.IGNORECASE)
_HIRING_SIGNAL = re.compile(r"\b(?:we are hiring|we're hiring|now hiring|open role|job opening|looking to hire)\b", re.IGNORECASE)
_NOISE = re.compile(r"\b(?:course|bootcamp|training program|resume service|cv service|recruiting service)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RedditHiringCandidate:
    subreddit: str
    post_id: str
    permalink: str
    title: str
    body: str
    posted_at: str
    employer: str
    application_url: str
    canonical_url: str
    application_route: str
    confidence: float
    classification: str = "hiring_post"


def canonicalize_ats_url(url: str) -> tuple[str, str] | None:
    """Recognize a direct public Greenhouse, Lever, or Ashby posting URL."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.strip("/")
    parts = [part for part in path.split("/") if part]
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and len(parts) >= 3 and parts[1] == "jobs":
        return "greenhouse", f"https://{host}/{parts[0]}/jobs/{parts[2]}"
    if host == "jobs.lever.co" and len(parts) >= 2:
        return "lever", f"https://jobs.lever.co/{parts[0]}/{parts[1]}"
    if host == "jobs.ashbyhq.com" and len(parts) >= 2:
        return "ashby", f"https://jobs.ashbyhq.com/{parts[0]}/{parts[1]}"
    return None


def parse_hiring_post(post: dict) -> RedditHiringCandidate | None:
    """Return a conservative job candidate; discard self-promotion/discussion/noise."""
    title = str(post.get("title") or "").strip()
    body = str(post.get("selftext") or post.get("body") or "").strip()
    combined = f"{title}\n{body}"
    if not title or _FOR_HIRE_TAG.search(title) or _NOISE.search(combined):
        return None
    tagged = bool(_HIRING_TAG.search(title))
    if not tagged and not _HIRING_SIGNAL.search(combined):
        return None

    subreddit = str(post.get("subreddit") or "").strip().lstrip("r/")
    post_id = str(post.get("id") or "").strip()
    permalink_path = str(post.get("permalink") or "").strip()
    permalink = (
        f"https://www.reddit.com/{permalink_path.lstrip('/')}"
        if permalink_path.startswith("/")
        else permalink_path
    )
    urls: list[str] = []
    for candidate in _URL.findall(f"{title}\n{body}"):
        clean = candidate.rstrip(".,;:!?\"'")
        parsed = urlparse(clean)
        if parsed.hostname and not parsed.hostname.lower().endswith("reddit.com") and clean not in urls:
            urls.append(clean)
    ats_match = next((canonicalize_ats_url(url) for url in urls if canonicalize_ats_url(url)), None)
    application_url = ats_match[1] if ats_match else (urls[0] if urls else "")
    route = ats_match[0] if ats_match else "unknown"
    employer = str(post.get("employer") or "").strip()
    confidence = 0.75 if tagged else 0.55
    if application_url:
        confidence = min(0.9, confidence + 0.1)
    return RedditHiringCandidate(
        subreddit=subreddit,
        post_id=post_id,
        permalink=permalink,
        title=title,
        body=body,
        posted_at=str(post.get("created_utc") or post.get("created_at") or ""),
        employer=employer,
        application_url=application_url,
        canonical_url=application_url,
        application_route=route,
        confidence=confidence,
    )
