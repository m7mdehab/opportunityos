"""ATS board discovery at scale (BRIEF-FR-006 E1).

Probes candidate company boards on Greenhouse, Lever, and Ashby's documented
public JSON endpoints, classifies each, and emits a registry entry generated
from a template for boards that are live and relevant. See
`reports/evidence/FR-006/orders/E1-discovery.md` for the governing rules.

Nothing here submits or writes anything except a local registry entry and a
local resumable-progress cache; every network call is an unauthenticated GET
to a documented public endpoint.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

from opportunity.transport import DiscoveryRequest, HttpTransport, RateLimiter, TransportResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
DISCOVERY_DIR = Path(__file__).resolve().parent
SEEDS_DIR = DISCOVERY_DIR / "seeds"

# Runtime cache only -- never a seed source of truth, safe to delete, not evidence.
DEFAULT_PROGRESS_PATH = DISCOVERY_DIR / ".progress.json"

FOUNDER_WATCHLIST_PATH = REPO_ROOT / "private" / "watchlist.yaml"
FOUNDER_WATCHLIST_TEMPLATE_PATH = REPO_ROOT / "private" / "watchlist.yaml.template"
SOURCE_REGISTRY_PATH = REPO_ROOT / "docs" / "SOURCE_REGISTRY.yaml"

ATS_HOSTS: dict[str, str] = {
    "greenhouse": "boards-api.greenhouse.io",
    "lever": "api.lever.co",
    "ashby": "api.ashbyhq.com",
}

# Minimum seconds between requests to the SAME ATS host, shared across every board on
# that host -- not per board. AGENTS.md: "a 300-board sweep that hammers one host is a
# policy violation even if every individual board is public."
DEFAULT_MIN_INTERVAL_S: dict[str, float] = {
    "greenhouse": 0.4,
    "lever": 0.4,
    "ashby": 0.4,
}

CLASSIFICATIONS = ("live", "empty", "absent", "blocked", "error")

_POLICY_EVIDENCE: dict[str, str] = {
    "greenhouse": "https://www.greenhouse.com/terms-of-use",
    "lever": "https://www.lever.co/terms",
    "ashby": "https://www.ashbyhq.com/privacy",
}


def candidate_url(kind: str, token: str) -> str:
    if kind == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    if kind == "lever":
        return f"https://api.lever.co/v0/postings/{token}?mode=json"
    if kind == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=false"
    raise ValueError(f"Unknown ATS kind: {kind!r}")


@dataclass(frozen=True, slots=True)
class BoardCandidate:
    kind: str
    token: str
    company: str = ""
    seed: str = ""

    @property
    def candidate_id(self) -> str:
        return f"{self.kind}:{self.token}"

    @property
    def url(self) -> str:
        return candidate_url(self.kind, self.token)


@dataclass(frozen=True, slots=True)
class Posting:
    title: str
    posted_date: str = ""


def _extract_postings(kind: str, payload: str) -> list[Posting]:
    data = json.loads(payload)
    if kind == "greenhouse":
        items = data.get("jobs", []) if isinstance(data, dict) else []
        return [
            Posting(
                title=str(item.get("title", "")),
                posted_date=str(item.get("updated_at") or item.get("first_published") or ""),
            )
            for item in items
            if isinstance(item, dict)
        ]
    if kind == "lever":
        items = data if isinstance(data, list) else []
        out: list[Posting] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            created = item.get("createdAt")
            posted = ""
            if isinstance(created, (int, float)):
                posted = datetime.fromtimestamp(created / 1000, tz=timezone.utc).date().isoformat()
            out.append(Posting(title=str(item.get("text", "")), posted_date=posted))
        return out
    if kind == "ashby":
        items = data.get("jobs", []) if isinstance(data, dict) else []
        return [
            Posting(title=str(item.get("title", "")), posted_date=str(item.get("publishedAt") or ""))
            for item in items
            if isinstance(item, dict)
        ]
    return []


def classify_status(status_code: int, body: str, kind: str) -> tuple[str, str, tuple[Posting, ...]]:
    """Classify a probe outcome. `blocked` (403/429) is recorded and must never be retried."""
    if status_code in (403, 429):
        return "blocked", f"HTTP {status_code}", ()
    if status_code == 404:
        return "absent", "HTTP 404", ()
    if 200 <= status_code < 300:
        try:
            postings = tuple(_extract_postings(kind, body))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            return "error", f"parse_error: {error}", ()
        if postings:
            return "live", f"HTTP 200; {len(postings)} postings parsed", postings
        return "empty", "HTTP 200; zero postings", ()
    return "error", f"HTTP {status_code}", ()


# ---------------------------------------------------------------------------
# Title-family relevance filter -- small interface so B3's family model can be
# wired in without this module depending on it existing at import time.
# ---------------------------------------------------------------------------


class TitleFamilyClassifier:
    def is_target_family(self, title: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


_FALLBACK_KEYWORDS = (
    "data engineer", "data scientist", "machine learning", "ml engineer", "ai engineer",
    "analytics", "business intelligence", "backend", "back end", "back-end",
    "software engineer", "devops", "platform engineer", "site reliability", "sre",
    "cloud engineer", "solutions engineer", "solution engineer", "customer engineer",
    "data migration", "etl", "frontend", "front end", "front-end", "full stack",
    "fullstack", "product manager", "program manager", "project manager", "tutor",
)


class KeywordFallbackClassifier(TitleFamilyClassifier):
    """Committed fallback used only when `matching.title_family` is unavailable."""

    def is_target_family(self, title: str) -> bool:
        lowered = (title or "").lower()
        return any(keyword in lowered for keyword in _FALLBACK_KEYWORDS)


class TitleFamilyModelClassifier(TitleFamilyClassifier):
    """Wraps B3's `matching.title_family.normalize_title`; `other` is not a target family."""

    def __init__(self) -> None:
        from matching.title_family import normalize_title  # local import: B3 may not exist yet

        self._normalize_title = normalize_title

    def is_target_family(self, title: str) -> bool:
        family_id, _level, _rule = self._normalize_title(title or "")
        return family_id != "other"


