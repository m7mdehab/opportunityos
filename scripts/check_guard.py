#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def allowlist() -> list[str]:
    return [
        line.strip()
        for line in (ROOT / ".mirror-allowlist").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def mirrored(path: Path, patterns: list[str]) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns)


def readable(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def tree_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    ]


def display_path(path: Path, scan_root: Path | None) -> str:
    if scan_root and path.is_relative_to(scan_root):
        return path.relative_to(scan_root).as_posix()
    if path.is_relative_to(ROOT):
        return path.relative_to(ROOT).as_posix()
    return path.name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mirror-only", action="store_true")
    parser.add_argument("--checks", choices=("all", "secrets", "pii"), default="all")
    parser.add_argument("--allow-missing-patterns", action="store_true")
    parser.add_argument("--scan-file", type=Path)
    parser.add_argument("--scan-root", type=Path)
    args = parser.parse_args()
    if args.scan_file and args.scan_root:
        parser.error("--scan-file and --scan-root are mutually exclusive")
    patterns = allowlist()
    scan_root = args.scan_root.resolve() if args.scan_root else None
    if args.scan_file:
        selected_files = [args.scan_file.resolve()]
        pii_files = selected_files
    elif scan_root:
        selected_files = tree_files(scan_root)
        pii_files = selected_files
    else:
        all_files = repository_files()
        mirrored_files = [path for path in all_files if mirrored(path, patterns)]
        selected_files = mirrored_files if args.mirror_only else all_files
        pii_files = mirrored_files
    failures: list[str] = []

    founder_patterns: list[re.Pattern[str]] = []
    encoded_founder_patterns = os.environ.get("FOUNDER_NAME_PATTERNS", "")
    if args.checks in {"all", "pii"} and not encoded_founder_patterns and not args.allow_missing_patterns:
        failures.append(
            "RULE PII_FOUNDER_NAME_PATTERNS_MISSING FAILED: FOUNDER_NAME_PATTERNS is unset. REMEDY: restore the agent-derived repository secret or pass --allow-missing-patterns only for an explicit local structural scan."
        )
    elif args.checks in {"all", "pii"} and encoded_founder_patterns:
        try:
            expressions = json.loads(encoded_founder_patterns)
            if not isinstance(expressions, list) or not expressions:
                raise ValueError("expected a non-empty JSON array")
            founder_patterns = [re.compile(expression) for expression in expressions]
        except (json.JSONDecodeError, TypeError, ValueError, re.error) as error:
            failures.append(
                f"RULE PII_FOUNDER_NAME_PATTERNS_INVALID FAILED: FOUNDER_NAME_PATTERNS is invalid ({error}). REMEDY: regenerate it with scripts/derive_founder_patterns.py and reset the repository secret."
            )

    if args.checks in {"all", "secrets"}:
        secret_patterns = {
            "PRIVATE_KEY": re.compile("-----BEGIN " + "(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            "GITHUB_TOKEN": re.compile("gh" + r"[pousr]_[A-Za-z0-9]{20,}"),
            "OPENAI_KEY": re.compile("sk-" + r"[A-Za-z0-9_-]{20,}"),
            "AWS_ACCESS_KEY": re.compile("AKIA" + r"[A-Z0-9]{16}"),
            "CONNECTION_STRING": re.compile(
                r"(?i)(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s'\"]+"
            ),
            "ASSIGNED_SECRET": re.compile(
                r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}['\"]"
            ),
        }
        for path in selected_files:
            relative = display_path(path, scan_root)
            if path.name == ".env" or path.name.startswith(".env."):
                failures.append(
                    f"RULE SECRET_ENV_FILE FAILED: {relative}. REMEDY: remove the .env file from git and store values in repository secrets."
                )
            text = readable(path)
            for label, pattern in secret_patterns.items():
                if pattern.search(text):
                    failures.append(
                        f"RULE SECRET_{label} FAILED: {relative}. REMEDY: remove and rotate the credential, then use the designated secret store."
                    )

    if args.checks in {"all", "pii"}:
        pii_patterns: list[tuple[str, re.Pattern[str]]] = []
        for line_number, line in enumerate(
            (ROOT / ".github" / "pii-patterns.txt").read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                label, expression = line.split("\t", 1)
                pii_patterns.append((label, re.compile(expression)))
            except (ValueError, re.error) as error:
                failures.append(
                    f"RULE PII_PATTERN_CONFIG FAILED: .github/pii-patterns.txt:{line_number}. REMEDY: use label<TAB>valid Python regex ({error})."
                )

        for path in pii_files:
            relative = display_path(path, scan_root)
            if path.suffix.lower() in {".pdf", ".docx"} and not relative.startswith("docs/"):
                failures.append(
                    f"RULE PII_DOCUMENT_LOCATION FAILED: {relative}. REMEDY: remove the document from mirrored paths or place an approved non-personal document under docs/."
                )
            text = readable(path)
            for label, pattern in pii_patterns:
                if pattern.search(text):
                    failures.append(
                        f"RULE PII_{label.upper()} FAILED: {relative}. REMEDY: remove or redact the personal identifier before mirroring."
                    )
            for pattern in founder_patterns:
                if pattern.search(text):
                    failures.append(
                        f"RULE PII_FOUNDER_NAME FAILED: {relative}. REMEDY: replace the founder's name with 'the founder' before mirroring."
                    )

    if failures:
        print("\n".join(sorted(set(failures))), file=sys.stderr)
        raise SystemExit(1)
    scope = "mirror boundary" if args.mirror_only else "repository and mirror boundary"
    print(f"Guard checks passed for {scope}.")


if __name__ == "__main__":
    main()
