"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { ActionState, ActionType } from "@/lib/contract/types"

const APPLICATION_STATES: ActionState[] = [
  "applied", "recruiter_screen", "assessment", "interviewing",
  "final_interview", "offer", "accepted", "submitted",
]
const CLOSED_STATES: ActionState[] = [
  "accepted", "rejected_by_founder", "rejected_by_employer", "withdrawn",
  "no_response", "position_closed", "archived", "dismissed",
]

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
  onSubmit: (type: ActionType, until: string | null) => void
}) {
  const [showSnooze, setShowSnooze] = useState(false)
  const [until, setUntil] = useState("")

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
      {currentState && isClosed && (
        <p className="text-xs text-muted-foreground">
          This application is closed. Restore is not available yet.
        </p>
      )}
    </div>
  )
}
