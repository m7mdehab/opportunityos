#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def fail(rule: str, path: Path, remedy: str) -> None:
    errors.append(f"RULE {rule} FAILED: {path.relative_to(ROOT)}. REMEDY: {remedy}")


briefs: dict[int, Path] = {}
for path in (ROOT / "briefs").glob("BRIEF-*.md"):
    match = re.fullmatch(r"BRIEF-(\d+)\.md", path.name)
    if match:
        briefs[int(match.group(1))] = path

for report in (ROOT / "reports").glob("REPORT-*.md"):
    match = re.fullmatch(r"REPORT-(\d+)\.md", report.name)
    if not match:
        continue
    number = int(match.group(1))
    brief = briefs.get(number)
    if brief is None:
        fail(
            "REPORT_BRIEF_PAIRING",
            report,
            f"add briefs/BRIEF-{number:03d}.md or remove the unmatched report",
        )
        continue
    unchecked = re.findall(r"(?m)^\s*- \[ \]\s+(.+)$", brief.read_text(encoding="utf-8"))
    if unchecked:
        report_text = report.read_text(encoding="utf-8")
        deferred = re.search(
            r"(?ims)^##+\s+Deferred acceptance items\s*$\n(.*?)(?=^##+\s+|\Z)",
            report_text,
        )
        missing = [item for item in unchecked if not deferred or item not in deferred.group(1)]
        if missing:
            fail(
                "BRIEF_COMPLETION",
                report,
                "check completed acceptance boxes or add a 'Deferred acceptance items' section naming each unchecked item exactly",
            )

for adr in (ROOT / "docs" / "adr").glob("*.md"):
    text = adr.read_text(encoding="utf-8")
    status = re.search(r"(?im)^-?\s*\*\*Status:\*\*\s*(proposed|accepted|superseded)\s*$", text)
    if not status:
        fail(
            "ADR_STATUS",
            adr,
            "add a Status field with proposed, accepted, or superseded",
        )
        continue
    if status.group(1).lower() == "superseded":
        successor = re.search(r"(?im)^-?\s*\*\*Superseded by:\*\*\s*(.+)$", text)
        if not successor or successor.group(1).strip().lower() in {"", "none", "n/a"}:
            fail(
                "ADR_SUCCESSOR",
                adr,
                "name the successor ADR in the 'Superseded by' field",
            )

if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("Repository integrity checks passed.")
