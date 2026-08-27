"""Permitted public GET adapters and their normalizers."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from html import unescape
from typing import Any, Callable

from recon.models import Record


@dataclass(frozen=True)
class Source:
    source_id: str
    track: str
    url: str
    parser: Callable[[str, str], list[Record]]
    policy_url: str


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def _record(source: str, track: str, item: dict[str, Any], pointer: str) -> Record:
    location = item.get("location") or item.get("candidate_required_location") or item.get("locations") or item.get("locationName") or ""
    if isinstance(location, list):
        location = ", ".join(str(part) for part in location)
    organization = item.get("company_name") or item.get("company") or item.get("organization") or item.get("companyName") or item.get("team") or ""
    if isinstance(organization, dict):
        organization = organization.get("name") or ""
    url = item.get("url") or item.get("url_redirect") or item.get("absolute_url") or item.get("hostedUrl") or item.get("applyUrl") or ""
    return Record(
        source=source,
        track=track,
        title=_text(item.get("title") or item.get("name") or item.get("headline")),
        organization=_text(organization),
        location_text=_text(location),
        url=str(url),
        posted_date=str(item.get("publication_date") or item.get("date") or item.get("created_at") or item.get("updatedAt") or ""),
        description=_text(item.get("description") or item.get("description_plain") or item.get("content") or item.get("snippet")),
        raw_payload_pointer=pointer,
    )


def json_jobs(source: str, track: str) -> Callable[[str, str], list[Record]]:
    def parse(payload: str, pointer: str) -> list[Record]:
        parsed = json.loads(payload)
        if isinstance(parsed, list):
            items = parsed[1:] if source == "remote_ok" and parsed and not parsed[0].get("position") else parsed
        else:
            items = next((parsed.get(key, []) for key in ("jobs", "data", "results", "projects")), [])
            if isinstance(items, dict):
                items = next((items.get(key, []) for key in ("jobs", "results", "items")), [])
        return [_record(source, track, item, pointer) for item in items if isinstance(item, dict)]
    return parse


def rss(source: str, track: str) -> Callable[[str, str], list[Record]]:
    def parse(payload: str, pointer: str) -> list[Record]:
        root = element_tree.fromstring(payload)
        records: list[Record] = []
        for item in root.findall(".//item"):
            records.append(Record(
                source=source, track=track,
                title=_text(item.findtext("title")), organization="",
                location_text="", url=item.findtext("link") or "",
                posted_date=item.findtext("pubDate") or "",
                description=_text(item.findtext("description")), raw_payload_pointer=pointer,
            ))
        return records
    return parse


def html_links(source: str, track: str) -> Callable[[str, str], list[Record]]:
    def parse(payload: str, pointer: str) -> list[Record]:
        links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', payload, re.I | re.S)
        records = []
        for url, title in links:
            cleaned = _text(title)
            if len(cleaned) >= 12:
                records.append(Record(source, track, cleaned, "", "", unescape(url), "", "", pointer))
        return records
    return parse


EMPLOYMENT_SOURCES = (
    Source("himalayas", "employment", "https://himalayas.app/jobs/api?limit=100", json_jobs("himalayas", "employment"), "https://himalayas.app/terms"),
    Source("jobicy", "employment", "https://jobicy.com/api/v2/remote-jobs?count=50", json_jobs("jobicy", "employment"), "https://jobicy.com/terms"),
    Source("remotive", "employment", "https://remotive.com/api/remote-jobs?limit=100", json_jobs("remotive", "employment"), "https://remotive.com/terms"),
    Source("remote_ok", "employment", "https://remoteok.com/api", json_jobs("remote_ok", "employment"), "https://remoteok.com/terms"),
    Source("we_work_remotely", "employment", "https://weworkremotely.com/remote-jobs.rss", rss("we_work_remotely", "employment"), "https://weworkremotely.com/terms-and-conditions"),
)

INDEPENDENT_SOURCES = (
    Source("ungm", "independent", "https://www.ungm.org/Public/Notice", html_links("ungm", "independent"), "https://www.ungm.org/Public/Terms"),
    Source("world_bank", "independent", "https://projects.worldbank.org/en/projects-operations/opportunities", html_links("world_bank", "independent"), "https://www.worldbank.org/en/about/legal/terms-of-use"),
    Source("eu_ted", "independent", "https://api.ted.europa.eu/v3/notices/search", json_jobs("eu_ted", "independent"), "https://docs.ted.europa.eu/legal-notice.html"),
    Source("afdb", "independent", "https://www.afdb.org/en/news-keywords/procurement-notices", html_links("afdb", "independent"), "https://www.afdb.org/en/terms-and-conditions"),
    Source("freelancer", "independent", "https://www.freelancer.com/api/projects/0.1/projects/active/?limit=50", json_jobs("freelancer", "independent"), "https://www.freelancer.com/about/terms"),
    Source("etimad", "independent", "https://tenders.etimad.sa/Tender/AllTendersForVisitor", html_links("etimad", "independent"), "https://tenders.etimad.sa/"),
)


ATS_WATCHLIST: dict[str, tuple[str, str]] = {
    "cloudflare": ("greenhouse", "cloudflare"), "datadog": ("greenhouse", "datadog"),
    "duolingo": ("greenhouse", "duolingo"), "figma": ("greenhouse", "figma"),
    "flexport": ("greenhouse", "flexport"), "coinbase": ("greenhouse", "coinbase"),
    "hubspot": ("greenhouse", "hubspot"), "plaid": ("greenhouse", "plaid"),
    "stripe": ("greenhouse", "stripe"), "twilio": ("greenhouse", "twilio"),
    "coursera": ("lever", "coursera"), "mixpanel": ("lever", "mixpanel"),
    "postman": ("lever", "postman"), "samsara": ("lever", "samsara"),
    "sourcegraph": ("lever", "sourcegraph"), "netlify": ("lever", "netlify"),
    "sentry": ("lever", "sentry"), "docker": ("lever", "docker"),
    "notion": ("ashby", "notion"), "ramp": ("ashby", "ramp"), "webflow": ("ashby", "webflow"),
    "posthog": ("ashby", "posthog"), "deepl": ("ashby", "deepl"), "openai": ("ashby", "openai"),
    "linear": ("ashby", "linear"), "vanta": ("ashby", "vanta"), "calendly": ("ashby", "calendly"),
}


def ats_sources() -> tuple[Source, ...]:
    sources: list[Source] = []
    for company, (kind, board) in ATS_WATCHLIST.items():
        if kind == "greenhouse":
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        elif kind == "lever":
            url = f"https://api.lever.co/v0/postings/{board}?mode=json"
        else:
            url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=false"
        sources.append(Source(f"{kind}:{company}", "employment", url, json_jobs(kind, "employment"), "https://www.ashbyhq.com/privacy" if kind == "ashby" else "https://www.greenhouse.com/terms-of-use" if kind == "greenhouse" else "https://www.lever.co/terms"))
    return tuple(sources)
