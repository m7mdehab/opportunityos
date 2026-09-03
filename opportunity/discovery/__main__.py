"""CLI entry point for the BRIEF-FR-006 E1 ATS board-discovery sweep.

    py -3.12 -m opportunity.discovery [--limit N] [--dry-run]

Every candidate is probed once via a plain unauthenticated GET (the same
`opportunity.transport.HttpTransport` used elsewhere in this repository), paced by a
per-ATS-host shared rate limiter. Progress is written after every candidate to
`opportunity/discovery/.progress.json` so an interrupted or `--limit`-bounded sweep resumes
rather than restarting. A 403/429 is recorded once and, because progress persists it, is
never re-requested in a later invocation of this command either.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from opportunity.discovery import boards
from opportunity.transport import HttpTransport, RateLimiter


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the E1 ATS board discovery sweep.")
    parser.add_argument(
        "--limit", type=int, default=None, help="Max NEW HTTP requests to make this invocation (resumable)."
    )
    parser.add_argument("--registry", type=Path, default=boards.SOURCE_REGISTRY_PATH)
    parser.add_argument("--progress", type=Path, default=boards.DEFAULT_PROGRESS_PATH)
    parser.add_argument(
        "--dry-run", action="store_true", help="Probe and classify but do not write docs/SOURCE_REGISTRY.yaml."
    )
    args = parser.parse_args()

    already = boards.registered_source_ids(args.registry)

    # `recon.sources.ATS_WATCHLIST` (12 GH + 2 Lever + 13 Ashby boards) is deliberately NOT a
    # seed here: every board on it is already registered by FR-003, so it contributes nothing
    # new, and its Ashby members would otherwise get probed even though Ashby automation.read
    # stays disabled this brief (see the re-recon note in docs/SOURCE_EVIDENCE.md) -- there is
    # no policy basis to register a new Ashby board as read-allowed from this sweep. The two
    # seeds the brief actually asks for are a committed public directory and the founder
    # watchlist; both are Greenhouse/Lever only by construction (`kinds` default), so this
    # sweep never probes Ashby at all. Named assumption: Ashby is out of scope for E1's board
    # DISCOVERY quota; it is handled solely by the separate re-recon step below.
    remoteintech_candidates = boards.load_remoteintech_seed_candidates()
    founder_candidates = boards.load_founder_watchlist_candidates()

    seeds_used = [
        "remoteintech_directory (https://github.com/remoteintech/remote-jobs, accessed 2026-09-03;"
        " see opportunity/discovery/seeds/remoteintech_companies.json)",
    ]
    if founder_candidates:
        seeds_used.append("founder_watchlist (private/watchlist.yaml)")
    else:
        seeds_used.append("founder_watchlist (private/watchlist.yaml not present this run; template only)")

    all_candidates = boards.dedupe_candidates(
        [*remoteintech_candidates, *founder_candidates],
        already_registered=already,
    )

    classifier, classifier_label = boards.default_classifier()

    result = boards.run_sweep(
        all_candidates,
        transport=HttpTransport(),
        rate_limiter=RateLimiter(default_min_interval_s=0.4),
        classifier=classifier,
        classifier_label=classifier_label,
        progress_path=args.progress,
        seeds_used=seeds_used,
        max_new_requests=args.limit,
    )

    print(f"Seed directories used: {'; '.join(result.seeds_used)}")
    print(f"Title-family classifier used: {result.classifier_label}")
    print(f"Total candidates considered (deduped, minus already-registered): {result.total_candidates}")
    print(f"New HTTP requests made this invocation: {result.processed_this_run}")
    print(f"Wall-clock this invocation: {result.wall_clock_s:.1f}s")
    print("Classification breakdown (cumulative across all resumed invocations):")
    for classification in boards.CLASSIFICATIONS:
        print(f"  {classification}: {result.counts.get(classification, 0)}")
    print(
        f"Boards registered (>=1 posting in a target title family within 90 days): {len(result.registered)}"
    )
    if result.blocked_ids:
        print(f"Blocked (403/429) -- recorded once, never re-requested: {', '.join(result.blocked_ids)}")
    else:
        print("Blocked (403/429): none")

    if not args.dry_run and result.registered:
        written = boards.append_registry_entries(args.registry, result.registered)
        print(f"Appended {written} new entries to {args.registry}")
    elif args.dry_run:
        print("--dry-run: docs/SOURCE_REGISTRY.yaml was not modified")


if __name__ == "__main__":
    main()
