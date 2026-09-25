"use client"

import { useEffect, useMemo, useState } from "react"
import DOMPurify from "dompurify"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button"
import { ArtifactsPanel } from "@/components/feed/artifacts-panel"
import { ConstraintOutcomeBadge } from "@/components/feed/constraint-outcome"
import { DecisionBadge } from "@/components/feed/decision-badge"
import { FeedbackButtons } from "@/components/feed/feedback-buttons"
import { TriageActions } from "@/components/feed/triage-actions"
import { TrackerFollowUps } from "@/components/feed/tracker-followups"
import { TrackerInterviews } from "@/components/feed/tracker-interviews"
import { TrackerDocuments } from "@/components/feed/tracker-documents"
import { TrackerNotes } from "@/components/feed/tracker-notes"
import { TrackerActivityTimeline } from "@/components/feed/tracker-activity-timeline"
import { api } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"
import { notifyTrackerActivityChanged } from "@/lib/tracker-activity"
import type {
  ActionState,
  ActionResponse,
  ActionType,
  ApplicationStage,
  FeedbackLabel,
  OpportunityDetail,
} from "@/lib/contract/types"

const APPLICATION_TRACKED_STATES = new Set([
  "submitted",
  "applied",
  "recruiter_screen",
  "assessment",
  "interviewing",
  "final_interview",
  "offer",
  "accepted",
  "rejected_by_employer",
  "withdrawn",
  "no_response",
])

const FOLLOW_UP_TRACKED_STATES = new Set([
  "saved",
  "submitted",
  "applied",
  "recruiter_screen",
  "assessment",
  "interviewing",
  "final_interview",
  "offer",
  "accepted",
])

const INTERVIEW_TRACKED_STATES = new Set([
  "applied",
  "recruiter_screen",
  "assessment",
  "interviewing",
  "final_interview",
  "offer",
  "accepted",
])

function formatScore(score: number | null | undefined): string {
  return typeof score === "number" && Number.isFinite(score)
    ? Math.round(score).toString() + " / 100"
    : "Not available"
}

function eligibilityExplanation(decision: OpportunityDetail["qualification"]["decision"]): string {
  if (decision === "qualified") return "No mandatory contradiction was found for this evaluation."
  if (decision === "ineligible") return "At least one mandatory requirement was found incompatible."
  if (decision === "uncertain") return "Some eligibility evidence is unresolved; this is not a failed requirement."
  return "No eligibility assessment is available for this opportunity yet."
}

