#!/usr/bin/env python3
"""FR-006 A-23 live probe for exact public Greenhouse/Lever seed URLs.

Only tokens extracted from explicit public ATS URLs are probed.  The existing
board-discovery implementation supplies host-level policy gating, shared ATS
rate limiting, 403/429 no-retry progress semantics, 90-day recency, and the
committed title-family classifier.  This script never reads the Founder Truth
Pack and never submits to a source.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from opportunity.discovery.boards import (
    BoardCandidate,
    dedupe_candidates,
    registered_source_ids,
    render_registry_entry,
    run_sweep,
)
from scripts.fr006_exact_seed_scan import scan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    exact = scan(args.roots)
    candidates = [
        BoardCandidate(kind=kind, token=token, company=token, seed="exact_public_ats_url")
        for kind in ("greenhouse", "lever")
        for token in exact[kind]
    ]
    existing_ids = registered_source_ids()
    existing_ats = sorted(
        source_id
        for source_id in existing_ids
        if source_id.startswith("greenhouse:") or source_id.startswith("lever:")
    )
    pending = dedupe_candidates(candidates, existing_ids)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    progress_path = args.output.with_suffix(".progress.json")
    result = run_sweep(
        pending,
        progress_path=progress_path,
        seeds_used=[str(root) for root in args.roots],
    )

    new_entries = sorted(result.registered, key=lambda entry: entry.source_id)
    total_after = len(existing_ats) + len(new_entries)
    payload = {
        "exact_seed_counts": {kind: len(tokens) for kind, tokens in exact.items()},
        "exact_seed_total": sum(len(tokens) for tokens in exact.values()),
        "already_registered_ats": len(existing_ats),
        "pending_exact_candidates": len(pending),
        "processed_this_run": result.processed_this_run,
        "classifications": result.counts,
        "new_live_relevant_boards": len(new_entries),
        "live_relevant_board_total_after_union": total_after,
        "blocked_ids": result.blocked_ids,
        "classifier": result.classifier_label,
        "wall_clock_s": result.wall_clock_s,
        "new_entries": [asdict(entry) for entry in new_entries],
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    registry_fragment = args.output.with_suffix(".registry.yaml")
    registry_fragment.write_text(
        "".join(render_registry_entry(entry) for entry in new_entries),
        encoding="utf-8",
    )

    print(
        "A-23 exact live probe: "
        f"exact={payload['exact_seed_total']} existing_ats={len(existing_ats)} "
        f"pending={len(pending)} processed={result.processed_this_run} "
        f"counts={result.counts} new_live_relevant={len(new_entries)} "
        f"total_live_relevant={total_after} classifier={result.classifier_label}"
    )
    for entry in new_entries:
        print(
            "A23_NEW_BOARD "
            f"source_id={entry.source_id} records={entry.record_count} "
            f"matched_recent_family={entry.matched_count} latency_ms={entry.latency_ms}"
        )
    if result.blocked_ids:
        print("A23_BLOCKED " + ",".join(sorted(result.blocked_ids)))
    if total_after < 300:
        print(f"A-23 BOARD TARGET NOT CLOSED: {total_after}/300 live relevant ATS boards")
    else:
        print(f"A-23 BOARD TARGET PASS: {total_after}/300 live relevant ATS boards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
