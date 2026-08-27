#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import itertools
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def command(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def gh_executable() -> str:
    found = shutil.which("gh")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GitHub CLI" / "gh.exe"
    return str(local) if local.exists() else "gh"


def github_identity() -> tuple[str, str, str]:
    gh = gh_executable()
    name = command(gh, "api", "user", "--jq", ".name")
    login = command(gh, "api", "user", "--jq", ".login")
    email = command(gh, "api", "user", "--jq", ".email")
    if name and name != "null" and len(name.split()) >= 2:
        return name, email if email != "null" else "", login

    git_name = command("git", "config", "--get", "user.name")
    git_email = command("git", "config", "--get", "user.email")
    if git_name and len(git_name.split()) >= 2 and "automation" not in git_name.lower():
        return git_name, git_email, login

    records = command("git", "log", "--format=%an|%ae")
    for record in sorted(set(records.splitlines())):
        author, _, author_email = record.partition("|")
        if author and len(author.split()) >= 2 and "automation" not in author.lower():
            return author, author_email, login
    raise SystemExit(
        "IDENTITY DERIVATION FAILED: gh api user.name, git user identity, and git author history yielded no canonical value."
    )


def transliterations(element: str) -> set[str]:
    variants = {element}
    replacements = (
        ("ou", "u"),
        ("u", "ou"),
        ("oo", "u"),
        ("ee", "i"),
        ("i", "ee"),
        ("y", "i"),
        ("q", "k"),
        ("dj", "j"),
    )
    lowered = element.lower()
    for old, new in replacements:
        if old in lowered:
            variants.add(re.sub(old, new, element, flags=re.IGNORECASE))
    normalized = re.sub(r"[^a-z]", "", lowered)
    canonical_family = {
        "mohammed",
        "mohamed",
        "muhammad",
        "mohamad",
        "muhammed",
    }
    if normalized in canonical_family:
        variants.update(value.title() for value in canonical_family)
    return {value for value in variants if value}


def surname_forms(element: str) -> set[str]:
    stripped = re.sub(r"^(?:el|al)[- ]?", "", element, flags=re.IGNORECASE)
    forms: set[str] = set()
    for variant in transliterations(stripped):
        forms.update(
            {
                variant,
                f"El-{variant}",
                f"El {variant}",
                f"El{variant}",
                f"Al-{variant}",
                f"Al {variant}",
                f"Al{variant}",
            }
        )
    return forms


def pattern_set(name: str, email: str, login: str) -> tuple[list[str], str]:
    elements = [part for part in re.split(r"\s+", name.strip()) if part]
    given_sets = [sorted(transliterations(part)) for part in elements[:-1]]
    family_set = sorted(surname_forms(elements[-1]))
    full_names: set[str] = set()
    for given in itertools.product(*given_sets):
        for family in family_set:
            ordered = [*given, family]
            full_names.add(" ".join(ordered))
            full_names.add(" ".join([family, *given]))

    patterns = [
        rf"(?i)(?<!\w){re.escape(value).replace(r'\ ', r'[ ._-]+')}(?!\w)"
        for value in sorted(full_names)
    ]
    local_part = email.partition("@")[0].strip()
    if local_part and local_part.lower() != login.lower() and "noreply" not in email.lower():
        patterns.append(rf"(?i)(?<![\w.+-]){re.escape(local_part)}(?![\w.+-])")
    return sorted(set(patterns)), sorted(full_names, key=len, reverse=True)[0]


def mirrored_files(root: Path) -> list[Path]:
    allowlist = [
        line.strip()
        for line in (root / ".mirror-allowlist").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    tracked = command("git", "ls-files", "-z").split("\x00")
    return [
        root / relative
        for relative in tracked
        if relative and any(fnmatch.fnmatchcase(relative, pattern) for pattern in allowlist)
    ]


def validate(patterns: list[str], planted: str) -> None:
    compiled = [re.compile(pattern) for pattern in patterns]
    for path in mirrored_files(ROOT):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(pattern.search(text) for pattern in compiled):
            raise SystemExit(
                "IDENTITY PATTERN VALIDATION FAILED: a generated pattern matches current mirrored content."
            )
    with tempfile.TemporaryDirectory(prefix="opportunityos-name-pattern-") as temporary:
        scratch = Path(temporary) / "planted-variant.txt"
        scratch.write_text(f"Deliberate planted identity: {planted}\n", encoding="utf-8")
        text = scratch.read_text(encoding="utf-8")
        if not any(pattern.search(text) for pattern in compiled):
            raise SystemExit(
                "IDENTITY PATTERN VALIDATION FAILED: the planted founder-name variant was not detected."
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    name, email, login = github_identity()
    patterns, planted = pattern_set(name, email, login)
    if args.validate:
        validate(patterns, planted)
    # Never invoke this command in GitHub Actions: stdout contains founder-name variants and would persist in build logs.
    print(json.dumps(patterns, separators=(",", ":")))


if __name__ == "__main__":
    main()
