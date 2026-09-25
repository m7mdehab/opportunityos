"""Bounded, read-only checks for persisted Founder feed projections."""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, cast, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from matching.title_family import normalize_title
from storage.feed_projection import FeedProjectionRecord, projection_identity
from storage.feed_projection_service import _target_tier_for_family
from storage.models import MatchEvaluationRecord, OpportunityRecord

MAX_VERIFICATION_PAGE_SIZE = 100
_TARGET_TIER_VALUES = frozenset({"primary", "adjacent", "stretch", "outside_targets"})
_SCORE_FIELDS = ("fit_score", "preference_score", "confidence_score")


@dataclass(frozen=True, slots=True)
class ProjectionInvariantPage:
    """Sanitized summary of one scan page.

    ``next_cursor`` is available to the in-process caller for keyset
    continuation but is excluded from repr and safe serialization. The
    serialized cursor fingerprint cannot be used to recover an opportunity ID.
    """

    scanned: int
    next_cursor: str | None = field(repr=False)
    has_more: bool
    issue_counts: tuple[tuple[str, int], ...]
    issue_tokens: tuple[str, ...]
    issue_tokens_truncated: bool

    def to_safe_dict(self) -> dict[str, Any]:
        cursor_fingerprint = (
            hashlib.sha256(self.next_cursor.encode("utf-8")).hexdigest()[:16]
            if self.next_cursor is not None
            else None
        )
        return {
            "scanned": self.scanned,
            "cursor_fingerprint": cursor_fingerprint,
            "has_more": self.has_more,
            "issue_counts": dict(self.issue_counts),
            "issue_tokens": list(self.issue_tokens),
            "issue_tokens_truncated": self.issue_tokens_truncated,
        }


def _score_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        numeric = float(value)
    except OverflowError:
        return None
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 100.0:
        return None
    return numeric


def _scores_equal(left: Any, right: Any) -> bool:
    left_score = _score_value(left)
    right_score = _score_value(right)
    if left is None or right is None:
        return left is None and right is None
    if left_score is None or right_score is None:
        return False
    return math.isclose(left_score, right_score, rel_tol=0.0, abs_tol=1e-9)


def _detail_score_expressions(session: Session) -> tuple[Any, Any, Any, Any]:
    """Select only the two numeric JSON members, never the evaluation rationale blob."""
    detail = MatchEvaluationRecord.evaluation_detail_json
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        return (
            func.json_type(detail, "$.preference_score"),
            func.json_extract(detail, "$.preference_score"),
            func.json_type(detail, "$.confidence_score"),
            func.json_extract(detail, "$.confidence_score"),
        )
    if dialect == "postgresql":
        parsed = cast(detail, JSONB)
        preference = parsed["preference_score"]
        confidence = parsed["confidence_score"]
        return (
            func.jsonb_typeof(preference),
            preference.astext,
            func.jsonb_typeof(confidence),
            confidence.astext,
        )
    raise NotImplementedError(f"projection verification does not support {dialect!r}")


def _detail_score(value_type: Any, value: Any) -> float | None:
    """Convert a database-extracted JSON number; JSON strings and booleans stay invalid."""
    if value_type not in {"number", "integer", "real"}:
        return None
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return _score_value(numeric)


def _issue_codes(row: Any, *, truth_graph: Any) -> tuple[str, ...]:
    issues: list[str] = []
    source_title = row.source_title

    if row.projection_id != projection_identity(row.opportunity_id, row.truth_pack_hash):
        issues.append("projection_identity")
    if row.source_content_hash is None:
        issues.append("opportunity_missing")
    elif row.projection_content_hash != row.source_content_hash:
        issues.append("content_hash_mismatch")
    if source_title is not None and row.projection_title != source_title:
        issues.append("title_mismatch")
    if row.source_organization is not None and row.projection_organization != row.source_organization:
        issues.append("organization_mismatch")
    if row.projection_version not in {"v1", "v2"}:
        issues.append("unknown_projection_version")

    for field_name in _SCORE_FIELDS:
        if getattr(row, field_name) is not None and _score_value(getattr(row, field_name)) is None:
            issues.append(f"invalid_{field_name}")

    if row.target_tier is not None and row.target_tier not in _TARGET_TIER_VALUES:
        issues.append("invalid_target_tier")

    evaluation_exists = row.evaluation_id is not None
    if not evaluation_exists:
        if any(getattr(row, name) is not None for name in (
            "qualification_decision", "fit_score", "preference_score",
            "confidence_score", "priority_score",
        )):
            issues.append("scores_without_evaluation")
    else:
        if row.evaluation_truth_pack_hash != row.truth_pack_hash:
            issues.append("evaluation_truth_pack_mismatch")
        if row.qualification_decision != row.evaluation_decision:
            issues.append("decision_mismatch")
        if not _scores_equal(row.fit_score, row.evaluation_fit_score):
            issues.append("fit_score_mismatch")
        if row.evaluated_at != row.evaluation_evaluated_at:
            issues.append("evaluation_time_mismatch")
        if row.priority_score is None:
            issues.append("priority_missing")

    if row.projection_version == "v2" and source_title is not None:
        expected_family, expected_level, _rule = normalize_title(source_title)
        if row.title_family != expected_family:
            issues.append("title_family_mismatch")
        if row.title_level != expected_level:
            issues.append("title_level_mismatch")

        if evaluation_exists:
            for field_name in ("preference_score", "confidence_score"):
                expected = _detail_score(
                    getattr(row, f"evaluation_{field_name}_json_type"),
                    getattr(row, f"evaluation_{field_name}_json_value"),
                )
                if expected != getattr(row, field_name) and not _scores_equal(
                    expected, getattr(row, field_name)
                ):
                    issues.append(f"{field_name}_mismatch")

        if truth_graph is not None:
            expected_tier = _target_tier_for_family(expected_family, truth_graph)
            if row.target_tier != expected_tier:
                issues.append("target_tier_mismatch")

    return tuple(issues)