def default_classifier() -> tuple[TitleFamilyClassifier, str]:
    """Returns (classifier, label). The label MUST be reported: a keyword-fallback count
    is a different number from a title-family-model count."""
    try:
        return TitleFamilyModelClassifier(), "title_family_model"
    except Exception:
        return KeywordFallbackClassifier(), "keyword_fallback"


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def relevant_postings(
    postings: Iterable[Posting],
    classifier: TitleFamilyClassifier,
    now: date,
    window_days: int = 90,
) -> list[Posting]:
    """>= 1 posting in a target title family, posted within `window_days` of `now`.

    Assumption (named): a posting whose date could not be parsed is treated as within the
    window rather than silently dropped, because failing to parse a timestamp is not evidence
    the posting is stale.
    """
    cutoff = now - timedelta(days=window_days)
    matched: list[Posting] = []
    for posting in postings:
        if not classifier.is_target_family(posting.title):
            continue
        posted = _parse_date(posting.posted_date)
        if posted is not None and posted < cutoff:
            continue
        matched.append(posting)
    return matched


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


def load_watchlist_ats_candidates() -> list[BoardCandidate]:
    """The already-committed FR-003 ATS watchlist (`recon/sources.py:ATS_WATCHLIST`)."""
    from recon.sources import ATS_WATCHLIST

    return [
        BoardCandidate(kind=kind, token=token, company=company, seed="recon_ats_watchlist")
        for company, (kind, token) in ATS_WATCHLIST.items()
    ]


def load_remoteintech_seed_candidates(
    path: Path | None = None, kinds: Sequence[str] = ("greenhouse", "lever")
) -> list[BoardCandidate]:
    """Committed public directory: github.com/remoteintech/remote-jobs (see
    `opportunity/discovery/seeds/remoteintech_companies.json` for citation and date).

    Each company-name slug is a discovery CANDIDATE token, tried against the requested
    ATS kinds; only a live HTTP 200 with parseable postings confirms the guess.
    """
    target = path or (SEEDS_DIR / "remoteintech_companies.json")
    if not target.exists():
        return []
    data = json.loads(target.read_text(encoding="utf-8"))
    slugs = data.get("slugs", [])
    return [
        BoardCandidate(kind=kind, token=slug, company=slug, seed="remoteintech_directory")
        for slug in slugs
        for kind in kinds
    ]


