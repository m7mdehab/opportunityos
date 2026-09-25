"""Small SQL-backed operations for the FR-008 Founder tracker."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, load_only
from outbound.models import ActionStatus

from api.serialization import (
    top_reasons_from_list,
    unpack_reasons,
    unpack_remote_scope_regions,
)
from storage.feed_projection import FeedProjectionRecord
from storage.models import (
    FounderActivityEventRecord,
    FounderTriageStateRecord,
    OutboundActionRecordModel,
    OpportunityRecord,
)

TrackerAction = Literal["save", "mark_applied", "reject", "dismiss", "snooze", "set_stage"]
TrackerBucket = Literal["saved", "applied", "rejected", "all"]

APPLICATION_STAGES = (
    "applied",
    "recruiter_screen",
    "assessment",
    "interviewing",
    "final_interview",
    "offer",
    "accepted",
)
ACTIVE_APPLICATION_STAGES = APPLICATION_STAGES[:-1]
APPLICATION_STAGE_ORDER = {state: index for index, state in enumerate(APPLICATION_STAGES)}
APPLICATION_TERMINAL_OUTCOMES = frozenset({
    "rejected_by_employer",
    "withdrawn",
    "no_response",
})
APPLICATION_STAGE_TARGETS = frozenset((*APPLICATION_STAGES, *APPLICATION_TERMINAL_OUTCOMES))

BUCKET_STATES: dict[str, tuple[str, ...]] = {
    "saved": ("saved",),
    "applied": (
        "applied", "recruiter_screen", "assessment", "interviewing",
        "final_interview", "offer", "accepted",
    ),
    "rejected": (
        "rejected_by_founder", "rejected_by_employer", "withdrawn",
        "no_response", "position_closed", "archived", "dismissed",
    ),
}
BUCKET_STATES["all"] = tuple(dict.fromkeys(
    (*BUCKET_STATES["saved"], *BUCKET_STATES["applied"], *BUCKET_STATES["rejected"])
))

ACTION_TARGET: dict[str, str] = {
    "save": "saved",
    "mark_applied": "applied",
    "reject": "rejected_by_founder",
    "dismiss": "dismissed",
    "snooze": "snoozed",
}


class TrackerTransitionError(ValueError):
    """Requested basic triage action is invalid from the current state."""


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


def _event_key(opportunity_id: str, request_key: str | None) -> str | None:
    if not request_key:
        return None
    if len(request_key) > 128:
        raise TrackerTransitionError("idempotency key is too long")
    digest = hashlib.sha256(f"{opportunity_id}:{request_key}".encode()).hexdigest()
    return f"tracker:{digest}"


def _allowed(previous: str, target: str, *, application_stage: bool = False) -> bool:
    if application_stage:
        if target in APPLICATION_STAGE_ORDER:
            previous_order = APPLICATION_STAGE_ORDER.get(previous)
            return previous_order is not None and APPLICATION_STAGE_ORDER[target] > previous_order
        if target in APPLICATION_TERMINAL_OUTCOMES:
            return previous in ACTIVE_APPLICATION_STAGES
        return False
    if target == "saved":
        return previous in {"to_review", "saved", "snoozed"}
    if target == "applied":
        return previous in {"to_review", "saved", "applied", "snoozed", "dismissed"}
    if target == "rejected_by_founder":
        return previous in {"to_review", "saved", "snoozed", "rejected_by_founder", "dismissed"}
    if target == "dismissed":
        # Legacy compatibility action; canonical Founder rejection uses
        # `rejected_by_founder` above.
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
    """Write a current state and exactly one event for each real transition.

    The caller owns the transaction so the current state, event, and any
    related founder-attested action commit together.
    """
    if action not in {*ACTION_TARGET, "set_stage"}:
        raise TrackerTransitionError("unknown tracker action")
    if action == "set_stage":
        if target_stage not in APPLICATION_STAGE_TARGETS:
            raise TrackerTransitionError("invalid application stage")
        target = target_stage
    else:
        if target_stage is not None:
            raise TrackerTransitionError("stage is only valid for set_stage")
        target = ACTION_TARGET[action]
    if session.query(OpportunityRecord.id).filter_by(id=opportunity_id).first() is None:
        raise TrackerTransitionError("opportunity not found")

    idempotency_key = _event_key(opportunity_id, request_key)
    if idempotency_key:
        previous_event = (
            session.query(FounderActivityEventRecord)
            .filter_by(idempotency_key=idempotency_key)
            .first()
        )
        if previous_event is not None:
            if previous_event.opportunity_id != opportunity_id or previous_event.to_state != target:
                raise TrackerTransitionError("idempotency key was already used for another action")
            current_triage = session.get(FounderTriageStateRecord, opportunity_id)
            return TransitionResult(
                opportunity_id=opportunity_id,
                state=current_triage.state if current_triage is not None else (previous_event.to_state or target),
                previous_state=previous_event.from_state or "to_review",
                changed=False,
                event_id=previous_event.id,
            )

    triage = session.get(FounderTriageStateRecord, opportunity_id)
    previous_state = triage.state if triage is not None else "to_review"
    if previous_state == target:
        if target == "snoozed" and triage is not None:
            triage.snoozed_until = snoozed_until
            triage.updated_at = now
        return TransitionResult(opportunity_id, target, previous_state, False, None)
    if not _allowed(previous_state, target, application_stage=action == "set_stage"):
        raise TrackerTransitionError(f"cannot transition from {previous_state} to {target}")

    previous_snapshot = {
        "snoozed_until": triage.snoozed_until.isoformat() if triage and triage.snoozed_until else None,
        "saved_at": triage.saved_at.isoformat() if triage and triage.saved_at else None,
        "applied_at": triage.applied_at.isoformat() if triage and triage.applied_at else None,
        "closed_at": triage.closed_at.isoformat() if triage and triage.closed_at else None,
    }

    if triage is None:
        triage = FounderTriageStateRecord(
            opportunity_id=opportunity_id,
            state=target,
            snoozed_until=snoozed_until if target == "snoozed" else None,
            created_at=now,
            updated_at=now,
        )
        session.add(triage)
    else:
        triage.state = target
        triage.snoozed_until = snoozed_until if target == "snoozed" else None
        triage.updated_at = now

    if target == "saved":
        triage.saved_at = now
        triage.closed_at = None
    elif target == "applied":
        triage.applied_at = now
        triage.closed_at = None
    elif target in {
        "rejected_by_founder", "dismissed", "accepted",
        *APPLICATION_TERMINAL_OUTCOMES,
    }:
        triage.closed_at = now

    event = FounderActivityEventRecord(
        id=f"tracker-event-{uuid.uuid4().hex}",
        opportunity_id=opportunity_id,
        action_type="application_stage_updated" if action == "set_stage" else target,
        from_state=previous_state,
        to_state=target,
        event_at=now,
        metadata_json=json.dumps(
            {
                "source": "founder_action",
                "previous_tracker_fields": previous_snapshot,
            },
            separators=(",", ":"),
        ),
        idempotency_key=idempotency_key,
        created_at=now,
    )
    session.add(event)
    session.flush()
    return TransitionResult(opportunity_id, target, previous_state, True, event.id)


def restore_tracker_transition(
    session: Session,
    opportunity_id: str,
    event_id: str,
    now: datetime,
    *,
    request_key: str,
) -> RestoreResult:
    """Restore one latest save/apply/reject transition and append its audit event."""
    if not event_id or len(event_id) > 64:
        raise TrackerTransitionError("invalid event id")
    idempotency_key = _event_key(opportunity_id, request_key)
    if idempotency_key is None:
        raise TrackerTransitionError("idempotency key is required")

    previous_restore = (
        session.query(FounderActivityEventRecord)
        .filter_by(idempotency_key=idempotency_key)
        .first()
    )
    if previous_restore is not None:
        try:
            metadata = json.loads(previous_restore.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        if (
            previous_restore.opportunity_id != opportunity_id
            or previous_restore.action_type != "tracker_restored"
            or metadata.get("restored_event_id") != event_id
        ):
            raise TrackerTransitionError("idempotency key was already used for another action")
        return RestoreResult(
            opportunity_id=opportunity_id,
            state=previous_restore.to_state or "to_review",
            changed=False,
            event_id=previous_restore.id,
        )

    original = session.get(FounderActivityEventRecord, event_id)
    if original is None or original.opportunity_id != opportunity_id:
        raise TrackerTransitionError("tracker event not found")
    if original.action_type not in {"saved", "applied", "rejected_by_founder"}:
        raise TrackerTransitionError("this tracker action cannot be undone")
    if not original.from_state or not original.to_state:
        raise TrackerTransitionError("tracker event has no restorable state")

    latest = (
        session.query(FounderActivityEventRecord)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(
            FounderActivityEventRecord.event_at.desc(),
            FounderActivityEventRecord.created_at.desc(),
            FounderActivityEventRecord.id.desc(),
        )
        .first()
    )
    if latest is None or latest.id != original.id:
        raise TrackerTransitionError("tracker action is no longer the latest activity")

    triage = session.get(FounderTriageStateRecord, opportunity_id)
    if triage is None or triage.state != original.to_state:
        raise TrackerTransitionError("current tracker state no longer matches this action")

    try:
        metadata = json.loads(original.metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    snapshot = metadata.get("previous_tracker_fields")
    if not isinstance(snapshot, dict):
        snapshot = {}

    def snapshot_datetime(name: str) -> datetime | None:
        value = snapshot.get(name)
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed

    triage.state = original.from_state
    triage.snoozed_until = snapshot_datetime("snoozed_until") if original.from_state == "snoozed" else None
    triage.saved_at = snapshot_datetime("saved_at")
    triage.applied_at = snapshot_datetime("applied_at")
    triage.closed_at = snapshot_datetime("closed_at")
    triage.updated_at = now

    if original.action_type == "applied":
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
            attestation.updated_at = now

    restore_event = FounderActivityEventRecord(
        id=f"tracker-event-{uuid.uuid4().hex}",
        opportunity_id=opportunity_id,
        action_type="tracker_restored",
        from_state=original.to_state,
        to_state=original.from_state,
        event_at=now,
        metadata_json=json.dumps(
            {"source": "founder_undo", "restored_event_id": original.id},
            separators=(",", ":"),
        ),
        idempotency_key=idempotency_key,
        created_at=now,
    )
    session.add(restore_event)
    session.flush()
    return RestoreResult(opportunity_id, original.from_state, True, restore_event.id)


def list_tracker_items(
    session: Session,
    bucket: TrackerBucket,
    *,
    truth_pack_hash: str | None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Return a bounded tracker page using SQL state filtering and pagination."""
    if bucket not in {"saved", "applied", "rejected", "all"}:
        raise ValueError("unknown tracker bucket")
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, 100))
    states = BUCKET_STATES[bucket]
    base = session.query(FounderTriageStateRecord).filter(
        FounderTriageStateRecord.state.in_(states)
    )
    total = base.with_entities(func.count(FounderTriageStateRecord.opportunity_id)).scalar() or 0

    projection_join = and_(
        FeedProjectionRecord.opportunity_id == OpportunityRecord.id,
        FeedProjectionRecord.truth_pack_hash == truth_pack_hash,
    )
    rows = (
        session.query(FounderTriageStateRecord, OpportunityRecord, FeedProjectionRecord)
        .join(OpportunityRecord, OpportunityRecord.id == FounderTriageStateRecord.opportunity_id)
        .filter(FounderTriageStateRecord.state.in_(states))
        .outerjoin(FeedProjectionRecord, projection_join)
        .options(load_only(
            OpportunityRecord.id,
            OpportunityRecord.track,
            OpportunityRecord.title,
            OpportunityRecord.organization,
            OpportunityRecord.source_id,
            OpportunityRecord.source_url,
            OpportunityRecord.deadline,
            OpportunityRecord.posted_date,
            OpportunityRecord.is_stale,
            OpportunityRecord.work_mode,
            OpportunityRecord.work_mode_source,
            OpportunityRecord.location_country,
            OpportunityRecord.location_city,
            OpportunityRecord.location_region,
            OpportunityRecord.remote_scope,
            OpportunityRecord.remote_scope_regions,
            OpportunityRecord.employment_type,
            OpportunityRecord.seniority_level,
            OpportunityRecord.compensation_min,
            OpportunityRecord.compensation_max,
            OpportunityRecord.compensation_currency,
            OpportunityRecord.compensation_period,
            OpportunityRecord.title_family,
            OpportunityRecord.title_level,
            OpportunityRecord.family_key,
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