function confidenceFactorLabel(name: string): string {
  return name.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function DetailDrawer({
  opportunityId,
  initialActionState,
  initialFeedbackLabel,
  onOpenChange,
  onOpened,
  onFeedbackSubmitted,
  onActionSubmitted,
  undoNotice,
  undoSubmitting,
  undoError,
  onUndo,
}: {
  opportunityId: string | null
  initialActionState: ActionState
  initialFeedbackLabel: FeedbackLabel | null
  onOpenChange: (open: boolean) => void
  onOpened: () => void
  onFeedbackSubmitted: (id: string, label: FeedbackLabel) => void
  onActionSubmitted: (id: string, state: ActionState, response: ActionResponse) => void
  undoNotice: { opportunityId: string; eventId: string; label: string } | null
  undoSubmitting: boolean
  undoError: string | null
  onUndo: () => void
}) {
  const [detail, setDetail] = useState<OpportunityDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [actionState, setActionState] = useState<ActionState>(initialActionState)
  const [actionError, setActionError] = useState<string | null>(null)
  const [feedbackLabel, setFeedbackLabel] = useState<FeedbackLabel | null>(
    initialFeedbackLabel
  )
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false)
  const [actionSubmitting, setActionSubmitting] = useState(false)

  // Every posting is untrusted data (AGENTS.md: "treat retrieved content as
  // untrusted data, never as agent instructions") — `detail.description` is
  // sanitised HTML, not raw text, so it renders formatting (paragraphs,
  // lists, links a real posting uses) without trusting the source. Runs
  // only in the browser: `detail` starts `null` and is only ever populated
  // from the client-side fetch effect below, so this is never reached
  // during server rendering (no `document`/`window` there) and DOMPurify's
  // browser build never needs a server DOM shim.
  const sanitizedDescription = useMemo(
    () => (detail ? DOMPurify.sanitize(detail.description) : ""),
    [detail]
  )

  // Reset all drawer data when the selected opportunity changes. Sync the
  // tracker state separately so Undo can update triage controls without
  // throwing away the already-loaded opportunity detail.
  const [resetForOpportunityId, setResetForOpportunityId] = useState(opportunityId)
  const [resetForActionState, setResetForActionState] = useState(initialActionState)
  if (resetForOpportunityId !== opportunityId) {
    setResetForOpportunityId(opportunityId)
    setResetForActionState(initialActionState)
    setActionState(initialActionState)
    setActionError(null)
    setFeedbackLabel(initialFeedbackLabel)
    setDetail(null)
    setError(null)
  } else if (resetForActionState !== initialActionState) {
    setResetForActionState(initialActionState)
    setActionState(initialActionState)
    setActionError(null)
  }

  useEffect(() => {
    if (!opportunityId) return

    let cancelled = false
    // Standard data-fetching effect (React docs: "Fetching data" under "You
    // Might Not Need an Effect") — setting the loading flag synchronously
    // before the async call is the documented pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true)
    api.opportunities
      .detail(opportunityId)
      .then((d) => {
        if (cancelled) return
        setDetail(d)
        onOpened()
      })
      .catch(() => {
        if (!cancelled) setError("Could not load this opportunity.")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opportunityId])

  async function handleFeedback(label: FeedbackLabel, note: string | null) {
    if (!opportunityId) return
    setFeedbackSubmitting(true)
    try {
      await api.opportunities.submitFeedback(opportunityId, label, note)
      setFeedbackLabel(label)
      onFeedbackSubmitted(opportunityId, label)
    } finally {
      setFeedbackSubmitting(false)
    }
  }

  async function handleAction(
    type: ActionType,
    until: string | null,
    stage?: ApplicationStage
  ) {
    if (!opportunityId) return
    setActionError(null)
    setActionSubmitting(true)
    try {
      const res = await api.opportunities.submitAction(
        opportunityId,
        type,
        until,
        crypto.randomUUID(),
        stage
      )
      const state = res.tracker_state ?? res.action_state
      setActionState(state)
      onActionSubmitted(opportunityId, state, res)
      notifyTrackerActivityChanged()
    } catch (actionFailure) {
      const detail = actionFailure instanceof ApiError &&
        actionFailure.body && typeof actionFailure.body === "object" &&
        "detail" in actionFailure.body && typeof actionFailure.body.detail === "string"
        ? actionFailure.body.detail
        : actionFailure instanceof Error
          ? actionFailure.message
          : "Could not update this tracker state."
      setActionError(detail)
    } finally {
      setActionSubmitting(false)
    }
  }

  return (
    <Sheet open={opportunityId !== null} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto sm:max-w-lg"
        aria-describedby={undefined}
      >
        {loading && (
          <div className="p-6 text-sm text-muted-foreground">Loading…</div>
        )}
        {error && (
          <div role="alert" className="p-6 text-sm text-destructive">
            {error}
          </div>
        )}
        {detail && (
          <div className="flex flex-col gap-6 p-4">
            <SheetHeader className="p-0">
              <SheetTitle>{detail.title}</SheetTitle>
              <SheetDescription>
                {detail.organization} · {detail.source_id}
              </SheetDescription>
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <DecisionBadge decision={detail.qualification.decision} />
                <span className="text-xs text-muted-foreground">
                  {detail.track}
                </span>
                {detail.is_stale && (
                  <span className="text-xs font-medium text-amber-700 dark:text-amber-300">
                    Stale — not recently reverified
                  </span>
                )}
              </div>
            </SheetHeader>

            <section>
              <div
                data-testid="opportunity-description"
                className="text-sm [&_a]:underline [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:list-decimal [&_ol]:pl-4"
                // Sanitised above with DOMPurify — the one deliberate
                // `dangerouslySetInnerHTML` in this file, and only ever fed
                // sanitised output, never `detail.description` directly.
                dangerouslySetInnerHTML={{ __html: sanitizedDescription }}
              />
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <dt>Deadline</dt>
                <dd>{detail.deadline ?? "—"}</dd>
                <dt>Posted</dt>
                <dd>{detail.posted_date ?? "—"}</dd>
                <dt>Reverified</dt>
                <dd>{detail.reverified_at ?? "—"}</dd>
              </dl>
              <a
                href={detail.source_url}
                target="_blank"
                rel="noreferrer noopener"
                className="mt-2 inline-block text-xs text-primary underline underline-offset-4"
              >
                View original source
              </a>
            </section>

            <Separator />

            <section aria-labelledby="match-overview-heading" data-testid="match-overview">
              <h3 id="match-overview-heading" className="text-sm font-semibold">
                Match overview
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Eligibility, Capability Fit, Preference, and Confidence answer separate questions. Recommended order is a way to sort jobs, not the explanation for this evaluation.
              </p>
              <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                <div data-testid="eligibility-explanation" className="rounded-md border border-border p-2">
                  <dt className="text-xs font-medium">Eligibility</dt>
                  <dd className="mt-1"><DecisionBadge decision={detail.qualification.decision} /></dd>
                  <dd className="mt-1 text-[11px] text-muted-foreground">
                    {eligibilityExplanation(detail.qualification.decision)}
                  </dd>
                </div>
                <div data-testid="capability-fit-summary" className="rounded-md border border-border p-2">
                  <dt className="text-xs font-medium">Capability Fit</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums">{formatScore(detail.scoring.fit_score)}</dd>
                  <dd className="text-[11px] text-muted-foreground">
                    How verified skills, role history, experience, seniority, and education align with the work.
                  </dd>
                </div>
                <div data-testid="preference-score-summary" className="rounded-md border border-border p-2">
                  <dt className="text-xs font-medium">Preference</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums">{formatScore(detail.scoring.preference_score)}</dd>
                  <dd className="text-[11px] text-muted-foreground">
                    How the job fits stated preferences. It does not change eligibility or Capability Fit; no per-preference breakdown is provided here.
                  </dd>
                </div>
                <div data-testid="confidence-score-summary" className="rounded-md border border-border p-2">
                  <dt className="text-xs font-medium">Confidence</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums">{formatScore(detail.scoring.confidence_score)}</dd>
                  <dd className="text-[11px] text-muted-foreground">
                    How complete and reliable the evidence is behind these assessments.
                  </dd>
                </div>
              </dl>
              {detail.scoring.confidence_factors?.length ? (
                <div className="mt-3" data-testid="confidence-factors">
                  <h4 className="text-xs font-semibold">Confidence evidence</h4>
                  <ul className="mt-1 space-y-2">
                    {detail.scoring.confidence_factors.map((factor) => (
                      <li key={factor.name} className="rounded-md border border-border p-2">
                        <div className="flex items-center justify-between gap-2 text-xs">
                          <span className="font-medium">{confidenceFactorLabel(factor.name)}</span>
                          <span className="tabular-nums text-muted-foreground">{formatScore(factor.score)}</span>
                        </div>
                        <p className="mt-1 text-[11px] text-muted-foreground">{factor.explanation}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="mt-2 text-xs text-muted-foreground" data-testid="confidence-factors-unavailable">
                  No confidence factor breakdown was recorded for this evaluation.
                </p>
              )}
            </section>

            <Separator />

            <section aria-labelledby="qualification-heading">
              <h3 id="qualification-heading" className="text-sm font-semibold">
                Qualification checklist
              </h3>
              {detail.qualification.constraints.length === 0 ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  Not yet evaluated against a truth pack.
                </p>
              ) : (
                <>
                  {/* "Requirements split required/nice-to-have with your
                      match against each": `is_hard_failure` is already the
                      exact required/soft distinction the matching engine
                      computed — a hard failure is a required constraint,
                      anything else is nice-to-have. No new API field
                      needed; this only regroups `qualification.constraints`
                      already returned by GET /api/opportunities/{id}. */}
                  {(["required", "nice_to_have"] as const).map((bucket) => {
                    const items = detail.qualification.constraints.filter((c) =>
                      bucket === "required" ? c.is_hard_failure : !c.is_hard_failure
                    )
                    if (items.length === 0) return null
                    return (
                      <div key={bucket} className="mt-2">
                        <h4 className="text-xs font-semibold text-muted-foreground">
                          {bucket === "required" ? "Required" : "Nice to have"}
                        </h4>
                        <ul className="mt-1 space-y-2">
                          {items.map((c) => (
                            <li
                              key={c.constraint_name}
                              data-testid={`requirement-${bucket}-${c.constraint_name}`}
                              className="rounded-md border border-border p-2"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-xs font-medium">
                                  {c.constraint_name.replaceAll("_", " ")}
                                </span>
                                <ConstraintOutcomeBadge outcome={c.outcome} />
                              </div>
                              <p className="mt-1 text-xs text-muted-foreground">
                                {c.reason}
                              </p>
                              {c.founder_fact && (
                                <p className="mt-0.5 text-[11px] text-muted-foreground">
                                  Your match: {c.founder_fact}
                                </p>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )
                  })}
                </>
              )}
            </section>

            <Separator />

            <section aria-labelledby="geography-heading">
              <h3 id="geography-heading" className="text-sm font-semibold">
                Geography reasoning
              </h3>
              {(() => {
                const geoConstraint = detail.qualification.constraints.find((c) =>
                  /geo|location|remote|relocat/i.test(c.constraint_name)
                )
                if (!geoConstraint) {
                  return (
                    <p className="mt-1 text-xs text-muted-foreground">
                      No geography-specific constraint was reported by qualification
                      for this opportunity.
                    </p>
                  )
                }
                return (
                  <div
                    data-testid="geography-reasoning"
                    className="mt-1 rounded-md border border-border p-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium">
                        {geoConstraint.constraint_name.replaceAll("_", " ")}
                      </span>
                      <ConstraintOutcomeBadge outcome={geoConstraint.outcome} />
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {geoConstraint.reason}
                    </p>
                    {geoConstraint.founder_fact && (
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        Your fact: {geoConstraint.founder_fact}
                      </p>
                    )}
                  </div>
                )
              })()}
            </section>

            <Separator />

            <section aria-labelledby="scoring-heading">
              <h3 id="scoring-heading" className="text-sm font-semibold">
                Capability Fit dimensions
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">
                These component scores explain Capability Fit. Displayed weights are provisional until calibrated against Founder-reviewed examples.
              </p>
              {detail.scoring.dimension_scores.length === 0 ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  No scoring available yet.
                </p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {detail.scoring.dimension_scores.map((d) => (
                    <li key={d.dimension}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium">
                          {d.dimension.replaceAll("_", " ")}
                        </span>
                        <span className="tabular-nums text-muted-foreground">
                          {Math.round(d.score * 100)}% (weight {Math.round(d.weight * 100)}%)
                        </span>
                      </div>
                      <div
                        role="progressbar"
                        aria-label={`${d.dimension} score`}
                        aria-valuenow={Math.round(d.score * 100)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted"
                      >
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width: `${Math.round(d.score * 100)}%` }}
                        />
                      </div>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {d.rationale}
                      </p>
                    </li>
                  ))}
                </ul>
              )}

              {(detail.scoring.strengths.length > 0 ||
                detail.scoring.gaps.length > 0 ||
                detail.scoring.unknowns.length > 0) && (
                <div className="mt-3 grid gap-2 text-xs sm:grid-cols-3">
                  <div>
                    <p className="font-medium text-emerald-700 dark:text-emerald-300">
                      Strengths
                    </p>
                    <ul className="list-disc pl-4">
                      {detail.scoring.strengths.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="font-medium text-red-700 dark:text-red-300">Gaps</p>
                    <ul className="list-disc pl-4">
                      {detail.scoring.gaps.map((g) => (
                        <li key={g}>{g}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="font-medium text-amber-700 dark:text-amber-300">
                      Unknowns
                    </p>
                    <ul className="list-disc pl-4">
                      {detail.scoring.unknowns.map((u) => (
                        <li key={u}>{u}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {detail.scoring.explanation && (
                <p className="mt-3 text-xs text-muted-foreground">
                  {detail.scoring.explanation}
                </p>
              )}
            </section>

            <Separator />

            <section aria-labelledby="provenance-heading">
              <h3 id="provenance-heading" className="text-sm font-semibold">
                Field provenance
              </h3>
              {detail.fields.length === 0 ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  No field-level provenance recorded.
                </p>
              ) : (
                <ul className="mt-2 space-y-2 text-xs">
                  {detail.fields.map((f) => (
                    <li key={f.field_name} className="rounded-md border border-border p-2">
                      <p className="font-medium">{f.field_name}</p>
                      <p className="text-muted-foreground">
                        value: {f.value ?? "—"}
                      </p>
                      <p className="text-muted-foreground">
                        raw: {f.raw_value ?? "—"} ({f.derivation_type})
                      </p>
                      {f.rule_id && (
                        <p className="text-muted-foreground">rule: {f.rule_id}</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <Separator />

            {opportunityId && <ArtifactsPanel opportunityId={opportunityId} />}

            <Separator />

            <section aria-labelledby="feedback-heading">
              <h3 id="feedback-heading" className="text-sm font-semibold">
                Feedback
              </h3>
              <div className="mt-2">
                <FeedbackButtons
                  currentLabel={feedbackLabel}
                  submitting={feedbackSubmitting}
                  onSubmit={handleFeedback}
                />
              </div>
            </section>

            <Separator />

            <section aria-labelledby="triage-heading">
              <h3 id="triage-heading" className="text-sm font-semibold">
                Triage
              </h3>
              <div className="mt-2">
                <TriageActions
                  currentState={actionState}
                  submitting={actionSubmitting}
                  onSubmit={handleAction}
                />
              </div>
              {actionError && (
                <p role="alert" data-testid="tracker-action-error" className="mt-2 text-sm text-destructive">
                  {actionError}
                </p>
              )}
              {undoNotice && (
                <div role="status" data-testid="tracker-undo-notice" className="mt-3 flex items-center gap-3 rounded-lg border bg-card px-3 py-2 text-sm">
                  <span>{undoNotice.label}.</span>
                  <Button type="button" size="sm" variant="outline" data-testid="undo-tracker-action" disabled={undoSubmitting} onClick={onUndo}>
                    {undoSubmitting ? "Undoing…" : "Undo"}
                  </Button>
                </div>
              )}
              {undoError && <p role="alert" data-testid="tracker-undo-error" className="mt-2 text-sm text-destructive">{undoError}</p>}
            </section>

            {opportunityId && actionState &&
              APPLICATION_TRACKED_STATES.has(actionState) && (
                <>
                  <Separator />
                  <TrackerNotes key={opportunityId} opportunityId={opportunityId} />
                  <Separator />
                  <TrackerDocuments key={`documents-${opportunityId}`} opportunityId={opportunityId} />
                </>
              )}

            {opportunityId && actionState &&
              FOLLOW_UP_TRACKED_STATES.has(actionState) && (
                <>
                  <Separator />
                  <TrackerFollowUps key={opportunityId} opportunityId={opportunityId} />
                </>
              )}

            {opportunityId && actionState &&
              INTERVIEW_TRACKED_STATES.has(actionState) && (
                <>
                  <Separator />
                  <TrackerInterviews key={opportunityId} opportunityId={opportunityId} />
                </>
              )}

            <>
              <Separator />
              <TrackerActivityTimeline key={`activity-${detail.id}`} opportunityId={detail.id} />
            </>

            {(detail.action_history.length > 0 ||
              detail.feedback_history.length > 0) && (
              <>
                <Separator />
                <section aria-labelledby="history-heading">
                  <h3 id="history-heading" className="text-sm font-semibold">
                    History
                  </h3>
                  <ul className="mt-2 space-y-1 text-[11px] text-muted-foreground">
                    {detail.action_history.map((a) => (
                      <li key={a.action_id}>
                        {a.created_at} — action: {a.action_status} ({a.execution_mode})
                      </li>
                    ))}
                    {detail.feedback_history.map((f) => (
                      <li key={f.id}>
                        {f.created_at} — feedback: {f.feedback_label}
                        {f.notes ? ` — “${f.notes}”` : ""}
                      </li>
                    ))}
                  </ul>
                </section>
              </>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
