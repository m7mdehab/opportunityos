"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { ActionState, ActionType } from "@/lib/contract/types"

const ACTION_STATE_LABEL: Record<string, string> = {
  submitted: "Marked applied",
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
          disabled={submitting}
          onClick={() => onSubmit("mark_applied", null)}
        >
          Mark applied
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={submitting}
          onClick={() => onSubmit("dismiss", null)}
        >
          Dismiss
        </Button>
        {currentState && (
          <Button type="button" size="sm" variant="ghost" disabled={submitting} onClick={() => onSubmit("clear", null)}>
            Clear / undo
          </Button>
        )}
        {!showSnooze ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={submitting}
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
    </div>
  )
}
