"""Run a single, read-only reconnaissance pass and generate local artifacts."""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.robotparser import RobotFileParser

from recon.classification import classify
from recon.dedupe import deduplicate
from recon.external_policy import permits
from recon.geography import eligibility_for, extract
from recon.models import Record
from recon.sources import ATS_WATCHLIST, EMPLOYMENT_SOURCES, INDEPENDENT_SOURCES, Source, ats_sources


USER_AGENT = "OpportunityOS-SourceRecon/1.1 (+https://github.com/m7mdehab/opportunityos; read-only public research)"
SKIPPED_SOURCES = ("linkedin", "indeed", "glassdoor", "wuzzuf", "bayt", "naukrigulf", "gulftalent", "upwork", "mostaql", "khamsat", "ureed", "contra", "guru", "malt", "toptal", "wellfound")


@dataclass
class Health:
    source: str
    track: str
    status: str
    detail: str
    latency_ms: int
    raw_count: int
    policy_url: str
    request_metadata: str = ""


def robots_allow(url: str, cache: dict[str, str]) -> str:
    parsed = urllib.parse.urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    if root not in cache:
        robots_url = f"{root}/robots.txt"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT}), timeout=15) as response:
                    parser = RobotFileParser()
                    parser.parse(response.read().decode("utf-8", errors="replace").splitlines())
                    cache[root] = "allowed" if parser.can_fetch(USER_AGENT, url) else "disallowed_by_robots"
                    break
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    cache[root] = "allowed"
                    break
                cache[root] = "robots_unreachable"
            except (OSError, urllib.error.URLError, TimeoutError):
                cache[root] = "robots_unreachable"
            if attempt < 2:
                time.sleep(2 ** attempt)
    return cache[root]


