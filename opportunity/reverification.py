from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error
from opportunity.models import Opportunity
from opportunity.registry import SourceRegistry
from opportunity.transport import RateLimiter

#: Default staleness threshold: an opportunity is a re-verification
#: candidate once this many days have passed since it was first ingested
#: (``OpportunityRecord.created_at``). ``posted_date`` is a best-effort,
#: unstructured string field on that record (not reliably parseable as a
#: date across every source's format), so ``created_at`` -- a real
#: ``DateTime`` column already used for the same "how recent is this row"
#: purpose elsewhere in this project (e.g. ``api/routes_api.py``'s
#: ``dashboard_daily`` "unique_new" count) -- is used instead. Named as an
#: assumption in this work order's return.
DEFAULT_STALE_AFTER_DAYS = 14


def _to_utc_naive(value: datetime) -> datetime:
    """Normalize to a naive ``datetime`` carrying UTC wall-clock time, for
    writing into / comparing against ``opportunities.created_at`` /
    ``opportunities.reverified_at`` (PostgreSQL ``TIMESTAMP WITHOUT TIME
    ZONE``) -- mirrors ``worker.handlers._to_utc_naive`` and
    ``matching.evaluate_persist._to_utc_naive`` exactly, and for the
    identical reason (a session timezone other than UTC otherwise silently
    shifts a tz-aware value on write/compare).
    """
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class StaleOpportunityReverifier:
    @staticmethod
    def reverify_url(url: str, timeout_seconds: int = 5) -> Dict[str, Any]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "OpportunityOS-Reverifier/0.2 (Verification Diagnostic)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                status_code = response.getcode()
                return {
                    "is_stale": status_code in (404, 410),
                    "status_code": status_code,
                    "reverified_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "URL is active and reachable" if status_code == 200 else f"HTTP {status_code}",
                }
        except urllib.error.HTTPError as e:
            return {
                "is_stale": e.code in (404, 410),
                "status_code": e.code,
                "reverified_at": datetime.now(timezone.utc).isoformat(),
                "reason": f"HTTP error {e.code}",
            }
        except urllib.error.URLError as e:
            return {
                "is_stale": False,
                "status_code": None,
                "reverified_at": datetime.now(timezone.utc).isoformat(),
                "reason": f"Transient network failure: {e.reason}",
            }

    @staticmethod
    def reverify_stale_opportunities(
        session: Any,
        *,
        registry: Optional[SourceRegistry] = None,
        rate_limiter: Optional[RateLimiter] = None,
        now: Optional[datetime] = None,
        stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
        reverify_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
    ) -> Dict[str, int]:
        """Re-verify every opportunity older than ``stale_after_days`` and
        write ``is_stale``/``reverified_at`` -- the first writer
        ``stale_postings`` has ever had (see this module's callers in
        ``worker/handlers.py`` and this work order's report).

        Gating, in order, per candidate opportunity:
          1. ``registry.is_read_allowed(record.source_id)`` -- a read-forbidden
             source is never re-verified: it is left alone (``is_stale``
             untouched) and counted in ``skipped_policy``. This is the exact
             same boundary ``worker.handlers.make_poll_source_handler`` and
             ``worker.scheduler.PollScheduler`` enforce for a normal poll --
             re-verification does not get a separate, looser gate.
          2. ``rate_limiter.acquire(record.source_id)`` -- the identical
             shared, per-source ``RateLimiter`` (``opportunity.transport``)
             a poll uses, so re-verification paces requests to the same host
             a poll would, rather than bursting one request per stale row.

        ``reverify_fn`` defaults to ``StaleOpportunityReverifier.reverify_url``
        (a real network request); tests must inject a fake to stay offline.
        A row is marked stale (``is_stale = True``) only when ``reverify_fn``
        reports ``is_stale`` truthy (its own docstring: HTTP 404/410, or a
        non-HTTP transient failure is deliberately *not* treated as stale --
        a network hiccup must never fabricate a "gone" claim).
        """
        from storage.models import OpportunityRecord  # local import: keeps this module's pure
        # reverify_url() helper free of a hard storage.models dependency for callers that
        # never touch the database (e.g. recon scripts).

        reg = registry or SourceRegistry()
        limiter = rate_limiter or RateLimiter()
        clock_now = now or datetime.now(timezone.utc)
        cutoff = _to_utc_naive(clock_now - timedelta(days=stale_after_days))
        reverify = reverify_fn or StaleOpportunityReverifier.reverify_url

        candidates = (
            session.query(OpportunityRecord)
            .filter(OpportunityRecord.created_at < cutoff)
            .all()
        )

        checked = 0
        marked_stale = 0
        skipped_policy = 0
        for record in candidates:
            if not reg.is_read_allowed(record.source_id):
                skipped_policy += 1
                continue
            limiter.acquire(record.source_id)
            result = reverify(record.source_url)
            record.is_stale = bool(result.get("is_stale"))
            record.reverified_at = _to_utc_naive(clock_now)
            checked += 1
            if record.is_stale:
                marked_stale += 1
        session.commit()

        return {
            "candidates": len(candidates),
            "checked": checked,
            "marked_stale": marked_stale,
            "skipped_policy": skipped_policy,
        }
