"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { ActionState, ActionType, ApplicationStage } from "@/lib/contract/types"

const APPLICATION_STATES: ActionState[] = [
  "applied", "recruiter_screen", "assessment", "interviewing",
  "final_interview", "offer", "accepted", "submitted",
]
const CLOSED_STATES: ActionState[] = [
  "accepted", "rejected_by_founder", "rejected_by_employer", "withdrawn",
  "no_response", "position_closed", "archived", "dismissed",
]

const PIPELINE_STAGES: ApplicationStage[] = [
  "applied", "recruiter_screen", "assessment", "interviewing",
  "final_interview", "offer", "accepted",
]
const PIPELINE_TERMINAL_OUTCOMES: ApplicationStage[] = [
  "rejected_by_employer", "withdrawn", "no_response",
]
const PIPELINE_STAGE_LABEL: Record<ApplicationStage, string> = {
  applied: "Applied",
  recruiter_screen: "Recruiter screen",
  assessment: "Assessment",
  interviewing: "Interviewing",
  final_interview: "Final interview",
  offer: "Offer",
  accepted: "Accepted",
  rejected_by_employer: "Rejected by employer",
  withdrawn: "Withdrawn",
  no_response: "No response",
}

const ACTION_STATE_LABEL: Record<string, string> = {
  submitted: "Marked applied",
  applied: "Applied",
  saved: "Saved",
  rejected_by_founder: "Rejected by me",
  rejected_by_employer: "Rejected by employer",
  recruiter_screen: "Recruiter screen",
  assessment: "Assessment",
  interviewing: "Interviewing",
  final_interview: "Final interview",
  offer: "Offer",
  accepted: "Accepted",
  withdrawn: "Withdrawn",
  no_response: "No response",
  dismissed: "Dismissed",
  snoozed: "Snoozed",
}

export function TriageActions({
  currentState,
  submitting,
  onSubmit,
}: {
  currentState: ActionState
  submitting: boolean
  onSubmit: (type: ActionType, until: string | null, stage?: ApplicationStage) => void
}) {
  const [showSnooze, setShowSnooze] = useState(false)
  const [until, setUntil] = useState("")
  const [selectedStage, setSelectedStage] = useState<ApplicationStage>("recruiter_screen")
  const currentPipelineStage = currentState === "submitted" ? "applied" : currentState
  const currentPipelineIndex = currentPipelineStage
    ? PIPELINE_STAGES.indexOf(currentPipelineStage as ApplicationStage)
    : -1
  const isInApplication = currentState !== null && APPLICATION_STATES.includes(currentState)
  const isClosed = currentState !== null && CLOSED_STATES.includes(currentState)
  const availableStages = currentPipelineIndex >= 0 && !isClosed
    ? [
        PIPELINE_STAGES[currentPipelineIndex],
        ...PIPELINE_STAGES.slice(currentPipelineIndex + 1),
        ...PIPELINE_TERMINAL_OUTCOMES,
      ]
    : []
  const displayedStage = availableStages.includes(selectedStage)
    ? selectedStage
    : availableStages[0]

  return (
    <div className="space-y-2">
      {currentState && (
        <p className="text-xs text-muted-foreground">
          Current status: <strong>{ACTION_STATE_LABEL[currentState] ?? currentState}</strong>
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={submitting || currentState === "saved" || isInApplication || isClosed}
          onClick={() => onSubmit("save", null)}
        >
          Save for later
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={submitting || isInApplication || isClosed}
          onClick={() => onSubmit("mark_applied", null)}
        >
          Mark applied
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={submitting || isInApplication || isClosed}
          onClick={() => onSubmit("reject", null)}
        >
          Reject
        </Button>
        {!showSnooze ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={submitting || currentState === "saved" || isInApplication || isClosed}
            onClick={() => setShowSnooze(true)}
          >
            Snooze
          </Button>
        ) : (
          <div className="flex items-center gap-2">
            <Label htmlFor="snooze-until" className="sr-only">
              Snooze until
            </Label>
            <Input
              id="snooze-until"
              type="date"
              className="h-8 w-36"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={submitting || !until}
              onClick={() => {
                onSubmit("snooze", until)
                setShowSnooze(false)
              }}
            >
              Confirm snooze
            </Button>
          </div>
        )}
      </div>
      {availableStages.length > 0 && displayedStage && (
        <div className="flex flex-wrap items-end gap-2 border-t pt-3">
          <div className="space-y-1">
            <Label htmlFor="application-stage" className="text-xs text-muted-foreground">
              Application stage
            </Label>
            <select
              id="application-stage"
              aria-label="Application stage"
              className="h-8 rounded-md border border-input bg-background px-2 text-sm"
              value={displayedStage}
              onChange={(event) => setSelectedStage(event.target.value as ApplicationStage)}
            >
              {availableStages.map((stage) => (
                <option key={stage} value={stage}>
                  {stage === currentPipelineStage
                    ? `${PIPELINE_STAGE_LABEL[stage]} (current; no change)`
                    : PIPELINE_STAGE_LABEL[stage]}
                </option>
              ))}
            </select>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={submitting}
            onClick={() => onSubmit("set_stage", null, displayedStage)}
          >
            Update stage
          </Button>
        </div>
      )}
      {currentState && isClosed && (
        <p className="text-xs text-muted-foreground">
          This application is closed. Restore is not available yet.
        </p>
      )}
    </div>
  )
}
