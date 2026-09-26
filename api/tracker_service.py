"""Focused Founder review-state operations over the accepted W23 schema."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, load_only

from outbound.models import ActionStatus
from api.serialization import top_reasons_from_list, unpack_reasons, unpack_remote_scope_regions
from storage.feed_projection import FeedProjectionRecord
from storage.models import (
    FounderActivityEventRecord,
    FounderTriageStateRecord,
    OpportunityRecord,
    OutboundActionRecordModel,
)

TrackerAction = Literal["save", "mark_applied", "reject", "dismiss", "snooze", "set_stage"]
TrackerBucket = Literal["saved", "applied", "rejected", "all"]

BUCKET_STATES: dict[str, tuple[str, ...]] = {
    "saved": ("saved",),
    "applied": ("applied", "submitted"),
    "rejected": ("rejected_by_founder", "dismissed"),
}
BUCKET_STATES["all"] = tuple(dict.fromkeys(
    (*BUCKET_STATES["saved"], *BUCKET_STATES["applied"], *BUCKET_STATES["rejected"])
))

ACTION_TARGET = {
    "save": "saved",
    "mark_applied": "applied",
    "reject": "rejected_by_founder",
    "dismiss": "dismissed",
    "snooze": "snoozed",
}


class TrackerTransitionError(ValueError):
    pass


@dataclass(frozen=True)
class TransitionResult:
    opportunity_id: str
    state: str
    previous_state: str
    changed: bool
    event_id: str | None


@dataclass(frozen=True)
class RestoreResult:
    opportunity_id: str
    state: str
    changed: bool
    event_id: str | None


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _event_id(opportunity_id: str, request_key: str | None, action: str, now: datetime) -> str:
    seed = (
        f"{opportunity_id}:{request_key}"
        if request_key
        else f"{opportunity_id}:{action}:{now.isoformat()}"
    )
    return "activity-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:55]


def _allowed(previous: str, target: str) -> bool:
    if target == "saved":
        return previous in {"to_review", "saved", "snoozed"}
    if target == "applied":
        return previous in {"to_review", "saved", "applied", "submitted", "snoozed", "dismissed"}
    if target == "rejected_by_founder":
        return previous in {"to_review", "saved", "snoozed", "rejected_by_founder", "dismissed"}
    if target == "dismissed":
        return True
    if target == "snoozed":
        return previous in {"to_review", "snoozed", "dismissed"}
    return False


def transition_tracker_state(
    session: Session,
    opportunity_id: str,
    action: TrackerAction,
    now: datetime,
    *,
    snoozed_until: datetime | None = None,
    request_key: str | None = None,
    target_stage: str | None = None,
) -> TransitionResult:
    if action == "set_stage" or target_stage is not None:
        raise TrackerTransitionError("application pipeline stages are deferred from this release")
    if action not in ACTION_TARGET:
        raise TrackerTransitionError("unknown tracker action")
    if session.query(OpportunityRecord.id).filter_by(id=opportunity_id).first() is None:
        raise TrackerTransitionError("opportunity not found")
    if request_key and len(request_key) > 128:
        raise TrackerTransitionError("idempotency key is too long")

    target = ACTION_TARGET[action]
    event_id = _event_id(opportunity_id, request_key, action, now)
    if request_key:
        replay = session.get(FounderActivityEventRecord, event_id)
        if replay is not None:
            if replay.opportunity_id != opportunity_id or replay.action_type != action:
                raise TrackerTransitionError("idempotency key was already used for another action")
            triage = session.get(FounderTriageStateRecord, opportunity_id)
            state = triage.state if triage is not None else (replay.resulting_state or "to_review")
            return TransitionResult(opportunity_id, state, state, False, replay.id)

    timestamp = _naive_utc(now)
    triage = session.get(FounderTriageStateRecord, opportunity_id)
    previous = triage.state if triage is not None else "to_review"
    if previous == target:
        if target == "snoozed" and triage is not None:
            triage.snoozed_until = _naive_utc(snoozed_until) if snoozed_until else None
            triage.updated_at = timestamp
        return TransitionResult(opportunity_id, target, previous, False, None)
    if not _allowed(previous, target):
        raise TrackerTransitionError(f"cannot transition from {previous} to {target}")

    if triage is None:
        triage = FounderTriageStateRecord(
            opportunity_id=opportunity_id,
            state=target,
            snoozed_until=_naive_utc(snoozed_until) if target == "snoozed" and snoozed_until else None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(triage)
    else:
        triage.state = target
        triage.snoozed_until = _naive_utc(snoozed_until) if target == "snoozed" and snoozed_until else None
        triage.updated_at = timestamp

    event = FounderActivityEventRecord(
        id=event_id,
        opportunity_id=opportunity_id,
        action_type=action,
        resulting_state=target,
        snoozed_until=triage.snoozed_until,
        created_at=timestamp,
    )
    session.add(event)
    session.flush()
    return TransitionResult(opportunity_id, target, previous, True, event.id)


def restore_tracker_transition(
    session: Session,
    opportunity_id: str,
    event_id: str,
    now: datetime,
    *,
    request_key: str,
) -> RestoreResult:
    if not request_key or len(request_key) > 128:
        raise TrackerTransitionError("idempotency key is required and must be at most 128 characters")

    original = session.get(FounderActivityEventRecord, event_id)
    if original is None or original.opportunity_id != opportunity_id:
        raise TrackerTransitionError("tracker event not found")
    if original.action_type not in {"save", "mark_applied", "reject"}:
        raise TrackerTransitionError("this tracker action cannot be undone")

    latest = (
        session.query(FounderActivityEventRecord)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(FounderActivityEventRecord.created_at.desc(), FounderActivityEventRecord.id.desc())
        .first()
    )
    if latest is None or latest.id != original.id:
        raise TrackerTransitionError("tracker action is no longer the latest activity")

    triage = session.get(FounderTriageStateRecord, opportunity_id)
    if triage is None or triage.state != original.resulting_state:
        raise TrackerTransitionError("current tracker state no longer matches this action")

    previous = (
        session.query(FounderActivityEventRecord)
        .filter(
            FounderActivityEventRecord.opportunity_id == opportunity_id,
            or_before(FounderActivityEventRecord, original),
        )
        .order_by(FounderActivityEventRecord.created_at.desc(), FounderActivityEventRecord.id.desc())
        .first()
    )
    previous_state = previous.resulting_state if previous and previous.resulting_state else "to_review"
    timestamp = _naive_utc(now)

    if previous_state == "to_review":
        session.delete(triage)
    else:
        triage.state = previous_state
        triage.snoozed_until = previous.snoozed_until if previous_state == "snoozed" and previous else None
        triage.updated_at = timestamp

    if original.action_type == "mark_applied":
        attestation = (
            session.query(OutboundActionRecordModel)
            .filter_by(
                opportunity_id=opportunity_id,
                adapter_name="founder_attested",
                action_status=ActionStatus.SUBMITTED.value,
            )
            .order_by(OutboundActionRecordModel.created_at.desc())
            .first()
        )
        if attestation is not None:
            attestation.action_status = ActionStatus.UNDONE.value
            attestation.updated_at = timestamp

    restore_id = _event_id(opportunity_id, request_key, "restore", now)
    replay = session.get(FounderActivityEventRecord, restore_id)
    if replay is None:
        session.add(FounderActivityEventRecord(
            id=restore_id,
            opportunity_id=opportunity_id,
            action_type="restore",
            resulting_state=None if previous_state == "to_review" else previous_state,
            snoozed_until=None,
            created_at=timestamp,
        ))
        session.flush()
    return RestoreResult(opportunity_id, previous_state, replay is None, restore_id)


def or_before(model, event: FounderActivityEventRecord):
    return (
        (model.created_at < event.created_at)
        | ((model.created_at == event.created_at) & (model.id < event.id))
    )


def list_tracker_items(
    session: Session,
    bucket: TrackerBucket,
    *,
    truth_pack_hash: str | None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    if bucket not in BUCKET_STATES:
        raise ValueError("unknown tracker bucket")
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, 100))
    states = BUCKET_STATES[bucket]
    base = session.query(FounderTriageStateRecord).filter(FounderTriageStateRecord.state.in_(states))
    total = base.with_entities(func.count(FounderTriageStateRecord.opportunity_id)).scalar() or 0

    join_condition = FeedProjectionRecord.opportunity_id == OpportunityRecord.id
    if truth_pack_hash:
        join_condition = and_(join_condition, FeedProjectionRecord.truth_pack_hash == truth_pack_hash)
    rows = (
        session.query(FounderTriageStateRecord, OpportunityRecord, FeedProjectionRecord)
        .join(OpportunityRecord, OpportunityRecord.id == FounderTriageStateRecord.opportunity_id)
        .outerjoin(FeedProjectionRecord, join_condition)
        .filter(FounderTriageStateRecord.state.in_(states))
        .options(load_only(
            OpportunityRecord.id, OpportunityRecord.track, OpportunityRecord.title,
            OpportunityRecord.organization, OpportunityRecord.source_id, OpportunityRecord.source_url,
            OpportunityRecord.deadline, OpportunityRecord.posted_date, OpportunityRecord.is_stale,
            OpportunityRecord.work_mode, OpportunityRecord.work_mode_source,
            OpportunityRecord.location_country, OpportunityRecord.location_city,
            OpportunityRecord.location_region, OpportunityRecord.remote_scope,
            OpportunityRecord.remote_scope_regions, OpportunityRecord.employment_type,
            OpportunityRecord.seniority_level, OpportunityRecord.compensation_min,
            OpportunityRecord.compensation_max, OpportunityRecord.compensation_currency,
            OpportunityRecord.compensation_period, OpportunityRecord.title_family,
            OpportunityRecord.title_level, OpportunityRecord.family_key,
        ))
        .order_by(FounderTriageStateRecord.updated_at.desc(), OpportunityRecord.id.asc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )

    items = []
    for triage, opportunity, projection in rows:
        reasons = unpack_reasons(projection.reasons_json) if projection is not None else []
        items.append({
            "id": opportunity.id,
            "title": opportunity.title,
            "organization": opportunity.organization,
            "source_id": opportunity.source_id,
            "source_url": opportunity.source_url,
            "track": opportunity.track,
            "decision": projection.qualification_decision if projection is not None else None,
            "fit_score": projection.fit_score if projection is not None else None,
            "top_reasons": top_reasons_from_list(reasons),
            "deadline": opportunity.deadline,
            "posted_date": opportunity.posted_date,
            "is_stale": bool(opportunity.is_stale),
            "action_state": "submitted" if triage.state == "applied" else triage.state,
            "tracker_state": triage.state,
            "feedback_label": None,
            "hidden_by": [],
            "flagged_by": [],
            "work_mode": opportunity.work_mode,
            "work_mode_source": opportunity.work_mode_source,
            "location_country": opportunity.location_country,
            "location_city": opportunity.location_city,
            "location_region": opportunity.location_region,
            "remote_scope": opportunity.remote_scope,
            "remote_scope_regions": unpack_remote_scope_regions(opportunity.remote_scope_regions),
            "employment_type": opportunity.employment_type,
            "seniority_level": opportunity.seniority_level,
            "compensation_min": opportunity.compensation_min,
            "compensation_max": opportunity.compensation_max,
            "compensation_currency": opportunity.compensation_currency,
            "compensation_period": opportunity.compensation_period,
            "title_family": opportunity.title_family,
            "title_level": opportunity.title_level,
            "family_key": opportunity.family_key,
            "family_size": None,
        })
    return {
        "bucket": bucket,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "items": items,
    }
