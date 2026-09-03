#!/usr/bin/env py -3.12
"""Corpus metrics for claim A-12 (BRIEF-FR-006).

Prints, with denominators, every quantitative number the brief's A-12 claim measures
against the committed fixture corpus at ``opportunity/fixtures/corpus/``:

- corpus size (payload count, per-source histogram)
- share of rows with a work mode other than ``unspecified``
- share with a ``location_country`` or a non-unspecified ``remote_scope``
- the adapter vs. inference split of work-mode values (``Opportunity.work_mode_source``)
- the qualification decision distribution, computed twice: once against
  ``truth.fixtures.founder_shaped_graph()`` (the figure that answers the claim -- this is
  what a founder actually saw) and once against an empty ``TruthGraph`` (so the difference
  from A1C's original number is visible, not silently overwritten)

The work-mode / location-country / remote-scope / adapter-inference-split metrics all read
fields (``Opportunity.work_mode``, ``work_mode_source``, ``location_country``,
``remote_scope``) added by work order A1. Those fields now exist on every real
``Opportunity`` with defaults, so a real corpus row can never trigger the "attribute is
missing" branches below; those branches exist for callers that pass in a stripped/stubbed
record (see scripts/test_corpus_metrics.py) and are kept so a genuinely missing field is
still reported as NOT AVAILABLE rather than a fabricated 0%.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path
from typing import Any

# An editable install of a *different* worktree can shadow this repository's own
# `opportunity`/`matching`/`truth` packages when this file is invoked directly
# (`py -3.12 scripts/corpus_metrics.py`) rather than as a module. Force this
# worktree's repository root to the front of sys.path so the packages below
# always resolve to the code actually sitting next to this script.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT in sys.path:
    sys.path.remove(_REPO_ROOT)
sys.path.insert(0, _REPO_ROOT)

from opportunity.adapters import get_all_standard_adapters
from opportunity.fixtures import CorpusFixture, load_corpus
from opportunity.models import Opportunity

MISSING = object()


def build_adapter_map() -> dict[str, Any]:
    return {adapter.source_id: adapter for adapter in get_all_standard_adapters()}


def parse_corpus(fixtures: list[CorpusFixture]) -> tuple[list[Opportunity], list[str]]:
    """Re-parse every fixture through its own (unmodified) adapter. Returns (opportunities, parse_errors)."""
    adapter_map = build_adapter_map()
    opportunities: list[Opportunity] = []
    parse_errors: list[str] = []
    for fixture in fixtures:
        adapter = adapter_map.get(fixture.source_id)
        if adapter is None:
            parse_errors.append(f"{fixture.path}: no adapter registered for source_id '{fixture.source_id}'")
            continue
        try:
            result = adapter.parse_payload(
                fixture.raw_body,
                raw_pointer=f"corpus:{fixture.path.name}",
                fetched_at=fixture.fetched_at,
            )
        except Exception as e:  # noqa: BLE001 - report, do not hide
            parse_errors.append(f"{fixture.path}: parse_payload raised {type(e).__name__}: {e}")
            continue
        if not result.opportunities:
            parse_errors.append(
                f"{fixture.path}: adapter parsed zero opportunities from a single-record fixture "
                f"(schema_drift={result.has_schema_drift}, error={result.parser_error})"
            )
            continue
        opportunities.extend(result.opportunities)
    return opportunities, parse_errors


def print_denominator_line(label: str, numerator: int, denominator: int) -> None:
    pct = (100.0 * numerator / denominator) if denominator else 0.0
    print(f"{label}: {numerator}/{denominator} ({pct:.1f}%)")


def report_work_mode_coverage(opportunities: list[Opportunity]) -> None:
    print()
    print("--- work-mode coverage (Opportunity.work_mode, added by A1) ---")
    missing = [o for o in opportunities if getattr(o, "work_mode", MISSING) is MISSING]
    if missing:
        print(
            "NOT AVAILABLE on this worktree: Opportunity has no 'work_mode' attribute yet. "
            "This field is added by work order A1 (BRIEF-FR-006 Track A). Re-run this script "
            "after A1's extraction change is merged to get a real number here. "
            f"({len(missing)}/{len(opportunities)} rows lack the attribute.)"
        )
        return
    # Compare the WorkMode enum member directly to the plain string, not via str(x): WorkMode
    # mixes in `str`, so equality with a plain string works correctly (`WorkMode.UNSPECIFIED ==
    # "unspecified"` is True), but `str(WorkMode.UNSPECIFIED)` renders as "WorkMode.UNSPECIFIED"
    # (Enum.__str__), which would make this comparison always-true and silently report every row
    # as non-unspecified.
    non_unspecified = sum(1 for o in opportunities if getattr(o, "work_mode") != "unspecified")
    print_denominator_line("work_mode != unspecified", non_unspecified, len(opportunities))


def report_location_coverage(opportunities: list[Opportunity]) -> None:
    print()
    print("--- location coverage (location_country OR non-unspecified remote_scope, added by A1) ---")
    missing_country = [o for o in opportunities if getattr(o, "location_country", MISSING) is MISSING]
    missing_scope = [o for o in opportunities if getattr(o, "remote_scope", MISSING) is MISSING]
    if missing_country or missing_scope:
        print(
            "NOT AVAILABLE on this worktree: Opportunity has no 'location_country' and/or "
            "'remote_scope' attribute yet. Both are added by work order A1 (BRIEF-FR-006 Track A). "
            "Re-run this script after A1's extraction change is merged to get a real number here."
        )
        return
    covered = sum(
        1
        for o in opportunities
        if getattr(o, "location_country", None) or getattr(o, "remote_scope", "unspecified") != "unspecified"
    )
    print_denominator_line("location_country or remote_scope != unspecified", covered, len(opportunities))


def report_adapter_inference_split(opportunities: list[Opportunity]) -> None:
    print()
    print("--- adapter vs. inference split of work_mode (Opportunity.work_mode_source, added by A1) ---")
    missing = [o for o in opportunities if getattr(o, "work_mode_source", MISSING) is MISSING]
    if missing:
        print(
            "NOT AVAILABLE on this worktree: Opportunity has no 'work_mode_source' attribute yet. "
            "This field is added by work order A1 (BRIEF-FR-006 Track A), with values exactly "
            "'adapter', 'inference', or 'none'. Re-run this script after A1's extraction change "
            "is merged to get a real split here."
        )
        return
    counts = collections.Counter(str(getattr(o, "work_mode_source")) for o in opportunities)
    total = len(opportunities)
    for label in ("adapter", "inference", "none"):
        print_denominator_line(f"work_mode_source == {label}", counts.get(label, 0), total)
    other = total - sum(counts.get(k, 0) for k in ("adapter", "inference", "none"))
    if other:
        print(f"work_mode_source with unexpected value: {other}/{total}")


def _qualification_distribution(
    opportunities: list[Opportunity], truth_graph: Any
) -> tuple[collections.Counter[str], int]:
    from matching.qualification import QualificationEngine

    engine = QualificationEngine()
    decisions: collections.Counter[str] = collections.Counter()
    eval_errors = 0
    for opp in opportunities:
        try:
            decision, _results = engine.evaluate(opp, truth_graph)
        except Exception:  # noqa: BLE001 - count, do not hide
            eval_errors += 1
            continue
        decisions[str(decision.value)] += 1
    return decisions, eval_errors


def report_qualification_founder_shaped(opportunities: list[Opportunity]) -> None:
    print()
    print("--- qualification decision distribution: against truth.fixtures.founder_shaped_graph() ---")
    try:
        from truth.fixtures import founder_shaped_graph
    except ImportError as e:
        print(f"NOT AVAILABLE: could not import founder_shaped_graph ({e}).")
        return
    decisions, eval_errors = _qualification_distribution(opportunities, founder_shaped_graph())
    total = len(opportunities)
    for label in ("qualified", "ineligible", "uncertain"):
        print_denominator_line(f"decision == {label}", decisions.get(label, 0), total)
    if eval_errors:
        print(f"evaluation errors (excluded from the distribution above): {eval_errors}/{total}")
    print(
        "Note: evaluated against the founder-shaped synthetic pack (truth.fixtures."
        "founder_shaped_graph(), never the founder's own pack), so this is the figure "
        "comparable to what a founder actually saw."
    )


def report_qualification_empty_graph(opportunities: list[Opportunity]) -> None:
    print()
    print("--- qualification decision distribution: against an empty TruthGraph (for comparison) ---")
    try:
        from truth.graph import TruthGraph
    except ImportError as e:
        print(f"NOT AVAILABLE: could not import the qualifier ({e}).")
        return
    decisions, eval_errors = _qualification_distribution(opportunities, TruthGraph())
    total = len(opportunities)
    for label in ("qualified", "ineligible", "uncertain"):
        print_denominator_line(f"decision == {label}", decisions.get(label, 0), total)
    if eval_errors:
        print(f"evaluation errors (excluded from the distribution above): {eval_errors}/{total}")
    print(
        "Note: evaluated with an empty TruthGraph (no founder-specific assertions), so this is "
        "the qualifier's structural behaviour over the corpus, not a founder-personalised result. "
        "This is A1C's original figure, kept for comparison, not the figure the A-12 claim answers."
    )


def main() -> int:
    fixtures = load_corpus()
    if not fixtures:
        print("ERROR: no fixtures found under opportunity/fixtures/corpus/.", file=sys.stderr)
        return 1

    per_source: collections.Counter[str] = collections.Counter(f.source_id for f in fixtures)
    print("=== corpus size ===")
    print(f"total payloads: {len(fixtures)}")
    print(f"distinct sources: {len(per_source)}")
    print("--- per-source histogram ---")
    for source_id, count in sorted(per_source.items()):
        print(f"{source_id}: {count}")

    opportunities, parse_errors = parse_corpus(fixtures)
    print()
    print(f"payloads re-parsed into an Opportunity via their own adapter: {len(opportunities)}/{len(fixtures)}")
    if parse_errors:
        print(f"parse errors (excluded from metrics below): {len(parse_errors)}")
        for err in parse_errors[:10]:
            print(f"  - {err}")
        if len(parse_errors) > 10:
            print(f"  ... and {len(parse_errors) - 10} more")

    report_work_mode_coverage(opportunities)
    report_location_coverage(opportunities)
    report_adapter_inference_split(opportunities)
    report_qualification_founder_shaped(opportunities)
    report_qualification_empty_graph(opportunities)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
