"""Test-only seeding script for the D7 phase 2 real-stack Playwright run.

Populates the real PostgreSQL database (`OPPORTUNITYOS_DB_URL`) with the
same synthetic opportunities the mock layer serves
(`web/lib/mock/fixtures.ts::buildDefaultOpportunities`), so
`web/tests/e2e/smoke.spec.ts` passes unmodified whether it is run against
the MSW mock (phase 1, `playwright.config.ts`) or the real FastAPI service
(phase 2, `playwright.real.config.ts`).

Every organisation name is suffixed "(synthetic)", every source id is
`src-*`, and no real person, employer, or contact detail appears anywhere
in this file -- this is fixture data for a local, disposable test database,
never `private/`.

Idempotent: running this script twice leaves the same rows, not
duplicates. It always deletes its own seed rows (by a fixed, known id set)
before re-inserting them in one transaction, rather than checking for
existence row by row.

Not part of the application; imported by nothing except the Playwright
real-stack config's `webServer` command, which runs it once before
`uvicorn` starts.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from storage.engine import get_engine, get_session_factory  # noqa: E402
from storage.models import (  # noqa: E402
    FieldProvenanceRecord,
    FounderFeedbackRecord,
    FounderTriageStateRecord,
    MatchEvaluationRecord,
    OpportunityRecord,
    OutboundActionRecordModel,
    SourcePollRunRecord,
)

POLICY_VERSION = "policy-2026.3-synthetic"


def _checksum(*parts: str) -> str:
    return "sha256:" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


@dataclass
class Constraint:
    name: str
    passed: bool | None  # True=PASS, False=FAIL, None=UNKNOWN
    reason: str
    required_field: str | None = None
    founder_fact: str | None = None
    is_hard_failure: bool = False
    provenance_pointer: str | None = None

    def __post_init__(self) -> None:
        if self.is_hard_failure is False and self.passed is False:
            self.is_hard_failure = True


@dataclass
class Dimension:
    name: str
    score: float
    weight: float
    rationale: str

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class Field:
    field_name: str
    raw_value: str | None
    normalized_value: str | None
    derivation_type: str
    raw_pointer: str | None
    rule_id: str | None = None


@dataclass
class SeedOpportunity:
    id: str
    title: str
    organization: str
    source_id: str
    source_url: str
    track: str
    decision: str | None  # "qualified" | "ineligible" | "uncertain" | None
    fit_score: float | None
    deadline: str | None
    posted_date: str | None
    is_stale: bool
    description: str
    fields: list[Field] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    dimensions: list[Dimension] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    uncertainty_penalty: float = 0.0
    explanation: str = ""
    action_state: str | None = None  # "dismissed" | "snoozed" | "submitted"
    feedback_label: str | None = None


def _default_opportunities(now: datetime) -> list[SeedOpportunity]:
    today = now.date().isoformat()

    return [
        SeedOpportunity(
            id="opp-001",
            title="Senior Localization Program Manager",
            organization="Northwind Regional Cooperative (synthetic)",
            source_id="src-jobboard-alpha",
            source_url="https://jobs.example.org/postings/opp-001",
            track="employment",
            decision="qualified",
            fit_score=88.0,
            deadline=(now + timedelta(days=18)).date().isoformat(),
            posted_date=(now - timedelta(days=4)).date().isoformat(),
            is_stale=False,
            description=(
                "Synthetic posting: lead a distributed localization program "
                "across four MENA markets."
            ),
            fields=[
                Field(
                    "title",
                    "Sr. Localization Program Manager",
                    "Senior Localization Program Manager",
                    "normalized",
                    "listing.title",
                    "title-normalize-v1",
                ),
                Field(
                    "deadline",
                    "Sep 20, 2026",
                    (now + timedelta(days=18)).date().isoformat(),
                    "parsed_date",
                    "listing.close_date",
                    "date-parse-v2",
                ),
            ],
            constraints=[
                Constraint(
                    "work_authorization",
                    True,
                    "Founder holds an eligible regional work permit.",
                    founder_fact="truth.identity.work_authorization",
                    provenance_pointer="truth#identity.work_authorization",
                ),
                Constraint(
                    "minimum_experience_years",
                    True,
                    "8 years recorded against a 5 year minimum.",
                    required_field="employment.years_experience",
                    founder_fact="truth.employment[*].duration",
                ),
                Constraint(
                    "language_requirement",
                    True,
                    "Bilingual Arabic/English evidenced by prior roles.",
                    founder_fact="truth.skills.languages",
                ),
            ],
            dimensions=[
                Dimension("relevance", 0.92, 0.4, "Core responsibilities closely match recent roles."),
                Dimension("seniority_fit", 0.86, 0.3, "Level matches; scope slightly larger than prior roles."),
                Dimension("compensation_alignment", 0.8, 0.3, "Posted band is within founder's stated range."),
            ],
            strengths=["Direct domain match", "Language requirement fully met"],
            gaps=["No prior experience with this specific CMS vendor"],
            explanation=(
                "High confidence match: every hard constraint passed and dimension "
                "scores are consistently strong."
            ),
        ),
        SeedOpportunity(
            id="opp-002",
            title="Field Operations Lead — Emergency Response",
            organization="Coastal Relief Trust (synthetic)",
            source_id="src-ngo-board",
            source_url="https://jobs.example.org/postings/opp-002",
            track="employment",
            decision="ineligible",
            fit_score=12.0,
            deadline=(now + timedelta(days=8)).date().isoformat(),
            posted_date=(now - timedelta(days=13)).date().isoformat(),
            is_stale=False,
            description=(
                "Synthetic posting: on-site emergency logistics coordination role "
                "requiring a heavy-vehicle license."
            ),
            fields=[
                Field(
                    "location_requirement",
                    "Must relocate to Coastal Region within 30 days",
                    "On-site, Coastal Region",
                    "normalized",
                    "listing.location",
                    "location-normalize-v1",
                ),
            ],
            constraints=[
                Constraint(
                    "driving_license_class",
                    False,
                    "Posting requires class-C license; truth pack records no driving license.",
                    required_field="identity.driving_license_class",
                    is_hard_failure=True,
                    provenance_pointer="truth#identity.driving_license_class",
                ),
                Constraint(
                    "location_relocation",
                    True,
                    "Founder's preferences allow relocation for this region.",
                    founder_fact="truth.preferences.relocation_regions",
                ),
                Constraint(
                    "field_certification",
                    None,
                    "Posting references a field-response certification the truth pack "
                    "does not confirm or deny.",
                    required_field="certifications.field_response",
                    is_hard_failure=False,
                ),
            ],
            dimensions=[
                Dimension("relevance", 0.35, 0.4, "Some operational overlap but different domain focus."),
                Dimension("seniority_fit", 0.5, 0.3, "Level roughly matches."),
                Dimension("compensation_alignment", 0.2, 0.3, "Posted band well below founder's stated minimum."),
            ],
            strengths=["Operational leadership experience transfers"],
            gaps=["No driving license on file", "No confirmed field certification"],
            unknowns=["field_response certification status"],
            uncertainty_penalty=0.05,
            explanation=(
                "Disqualified on a hard constraint (driving license). Certification "
                "status is unknown, not failed, and did not by itself decide the outcome."
            ),
            action_state="dismissed",
            feedback_label="eligibility_wrong",
        ),
        SeedOpportunity(
            id="opp-003",
            title="Independent Grant Writing Contract",
            organization="Levant Policy Studio (synthetic)",
            source_id="src-freelance-board",
            source_url="https://jobs.example.org/postings/opp-003",
            track="freelance",
            decision="uncertain",
            fit_score=55.0,
            deadline=(now + timedelta(days=23)).date().isoformat(),
            posted_date=(now - timedelta(days=5)).date().isoformat(),
            is_stale=False,
            description=(
                "Synthetic posting: short-term grant writing engagement, scope and "
                "duration not fully specified."
            ),
            fields=[
                Field(
                    "engagement_length",
                    "flexible",
                    None,
                    "unparsed",
                    "listing.duration",
                ),
            ],
            constraints=[
                Constraint(
                    "engagement_length_within_preference",
                    None,
                    "Posting does not state a fixed duration; truth pack preference "
                    "could not be evaluated.",
                    required_field="preferences.engagement_length",
                ),
                Constraint(
                    "rate_meets_minimum",
                    None,
                    "Posting has no published rate; truth pack minimum rate could not "
                    "be compared.",
                    required_field="preferences.minimum_rate",
                ),
                Constraint(
                    "subject_matter_match",
                    True,
                    "Grant writing experience is directly evidenced.",
                    founder_fact="truth.employment[2].achievements",
                ),
            ],
            dimensions=[
                Dimension("relevance", 0.7, 0.4, "Subject matter matches well."),
                Dimension("seniority_fit", 0.6, 0.3, "Cannot fully assess without a defined scope."),
                Dimension("compensation_alignment", 0.3, 0.3, "No rate published; scored conservatively."),
            ],
            strengths=["Directly relevant grant-writing history"],
            unknowns=["engagement length", "rate"],
            uncertainty_penalty=0.25,
            explanation=(
                "Two soft constraints could not be resolved either way (UNKNOWN, not "
                "FAIL). The decision is uncertain rather than qualified or ineligible "
                "until the founder or a source update resolves them."
            ),
        ),
        SeedOpportunity(
            id="opp-004",
            title="Data Governance Advisor (Procurement Notice)",
            organization="Regional Statistics Authority (synthetic)",
            source_id="src-ted-search",
            source_url="https://ted.example.org/notices/opp-004",
            track="procurement",
            decision=None,
            fit_score=None,
            deadline=(now + timedelta(days=33)).date().isoformat(),
            posted_date=today,
            is_stale=False,
            description=(
                "Synthetic notice: newly discovered procurement opportunity, not yet "
                "evaluated against the truth pack."
            ),
            fields=[
                Field(
                    "title",
                    "DATA GOVERNANCE ADVISOR",
                    "Data Governance Advisor (Procurement Notice)",
                    "normalized",
                    "notice.title",
                    "title-normalize-v1",
                ),
            ],
        ),
        SeedOpportunity(
            id="opp-005",
            title="Regional Partnerships Contractor",
            organization="Desert Bloom Cooperative (synthetic)",
            source_id="src-jobboard-alpha",
            source_url="https://jobs.example.org/postings/opp-005",
            track="contract",
            decision="qualified",
            fit_score=71.0,
            deadline=(now + timedelta(days=13)).date().isoformat(),
            posted_date=(now - timedelta(days=23)).date().isoformat(),
            is_stale=True,
            description=(
                "Synthetic posting: six-month partnerships contract. Source has not "
                "re-verified this listing recently."
            ),
            fields=[
                Field("contract_length", "6 mo", "6 months", "normalized", "listing.duration", "duration-normalize-v1"),
            ],
            constraints=[
                Constraint("contract_length_within_preference", True, "6 months is within the founder's stated range."),
                Constraint("remote_allowed", True, "Posting explicitly allows remote work."),
            ],
            dimensions=[
                Dimension("relevance", 0.75, 0.4, "Solid overlap with partnerships experience."),
                Dimension("seniority_fit", 0.7, 0.3, "Matches mid-senior scope."),
                Dimension("compensation_alignment", 0.68, 0.3, "Within range but near the lower bound."),
            ],
            strengths=["Remote-friendly", "Duration matches preference"],
            gaps=["Compensation is at the low end of the acceptable range"],
            explanation=(
                "Qualifies on all hard constraints. Flagged stale because the source "
                "has not reverified this posting in over a week -- treat deadline and "
                "status as provisional."
            ),
        ),
        SeedOpportunity(
            id="opp-006",
            title="Program Evaluation Lead",
            organization="Amber Horizon Foundation (synthetic)",
            source_id="src-ngo-board",
            source_url="https://jobs.example.org/postings/opp-006",
            track="employment",
            decision="qualified",
            fit_score=90.0,
            deadline=(now + timedelta(days=16)).date().isoformat(),
            posted_date=(now - timedelta(days=8)).date().isoformat(),
            is_stale=False,
            description="Synthetic posting: lead evaluation function for a multi-country program.",
            fields=[
                Field("title", "Program Evaluation Lead", "Program Evaluation Lead", "normalized", "listing.title", "title-normalize-v1"),
            ],
            constraints=[
                Constraint("minimum_experience_years", True, "10 years recorded against a 6 year minimum."),
                Constraint("work_authorization", True, "Founder holds an eligible regional work permit."),
            ],
            dimensions=[
                Dimension("relevance", 0.95, 0.4, "Near-exact match to prior role."),
                Dimension("seniority_fit", 0.9, 0.3, "Matches evidenced seniority."),
                Dimension("compensation_alignment", 0.85, 0.3, "Within preferred band."),
            ],
            strengths=["Direct domain match", "Compensation alignment"],
            explanation="High-confidence match; founder has already marked this applied.",
            action_state="submitted",
            feedback_label="good_match",
        ),
        SeedOpportunity(
            id="opp-007",
            title="Compliance Monitoring Consultant",
            organization="Tidewater Advisory Group (synthetic)",
            source_id="src-freelance-board",
            source_url="https://jobs.example.org/postings/opp-007",
            track="contract",
            decision="ineligible",
            fit_score=30.0,
            deadline=(now + timedelta(days=3)).date().isoformat(),
            posted_date=(now - timedelta(days=18)).date().isoformat(),
            is_stale=False,
            description="Synthetic posting: compliance monitoring role requiring a specific professional license.",
            constraints=[
                Constraint(
                    "professional_license",
                    False,
                    "Posting requires an active compliance license; truth pack records none.",
                    required_field="certifications.compliance_license",
                    is_hard_failure=True,
                ),
            ],
            dimensions=[
                Dimension("relevance", 0.4, 0.4, "Partial subject-matter overlap."),
                Dimension("seniority_fit", 0.5, 0.3, "Roughly matches."),
                Dimension("compensation_alignment", 0.4, 0.3, "Below preferred range."),
            ],
            gaps=["No compliance license on file"],
            explanation="Disqualified on a single hard constraint.",
            action_state="dismissed",
            feedback_label="eligibility_wrong",
        ),
        SeedOpportunity(
            id="opp-008",
            title="Youth Skills Program Coordinator",
            organization="Cedar Valley Trust (synthetic)",
            source_id="src-ngo-board",
            source_url="https://jobs.example.org/postings/opp-008",
            track="employment",
            decision="qualified",
            fit_score=45.0,
            deadline=(now + timedelta(days=28)).date().isoformat(),
            posted_date=(now - timedelta(days=11)).date().isoformat(),
            is_stale=False,
            description="Synthetic posting: coordinate a regional youth skills program.",
            constraints=[
                Constraint("minimum_experience_years", True, "4 years recorded against a 3 year minimum."),
            ],
            dimensions=[
                Dimension("relevance", 0.55, 0.4, "Adjacent but not identical domain."),
                Dimension("seniority_fit", 0.5, 0.3, "Slightly below evidenced seniority."),
                Dimension("compensation_alignment", 0.3, 0.3, "Below preferred band."),
            ],
            strengths=["Adjacent domain experience"],
            gaps=["Compensation below preference"],
            explanation="Qualifies but scores modestly; founder chose to snooze rather than act now.",
            action_state="snoozed",
        ),
        SeedOpportunity(
            id="opp-009",
            title="Digital Inclusion Strategy Consultant",
            organization="Falcon Ridge Institute (synthetic)",
            source_id="src-freelance-board",
            source_url="https://jobs.example.org/postings/opp-009",
            track="freelance",
            decision="qualified",
            fit_score=76.0,
            deadline=(now + timedelta(days=20)).date().isoformat(),
            posted_date=(now - timedelta(days=3)).date().isoformat(),
            is_stale=False,
            description="Synthetic posting: digital inclusion strategy engagement.",
            constraints=[
                Constraint("rate_meets_minimum", True, "Published rate exceeds the founder's stated minimum."),
            ],
            dimensions=[
                Dimension("relevance", 0.8, 0.4, "Strong strategy-consulting overlap."),
                Dimension("seniority_fit", 0.75, 0.3, "Matches evidenced seniority."),
                Dimension("compensation_alignment", 0.72, 0.3, "Comfortably within range."),
            ],
            strengths=["Rate and scope both align"],
            explanation="Strong match; founder suspects this may duplicate another listing.",
            feedback_label="duplicate_issue",
        ),
    ]


SEED_OPPORTUNITY_IDS = [f"opp-{i:03d}" for i in range(1, 10)]
SEED_POLL_RUN_ID_PREFIX = "seed-poll-"


def _delete_existing(session) -> None:
    # `field_provenances`, `founder_feedback`, `founder_opportunity_views`,
    # `founder_triage_states`, and `match_evaluations` all cascade on
    # `opportunities.id` (ondelete="CASCADE" -- see storage/models.py), so
    # deleting the opportunity rows is enough for those. `outbound_actions`
    # has no foreign key to `opportunities` and must be deleted explicitly.
    session.query(OutboundActionRecordModel).filter(
        OutboundActionRecordModel.opportunity_id.in_(SEED_OPPORTUNITY_IDS)
    ).delete(synchronize_session=False)
    session.query(OpportunityRecord).filter(
        OpportunityRecord.id.in_(SEED_OPPORTUNITY_IDS)
    ).delete(synchronize_session=False)
    session.query(SourcePollRunRecord).filter(
        SourcePollRunRecord.id.like(f"{SEED_POLL_RUN_ID_PREFIX}%")
    ).delete(synchronize_session=False)


def _insert_opportunity_core(session, seed: SeedOpportunity, now: datetime) -> str:
    """Insert the `OpportunityRecord` and its `FieldProvenanceRecord` rows
    (the only two tables with a declared ORM `relationship()` back to
    `OpportunityRecord`) and return the opportunity's content hash.

    Split from `_insert_opportunity_children` and flushed before it: the
    other child tables (`match_evaluations`, `founder_triage_states`,
    `outbound_actions`, `founder_feedback`) have a foreign key to
    `opportunities` but no declared ORM `relationship()`, so SQLAlchemy's
    unit-of-work cannot infer an insert order between them and
    `OpportunityRecord` from the object graph alone. Without an explicit
    flush in between, a single `commit()` at the end can batch-insert a
    child table's rows before its parent `opportunities` row exists,
    raising a foreign key violation.
    """
    content_hash = _checksum("opportunity", seed.id)

    session.add(
        OpportunityRecord(
            id=seed.id,
            track=seed.track,
            title=seed.title,
            organization=seed.organization,
            description=seed.description,
            source_id=seed.source_id,
            source_url=seed.source_url,
            content_hash=content_hash,
            posted_date=seed.posted_date,
            deadline=seed.deadline,
            is_stale=seed.is_stale,
            reverified_at=now,
            created_at=now,
        )
    )

    for f in seed.fields:
        session.add(
            FieldProvenanceRecord(
                opportunity_id=seed.id,
                field_name=f.field_name,
                raw_value=f.raw_value,
                normalized_value=f.normalized_value,
                derivation_type=f.derivation_type,
                raw_pointer=f.raw_pointer,
                record_checksum=_checksum(seed.id, f.field_name),
                rule_id=f.rule_id,
            )
        )

    return content_hash


def _insert_opportunity_children(session, seed: SeedOpportunity, content_hash: str, now: datetime) -> None:
    if seed.decision is not None:
        hard_constraints = [
            {
                "constraint_name": c.name,
                "passed": c.passed,
                "reason": c.reason,
                "required_field": c.required_field,
                "founder_fact": c.founder_fact,
                "is_hard_failure": c.is_hard_failure,
                "provenance_pointer": c.provenance_pointer,
            }
            for c in seed.constraints
        ]
        reasons = (
            [{"kind": "strength", "dimension": None, "text": t} for t in seed.strengths[:5]]
            + [{"kind": "gap", "dimension": None, "text": t} for t in seed.gaps[:5]]
            + [{"kind": "unknown", "dimension": None, "text": t} for t in seed.unknowns[:5]]
        )
        dimension_scores = [
            {
                "dimension_name": d.name,
                "raw_score": d.score,
                "weight": d.weight,
                "weighted_score": d.weighted_score,
                "explanation": d.rationale,
            }
            for d in seed.dimensions
        ]
        evaluation_detail = {
            "hard_constraints": hard_constraints,
            "strengths": seed.strengths,
            "gaps": seed.gaps,
            "unknowns": seed.unknowns,
            "uncertainty_penalty": seed.uncertainty_penalty,
            "explanation": seed.explanation,
        }
        session.add(
            MatchEvaluationRecord(
                id=f"eval-{seed.id}",
                opportunity_id=seed.id,
                truth_pack_hash="synthetic-seed-pack",
                qualification_decision=seed.decision,
                fit_score=seed.fit_score,
                dimension_scores_json=json.dumps(dimension_scores),
                reasons_json=json.dumps(reasons),
                evaluation_detail_json=json.dumps(evaluation_detail),
                policy_version=POLICY_VERSION,
                evaluated_at=now,
                created_at=now,
            )
        )

    if seed.action_state in ("dismissed", "snoozed"):
        snoozed_until = now + timedelta(days=30) if seed.action_state == "snoozed" else None
        session.add(
            FounderTriageStateRecord(
                opportunity_id=seed.id,
                state=seed.action_state,
                snoozed_until=snoozed_until,
                created_at=now,
                updated_at=now,
            )
        )
    elif seed.action_state == "submitted":
        session.add(
            OutboundActionRecordModel(
                id=f"action-seed-{seed.id}",
                opportunity_id=seed.id,
                opportunity_content_hash=content_hash,
                workspace="default",
                candidate_id="founder",
                track=seed.track,
                source=seed.source_id,
                adapter_name="founder_attested",
                adapter_version="1.0",
                execution_mode="dry_run",
                qualification_decision=seed.decision or "uncertain",
                match_score_snapshot=seed.fit_score or 0.0,
                artifact_ids_json="[]",
                artifact_hashes_json="[]",
                manifest_hash=_checksum("manifest", seed.id),
                action_status="submitted",
                idempotency_key=f"seed-founder-attested:{seed.id}",
                created_at=now,
                updated_at=now,
            )
        )

    if seed.feedback_label is not None:
        session.add(
            FounderFeedbackRecord(
                id=f"fb-seed-{seed.id}",
                opportunity_id=seed.id,
                feedback_label=seed.feedback_label,
                structured_reason=seed.feedback_label,
                notes=None,
                dedup_hash=_checksum("feedback", seed.id, seed.feedback_label),
                created_at=now,
            )
        )


def _insert_poll_runs(session, now: datetime) -> None:
    # Non-zero "fetched" dashboard numbers for today, per source, so the
    # header strip shows real counts rather than every stat reading zero.
    runs = [
        ("src-jobboard-alpha", 12),
        ("src-ngo-board", 0),
        ("src-freelance-board", 9),
        ("src-ted-search", 6),
    ]
    for source_id, raw_ingested in runs:
        session.add(
            SourcePollRunRecord(
                id=f"{SEED_POLL_RUN_ID_PREFIX}{source_id}",
                source_id=source_id,
                job_id=None,
                started_at=now,
                finished_at=now,
                status="ok" if raw_ingested > 0 else "parse_empty",
                raw_ingested=raw_ingested,
                unique_opportunities=raw_ingested,
                inserted=raw_ingested,
                unchanged=0,
                updated=0,
            )
        )


def main() -> None:
    db_url = os.environ.get("OPPORTUNITYOS_DB_URL")
    if not db_url or not db_url.startswith("postgresql"):
        raise SystemExit(
            f"seed_real.py requires a real PostgreSQL OPPORTUNITYOS_DB_URL, got: {db_url!r}"
        )

    engine = get_engine(db_url)
    session_factory = get_session_factory(engine)
    session = session_factory()

    try:
        now = datetime.now(timezone.utc)
        seeds = _default_opportunities(now)
        _delete_existing(session)
        session.flush()
        content_hashes = {seed.id: _insert_opportunity_core(session, seed, now) for seed in seeds}
        session.flush()
        for seed in seeds:
            _insert_opportunity_children(session, seed, content_hashes[seed.id], now)
        _insert_poll_runs(session, now)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()

    print(f"seed_real.py: seeded {len(SEED_OPPORTUNITY_IDS)} synthetic opportunities into {db_url.split('@')[-1]}")


if __name__ == "__main__":
    main()
