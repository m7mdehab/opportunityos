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


def section(text: str, title: str) -> str:
    match = re.search(
        rf"(?ims)^##+\s+(?:\d+\.\s+)?{re.escape(title)}\s*$\n(.*?)(?=^##+\s+|\Z)",
        text,
    )
    return match.group(1).strip() if match else ""


def _clean_markdown(text: str) -> str:
    # Underscores are meaningful inside decision tokens such as
    # PASS_WITH_NOT_CLOSED and must survive Markdown cleanup.
    return re.sub(r"[*`#]", "", text).strip()


def decision_line(text: str) -> str:
    """Return the report's declared decision without treating prose as a gate."""
    decision_text = section(text, "Decision")
    for raw in decision_text.splitlines():
        line = raw.strip().lstrip("- ").strip()
        cleaned = _clean_markdown(line)
        if cleaned:
            return cleaned

    inline_patterns = (
        r"(?im)^\s*\*\*Decision:\*\*\s*(.+?)\s*$",
        r"(?im)^\s*\*\*Decision:\s*(.+?)\*\*\s*$",
        r"(?im)^\s*Decision:\s*(.+?)\s*$",
    )
    for pattern in inline_patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_markdown(match.group(1)).strip().rstrip(".")
    return "undecided"


def is_terminal_pass(decision: str) -> bool:
    """True only for a terminal PASS, never PASS_WITH_NOT_CLOSED/partial debt."""
    normalized = (
        _clean_markdown(decision)
        .casefold()
        .replace("-", "_")
        .replace(" ", "_")
    )
    if any(
        marker in normalized
        for marker in ("not_closed", "partial", "not_pass", "fail")
    ):
        return False
    return bool(re.search(r"(^|[/_])pass($|[/_])", normalized))


def report_date(path: Path) -> str:
    match = re.search(
        r"(?m)^\*\*Date:\*\*\s*(.+)$", path.read_text(encoding="utf-8")
    )
    return match.group(1).strip() if match else "undated"


def brief_status(number: int, reports: dict[int, Path]) -> str:
    if number not in reports:
        return "in progress"
    report = reports[number].read_text(encoding="utf-8")
    return "passed" if is_terminal_pass(decision_line(report)) else "in progress"


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


def report_open_acceptance_items(report_path: Path) -> list[str]:
    """Expose explicit unresolved acceptance rows from the active report."""
    text = report_path.read_text(encoding="utf-8")
    items: list[str] = []
    for raw in text.splitlines():
        if not raw.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        label = _clean_markdown(cells[0])
        if not re.match(r"^A-\d+\b", label):
            continue
        row_text = _clean_markdown(" | ".join(cells[1:])).upper()
        if (
            "NOT_CLOSED" in row_text
            or "NOT CLOSED" in row_text
            or "PARTIAL" in row_text
        ):
            items.append(f"{label} — unresolved in latest report")

    if not items and not is_terminal_pass(decision_line(text)):
        decision = decision_line(text)
        if decision != "undecided":
            items.append(f"Latest report decision is {decision}")
    return items


