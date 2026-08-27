#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


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


def section(text: str, title: str) -> str:
    match = re.search(
        rf"(?ims)^##+\s+{re.escape(title)}\s*$\n(.*?)(?=^##+\s+|\Z)", text
    )
    return match.group(1).strip() if match else ""


def report_date(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?im)^\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else "unknown date"


def decision_line(text: str) -> str:
    value = section(text, "Decision")
    for line in value.splitlines():
        cleaned = line.strip().lstrip("- ")
        if re.match(r"(?i)^(PASS|CONDITIONAL PASS|FAIL)", cleaned):
            return cleaned
    return "No phase outcome recorded"


def acceptance_items(path: Path) -> list[str]:
    items: list[str] = []
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        item = re.match(r"^\s*- \[ \]\s+(.+)$", line)
        if item:
            if current:
                items.append(current)
            current = item.group(1).strip()
            continue
        continuation = re.match(r"^\s{2,}(\S.*)$", line)
        new_list_item = re.match(r"^\s*[-*+]\s+", line)
        if current and continuation and not new_list_item:
            current = f"{current} {continuation.group(1).strip()}"
        elif current:
            items.append(current)
            current = None
    if current:
        items.append(current)
    return items


def brief_status(number: int, reports: dict[int, Path]) -> str:
    report = reports.get(number)
    if report is None:
        return "in progress"
    decision = section(report.read_text(encoding="utf-8"), "Decision")
    if re.search(r"(?i)\bFAIL\b", decision):
        return "failed — remain in phase"
    return "passed"


def adr_records() -> tuple[list[str], list[str]]:
    proposed: list[str] = []
    accepted: list[str] = []
    for path in sorted((ROOT / "docs" / "adr").glob("*.md")):
        if "TEMPLATE" in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        status_match = re.search(r"(?im)^-?\s*\*\*Status:\*\*\s*(\w+)", text)
        title_match = re.search(r"(?m)^#\s+(.+)$", text)
        if not status_match:
            continue
        entry = f"[{title_match.group(1) if title_match else path.stem}](adr/{path.name})"
        status = status_match.group(1).lower()
        if status == "proposed":
            proposed.append(entry)
        elif status == "accepted":
            accepted.append(entry)
    return proposed, accepted


def source_counts() -> Counter[str]:
    registry = ROOT / "docs" / "SOURCE_REGISTRY.yaml"
    counts: Counter[str] = Counter()
    if not registry.exists():
        return counts
    text = registry.read_text(encoding="utf-8")
    for status in re.findall(r"(?m)^\s{2,}(?:policy_)?status:\s*([^#\s]+)", text):
        counts[status.strip("'\"")] += 1
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
            return match.group(1)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def bullets(items: list[str], empty: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def main() -> None:
    briefs = numbered_files("briefs", "BRIEF")
    reports = numbered_files("reports", "REPORT")
    statuses = {number: brief_status(number, reports) for number in sorted(briefs)}
    active_number = next(
        (number for number in sorted(briefs) if statuses[number] != "passed"), None
    )
    active_label = f"BRIEF-{active_number:03d}" if active_number is not None else "none"
    phase_status = statuses[active_number] if active_number is not None else "passed"
    open_items = acceptance_items(briefs[active_number]) if active_number is not None else []

    completed = [
        f"BRIEF-{number:03d} — {report_date(reports[number])}"
        for number in sorted(briefs)
        if statuses[number] == "passed"
    ]
    latest_number = max(reports) if reports else None
    latest_text = (
        reports[latest_number].read_text(encoding="utf-8") if latest_number is not None else ""
    )
    outcome = decision_line(latest_text) if latest_text else "No phase report yet"
    prerequisites = section(latest_text, "Next phase prerequisites") if latest_text else ""

    blocked: list[str] = []
    for title in ("Blocked", "Hard gate", "Failures and known limitations"):
        value = section(latest_text, title) if latest_text else ""
        blocked.extend(
            line.strip().lstrip("- ")
            for line in value.splitlines()
            if line.strip().startswith("-") and line.strip().lstrip("- ").lower() not in {"none", "none."}
        )

    proposed, accepted = adr_records()
    counts = source_counts()
    source_sha, source_subject = source_head()
    mirror_sha, mirror_time = mirror_sync()
    shipped = completed[-1] if completed else "repository foundation not yet reported"
    blocked_summary = blocked[0] if blocked else "none"
    next_summary = (
        next((line.strip().lstrip("- ") for line in prerequisites.splitlines() if line.strip()), "complete active brief")
        if prerequisites
        else "complete active brief"
    )

    output = f"""<!-- GENERATED BY scripts/generate_state.py — DO NOT EDIT -->
# OpportunityOS State

OpportunityOS is an opportunity-acquisition platform for MENA.
Last shipped: {shipped}.
Active work: {active_label}.
Phase status: {phase_status}.
Blocked: {blocked_summary}.
Next: {next_summary}.

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

{bullets([f"{status}: {count}" for status, count in sorted(counts.items())], "No source entries")}

## Next Prerequisites

{prerequisites or "- Complete the active brief."}
"""
    STATE_PATH.write_text(output, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
