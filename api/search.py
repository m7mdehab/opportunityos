"""Full-text search over opportunities (BRIEF-FR-006, work order C2).

Query language: bare terms (AND), quoted phrases, and negative terms with a
leading ``-`` including negated phrases (``-"customer engineer"``). This is
built entirely on PostgreSQL's ``websearch_to_tsquery``, not
``phraseto_tsquery`` and not a hand-rolled parser: ``websearch_to_tsquery``
is the one built-in tsquery-building function whose input grammar already
*is* the grammar this brief asks for (bare terms -> implicit AND, ``"..."``
-> phrase, a leading ``-`` -> negation, including on a phrase), and --
unlike ``to_tsquery`` -- it never raises a syntax error on malformed input.
Given an unbalanced quote, a lone ``-``, an empty string, or literal
``tsquery`` operator characters (``&``, ``|``, ``!``, ``(``, ``)``, ``:``),
it degrades to whatever it can parse, worst case an empty tsquery that
matches nothing. That is the entire "never a 500" guarantee this module
needs, satisfied by Postgres itself rather than a try/except around a
custom parser.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

_TS_CONFIG = "english"


@dataclass(frozen=True)
class SearchHit:
    """One search match: an opportunity id and its relevance-only score
    (``ts_rank`` against ``search_tsv``) -- not yet combined with fit.
    Keeping relevance separate from the combined ranking key (`rank_key`
    below) means relevance alone stays independently inspectable and
    testable."""

    opportunity_id: str
    relevance: float


def search_opportunity_ids(session: Session, raw_query: str) -> tuple[SearchHit, ...]:
    """Run `raw_query` through `websearch_to_tsquery` against `search_tsv`
    and return every matching opportunity id with its `ts_rank` relevance.
    Returns `()` for a blank query or a query that matches nothing --
    never raises. Callers combine this with `rank_key` for final ordering
    and must apply their own facet/filter intersection afterward; this
    function only answers "what does the text search itself match."
    """
    stripped = (raw_query or "").strip()
    if not stripped:
        return ()

    rows = session.execute(
        text(
            "SELECT id, ts_rank(search_tsv, websearch_to_tsquery(:cfg, :q)) AS relevance "
            "FROM opportunities "
            "WHERE search_tsv @@ websearch_to_tsquery(:cfg, :q)"
        ),
        {"cfg": _TS_CONFIG, "q": stripped},
    ).all()
    return tuple(SearchHit(opportunity_id=row.id, relevance=float(row.relevance)) for row in rows)


def is_query_unparseable(session: Session, raw_query: str) -> bool:
    """True when `raw_query` is non-blank but reduces to an empty tsquery
    under `websearch_to_tsquery` (a lone `-`, only stopwords, only
    punctuation, a quote that swallows the whole string with nothing left
    to search on). Distinct from:
    - a blank query (`""`/whitespace-only) -- that means "no search active",
      not "unparseable", and is never routed through this function by
      `api.routes_api.list_opportunities`.
    - a query that parses fine but matches zero rows -- a legitimate empty
      *result*, not a message-worthy parse failure.
    """
    stripped = (raw_query or "").strip()
    if not stripped:
        return False
    result = session.execute(
        text("SELECT (websearch_to_tsquery(:cfg, :q) = ''::tsquery) AS is_empty"),
        {"cfg": _TS_CONFIG, "q": stripped},
    ).scalar()
    return bool(result)


def rank_key(relevance: float, fit_score: float | None) -> float:
    """The ranking formula (brief C2 requirement 3): **relevance x fit**.

    - `relevance` is `ts_rank(search_tsv, websearch_to_tsquery(...))`, a
      small non-negative float (typically 0-1, occasionally slightly above
      1 for very dense matches).
    - `fit_score` is OpportunityOS's existing 0-100 scale
      (`matching/scorer.py` / `match_evaluations.fit_score`), normalised to
      0-1 here so relevance -- not fit's larger raw magnitude -- sets the
      scale of the product, and fit acts as a multiplicative weight on it.
    - A `None` fit_score (opportunity has no evaluation yet) uses a neutral
      0.5 multiplier: not 0 (which would always bury unevaluated matches
      last) and not 1 (which would rank them above every evaluated match
      with fit_score < 100).

    This function returns a **sort key only**. It reads `fit_score` but
    never writes it, and never touches `decision` -- nothing computed here
    is persisted anywhere. `api.test_search.NoReJudgementTest` asserts the
    underlying `match_evaluations` row (`decision`, `fit_score`) is
    byte-identical before and after a search request that ranks by this
    key.
    """
    fit_component = 0.5 if fit_score is None else max(0.0, min(100.0, fit_score)) / 100.0
    return relevance * fit_component