def load_founder_watchlist_candidates(path: Path | None = None) -> list[BoardCandidate]:
    """Founder-private second seed. NEVER read the real path implicitly in tests -- pass an
    explicit temp `path`. Returns [] if the file does not exist (template only, not populated)."""
    target = path if path is not None else FOUNDER_WATCHLIST_PATH
    if not target.exists():
        return []
    import yaml

    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    out: list[BoardCandidate] = []
    for item in data.get("companies", []) or []:
        kind = str(item.get("kind", "")).strip().lower()
        token = str(item.get("token", "")).strip()
        # Council review 4, finding 7: restricted to Greenhouse/Lever only. `ATS_HOSTS`
        # also lists `ashby`, which is registered `disabled` in the committed registry
        # (every `ashby:*` entry has `automation.read: disabled`) -- accepting an
        # `ashby` watchlist entry here would fail-open the sweep into probing
        # `api.ashbyhq.com` and writing a new `ashby:*` entry with `read: allowed`,
        # directly contradicting that disabled status.
        if kind not in ("greenhouse", "lever") or not token:
            continue
        out.append(
            BoardCandidate(kind=kind, token=token, company=str(item.get("name", token)), seed="founder_watchlist")
        )
    return out


def registered_source_ids(registry_path: Path | None = None) -> set[str]:
    target = registry_path or SOURCE_REGISTRY_PATH
    if not target.exists():
        return set()
    text = target.read_text(encoding="utf-8")
    return set(re.findall(r"(?m)^\s*-\s+source_id:\s*(\S+)", text))


class ATSHostNotReadAllowed(RuntimeError):
    """Raised when a candidate's ATS kind has no host-level read-allowed authority.

    Council review 4, finding 7: the registry is the authority for whether a host may
    be probed at all -- a candidate whose kind (e.g. `ashby`) has zero
    `read: allowed` entries in the committed registry must never reach a live
    request or a generated, read-allowed registry entry, regardless of how it was
    seeded (watchlist, directory, or otherwise).
    """


def _kind_has_host_level_read_allowed(kind: str, registry_path: Path | None = None) -> bool:
    """True iff the committed registry has >=1 `{kind}:*` entry with `automation.read: allowed`."""
    target = registry_path or SOURCE_REGISTRY_PATH
    if not target.exists():
        return False
    text = target.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(?ms)^\s*-\s+source_id:\s*{re.escape(kind)}:\S+.*?^\s*automation:\s*\n\s*read:\s*(\S+)"
    )
    return any(match.group(1) == "allowed" for match in pattern.finditer(text))


def _assert_kind_host_allowed(kind: str, registry_path: Path | None = None) -> None:
    if not _kind_has_host_level_read_allowed(kind, registry_path):
        raise ATSHostNotReadAllowed(
            f"Refused: ATS kind '{kind}' has no host-level 'automation.read: allowed' entry in "
            "the committed registry -- no entry for this kind may be generated or probed."
        )


def dedupe_candidates(candidates: Iterable[BoardCandidate], already_registered: set[str] = frozenset()) -> list[BoardCandidate]:
    seen: set[str] = set()
    out: list[BoardCandidate] = []
    for candidate in candidates:
        cid = candidate.candidate_id
        if cid in seen or cid in already_registered:
            continue
        seen.add(cid)
        out.append(candidate)
    return out


# ---------------------------------------------------------------------------
# Resumable progress
# ---------------------------------------------------------------------------


class CorruptProgressFile(RuntimeError):
    """Raised when the resumable-progress cache exists but cannot be parsed.

    Council review 4, finding 8: a crash mid-write used to leave invalid JSON, and
    the old ``load_progress`` swallowed that as ``{}`` -- silently re-probing every
    candidate, *including ones already recorded as blocked*. Refusing to run is the
    correct behaviour when the record of what is blocked has been lost; the caller
    must delete or manually recover the file before a sweep can proceed.
    """


