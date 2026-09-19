"""FR-007 Release Evidence Indexer.

Collects and indexes all verified evidence artifacts, soak proofs,
hosted acceptance criteria, and cost envelope status for FR-007.
Does not award unearned PASS to incomplete or unverified criteria.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EVIDENCE_DIR = REPO_ROOT / "reports" / "evidence" / "FR-007"


def build_release_evidence_index(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Index all committed evidence artifacts and current status for FR-007."""
    ev_dir = repo_root / "reports" / "evidence" / "FR-007"
    
    # 1. Discover raw evidence text files
    evidence_files = []
    if ev_dir.exists():
        for p in sorted(ev_dir.iterdir()):
            if p.is_file() and p.suffix in (".txt", ".json", ".log") and not p.name.startswith("."):
                stat = p.stat()
                evidence_files.append({
                    "filename": p.name,
                    "relative_path": str(p.relative_to(repo_root)).replace("\\", "/"),
                    "size_bytes": stat.st_size,
                })

    # 2. Load hosted acceptance manifest
    manifest_path = ev_dir / "hosted-acceptance-manifest.json"
    manifest_data = {}
    criteria_summary = {
        "PASS": 0,
        "REPOSITORY_VERIFIED": 0,
        "PARTIAL": 0,
        "NOT_EXECUTED": 0,
        "BLOCKED": 0,
    }
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
                for entry in manifest_data.get("criteria", {}).values():
                    st = entry.get("status", "NOT_EXECUTED")
                    if st in criteria_summary:
                        criteria_summary[st] += 1
        except Exception:
            pass

    # 3. Load cost envelope status
    quota_path = ev_dir / "cloud-cost-quota.json"
    cost_summary = {
        "configured": False,
        "total_out_of_pocket_usd": 0.0,
        "all_within_allowance": False,
    }
    if quota_path.exists():
        try:
            with open(quota_path, "r", encoding="utf-8") as f:
                quota_data = json.load(f)
                s = quota_data.get("summary", {})
                cost_summary = {
                    "configured": True,
                    "total_out_of_pocket_usd": s.get("total_founder_out_of_pocket_usd", 0.0),
                    "all_within_allowance": s.get("all_covered_by_allowance_or_credit", s.get("all_within_allowance", False)),
                }
        except Exception:
            pass

    # 4. Inspect soak snapshots
    soak_dir = ev_dir / "soak"
    soak_summary = {
        "snapshot_count": 0,
        "latest_snapshot": None,
    }
    if soak_dir.exists() and soak_dir.is_dir():
        soak_files = sorted(soak_dir.glob("*.json"))
        soak_summary["snapshot_count"] = len(soak_files)
        if soak_files:
            try:
                with open(soak_files[-1], "r", encoding="utf-8") as f:
                    last_snap = json.load(f)
                    soak_summary["latest_snapshot"] = {
                        "timestamp_utc": last_snap.get("timestamp_utc"),
                        "overall_state": last_snap.get("overall_state"),
                        "founder_pc_dependency": last_snap.get("founder_pc_dependency"),
                    }
            except Exception:
                pass

    index = {
        "index_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "brief": "FR-007",
        "evidence_files_count": len(evidence_files),
        "evidence_files": evidence_files,
        "acceptance_criteria_summary": criteria_summary,
        "cost_envelope_summary": cost_summary,
        "soak_summary": soak_summary,
    }
    return index


def format_markdown_summary(index_data: dict[str, Any]) -> str:
    """Format release evidence index as a clean markdown document."""
    lines = [
        "# FR-007 Release Evidence Index",
        "",
        f"**Generated**: {index_data.get('generated_at_utc')}",
        f"**Brief**: {index_data.get('brief')}",
        "",
        "## 1. Acceptance Criteria Status",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    crit_sum = index_data.get("acceptance_criteria_summary", {})
    for status, count in crit_sum.items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend([
        "",
        "## 2. Cost & Quota Status",
        "",
        f"- **Configured**: {index_data.get('cost_envelope_summary', {}).get('configured')}",
        f"- **Founder Out-of-Pocket**: ${index_data.get('cost_envelope_summary', {}).get('total_out_of_pocket_usd', 0.0):.2f}",
        f"- **All Within Allowance**: {index_data.get('cost_envelope_summary', {}).get('all_within_allowance')}",
        "",
        "## 3. Evidence Artifacts",
        "",
        f"Total indexed artifacts: {index_data.get('evidence_files_count', 0)}",
        "",
        "| Filename | Path | Size |",
        "|---|---|---|",
    ])
    for ef in index_data.get("evidence_files", []):
        lines.append(f"| `{ef['filename']}` | `{ef['relative_path']}` | {ef['size_bytes']} bytes |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Index FR-007 release evidence and acceptance criteria."
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Path to write evidence index JSON.",
    )
    parser.add_argument(
        "--markdown",
        type=str,
        default="",
        help="Path to write markdown summary report.",
    )
    args = parser.parse_args()

    index = build_release_evidence_index()

    if args.output:
        out_p = Path(args.output).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        print(f"Evidence index saved to {out_p}")
    else:
        print(json.dumps(index, indent=2))

    if args.markdown:
        md_p = Path(args.markdown).resolve()
        md_p.parent.mkdir(parents=True, exist_ok=True)
        md_p.write_text(format_markdown_summary(index), encoding="utf-8")
        print(f"Markdown summary saved to {md_p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
