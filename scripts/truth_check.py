#!/usr/bin/env python3
"""Print a pack-level validation report and section completeness for a
founder truth pack.

Default path: private/truth_pack.yaml (see truth.pack.DEFAULT_TRUTH_PACK_PATH).
That default is only ever touched by `load_founder_pack` when `--path` is
omitted; this script never reads private/ directly itself.

Prints no field values -- no names, employers, titles, skills, or evidence
content. Only section names, entry counts, and the validator's own findings
text (see truth/pack.py for exactly what is and is not checked) are ever
printed.

Exit code: 0 only when the pack loads and validates cleanly; 1 otherwise,
with findings printed to stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from truth.pack import (  # noqa: E402
    DEFAULT_TRUTH_PACK_PATH,
    TruthPackInvalid,
    TruthPackMissing,
    load_founder_pack,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_TRUTH_PACK_PATH,
        help="path to the truth pack YAML/JSON file (default: private/truth_pack.yaml)",
    )
    args = parser.parse_args(argv)

    try:
        loaded = load_founder_pack(args.path)
    except TruthPackMissing as error:
        print(f"truth pack missing: {error}")
        return 1
    except TruthPackInvalid as error:
        print("truth pack INVALID")
        print(f"  {error}")
        for finding in error.findings:
            print(f"  finding: {finding}")
        return 1

    report = loaded.report
    # `identity` and `approved_phrases` are not tracked by
    # truth.pack.PackValidationReport (a top-level pack section, not a
    # career_profile/capability_profile field), so their counts are read
    # directly off the loaded graph and merged in here -- section names and
    # entry counts only, same as every other line below.
    section_counts = list(report.section_counts)
    section_counts.append(("identity", 1 if loaded.graph.identity is not None else 0))
    section_counts.append(("approved_phrases", len(loaded.graph.approved_phrases)))
    section_counts.sort()

    print(f"path: {args.path}")
    print(f"truth pack valid: {report.valid}")
    print(f"truth_pack_hash: {loaded.truth_pack_hash}")
    print("section counts:")
    for name, count in section_counts:
        print(f"  {name}: {count}")

    empty = tuple(name for name, count in section_counts if count == 0)
    if empty:
        print("empty sections:")
        for name in empty:
            print(f"  {name}")
    else:
        print("empty sections: none")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
