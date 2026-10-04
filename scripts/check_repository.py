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

# Supabase Free-tier runtime recurrence guard.
#
# Scheduled/live database work is intentionally a very small reviewed surface.
# Any new scheduled workflow that can reach the hosted database must fail CI
# until it is explicitly reviewed and added here.
workflow_dir = ROOT / ".github" / "workflows"
scheduled_db_allowlist = {
    "fr007-worker-drain.yml",
    "fr007-cloud-observability.yml",
    "fr007-encrypted-backup.yml",
}
db_markers = (
    "OPOS_TARGET_DB_URL",
    "CLOUD_DATABASE_URL",
    "OPPORTUNITYOS_DB_URL",
)
for path in workflow_dir.glob("*.yml"):
    text = path.read_text(encoding="utf-8")
    has_schedule = "\n  schedule:" in text
    reaches_db = any(marker in text for marker in db_markers)
    if has_schedule and reaches_db and path.name not in scheduled_db_allowlist:
        fail(
            "SCHEDULED_SUPABASE_SURFACE",
            path,
            "remove scheduled hosted-DB access or explicitly review and add the workflow to the narrow scheduled_db_allowlist",
        )
    if "SELECT e.dimension_scores_json" in text:
        fail(
            "NO_CI_FULL_DIMENSION_EXPORT",
            path,
            "validate HOT/PROTECTED dimensions server-side and return only aggregate counts",
        )

worker_workflow = workflow_dir / "fr007-worker-drain.yml"
worker_text = worker_workflow.read_text(encoding="utf-8")
if worker_text.count('cron: "17 */12 * * *"') != 1 or "\n  push:" in worker_text:
    fail(
        "WORKER_TRIGGER_CONTRACT",
        worker_workflow,
        "keep exactly one twice-daily worker cron and no push trigger",
    )

for name in (
    "fr007-hot-evaluation-capacity-reclaim.yml",
    "fr007-orphan-deadletter-recovery.yml",
    "fr007-hosted-bootstrap.yml",
    "fr007-incremental-source-bootstrap.yml",
    "fr007-due-source-overnight-catchup.yml",
):
    path = workflow_dir / name
    text = path.read_text(encoding="utf-8")
    if "\n  push:" in text or "\n  schedule:" in text:
        fail(
            "MANUAL_LIVE_WORK_ONLY",
            path,
            "keep recovery/bootstrap/catch-up workflows workflow_dispatch/workflow_call only",
        )

runtime_takeover = workflow_dir / "fr007-runtime-takeover-proof.yml"
runtime_text = runtime_takeover.read_text(encoding="utf-8")
if runtime_text.count("github.event_name == 'workflow_dispatch'") < 4:
    fail(
        "RUNTIME_TAKEOVER_PUSH_SAFETY",
        runtime_takeover,
        "keep all live enqueue/drain/observe/summary jobs gated to workflow_dispatch",
    )

backup_script = (ROOT / "scripts" / "founder_state_backup.py").read_text(encoding="utf-8")
if 'REBUILDABLE_STATE_TABLES = frozenset({"founder_cv_selections"})' not in backup_script:
    fail(
        "FOUNDER_BACKUP_DERIVED_STATE_BOUND",
        ROOT / "scripts" / "founder_state_backup.py",
        "exclude generated CV recommendations from daily irreplaceable-state backup expansion",
    )

capacity_guard = (ROOT / "scripts" / "db_capacity_guard.py").read_text(encoding="utf-8")
locked_capacity_markers = (
    "PREFERRED_BYTES = 300 * MIB",
    "WARN_BYTES = 350 * MIB",
    "BLOCK_BYTES = 400 * MIB",
    "HARD_STOP_BYTES = 425 * MIB",
    "PROVIDER_LIMIT_BYTES = 500_000_000",
)
for marker in locked_capacity_markers:
    if marker not in capacity_guard:
        fail(
            "SUPABASE_CAPACITY_THRESHOLDS",
            ROOT / "scripts" / "db_capacity_guard.py",
            "do not loosen the reviewed Supabase Free-tier capacity thresholds without an explicit replacement design",
        )

scheduler_text = (ROOT / "worker" / "scheduler.py").read_text(encoding="utf-8")
if "OVERNIGHT_CATCHUP_CEILING_BYTES = 390 * 1024 * 1024" not in scheduler_text:
    fail(
        "SUPABASE_CATCHUP_CEILING",
        ROOT / "worker" / "scheduler.py",
        "retain the 390 MiB controlled catch-up ceiling unless replaced by a reviewed provider-capacity design",
    )

if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("Repository integrity checks passed.")
