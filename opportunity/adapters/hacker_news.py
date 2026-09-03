"""Hacker News "Who is hiring?" Public Firebase API Adapter.

BRIEF-FR-006 E23. Source recon (2026-09-03): `hacker-news.firebaseio.com/robots.txt`
returns `Allow: /*.json$` for all user agents, and `GET /v0/item/1.json` returned HTTP
200. No account, key, or authentication is required; this is the documented public
Firebase mirror of Hacker News (https://github.com/HackerNews/API).

The monthly "Who is hiring?" thread is not a single-request resource on the Firebase
API: the thread id must first be discovered (via the `whoishiring` account's submitted
items), then the thread item fetched for its `kids` (top-level comment ids), then each
top-level comment fetched individually as a job posting. `parse_payload` below is
therefore deliberately decoupled from the network: it consumes an already-assembled
JSON document (see `PAYLOAD SHAPE` below). `fetch_who_is_hiring_payload()` performs the
live, multi-step, GET-only Firebase orchestration and returns that JSON document as a
string, for use by recon and by the poll worker. This split is the "clearly marked
seam" called out in the work order: the live multi-request fetch is not wired into
`worker/handlers.py` by this work order (that file is outside E23's allowed-files list)
-- the Master wires the fetch step at integration; this module is ready to be called
with whatever payload results.

PAYLOAD SHAPE (what `parse_payload` expects):
    {
      "thread_id": 12345678,
      "thread_title": "Ask HN: Who is hiring? (September 2026)",
      "comments": [
        {"id": 111, "by": "someuser", "time": 1767000000, "text": "<p>Company | Remote ..."},
        ...
      ]
    }
Each entry in "comments" is a verbatim Hacker News Firebase `item` object for a
top-level comment (dead/deleted comments are skipped upstream by the fetch helper).
"""
from __future__ import annotations

import json
import re
import urllib.request
from html import unescape
from typing import Any

from opportunity.adapters.base import BaseAdapter
from opportunity.models import (
    DerivationType,
    FieldProvenance,
    Opportunity,
    ParseResult,
    Track,
    compute_deterministic_id,
)
from opportunity.normalization import (
    clean_text,
    compute_record_checksum,
    create_field_provenance,
    derive_geographic_eligibility,
    extract_compensation,
    extract_employment_type,
    extract_work_location,
    extract_seniority,
    extract_skills_from_text,
    extract_track,
)

USER_AGENT = "OpportunityOS-SourceRecon/1.1 (+https://github.com/m7mdehab/opportunityos; read-only public research)"
FIREBASE_BASE = "https://hacker-news.firebaseio.com/v0"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return unescape(_TAG_RE.sub(" ", text or "")).strip()


def fetch_who_is_hiring_payload(max_comments: int = 200, timeout: int = 20) -> str:
    """Live, GET-only, public-Firebase-API fetch of the latest "Who is hiring?" thread.

    Not exercised by the committed unit tests (which use a static fixture payload) to
    keep `unittest` offline and deterministic; used by recon and, at integration, by the
    poll worker. Every request is GET to `hacker-news.firebaseio.com`, matching the
    endpoint rule registered in `opportunity/registry.py`.
    """
    def _get(url: str) -> Any:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    user = _get(f"{FIREBASE_BASE}/user/whoishiring.json")
    submitted_ids = list(user.get("submitted", []))[:60]
    thread_item: dict[str, Any] | None = None
    for item_id in submitted_ids:
        item = _get(f"{FIREBASE_BASE}/item/{item_id}.json")
        if item and isinstance(item, dict) and str(item.get("title", "")).lower().startswith("ask hn: who is hiring"):
            thread_item = item
            break
    if thread_item is None:
        return json.dumps({"thread_id": None, "thread_title": "", "comments": []})

    comments: list[dict[str, Any]] = []
    for kid_id in list(thread_item.get("kids", []))[:max_comments]:
        kid = _get(f"{FIREBASE_BASE}/item/{kid_id}.json")
        if not kid or kid.get("deleted") or kid.get("dead"):
            continue
        comments.append(kid)

    return json.dumps({
        "thread_id": thread_item.get("id"),
        "thread_title": thread_item.get("title", ""),
        "comments": comments,
    })