def verify_feed_projection_page(
    session: Session,
    *,
    truth_pack_hash: str,
    start_after: str | None = None,
    page_size: int = MAX_VERIFICATION_PAGE_SIZE,
    truth_graph: Any = None,
    max_issue_tokens: int = 50,
) -> ProjectionInvariantPage:
    """Inspect one bounded projection page without hydrating job descriptions or writing rows."""
    if not isinstance(truth_pack_hash, str) or not truth_pack_hash or truth_pack_hash == "active":
        raise ValueError("an authoritative truth_pack_hash is required")
    if type(page_size) is not int:
        raise TypeError("page_size must be an integer")
    if not 1 <= page_size <= MAX_VERIFICATION_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_VERIFICATION_PAGE_SIZE}")
    if start_after is not None:
        if not isinstance(start_after, str):
            raise TypeError("start_after must be a string or None")
        if not start_after or start_after != start_after.strip() or len(start_after) > 160:
            raise ValueError("start_after must be a non-empty projection identity")
    if type(max_issue_tokens) is not int or max_issue_tokens < 0:
        raise ValueError("max_issue_tokens must be a non-negative integer")

    preference_type, preference_value, confidence_type, confidence_value = _detail_score_expressions(session)
    query = session.query(
        FeedProjectionRecord.id.label("projection_id"),
        FeedProjectionRecord.opportunity_id.label("opportunity_id"),
        FeedProjectionRecord.opportunity_content_hash.label("projection_content_hash"),
        FeedProjectionRecord.truth_pack_hash.label("truth_pack_hash"),
        FeedProjectionRecord.projection_version.label("projection_version"),
        FeedProjectionRecord.title.label("projection_title"),
        FeedProjectionRecord.organization.label("projection_organization"),
        FeedProjectionRecord.title_family.label("title_family"),
        FeedProjectionRecord.title_level.label("title_level"),
        FeedProjectionRecord.target_tier.label("target_tier"),
        FeedProjectionRecord.qualification_decision.label("qualification_decision"),
        FeedProjectionRecord.fit_score.label("fit_score"),
        FeedProjectionRecord.preference_score.label("preference_score"),
        FeedProjectionRecord.confidence_score.label("confidence_score"),
        FeedProjectionRecord.priority_score.label("priority_score"),
        FeedProjectionRecord.evaluated_at.label("evaluated_at"),
        OpportunityRecord.title.label("source_title"),
        OpportunityRecord.organization.label("source_organization"),
        OpportunityRecord.content_hash.label("source_content_hash"),
        MatchEvaluationRecord.id.label("evaluation_id"),
        MatchEvaluationRecord.truth_pack_hash.label("evaluation_truth_pack_hash"),
        MatchEvaluationRecord.qualification_decision.label("evaluation_decision"),
        MatchEvaluationRecord.fit_score.label("evaluation_fit_score"),
        preference_type.label("evaluation_preference_score_json_type"),
        preference_value.label("evaluation_preference_score_json_value"),
        confidence_type.label("evaluation_confidence_score_json_type"),
        confidence_value.label("evaluation_confidence_score_json_value"),
        MatchEvaluationRecord.evaluated_at.label("evaluation_evaluated_at"),
    ).outerjoin(
        OpportunityRecord,
        OpportunityRecord.id == FeedProjectionRecord.opportunity_id,
    ).outerjoin(
        MatchEvaluationRecord,
        and_(
            MatchEvaluationRecord.opportunity_id == FeedProjectionRecord.opportunity_id,
            MatchEvaluationRecord.truth_pack_hash == FeedProjectionRecord.truth_pack_hash,
        ),
    ).filter(FeedProjectionRecord.truth_pack_hash == truth_pack_hash)
    if start_after is not None:
        query = query.filter(FeedProjectionRecord.id > start_after)
    rows = query.order_by(FeedProjectionRecord.id.asc()).limit(page_size + 1).all()

    selected = rows[:page_size]
    issue_counts: Counter[str] = Counter()
    issue_tokens: list[str] = []
    for row in selected:
        for code in _issue_codes(row, truth_graph=truth_graph):
            issue_counts[code] += 1
            if len(issue_tokens) < max_issue_tokens:
                token_source = row.opportunity_id or row.projection_id
                token = hashlib.sha256(f"{token_source}\0{code}".encode("utf-8")).hexdigest()[:16]
                issue_tokens.append(token)

    next_cursor = selected[-1].projection_id if selected else start_after
    return ProjectionInvariantPage(
        scanned=len(selected),
        next_cursor=next_cursor,
        has_more=len(rows) > page_size,
        issue_counts=tuple(sorted(issue_counts.items())),
        issue_tokens=tuple(issue_tokens),
        issue_tokens_truncated=sum(issue_counts.values()) > len(issue_tokens),
    )
