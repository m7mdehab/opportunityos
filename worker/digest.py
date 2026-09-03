"""``python -m worker --digest``: the F3 daily digest.

Writes a Markdown **and** HTML digest of new, high-fit opportunities to
``out/digest/`` (build output -- gitignored), named deterministically by
date. Content is generated from already-stored ``opportunities`` /
``match_evaluations`` rows only: this module never imports a transport, an
adapter, or ``opportunity.registry`` and makes zero network requests --
see ``reports/evidence/FR-006/e4f3-run.md`` for the assertion that proves
that for E4F3.6.

Email delivery is explicitly out of scope (FR-007, needs a mailbox the
founder has not provided); the API exposes the latest digest instead (see
``api/routes_api.py``'s ``/digest/latest``).
"""
from __future__ import annotations

import html as html_lib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from api.settings import DEFAULT_HIGH_FIT_THRESHOLD
from storage.models import MatchEvaluationRecord, OpportunityRecord

#: Build output, relative to the process's current working directory --
#: gitignored (see .gitignore), never committed.
DEFAULT_OUT_DIR = Path("out") / "digest"

#: "New" for the digest means ingested within this many hours of the run.
#: Named as an assumption in this work order's report: the brief specifies
#: "new high-fit items" for a *daily* digest but does not define "new"
#: itself; a rolling 24h window (rather than, say, "since the last digest
#: file written") keeps a single run's output fully self-contained and
#: reproducible from stored rows alone.
DEFAULT_WINDOW_HOURS = 24.0


@dataclass(frozen=True, slots=True)
class DigestItem:
    id: str
    title: str
    organization: str
    fit_score: float
    decision: Optional[str]
    source_url: str


def _to_utc_naive(value: datetime) -> datetime:
    """Mirrors ``worker.handlers._to_utc_naive`` / ``opportunity.reverification._to_utc_naive``:
    normalize to naive UTC before comparing against ``opportunities.created_at``
    (PostgreSQL ``TIMESTAMP WITHOUT TIME ZONE``)."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _collect_digest_items(
    session: Any,
    *,
    now: datetime,
    window_hours: float,
    high_fit_threshold: float,
) -> list[DigestItem]:
    """New, high-fit opportunities from stored rows only -- no transport, no
    adapter, no registry call. "High-fit" is the most recent
    ``match_evaluations`` row for that opportunity (any truth-pack hash)
    scoring at or above ``high_fit_threshold``; an opportunity never
    evaluated is excluded (not fabricated as high-fit)."""
    window_start = _to_utc_naive(now - timedelta(hours=window_hours))
    naive_now = _to_utc_naive(now)

    candidates = (
        session.query(OpportunityRecord)
        .filter(OpportunityRecord.created_at >= window_start, OpportunityRecord.created_at <= naive_now)
        .all()
    )

    items: list[DigestItem] = []
    for record in candidates:
        latest_eval = (
            session.query(MatchEvaluationRecord)
            .filter_by(opportunity_id=record.id)
            .order_by(MatchEvaluationRecord.evaluated_at.desc())
            .first()
        )
        if latest_eval is None or latest_eval.fit_score is None:
            continue
        if latest_eval.fit_score < high_fit_threshold:
            continue
        items.append(
            DigestItem(
                id=record.id,
                title=record.title,
                organization=record.organization,
                fit_score=latest_eval.fit_score,
                decision=latest_eval.qualification_decision,
                source_url=record.source_url,
            )
        )
    items.sort(key=lambda item: item.fit_score, reverse=True)
    return items


def _render_markdown(items: list[DigestItem], digest_date: str) -> str:
    lines = [f"# OpportunityOS Daily Digest -- {digest_date}", ""]
    if not items:
        lines.append("No new high-fit opportunities today.")
    else:
        for item in items:
            lines.append(
                f"- **{item.title}** at {item.organization} -- fit {item.fit_score:.1f} "
                f"({item.decision or 'unscored'})"
            )
            lines.append(f"  {item.source_url}")
    return "\n".join(lines) + "\n"


def _render_html(items: list[DigestItem], digest_date: str) -> str:
    esc = html_lib.escape
    if not items:
        body = "<p>No new high-fit opportunities today.</p>"
    else:
        entries = "".join(
            "<li><strong>{title}</strong> at {org} -- fit {score:.1f} ({decision})<br>"
            '<a href="{url}">{url}</a></li>'.format(
                title=esc(item.title),
                org=esc(item.organization),
                score=item.fit_score,
                decision=esc(item.decision or "unscored"),
                url=esc(item.source_url),
            )
            for item in items
        )
        body = f"<ul>{entries}</ul>"
    title = f"OpportunityOS Daily Digest -- {digest_date}"
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>"
        f"{esc(title)}</title></head><body><h1>{esc(title)}</h1>{body}</body></html>\n"
    )


def generate_digest(
    session: Any,
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    now: Optional[datetime] = None,
    window_hours: float = DEFAULT_WINDOW_HOURS,
    high_fit_threshold: float = DEFAULT_HIGH_FIT_THRESHOLD,
) -> dict:
    """Write ``<out_dir>/<YYYY-MM-DD>.md`` and ``.html`` for new, high-fit
    opportunities and return a summary dict. Deterministic given the same
    session contents and ``now``. Zero network requests: every value comes
    from ``session.query(...)`` against already-persisted rows.
    """
    now = now or datetime.now(timezone.utc)
    digest_date = now.strftime("%Y-%m-%d")
    items = _collect_digest_items(
        session, now=now, window_hours=window_hours, high_fit_threshold=high_fit_threshold
    )

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    md_path = out_path / f"{digest_date}.md"
    html_path = out_path / f"{digest_date}.html"
    md_path.write_text(_render_markdown(items, digest_date), encoding="utf-8")
    html_path.write_text(_render_html(items, digest_date), encoding="utf-8")

    return {
        "date": digest_date,
        "count": len(items),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
    }


def latest_digest(out_dir: Path = DEFAULT_OUT_DIR) -> Optional[dict]:
    """The most recently generated digest under ``out_dir`` (by filename
    date, descending), or ``None`` if none has ever been written. Read-only,
    no network, used by the API's ``/digest/latest``."""
    out_path = Path(out_dir)
    if not out_path.exists():
        return None
    md_files = sorted(out_path.glob("*.md"), reverse=True)
    if not md_files:
        return None
    latest_md = md_files[0]
    digest_date = latest_md.stem
    html_file = out_path / f"{digest_date}.html"
    return {
        "date": digest_date,
        "markdown": latest_md.read_text(encoding="utf-8"),
        "html": html_file.read_text(encoding="utf-8") if html_file.exists() else None,
    }