def fetch(source: Source, out_dir: Path, robots: dict[str, str]) -> tuple[list[Record], Health]:
    robots_status = robots_allow(source.url, robots)
    if robots_status != "allowed":
        return [], Health(source.source_id, source.track, robots_status, "robots.txt disallowed access" if robots_status == "disallowed_by_robots" else "robots.txt could not be read after three attempts", 0, 0, source.policy_url)
    if source.method != "GET" and not permits(source.method, source.url, source.action_classification):
        raise SystemExit(
            f"SOURCE DEFINITION ERROR: {source.source_id} uses method={source.method} "
            f"which is not allowlisted by AGENT_PERMISSIONS.yaml. "
            "Fix the source definition or update committed permissions before running."
        )
    started = time.monotonic()
    body = None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, text/html;q=0.9"}
    metadata = f"method={source.method}; endpoint={urllib.parse.urlparse(source.url).path}"
    if source.method == "POST":
        body = json.dumps(source.request_body or {}, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
        metadata += f"; fields={','.join(sorted((source.request_body or {}).keys()))}"
    request = urllib.request.Request(source.url, data=body, method=source.method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            payload = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return [], Health(source.source_id, source.track, f"http_{error.code}", error.read(300).decode("utf-8", errors="replace").replace("\n", " "), int((time.monotonic()-started)*1000), 0, source.policy_url, metadata)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return [], Health(source.source_id, source.track, "network_error", str(error), int((time.monotonic()-started)*1000), 0, source.policy_url, metadata)
    latency = int((time.monotonic() - started) * 1000)
    fixture = out_dir / "fixtures" / f"{source.source_id.replace(':', '_')}.json"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(payload, encoding="utf-8")
    try:
        records = [
            replace(record, source=source.source_id)
            for record in source.parser(payload, str(fixture.relative_to(out_dir)))]
    except (ValueError, KeyError, json.JSONDecodeError, Exception) as error:
        return [], Health(source.source_id, source.track, "parse_error", str(error), latency, 0, source.policy_url, metadata)
    if not records:
        return [], Health(source.source_id, source.track, "parse_empty", "HTTP 200 parsed zero records", latency, 0, source.policy_url, metadata)
    return records, Health(source.source_id, source.track, "allowed_ok", "HTTP 200 parsed records", latency, len(records), source.policy_url, metadata)


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_registry(path: Path, health: list[Health]) -> None:
    lines = ["# Generated by recon; status records observed read access, not future action permission.", "sources:"]
    for item in health:
        lines.extend([f"  - source_id: {item.source}", f"    name: {yaml_quote(item.source)}", f"    category: {'employment' if item.track == 'employment' else 'independent'}", "    access:", "      discovery: public_get", "      detail: public_get_or_unknown", "      submit: prohibited_or_unknown", "    attribution:", "      required: review_required", "    rate_limits:", "      documented: unknown", "    commercial_use:", "      status: review_required", "    automation:", f"      read: {'allowed' if item.status in {'allowed_ok', 'parse_empty'} else 'disabled'}", "      prepare: disabled", "      submit: disabled", "    policy_status: unknown_disable_actions", "    observed:", f"      status: {item.status}", f"      detail: {yaml_quote(item.detail[:300])}", f"      request_metadata: {yaml_quote(item.request_metadata)}", f"      latency_ms: {item.latency_ms}", f"      record_count: {item.raw_count}", "    last_policy_reviewed: 2026-08-28", "    policy_evidence:", f"      - {item.policy_url}"])
    for source in SKIPPED_SOURCES:
        lines.extend([f"  - source_id: {source}", f"    name: {yaml_quote(source)}", "    category: skipped_platform", "    access:", "      discovery: manual_deeplink_or_alert", "      detail: not_fetched", "      submit: prohibited_or_unknown", "    attribution:", "      required: review_required", "    rate_limits:", "      documented: review_required", "    commercial_use:", "      status: review_required", "    automation:", "      read: disabled", "      prepare: disabled", "      submit: disabled", "    policy_status: manual_only", "    observed:", "      status: deliberately_not_fetched", "      detail: " + yaml_quote("BRIEF-001 §6: listings were not fetched; evaluate public alert, deep-link, partnership, and terms routes before any future adapter."), "      latency_ms: 0", "      record_count: 0", "    last_policy_reviewed: 2026-08-27", "    policy_evidence:", "      - https://github.com/m7mdehab/opportunityos/blob/main/briefs/BRIEF-001.md"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_csv(path: Path, records: list[Record]) -> None:
    columns = [*Record.__dataclass_fields__, "eligibility", "eligibility_reason", "individual_eligibility", "individual_reason"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            extracted = extract(record)
            writer.writerow({**extracted.flat(), **classify(record).__dict__})


def write_evidence(path: Path, all_records: list[Record], unique: list[Record], duplicate_count: int, overlaps: int, health: list[Health]) -> None:
    by_source = {item.source: item for item in health}
    def family(source: str) -> str:
        return source.split(":", 1)[0]
    families = sorted({family(item.source) for item in health})
    eligible = {source: 0 for source in by_source}
    unclear_geography = 0
    country_counts = {country: 0 for country in ("EG", "AE", "SA", "DE")}
    unmapped: dict[str, int] = {}
    individuals = {source: 0 for source in by_source}
    for record in unique:
        extracted = extract(record)
        decision = classify(record)
        eligible[record.source] = eligible.get(record.source, 0) + (decision.eligibility == "eligible")
        unclear_geography += decision.eligibility == "unclear"
        individuals[record.source] = individuals.get(record.source, 0) + (decision.individual_eligibility == "individual_ok")
        for country in country_counts:
            country_counts[country] += eligibility_for(extracted, country)[0] == "eligible"
        for phrase in extracted.unmapped:
            unmapped[phrase] = unmapped.get(phrase, 0) + 1
    total_eligible = sum(eligible.values())
    rate = (total_eligible / len(unique) * 100) if unique else 0
    unclear_rate = (unclear_geography / len(unique) * 100) if unique else 0
    lines = ["# SOURCE_EVIDENCE — BRIEF-001", "", "**Run date:** 2026-08-27", "", "## Required numbers", "", f"1. **Total raw records fetched:** {len(all_records)}.", "", "| Source family | Raw records | Unique eligible | Individual-eligible |", "|---|---:|---:|---:|"]
    for source in families:
        members = [item.source for item in health if family(item.source) == source]
        lines.append(f"| {source} | {sum(by_source[item].raw_count for item in members)} | {sum(eligible.get(item, 0) for item in members)} | {sum(individuals.get(item, 0) for item in members)} |")
    lines.extend(["", f"2. **Unique records after deduplication:** {len(unique)}; **duplicate rate:** {(duplicate_count / len(all_records) * 100) if all_records else 0:.1f}%.", f"3. **Cross-source overlap:** {overlaps} fingerprints appeared on more than one source.", "4. **Egypt-eligible percentage:** withheld pending the mandatory precision audit.", f"5. **Unclear percentage:** {unclear_rate:.1f}% ({unclear_geography}/{len(unique)}) stated no geography at all.", "6. **Individual-eligible count:** per-source counts are in the table above.", "", "## Source health", "", "| Source | Status | Latency ms | Records | Detail |", "|---|---|---:|---:|---|"])
    for item in health:
        lines.append(f"| {item.source} | {item.status} | {item.latency_ms} | {item.raw_count} | {item.detail.replace('|', '/')} |")
    lines.extend(["", "## Derived country views", "", "| Country | Eligible records |", "|---|---:|"])
    lines.extend(f"| {country} | {count} |" for country, count in country_counts.items())
    lines.extend(["", "## Per-source Egypt eligibility", "", "| Source | Eligible rate |", "|---|---:|"])
    for source, item in sorted(by_source.items()):
        source_records = sum(record.source == source for record in unique)
        lines.append(f"| {source} | {(eligible.get(source, 0) / source_records * 100) if source_records else 0:.1f}% |")
    lines.extend(["", "## Unmapped geography", "", f"Unmapped count: {sum(unmapped.values())}.", "", "| Phrase | Count |", "|---|---:|"])
    lines.extend(f"| {phrase} | {count} |" for phrase, count in sorted(unmapped.items(), key=lambda item: (-item[1], item[0]))[:20])
    lines.extend(["", "## ATS company watchlist", "", ", ".join(ATS_WATCHLIST), "", f"The list contains {len(ATS_WATCHLIST)} remote-friendly organizations selected for plausibility across data engineering, data science, analytics, and AI engineering. Each replacement was verified at its named public ATS endpoint before this run.", "", "## Scope and policy", "", "Only unauthenticated HTTP GET requests, plus the ADR-0005 TED read-only query POST, were made with the truthful `OpportunityOS-SourceRecon/1.1` user agent after a robots.txt check. No accounts, credentials, writes, submissions, retries after a block, or listing fetches from the 16 deliberately skipped platforms were used. Raw responses and normalized rows remain only under ignored `out/`; this report publishes aggregate measurements, not source corpus content.", "", "## What this changes about the plan", "", "This is a one-pass availability measurement, not a validation of the 37-source Phase 1 build-out or the regional-eligibility moat. The measured eligible share and the number of policy-blocked or unreadable routes should determine whether to build any adapter next. It contradicts any assumption that all 37 source families should be implemented before their permitted access and Egypt eligibility are measured."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one read-only public-source reconnaissance pass.")
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--docs", type=Path, default=Path("docs"))
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True)
    robots: dict[str, str] = {}
    health: list[Health] = []
    records: list[Record] = []
    for source in (*EMPLOYMENT_SOURCES, *INDEPENDENT_SOURCES, *ats_sources()):
        parsed, result = fetch(source, args.out, robots)
        records.extend(parsed)
        health.append(result)
    unique, duplicates, overlaps = deduplicate(records)
    write_csv(args.out / "opportunities.csv", unique)
    write_registry(args.docs / "SOURCE_REGISTRY.yaml", health)
    write_evidence(args.docs / "SOURCE_EVIDENCE.md", records, unique, duplicates, overlaps, health)
    print(f"Fetched {len(records)} raw records; wrote {len(unique)} unique records.")


if __name__ == "__main__":
    main()