def active_fr_tag(
    fr_briefs: dict[str, Path], fr_reports: dict[str, Path]
) -> str | None:
    """Return the newest FR brief that is currently open.

    Older PASS_WITH_NOT_CLOSED reports are historical evidence, not a request to
    rewind active work after later FR briefs superseded them. State therefore
    follows the newest authored FR brief. If that newest brief has no report it
    is active; if its report is non-terminal it remains active; if it terminally
    passed there is no active FR until a newer brief is authored.
    """
    if not fr_briefs:
        return None
    newest = max(fr_briefs)
    report_path = fr_reports.get(newest)
    if report_path is None:
        return newest
    report = report_path.read_text(encoding="utf-8")
    return None if is_terminal_pass(decision_line(report)) else newest


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
    registry = (
        registry_path
        if registry_path is not None
        else ROOT / "docs" / "SOURCE_REGISTRY.yaml"
    )
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
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def bullets(items: list[str], empty: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


_LIST_MARKER_RE = re.compile(r"^[-*]\s*")
_EMPHASIS_RE = re.compile(r"[*_`]")
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
    joined = lines[0]
    sentence = _first_sentence(joined)
    for line in lines[1:]:
        if sentence is not None:
            break
        joined = f"{joined} {line}"
        sentence = _first_sentence(joined)
    return sentence, joined


def next_summary_from_prerequisites(prerequisites: str) -> str:
    if not prerequisites.strip():
        return f"{_NEXT_SUMMARY_FALLBACK}."
    first_paragraph = re.split(r"\n\s*\n", prerequisites.strip(), maxsplit=1)[0]
    clean_lines = [
        cleaned
        for cleaned in (
            _clean_prerequisite_line(line) for line in first_paragraph.splitlines()
        )
        if cleaned
    ]
    if not clean_lines:
        return f"{_NEXT_SUMMARY_FALLBACK}."
    sentence, joined_paragraph = _join_lines_until_sentence(clean_lines)
    result = sentence if sentence is not None else joined_paragraph
    return _finalize_summary(_truncate_on_word_boundary(result))


def main() -> None:
    briefs = numbered_files("briefs", "BRIEF")
    reports = numbered_files("reports", "REPORT")
    fr_briefs = custom_files("briefs", "BRIEF-FR")
    fr_reports = custom_files("reports", "REPORT-FR")

    statuses = {number: brief_status(number, reports) for number in sorted(briefs)}
    active_number = next(
        (number for number in sorted(briefs) if statuses[number] != "passed"), None
    )
    current_fr_tag = active_fr_tag(fr_briefs, fr_reports)

    if current_fr_tag is not None:
        active_label = f"BRIEF-FR-{current_fr_tag}"
        phase_status = "in progress"
        if current_fr_tag in fr_reports:
            open_items = report_open_acceptance_items(fr_reports[current_fr_tag])
        else:
            open_items = acceptance_items(fr_briefs[current_fr_tag])
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
        if is_terminal_pass(decision_line(rep_001)):
            completed.append(f"GATE-FR-001 — {report_date(fr_reports['001'])}")
    for tag in sorted(fr_reports):
        if tag == "001":
            continue
        rep_text = fr_reports[tag].read_text(encoding="utf-8")
        if is_terminal_pass(decision_line(rep_text)):
            completed.append(f"BRIEF-FR-{tag} — {report_date(fr_reports[tag])}")

    latest_report_text = ""
    latest_report_name = ""
    if fr_reports:
        latest_tag = max(fr_reports)
        latest_report_text = fr_reports[latest_tag].read_text(encoding="utf-8")
        latest_report_name = (
            f"BRIEF-FR-{latest_tag}" if latest_tag != "001" else "GATE-FR-001"
        )
    elif reports:
        latest_number = max(reports)
        latest_report_text = reports[latest_number].read_text(encoding="utf-8")
        latest_report_name = f"BRIEF-{latest_number:03d}"

    outcome = (
        f"{latest_report_name} — {decision_line(latest_report_text)}"
        if latest_report_text
        else "No phase report yet"
    )

    prerequisites = (
        section(latest_report_text, "Next phase prerequisites")
        if latest_report_text
        else ""
    )
    if not prerequisites and latest_report_text:
        prerequisites = section(latest_report_text, "Next phase")
    if not prerequisites and latest_report_text:
        rec_match = re.search(
            r"(?m)^(?:\*\*)?FINAL RECOMMENDATION:(?:\*\*)?\s*(.+)$",
            latest_report_text,
        )
        if rec_match:
            rec_line = rec_match.group(1).strip("* ")
            prerequisites = (
                f"- {rec_line}\n"
                "- Phase 0/1 Foundation & Web Integration (PostgreSQL, background workers, "
                "FastAPI API layer, Next.js Web Dashboard)."
            )

    blocked = [
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

{bullets([f"{key}: {value}" for key, value in sorted(counts.items())], "None")}

## Next Prerequisites

{prerequisites if prerequisites else "- None"}
"""
    STATE_PATH.write_text(output.strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
