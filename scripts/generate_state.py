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


def source_counts() -> Counter[str]:
    registry = ROOT / "docs" / "SOURCE_REGISTRY.yaml"
    if not registry.exists():
        return Counter()
    counts: Counter[str] = Counter()
    for raw in registry.read_text(encoding="utf-8").splitlines():
        match = re.search(r"(?m)^\s*observed_status:\s*([a-z0-9_]+)\s*$", raw)
        if match:
            counts[match.group(1)] += 1
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

{bullets([f"{k}: {v}" for k, v in sorted(counts.items())], "None")}

## Next Prerequisites

{prerequisites if prerequisites else "- None"}
"""
    STATE_PATH.write_text(output.strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
