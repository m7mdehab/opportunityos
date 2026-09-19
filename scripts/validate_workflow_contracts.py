"""Validate GitHub Actions Observability Workflow Contracts.

Ensures .github/workflows/fr007-cloud-observability.yml adheres to:
- Standard GitHub-hosted Ubuntu runner only; no larger/billable runner
- Correct 30-minute external-monitor schedule
- Proper permissions (issues: write, actions: read)
- Non-cancelled concurrency for ordered alert execution
- Artifact retention >= 7 days (set to 90 days)
- Fail-closed release gate execution (no '|| true' on verifier)
- Exact CLI flag contract matching scripts/fr007_cloud_monitor.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "fr007-cloud-observability.yml"
)


def validate_workflow_contract(workflow_text: str) -> tuple[bool, list[str]]:
    """Verify static safety and CLI contract invariants in workflow YAML."""
    errors: list[str] = []

    # 1. Runner class
    if "runs-on: ubuntu-latest" not in workflow_text:
        errors.append("Workflow must use the standard 'ubuntu-latest' runner")
    if "runs-on: ubuntu-slim" in workflow_text:
        errors.append("Legacy ubuntu-slim cost model is forbidden under ADR-0023")

    # 2. Concurrency and non-cancellation
    if "cancel-in-progress: false" not in workflow_text:
        errors.append("Workflow must maintain 'cancel-in-progress: false' for ordered alerts")

    # 3. Permissions
    if "issues: write" not in workflow_text:
        errors.append("Workflow requires 'issues: write' permission for incident tracking")
    if "actions: read" not in workflow_text:
        errors.append("Workflow requires 'actions: read' permission to fetch remote soak artifacts")

    # 4. Schedule cadence
    if 'cron: "*/30 * * * *"' not in workflow_text and "cron: '*/30 * * * *'" not in workflow_text:
        errors.append("Workflow schedule must remain '*/30 * * * *' for the hosted monitoring contract")

    # 5. CLI flag alignment
    if "--output-report" not in workflow_text:
        errors.append("Workflow must invoke monitor with '--output-report'")
    if "--output-incident" not in workflow_text:
        errors.append("Workflow must invoke monitor with '--output-incident'")

    # 6. Fail-closed gates
    if "fr007_soak_verify.py || true" in workflow_text:
        errors.append("Workflow must not suppress soak verifier failures with '|| true'")

    # 7. Artifact persistence/retention
    if "retention-days: 90" not in workflow_text:
        errors.append("Soak snapshot artifact retention must be 90 days")
    if "env.EXEC_MODE == 'MONITOR'" not in workflow_text:
        errors.append("Only real MONITOR runs may publish soak-snapshot artifacts")
    if "path: .monitor_output/soak/*.json" not in workflow_text:
        errors.append("Soak artifact upload must contain only canonical soak JSON snapshots")
    if any(line.strip() == "path: .monitor_output/" for line in workflow_text.splitlines()):
        errors.append("Broad .monitor_output artifact upload is forbidden for soak evidence")

    # 8. Missing secret fail-closed guard
    if "Missing required hosted monitoring secrets" not in workflow_text:
        errors.append("Workflow must fail closed when hosted monitoring secrets are missing")

    return (len(errors) == 0), errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflow",
        type=str,
        default="",
        help="Path to fr007-cloud-observability.yml",
    )
    args = parser.parse_args()

    wf_p = Path(args.workflow).resolve() if args.workflow else WORKFLOW_PATH
    if not wf_p.is_file():
        sys.stderr.write(f"Error: Workflow file not found at {wf_p}\n")
        return 1

    text = wf_p.read_text(encoding="utf-8")
    valid, errors = validate_workflow_contract(text)
    if not valid:
        sys.stderr.write(f"Workflow contract validation FAILED for {wf_p.name}:\n")
        for err in errors:
            sys.stderr.write(f"  - {err}\n")
        return 1

    print(f"Workflow contract validation PASSED for {wf_p.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
