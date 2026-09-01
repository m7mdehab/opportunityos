#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "docs" / "STATE.md"


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def source_head() -> tuple[str, str]:
    commit = git(
        "log",
        "-1",
        "--format=%H%x00%s",
        "--",
        ".",
        ":(exclude)docs/STATE.md",
    )
    if not commit:
        return "uncommitted", "repository foundation"
    sha, _, subject = commit.partition("\x00")
    return sha[:7], subject


def numbered_files(directory: str, prefix: str) -> dict[int, Path]:
    result: dict[int, Path] = {}
    for path in (ROOT / directory).glob(f"{prefix}-*.md"):
        match = re.fullmatch(rf"{prefix}-(\d+)\.md", path.name)
        if match:
            result[int(match.group(1))] = path
    return result


def custom_files(directory: str, prefix: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in (ROOT / directory).glob(f"{prefix}-*.md"):
        match = re.fullmatch(rf"{prefix}-([A-Z0-9_-]+)\.md", path.name)
        if match:
            result[match.group(1)] = path
    return result


def gate_files(directory: str, prefix: str) -> dict[str, Path]:
    return custom_files(directory, prefix)


def section(text: str, title: str) -> str:
    match = re.search(
        rf"(?ims)^##+\s+(?:\d+\.\s+)?{re.escape(title)}\s*$\n(.*?)(?=^##+\s+|\Z)", text
    )
    return match.group(1).strip() if match else ""


def decision_line(text: str) -> str:
    decision_text = section(text, "Decision")
    for raw in decision_text.splitlines():
        line = raw.strip().lstrip("- ").strip()
        if not line:
            continue
        cleaned = re.sub(r"[\*_`#]", "", line).strip()
        if cleaned:
            return cleaned
    return "undecided"


def report_date(path: Path) -> str:
    match = re.search(r"(?m)^\*\*Date:\*\*\s*(.+)$", path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else "undated"


def brief_status(number: int, reports: dict[int, Path]) -> str:
    if number not in reports:
        return "in progress"
    report = reports[number].read_text(encoding="utf-8")
    decision = decision_line(report)
    return "passed" if "pass" in decision.lower() else "in progress"


def acceptance_items(brief_path: Path) -> list[str]:
    text = brief_path.read_text(encoding="utf-8")
    metrics_match = re.search(
        r"(?ims)^required_acceptance_metrics:\s*\n(.*?)(?=^\w|\Z)", text
    )
    if not metrics_match:
        return []
    items: list[str] = []
    for raw in metrics_match.group(1).splitlines():
        line = raw.strip()
        if line.startswith("-"):
            items.append(line.lstrip("- ").strip())
        elif ":" in line:
            key, _, value = line.partition(":")
            items.append(f"{key.strip()}: {value.strip()}")
    return items


def adr_records() -> tuple[list[str], list[str]]:
    proposed: list[str] = []
    accepted: list[str] = []
    for path in sorted((ROOT / "docs" / "adr").glob("ADR-*.md")):
        text = path.read_text(encoding="utf-8")
        status_match = re.search(r"(?m)^-\s+\*\*Status:\*\*\s*(.+)$", text)
        title_match = re.search(r"(?m)^#\s+(.+)$", text)
        if not (status_match and title_match):
            continue
        status = status_match.group(1).strip().lower()
        title = title_match.group(1).strip()
        rel_path = path.relative_to(ROOT / "docs").as_posix()
        link = f"[{title}]({rel_path})"
        if "accepted" in status:
            accepted.append(link)
        else:
            proposed.append(link)
    return proposed, accepted


def source_counts(registry_path: Path | None = None) -> Counter[str]:
    registry = registry_path if registry_path is not None else ROOT / "docs" / "SOURCE_REGISTRY.yaml"
    if not registry.exists():
        return Counter()
    data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    counts: Counter[str] = Counter()
    for entry in data.get("sources") or []:
        observed = (entry or {}).get("observed") or {}
        status = observed.get("status")
        if status:
            counts[status] += 1
    return counts


def mirror_sync() -> tuple[str, str]:
    record = git("log", "--format=%s%x00%cI", "--grep=^sync: ", "-1")
    if not record:
        return "not yet recorded", "not yet recorded"
    subject, _, timestamp = record.partition("\x00")
    return subject.removeprefix("sync: ").strip(), timestamp or "unknown"


def generated_at() -> str:
    if os.environ.get("STATE_PRESERVE_TIMESTAMP") == "1" and STATE_PATH.exists():
        existing = STATE_PATH.read_text(encoding="utf-8")
        match = re.search(r"(?m)^- \*\*Generated:\*\* (.+)$", existing)
        if match:
            return match.group(1).strip()
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def bullets(items: list[str], empty: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


_LIST_MARKER_RE = re.compile(r"^[-*]\s*")
_EMPHASIS_RE = re.compile(r"[*_`]")
# A sentence terminator only counts when followed by whitespace or end of
# string, so it does not fire on things like "Next.js" or "e.g.io".
_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")
_NEXT_SUMMARY_FALLBACK = "complete active brief"


def _clean_prerequisite_line(line: str) -> str:
    text = _LIST_MARKER_RE.sub("", line.strip())
    text = _EMPHASIS_RE.sub("", text)
    return text.strip()


def _first_sentence(text: str) -> str | None:
    match = _SENTENCE_END_RE.search(text)
    return text[: match.end()].strip() if match else None


def _truncate_on_word_boundary(text: str, limit: int = 300) -> str:
    if len(text) <= limit:
        return text
    truncated = text[:limit].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip()


def _finalize_summary(text: str) -> str:
    text = text.strip().rstrip(":.!?").strip()
    return f"{text}." if text else f"{_NEXT_SUMMARY_FALLBACK}."


def _join_lines_until_sentence(lines: list[str]) -> tuple[str | None, str]:
    """Progressively join cleaned `lines` (non-empty) until a sentence
    terminator is found — used both for a colon lead-in and for prose
    hard-wrapped across physical lines with no terminator on the first
    line. Returns (sentence, full_paragraph): `sentence` is the first
    complete sentence found across line boundaries, or None if no line in
    `lines` ever completes one; when None, `full_paragraph` is every line
    joined (the loop only runs to completion, without an early break, in
    that case), for use as the whole-paragraph fallback."""
    joined = lines[0]
    sentence = _first_sentence(joined)
    for line in lines[1:]:
        if sentence is not None:
            break
        joined = f"{joined} {line}"
        sentence = _first_sentence(joined)
    return sentence, joined


def next_summary_from_prerequisites(prerequisites: str) -> str:
    """Render the first complete sentence (or whole first paragraph, capped
    at 300 chars) of a prerequisites section, never a fragment ending in
    ':' or ':.'. A sentence may span several physical lines — a lead-in
    colon, or hard-wrapped prose with no terminator on its first line —
    joining stops as soon as a terminator is reached; only a paragraph
    with no terminator anywhere falls back to the whole joined text."""
    if not prerequisites.strip():
        return f"{_NEXT_SUMMARY_FALLBACK}."

    first_paragraph = re.split(r"\n\s*\n", prerequisites.strip(), maxsplit=1)[0]
    clean_lines = [
        cleaned
        for cleaned in (_clean_prerequisite_line(line) for line in first_paragraph.splitlines())
        if cleaned
    ]
    if not clean_lines:
        return f"{_NEXT_SUMMARY_FALLBACK}."

    sentence, joined_paragraph = _join_lines_until_sentence(clean_lines)
    result = sentence if sentence is not None else joined_paragraph

    result = _truncate_on_word_boundary(result)
    return _finalize_summary(result)


def main() -> None:
    briefs = numbered_files("briefs", "BRIEF")
    reports = numbered_files("reports", "REPORT")
    
    fr_briefs = custom_files("briefs", "BRIEF-FR")
    fr_reports = custom_files("reports", "REPORT-FR")
    
    gate_brief_files = gate_files("briefs", "GATE")
    
    statuses = {number: brief_status(number, reports) for number in sorted(briefs)}
    active_number = next(
        (number for number in sorted(briefs) if statuses[number] != "passed"), None
    )
    
    # Check FR series active status
    active_fr_tag = None
    for tag in sorted(fr_briefs):
        if tag not in fr_reports:
            active_fr_tag = f"FR-{tag}"
            break
        else:
            rep_text = fr_reports[tag].read_text(encoding="utf-8")
            if "pass" not in decision_line(rep_text).lower():
                active_fr_tag = f"FR-{tag}"
                break
                
    if active_fr_tag:
        active_label = f"BRIEF-{active_fr_tag}"
        tag_suffix = active_fr_tag.removeprefix("FR-")
        phase_status = "in progress"
        open_items = acceptance_items(fr_briefs[tag_suffix])
    elif active_number is not None:
        active_label = f"BRIEF-{active_number:03d}"
        phase_status = statuses[active_number]
        open_items = acceptance_items(briefs[active_number])
    else:
        active_label = "none"
        phase_status = "passed"
        open_items = []

    completed = [
        f"BRIEF-{number:03d} — {report_date(reports[number])}"
        for number in sorted(briefs)
        if statuses[number] == "passed"
    ]
    if "001" in fr_reports:
        rep_001 = fr_reports["001"].read_text(encoding="utf-8")
        if "pass" in decision_line(rep_001).lower():
            completed.append(f"GATE-FR-001 — {report_date(fr_reports['001'])}")
    for tag in sorted(fr_reports):
        if tag == "001":
            continue
        rep_text = fr_reports[tag].read_text(encoding="utf-8")
        if "pass" in decision_line(rep_text).lower():
            completed.append(f"BRIEF-FR-{tag} — {report_date(fr_reports[tag])}")
    
    latest_report_text = ""
    latest_report_name = ""
    if fr_reports:
        latest_tag = max(fr_reports.keys())
        latest_report_text = fr_reports[latest_tag].read_text(encoding="utf-8")
        latest_report_name = f"BRIEF-FR-{latest_tag}" if latest_tag != "001" else "GATE-FR-001"
    elif reports:
        latest_number = max(reports)
        latest_report_text = reports[latest_number].read_text(encoding="utf-8")
        latest_report_name = f"BRIEF-{latest_number:03d}"

    outcome = f"{latest_report_name} — {decision_line(latest_report_text)}" if latest_report_text else "No phase report yet"
    
    # Handle prerequisites & recommendations from report
    prerequisites = section(latest_report_text, "Next phase prerequisites") if latest_report_text else ""
    if not prerequisites and latest_report_text:
        rec_match = re.search(r"(?m)^(?:\*\*)?FINAL RECOMMENDATION:(?:\*\*)?\s*(.+)$", latest_report_text)
        if rec_match:
            rec_line = rec_match.group(1).strip("* ")
            prerequisites = f"- {rec_line}\n- Phase 0/1 Foundation & Web Integration (PostgreSQL, background workers, FastAPI API layer, Next.js Web Dashboard)."
        else:
            prerequisites = section(latest_report_text, "Next phase prerequisites")

    blocked: list[str] = [
        "BRIEF-007 / Phase 6: Multi-Tenant Family Alpha (strictly blocked until Founder Web Alpha is live and validated)"
    ]

    proposed, accepted = adr_records()
    counts = source_counts()
    source_sha, source_subject = source_head()
    mirror_sha, mirror_time = mirror_sync()
    shipped = completed[-1] if completed else "repository foundation not yet reported"
    blocked_summary = blocked[0] if blocked else "none"
    next_summary = next_summary_from_prerequisites(prerequisites)

    output = f"""<!-- GENERATED BY scripts/generate_state.py — DO NOT EDIT -->
# OpportunityOS State

OpportunityOS is an opportunity-acquisition platform for MENA.
Last shipped: {shipped}.
Active work: {active_label}.
Phase status: {phase_status}.
Blocked: {blocked_summary}.
Next: {next_summary}

## Repository

- **Generated:** {generated_at()}
- **State generated at commit:** `{source_sha}` — {source_subject}
- **Mirror sync:** `{mirror_sha}` at {mirror_time}

## Active Brief

- **Brief:** {active_label}
- **Phase status:** {phase_status}
- **Open acceptance items:** {len(open_items)}
{bullets(open_items, "None")}

## Completed Briefs

{bullets(completed, "None")}

## Last Phase Outcome

- {outcome}

## Decisions

### Open
{bullets(proposed, "None")}

### Accepted
{bullets(accepted, "None")}

## Blocked Items

{bullets(blocked, "None")}

## Source Status Counts

{bullets([f"{k}: {v}" for k, v in sorted(counts.items())], "None")}

## Next Prerequisites

{prerequisites if prerequisites else "- None"}
"""
    STATE_PATH.write_text(output.strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
