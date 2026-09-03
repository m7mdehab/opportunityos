#!/usr/bin/env py -3.12
"""Scoring metrics for claim A-13 (BRIEF-FR-006).

Runs `matching.scorer.OpportunityScorer` over the committed 540-payload fixture corpus
(`opportunity/fixtures/corpus/`) against `truth.fixtures.founder_shaped_graph()` -- the
founder-shaped synthetic pack, never the founder's own -- and prints:

- B1: the `seniority_and_experience` raw score and explanation for a Staff, a Principal, a
  Lead, a Senior, a Mid and a Junior posting drawn from the corpus (by the posting's
  structured `Opportunity.seniority` field, not a title-text guess).
- B2: the count of corpus rows where a required-skill match at >= working proficiency
  produced a core-skill strength, versus rows where a basic/foundations/unknown proficiency
  produced a partial, plus five real sample reason strings.
- B2 ordering: the `customer_solutions_engineering` title family's best overall score versus
  the `data_engineering` title family's best overall score, measured over the corpus.
- B3: the share of the corpus's titles that map to a title family via
  `matching.title_family.normalize_title`, the share mapping to `other`, and the `other`
  titles split into (a) not a role posting and (b) a role title the taxonomy failed to place.

Every number below is measured over the real, committed corpus. Nothing is filtered,
re-sampled, or re-weighted to move a percentage.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

# Windows terminals default stdout to the legacy cp1252 codepage, which cannot encode
# em dashes and other characters that appear verbatim in real posting titles (e.g. "Field
# Operations Lead — Emergency Response" in this corpus). Reconfigure to UTF-8 with
# replacement so a title's exact characters never crash the metrics run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# See scripts/corpus_metrics.py's identical header comment: force this worktree's own
# packages to the front of sys.path so a shadowing editable install cannot substitute a
# different worktree's code when this file is invoked directly.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT in sys.path:
    sys.path.remove(_REPO_ROOT)
sys.path.insert(0, _REPO_ROOT)

from opportunity.fixtures import load_corpus
from opportunity.models import Opportunity, SeniorityLevel

try:
    from scripts.corpus_metrics import parse_corpus
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from corpus_metrics import parse_corpus  # type: ignore[no-redef]


# A posting title is judged "not a role posting" (B3 group (a)) when it reads as a
# procurement/RFP-style notice rather than a job posting. This corpus (opportunity/fixtures/
# corpus/**) is drawn entirely from job-board adapters (greenhouse, himalayas, lever,
# remote_ok, remotive, we_work_remotely; see corpus_metrics.py's per-source histogram), unlike
# B3's original 67-title hand-assembled sample, which deliberately mixed in TED/UNGM/World
# Bank procurement-notice fixtures from elsewhere in the repo. So this keyword heuristic --
# rather than B3's fixture-provenance knowledge -- is the only signal available here, and is
# expected to find few or no matches in a job-board-only corpus; that is a real property of
# this corpus, not a defect in the heuristic.
_NOT_A_ROLE_POSTING_RE = re.compile(
    r"\b(rfp|request for proposal|tender|procurement|sow|statement of work|solicitation|"
    r"invitation to bid|\bitb\b|expression of interest|\beoi\b|notice)\b",
    re.IGNORECASE,
)

_B1_LEVELS: tuple[tuple[str, SeniorityLevel], ...] = (
    ("Junior", SeniorityLevel.ENTRY),
    ("Mid", SeniorityLevel.MID),
    ("Senior", SeniorityLevel.SENIOR),
    # SeniorityLevel has no separate STAFF member: matching/scorer.py's
    # _REQUIRED_LEVEL_BY_OPP_SENIORITY maps LEAD to seniority.py's "staff" threshold row
    # (industry usage treats Staff and Lead as the same tier). A "Staff" and a "Lead" row
    # therefore necessarily come from the same opp.seniority == LEAD posting; both labels
    # are printed, pointing at the same corpus row, so the brief's six-label table is
    # produced without fabricating a distinction the data model does not have.
    ("Lead", SeniorityLevel.LEAD),
    ("Staff (== Lead threshold; SeniorityLevel has no separate STAFF member)", SeniorityLevel.LEAD),
    ("Principal", SeniorityLevel.PRINCIPAL),
)


def _load_opportunities() -> list[Opportunity]:
    fixtures = load_corpus()
    opportunities, _errors = parse_corpus(fixtures)
    return opportunities


def _evaluator():
    from matching.scorer import OpportunityScorer
    from truth.fixtures import founder_shaped_graph

    return OpportunityScorer(), founder_shaped_graph()


def report_b1_seniority_table(opportunities: list[Opportunity]) -> None:
    print()
    print("=== B1: seniority_and_experience raw score/explanation by opportunity seniority ===")
    scorer, graph = _evaluator()
    by_level: dict[SeniorityLevel, Opportunity] = {}
    for opp in opportunities:
        if opp.seniority not in by_level:
            by_level[opp.seniority] = opp

    for label, level in _B1_LEVELS:
        opp = by_level.get(level)
        if opp is None:
            print(f"{label}: NOT AVAILABLE -- no corpus row has Opportunity.seniority == {level.value}")
            continue
        evaluation = scorer.evaluate(opp, graph)
        dim = next(ds for ds in evaluation.dimension_scores if ds.dimension_name == "seniority_and_experience")
        has_strength = any("Seniority alignment" in s for s in dim.strengths)
        print(
            f"{label} (opportunity_id={opp.id!r}, title={opp.title!r}): "
            f"raw_score={dim.raw_score:.3f} seniority_strength={'YES' if has_strength else 'no'}"
        )
        print(f"    explanation: {dim.explanation}")


def report_b2_core_skill_counts(opportunities: list[Opportunity]) -> None:
    print()
    print("=== B2: core-skill strength vs. partial-proficiency counts, over the corpus ===")
    scorer, graph = _evaluator()
    total = 0
    strength_rows = 0
    partial_rows = 0
    sample_reasons: list[str] = []
    skipped_no_core_skills_dim = 0
    for opp in opportunities:
        evaluation = scorer.evaluate(opp, graph)
        # "core_skills" is only emitted by the employment scoring path
        # (matching/scorer.py's _score_employment); Track.PROCUREMENT rows are scored via
        # _score_independent instead and have no such dimension.
        dim = next((ds for ds in evaluation.dimension_scores if ds.dimension_name == "core_skills"), None)
        if dim is None:
            skipped_no_core_skills_dim += 1
            continue
        total += 1
        if dim.strengths:
            strength_rows += 1
        if any("not a core-skill strength" in u for u in dim.unknowns):
            partial_rows += 1
        if dim.explanation and dim.explanation != "No explicit skills specified in posting." and len(sample_reasons) < 5:
            sample_reasons.append(f"{opp.id}: {dim.explanation}")

    from scripts.corpus_metrics import print_denominator_line

    if skipped_no_core_skills_dim:
        print(
            f"rows excluded (no core_skills dimension -- Track.PROCUREMENT, scored via "
            f"_score_independent instead): {skipped_no_core_skills_dim}"
        )
    print_denominator_line(
        "rows with >= 1 required-skill match at >= working proficiency (core-skill strength)",
        strength_rows,
        total,
    )
    print_denominator_line(
        "rows with >= 1 basic/foundations/unknown-proficiency match (partial, not a strength)",
        partial_rows,
        total,
    )
    print("five sample reason strings from real corpus rows:")
    for reason in sample_reasons:
        print(f"  - {reason}")
    if len(sample_reasons) < 5:
        print(f"  (only {len(sample_reasons)}/5 distinct non-trivial reason strings found)")


def report_b2_ordering(opportunities: list[Opportunity]) -> None:
    print()
    print("=== B2 ordering: customer_solutions_engineering vs. data_engineering, over the corpus ===")
    from matching.title_family import normalize_title

    scorer, graph = _evaluator()
    best: dict[str, tuple[float, str]] = {}
    for opp in opportunities:
        family_id, _level, _rule = normalize_title(opp.title)
        if family_id not in ("customer_solutions_engineering", "data_engineering"):
            continue
        evaluation = scorer.evaluate(opp, graph)
        current = best.get(family_id)
        if current is None or evaluation.overall_fit_score > current[0]:
            best[family_id] = (evaluation.overall_fit_score, opp.title)

    for family_id in ("customer_solutions_engineering", "data_engineering"):
        result = best.get(family_id)
        if result is None:
            print(f"{family_id}: NOT AVAILABLE -- no corpus title maps to this family")
        else:
            score, title = result
            print(f"{family_id}: best overall_fit_score={score:.2f} (title={title!r})")
    print(
        "Note: the fixture-based figures from B2's hand-built fixtures are 46.08 "
        "(customer_solutions_engineering) and 82.5 (data_engineering); the corpus figures "
        "above are measured independently over opportunity/fixtures/corpus/ and may differ "
        "-- the corpus figures are what the report quotes."
    )


def report_b3_title_family_mapping(opportunities: list[Opportunity]) -> None:
    print()
    print("=== B3: title-family mapping share, over the corpus's 540 titles ===")
    from matching.title_family import normalize_title
    from scripts.corpus_metrics import print_denominator_line

    total = len(opportunities)
    mapped = 0
    other_titles: list[str] = []
    for opp in opportunities:
        family_id, _level, _rule = normalize_title(opp.title)
        if family_id == "other":
            other_titles.append(opp.title)
        else:
            mapped += 1

    print_denominator_line("titles mapping to a family (not 'other')", mapped, total)
    print_denominator_line("titles mapping to 'other'", len(other_titles), total)

    group_a = [t for t in other_titles if _NOT_A_ROLE_POSTING_RE.search(t)]
    group_b = [t for t in other_titles if not _NOT_A_ROLE_POSTING_RE.search(t)]
    print_denominator_line("'other' titles: (a) not a role posting", len(group_a), len(other_titles) or 1)
    print_denominator_line("'other' titles: (b) a role title the taxonomy failed to place", len(group_b), len(other_titles) or 1)
    if group_a:
        print("  group (a) sample:")
        for t in group_a[:10]:
            print(f"    - {t}")
    if group_b:
        print("  group (b) sample:")
        for t in group_b[:10]:
            print(f"    - {t}")
    if len(group_b) > 10:
        print(f"    ... and {len(group_b) - 10} more")


def main() -> int:
    opportunities = _load_opportunities()
    if not opportunities:
        print("ERROR: no opportunities parsed from the corpus.", file=sys.stderr)
        return 1
    print(f"corpus opportunities evaluated: {len(opportunities)}")
    report_b1_seniority_table(opportunities)
    report_b2_core_skill_counts(opportunities)
    report_b2_ordering(opportunities)
    report_b3_title_family_mapping(opportunities)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
