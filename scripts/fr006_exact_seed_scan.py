#!/usr/bin/env python3
"""Extract exact public Greenhouse/Lever board tokens from a checked-out seed directory.

FR-006 A-23 recovery helper.  Unlike the historical company-name -> ATS-token
heuristic, this scanner only emits a candidate when the public seed itself
contains an explicit Greenhouse/Lever careers URL.  It performs no network I/O;
the workflow supplies a pinned/public checkout and records its commit SHA.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

_GREENHOUSE_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "boards-api.greenhouse.io",
}
_LEVER_HOSTS = {"jobs.lever.co", "api.lever.co"}
_URL_RE = re.compile(r"https?://[^\s<>\]\[\)\(\"']+", re.IGNORECASE)


def _candidate_from_url(raw_url: str) -> tuple[str, str] | None:
    url = raw_url.rstrip(".,;:!?")
    parsed = urlparse(url)
    host = parsed.netloc.casefold().split(":", 1)[0]
    parts = [part for part in parsed.path.split("/") if part]
    if host in _GREENHOUSE_HOSTS:
        # Candidate-facing Greenhouse URLs are normally /<board> or
        # /v1/boards/<board>/... on API links.
        if len(parts) >= 3 and parts[0].casefold() == "v1" and parts[1].casefold() == "boards":
            token = parts[2]
        elif parts:
            token = parts[0]
        else:
            return None
        return "greenhouse", token.casefold()
    if host in _LEVER_HOSTS:
        # Candidate-facing Lever URLs are /<site>; API links are /v0/postings/<site>.
        if len(parts) >= 3 and parts[0].casefold() == "v0" and parts[1].casefold() == "postings":
            token = parts[2]
        elif parts:
            token = parts[0]
        else:
            return None
        return "lever", token.casefold()
    return None


def scan(root: Path) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {"greenhouse": set(), "lever": set()}
    for path in sorted(root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for raw_url in _URL_RE.findall(text):
            candidate = _candidate_from_url(raw_url)
            if candidate is None:
                continue
            kind, token = candidate
            if token:
                found[kind].add(token)
    return {kind: sorted(tokens) for kind, tokens in found.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    result = scan(args.root)
    total = sum(len(v) for v in result.values())
    print(
        "A-23 exact ATS seed scan: "
        f"greenhouse={len(result['greenhouse'])} lever={len(result['lever'])} total={total}"
    )
    print("A23_EXACT_SEEDS_JSON=" + json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