class HackerNewsWhoIsHiringAdapter(BaseAdapter):
    """Parses an assembled Hacker News "Who is hiring?" thread payload (see module docstring)."""

    def __init__(self) -> None:
        super().__init__(
            source_id="hacker_news_who_is_hiring",
            track=Track.EMPLOYMENT,
            feed_url="https://hacker-news.firebaseio.com/v0/user/whoishiring.json",
            policy_url="https://github.com/HackerNews/API",
        )

    def parse_payload(
        self, payload: str, raw_pointer: str = "", fetched_at: str = ""
    ) -> ParseResult:
        data = json.loads(payload)
        if not isinstance(data, dict) or "comments" not in data:
            return ParseResult(opportunities=(), records_raw_count=0, has_schema_drift=True)

        comments = data["comments"]
        raw_count = len(comments)
        opportunities: list[Opportunity] = []
        for idx, comment in enumerate(comments):
            if not isinstance(comment, dict):
                continue
            item_pointer = f"{raw_pointer or 'feed'}:comments[{idx}]"
            record_checksum = compute_record_checksum(comment)

            remote_id = str(comment.get("id") or "")
            raw_text = comment.get("text") or ""
            plain_text = _strip_html(raw_text)
            if not plain_text:
                continue

            # Convention for "who is hiring" posts: "Company | Location | Role details ..."
            first_line = plain_text.split("\n", 1)[0][:300].strip()
            title = clean_text(first_line) or clean_text(plain_text[:120])
            if not title:
                continue

            organization = ""
            if "|" in first_line:
                organization = clean_text(first_line.split("|", 1)[0])

            description = clean_text(plain_text)
            url = f"https://news.ycombinator.com/item?id={remote_id}"

            skills = extract_skills_from_text(plain_text)
            seniority = extract_seniority(title, description)
            emp_type = extract_employment_type("", title, description)
            track = extract_track(self.track, "", title, description)
            # BRIEF-FR-006 A1 defect fix (post-merge grep sweep): this adapter
            # landed via E23 after A1's remote_policy=... constructor kwarg was
            # removed. No native work-mode field exists in free-text HN "who is
            # hiring" comments, so this is text inference only, same as every
            # other text-only adapter.
            work_loc = extract_work_location("", description)
            comp = extract_compensation(description)
            geo = derive_geographic_eligibility(
                title=title,
                location_raw="",
                description=description,
                track=track,
                source=self.source_id,
                url=url,
            )

            provenance = self.create_provenance(
                source_url=url,
                raw_pointer=item_pointer,
                fetched_at=fetched_at,
                payload=payload,
            )

            prov_list: list[FieldProvenance] = [
                create_field_provenance("track", "", track.value, DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_track"),
                create_field_provenance("organization", first_line, organization, DerivationType.RAW_EXTRACTION if organization else DerivationType.UNASSERTED_ABSENT, f"{item_pointer}.text", record_checksum, "clean_text"),
                create_field_provenance("title", first_line, title, DerivationType.RAW_EXTRACTION, f"{item_pointer}.text", record_checksum, "clean_text"),
                create_field_provenance("description", raw_text[:100], description[:100], DerivationType.RAW_EXTRACTION, f"{item_pointer}.text", record_checksum, "clean_text"),
                create_field_provenance("seniority", title, seniority.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.text", record_checksum, "extract_seniority"),
                create_field_provenance("employment_type", "", emp_type.value, DerivationType.RULE_DERIVATION, f"{item_pointer}.text", record_checksum, "extract_employment_type"),
                create_field_provenance(
                    "work_mode", "", work_loc.work_mode.value,
                    DerivationType.RULE_DERIVATION if work_loc.work_mode_source == "inference" else DerivationType.UNASSERTED_ABSENT,
                    f"{item_pointer}.text", record_checksum, work_loc.work_mode_rule_id or "extract_work_location",
                ),
                create_field_provenance("geographic_eligibility", description[:50], geo.status, DerivationType.RULE_DERIVATION, f"{item_pointer}.text", record_checksum, "classify_geography"),
            ]
            if skills:
                prov_list.append(create_field_provenance("skills", plain_text[:50], ", ".join(skills), DerivationType.RULE_DERIVATION, item_pointer, record_checksum, "extract_skills"))
            if comp is not None:
                prov_list.append(create_field_provenance("compensation", description[:50], f"{comp.min_amount}-{comp.max_amount} {comp.currency}", DerivationType.RULE_DERIVATION, f"{item_pointer}.text", record_checksum, "extract_compensation"))

            opp_id = compute_deterministic_id(self.source_id, remote_id, title, organization, item_pointer)

            opp = Opportunity(
                id=opp_id,
                track=track,
                source=self.source_id,
                source_url=url,
                source_id=remote_id,
                organization=organization,
                title=title,
                description=description,
                responsibilities=(),
                requirements=(),
                skills=skills,
                seniority=seniority,
                employment_type=emp_type,
                location_raw="",
                work_mode=work_loc.work_mode,
                work_mode_source=work_loc.work_mode_source,
                location_country=work_loc.location_country,
                location_city=work_loc.location_city,
                location_region=work_loc.location_region,
                remote_scope=work_loc.remote_scope,
                remote_scope_regions=work_loc.remote_scope_regions,
                geographic_eligibility=geo,
                compensation=comp,
                posted_date=None,
                raw_provenance=provenance,
                record_checksum=record_checksum,
                raw_record_pointer=item_pointer,
                field_provenances=tuple(prov_list),
                canonical_outbound_url=url,
            )
            opportunities.append(opp)

        return ParseResult(opportunities=tuple(opportunities), records_raw_count=raw_count)