def load_progress(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise CorruptProgressFile(f"Could not read progress file {path}: {error}") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise CorruptProgressFile(
            f"Progress file {path} exists but is not valid JSON (possible crash mid-write); "
            "refusing to run rather than silently re-probing candidates already recorded as "
            "blocked. Recover or delete the file to proceed."
        ) from error


def save_progress(path: Path, progress: dict[str, dict]) -> None:
    """Atomically replace the progress file so a crash mid-write can never corrupt it.

    Council review 4, finding 8: writes to a temporary path in the same directory
    first, then ``os.replace``s it into place -- ``os.replace`` is atomic on both
    POSIX and Windows, so readers only ever see the old complete file or the new
    complete file, never a partial write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp_path.write_text(json.dumps(progress, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Registry entry generation from a template
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegistryEntryDraft:
    source_id: str
    name: str
    kind: str
    token: str
    policy_evidence_url: str
    record_count: int
    matched_count: int
    latency_ms: int
    reviewed_date: str
    automation_read: str = "allowed"


def build_registry_entry(
    candidate: BoardCandidate,
    record_count: int,
    matched_count: int,
    latency_ms: int,
    reviewed_date: str | None = None,
    automation_read: str = "allowed",
    registry_path: Path | None = None,
) -> RegistryEntryDraft:
    if automation_read == "allowed":
        _assert_kind_host_allowed(candidate.kind, registry_path)
    return RegistryEntryDraft(
        source_id=candidate.candidate_id,
        name=candidate.candidate_id,
        kind=candidate.kind,
        token=candidate.token,
        policy_evidence_url=_POLICY_EVIDENCE[candidate.kind],
        record_count=record_count,
        matched_count=matched_count,
        latency_ms=latency_ms,
        reviewed_date=reviewed_date or date.today().isoformat(),
        automation_read=automation_read,
    )


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


_REGISTRY_ENTRY_TEMPLATE = (
    "  - source_id: {source_id}\n"
    "    name: {name_quoted}\n"
    "    category: employment\n"
    "    access:\n"
    "      discovery: public_get\n"
    "      detail: public_get_or_unknown\n"
    "      submit: prohibited_or_unknown\n"
    "    attribution:\n"
    "      required: review_required\n"
    "    rate_limits:\n"
    "      documented: shared_per_ats_host\n"
    "    commercial_use:\n"
    "      status: review_required\n"
    "    automation:\n"
    "      read: {automation_read}\n"
    "      prepare: disabled\n"
    "      submit: disabled\n"
    "    policy_status: unknown_disable_actions\n"
    "    observed:\n"
    "      status: allowed_ok\n"
    "      detail: {detail_quoted}\n"
    "      request_metadata: {request_meta_quoted}\n"
    "      latency_ms: {latency_ms}\n"
    "      record_count: {record_count}\n"
    "    last_policy_reviewed: {reviewed_date}\n"
    "    policy_evidence:\n"
    "      - {policy_evidence_url}\n"
)


def render_registry_entry(entry: RegistryEntryDraft) -> str:
    detail = f"HTTP 200; {entry.matched_count}/{entry.record_count} postings in target title families within 90 days"
    request_meta = f"method=GET; endpoint={candidate_url(entry.kind, entry.token)}"
    return _REGISTRY_ENTRY_TEMPLATE.format(
        source_id=entry.source_id,
        name_quoted=yaml_quote(entry.name),
        automation_read=entry.automation_read,
        detail_quoted=yaml_quote(detail),
        request_meta_quoted=yaml_quote(request_meta),
        latency_ms=entry.latency_ms,
        record_count=entry.record_count,
        reviewed_date=entry.reviewed_date,
        policy_evidence_url=entry.policy_evidence_url,
    )


def append_registry_entries(registry_path: Path, entries: Sequence[RegistryEntryDraft]) -> int:
    """Appends generated entries whose source_id is not already present. Returns count written."""
    if not entries:
        return 0
    existing = registry_path.read_text(encoding="utf-8") if registry_path.exists() else "sources:\n"
    existing_ids = set(re.findall(r"(?m)^\s*-\s+source_id:\s*(\S+)", existing))
    new_blocks = [render_registry_entry(e) for e in entries if e.source_id not in existing_ids]
    if not new_blocks:
        return 0
    if not existing.endswith("\n"):
        existing += "\n"
    registry_path.write_text(existing + "".join(new_blocks), encoding="utf-8", newline="\n")
    return len(new_blocks)


# ---------------------------------------------------------------------------
# Sweep orchestration
# ---------------------------------------------------------------------------


@dataclass
class SweepResult:
    total_candidates: int
    counts: dict[str, int]
    registered: list[RegistryEntryDraft]
    blocked_ids: list[str]
    seeds_used: list[str]
    classifier_label: str
    wall_clock_s: float
    processed_this_run: int


def run_sweep(
    candidates: Sequence[BoardCandidate],
    *,
    transport=None,
    rate_limiter: RateLimiter | None = None,
    classifier: TitleFamilyClassifier | None = None,
    classifier_label: str = "",
    now: date | None = None,
    progress_path: Path | None = None,
    seeds_used: Sequence[str] = (),
    max_new_requests: int | None = None,
) -> SweepResult:
    transport = transport or HttpTransport()
    rate_limiter = rate_limiter if rate_limiter is not None else RateLimiter()
    if classifier is None:
        classifier, classifier_label = default_classifier()
    now = now or date.today()
    progress_path = progress_path or DEFAULT_PROGRESS_PATH
    progress = load_progress(progress_path)

    counts: dict[str, int] = {c: 0 for c in CLASSIFICATIONS}
    registered: list[RegistryEntryDraft] = []
    blocked: list[str] = []
    processed_this_run = 0
    started = time.monotonic()

    for candidate in candidates:
        cid = candidate.candidate_id

        # Council review 4, finding 7: refuse before ever issuing the probe request --
        # a fail-open path here would let a founder watchlist entry (or any future
        # seed) reach a host the committed registry has never authorized for
        # automated read.
        _assert_kind_host_allowed(candidate.kind)

        if cid in progress:
            record = progress[cid]
            counts[record["classification"]] = counts.get(record["classification"], 0) + 1
            if record["classification"] == "blocked":
                blocked.append(cid)
            if record.get("registered") and record.get("entry"):
                registered.append(RegistryEntryDraft(**record["entry"]))
            continue

        if max_new_requests is not None and processed_this_run >= max_new_requests:
            break

        min_interval = DEFAULT_MIN_INTERVAL_S.get(candidate.kind, 0.5)
        wait = rate_limiter.acquire(candidate.kind, min_interval)
        if wait > 0 and isinstance(transport, HttpTransport):
            time.sleep(wait)

        request = DiscoveryRequest(source_id=cid, url=candidate.url, method="GET", timeout_s=20.0)
        response: TransportResponse = transport.fetch(request)
        classification, detail, postings = classify_status(response.status_code, response.body, candidate.kind)
        counts[classification] = counts.get(classification, 0) + 1
        processed_this_run += 1

        entry_draft: RegistryEntryDraft | None = None
        if classification == "blocked":
            blocked.append(cid)
        if classification == "live":
            matches = relevant_postings(postings, classifier, now)
            if matches:
                entry_draft = build_registry_entry(candidate, len(postings), len(matches), response.latency_ms)
                registered.append(entry_draft)

        progress[cid] = {
            "classification": classification,
            "detail": detail,
            "registered": entry_draft is not None,
            "entry": asdict(entry_draft) if entry_draft else None,
        }
        save_progress(progress_path, progress)

    wall_clock_s = time.monotonic() - started
    return SweepResult(
        total_candidates=len(candidates),
        counts=counts,
        registered=registered,
        blocked_ids=blocked,
        seeds_used=list(seeds_used),
        classifier_label=classifier_label,
        wall_clock_s=wall_clock_s,
        processed_this_run=processed_this_run,
    )
