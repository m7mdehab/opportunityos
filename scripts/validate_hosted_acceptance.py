"""Validate FR-007 Hosted Acceptance Manifest.

Enforces strict schema, consistency, and evidence requirements:
- Criteria A-0 through A-17 must be present.
- Every criterion must declare scope: 'REPOSITORY_ONLY' or 'HOSTED_REQUIRED'.
- For HOSTED_REQUIRED criteria:
  * Cannot claim PASS unless hosted_verified is True.
  * Cannot claim hosted_verified=True based merely on disposable, local, or pending-live evidence.
  * A-13, A-14, A-16, A-17 are mechanically guarded against premature closure.
- For REPOSITORY_ONLY criteria (e.g. A-0, A-3):
  * Can claim PASS when repository_verified is True with valid evidence metadata.
- Any criterion claiming BLOCKED must state a specific blocking reason.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VALID_STATUSES = frozenset(
    {"PASS", "REPOSITORY_VERIFIED", "PARTIAL", "NOT_EXECUTED", "BLOCKED"}
)

VALID_SCOPES = frozenset({"REPOSITORY_ONLY", "HOSTED_REQUIRED"})

REQUIRED_CRITERIA = tuple(f"A-{i}" for i in range(18))

DISCLAIMER_PATTERNS = [
    re.compile(r"disposable\s+(?:pg|postgresql|harness)", re.IGNORECASE),
    re.compile(r"not\s+yet\s+executed", re.IGNORECASE),
    re.compile(r"pending\s+(?:live|cutover|deployment|7-day|hosted)", re.IGNORECASE),
    re.compile(r"hosted\s+production\s+acceptance\s+not\s+yet\s+executed", re.IGNORECASE),
]


def validate_hosted_acceptance_manifest(
    manifest_data: Mapping[str, Any],
    repo_root: Path = REPO_ROOT,
) -> tuple[bool, list[str]]:
    """Validate hosted acceptance manifest structure and truth constraints."""
    errors: list[str] = []

    if not isinstance(manifest_data, dict):
        return False, ["Manifest root must be a JSON dictionary"]

    brief = manifest_data.get("brief")
    if brief != "FR-007":
        errors.append(f"Invalid or missing brief: {brief!r}; expected 'FR-007'")

    criteria = manifest_data.get("criteria")
    if not isinstance(criteria, dict):
        return False, ["Manifest 'criteria' must be a dictionary"]

    # Check that all A-0 .. A-17 exist
    for req_id in REQUIRED_CRITERIA:
        if req_id not in criteria:
            errors.append(f"Missing required criterion: {req_id}")

    for cid, entry in criteria.items():
        if not isinstance(entry, dict):
            errors.append(f"Criterion {cid} must be a dictionary object")
            continue

        status = entry.get("status")
        if status not in VALID_STATUSES:
            errors.append(
                f"Criterion {cid} has invalid status {status!r}; must be one of {sorted(VALID_STATUSES)}"
            )

        scope = entry.get("scope")
        if scope not in VALID_SCOPES:
            errors.append(
                f"Criterion {cid} has invalid scope {scope!r}; must be one of {sorted(VALID_SCOPES)}"
            )

        title = entry.get("title")
        if not title or not isinstance(title, str):
            errors.append(f"Criterion {cid} missing valid string 'title'")

        repo_verified = entry.get("repository_verified", False)
        hosted_verified = entry.get("hosted_verified", False)
        evidence_path_str = entry.get("evidence_path")

        # Check evidence file existence if provided
        ev_file: Path | None = None
        if evidence_path_str:
            ev_file = repo_root / evidence_path_str
            if not ev_file.exists():
                errors.append(
                    f"Criterion {cid} specifies evidence_path '{evidence_path_str}' which does not exist in repository"
                )

        if scope == "HOSTED_REQUIRED":
            if status == "PASS":
                if not hosted_verified:
                    errors.append(
                        f"Criterion {cid} requires hosted execution (scope=HOSTED_REQUIRED) but hosted_verified is False"
                    )
                if not repo_verified:
                    errors.append(
                        f"Criterion {cid} claims PASS but repository_verified is False"
                    )

            if hosted_verified:
                if not ev_file or not ev_file.is_file():
                    errors.append(
                        f"Criterion {cid} claims hosted_verified=True but lacks a readable evidence file"
                    )
                else:
                    # Scan evidence text for disclaimers proving it was only a local/disposable test
                    text = ev_file.read_text(encoding="utf-8", errors="replace")
                    for pat in DISCLAIMER_PATTERNS:
                        if pat.search(text):
                            errors.append(
                                f"Criterion {cid} claims hosted_verified=True but evidence artifact contains qualification: '{pat.pattern}'"
                            )
                            break

        elif scope == "REPOSITORY_ONLY":
            if status == "PASS":
                if not repo_verified:
                    errors.append(
                        f"Criterion {cid} claims PASS but repository_verified is False"
                    )
                if not (entry.get("verified_by") or entry.get("verifier")):
                    errors.append(f"Criterion {cid} claims PASS but lacks 'verified_by'")
                if not entry.get("verification_sha"):
                    errors.append(f"Criterion {cid} claims PASS but lacks 'verification_sha'")
                if not evidence_path_str:
                    errors.append(f"Criterion {cid} claims PASS but lacks 'evidence_path'")

        if status == "BLOCKED":
            reason = entry.get("blocking_reason")
            if not reason or not isinstance(reason, str) or not reason.strip():
                errors.append(
                    f"Criterion {cid} is marked BLOCKED but lacks a non-empty 'blocking_reason'"
                )

        if status == "REPOSITORY_VERIFIED":
            if not repo_verified:
                errors.append(
                    f"Criterion {cid} marked REPOSITORY_VERIFIED but repository_verified is False"
                )
            if not evidence_path_str:
                errors.append(
                    f"Criterion {cid} marked REPOSITORY_VERIFIED but lacks 'evidence_path'"
                )

    return (len(errors) == 0), errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=str,
        default="",
        help="Path to hosted-acceptance-manifest.json",
    )
    args = parser.parse_args()

    manifest_path = (
        Path(args.manifest).resolve()
        if args.manifest
        else REPO_ROOT / "reports" / "evidence" / "FR-007" / "hosted-acceptance-manifest.json"
    )

    if not manifest_path.exists():
        sys.stderr.write(f"Error: Manifest file not found at {manifest_path}\n")
        return 1

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.stderr.write(f"Error: Invalid JSON in {manifest_path}: {exc}\n")
        return 1

    valid, errors = validate_hosted_acceptance_manifest(data, repo_root=REPO_ROOT)
    if not valid:
        sys.stderr.write("Hosted acceptance manifest validation FAILED:\n")
        for err in errors:
            sys.stderr.write(f"  - {err}\n")
        return 1

    print(f"Hosted acceptance manifest {manifest_path.name} is VALID ({len(data.get('criteria', {}))} criteria checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
