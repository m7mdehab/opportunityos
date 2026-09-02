"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import type { FeedbackLabel } from "@/lib/contract/types"

const FEEDBACK_OPTIONS: { label: FeedbackLabel; text: string }[] = [
  { label: "good_match", text: "Good match" },
  { label: "bad_match", text: "Bad match" },
  { label: "eligibility_wrong", text: "Not eligible" },
  { label: "irrelevant_role", text: "Wrong track" },
  { label: "duplicate_issue", text: "Duplicate" },
]

export function FeedbackButtons({
  currentLabel,
  submitting,
  onSubmit,
}: {
  currentLabel: FeedbackLabel | null
  submitting: boolean
  onSubmit: (label: FeedbackLabel, note: string | null) => void
}) {
  const [note, setNote] = useState("")

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Feedback">
        {FEEDBACK_OPTIONS.map((opt) => (
          <Button
            key={opt.label}
            type="button"
            size="sm"
            variant={currentLabel === opt.label ? "default" : "outline"}
            disabled={submitting}
            aria-pressed={currentLabel === opt.label}
            onClick={() => onSubmit(opt.label, note.trim() || null)}
          >
            {opt.text}
          </Button>
        ))}
      </div>
      <div className="space-y-1">
        <Label htmlFor="feedback-note">Note (optional)</Label>
        <Textarea
          id="feedback-note"
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add context for this feedback…"
        />
      </div>
    </div>
  )
}
