"use client"

import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"
import type { TrackerFollowUp, TrackerFollowUpStatus } from "@/lib/contract/types"

export const TRACKER_FOLLOW_UPS_CHANGED_EVENT = "opportunityos:tracker-follow-ups-changed"

function failureMessage(failure: unknown) {
  if (
    failure instanceof ApiError &&
    failure.body && typeof failure.body === "object" &&
    "detail" in failure.body && typeof failure.body.detail === "string"
  ) {
    return failure.body.detail
  }
  return failure instanceof Error ? failure.message : "Could not update follow-ups."
}

function displayDate(value: string) {
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone: "UTC" }).format(date)
}

const STATUS_LABELS: Record<TrackerFollowUpStatus, string> = {
  overdue: "Overdue",
  due_today: "Due today",
  upcoming: "Upcoming",
  completed: "Completed",
}

export function TrackerFollowUps({ opportunityId }: { opportunityId: string }) {
  const [followUps, setFollowUps] = useState<TrackerFollowUp[]>([])
  const [dueDate, setDueDate] = useState("")
  const [draftNote, setDraftNote] = useState("")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDueDate, setEditDueDate] = useState("")
  const [editNote, setEditNote] = useState("")
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const response = await api.tracker.followUps.list(opportunityId)
    setFollowUps(response.items)
    setLoading(false)
  }, [opportunityId])

  useEffect(() => {
    let cancelled = false
    api.tracker.followUps.list(opportunityId)
      .then((response) => {
        if (!cancelled) setFollowUps(response.items)
      })
      .catch((failure: unknown) => {
        if (!cancelled) setError(failureMessage(failure))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [opportunityId])

  async function addFollowUp() {
    setError(null)
    setSubmitting(true)
    try {
      await api.tracker.followUps.create(
        opportunityId,
        { due_date: dueDate, note_text: draftNote.trim() || null },
        crypto.randomUUID(),
      )
      setDueDate("")
      setDraftNote("")
      await refresh()
      window.dispatchEvent(new Event(TRACKER_FOLLOW_UPS_CHANGED_EVENT))
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  async function saveFollowUp(followUpId: string) {
    setError(null)
    setSubmitting(true)
    try {
      await api.tracker.followUps.update(
        opportunityId,
        followUpId,
        { due_date: editDueDate, note_text: editNote.trim() || null },
        crypto.randomUUID(),
      )
      setEditingId(null)
      await refresh()
      window.dispatchEvent(new Event(TRACKER_FOLLOW_UPS_CHANGED_EVENT))
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  async function setCompleted(followUp: TrackerFollowUp, completed: boolean) {
    setError(null)
    setSubmitting(true)
    try {
      await api.tracker.followUps.update(
        opportunityId,
        followUp.id,
        { completed },
        crypto.randomUUID(),
      )
      if (editingId === followUp.id) setEditingId(null)
      await refresh()
      window.dispatchEvent(new Event(TRACKER_FOLLOW_UPS_CHANGED_EVENT))
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section aria-labelledby="tracker-follow-ups-heading" data-testid="tracker-follow-ups">
      <h3 id="tracker-follow-ups-heading" className="text-sm font-semibold">Follow-ups</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Set a private reminder date for this saved or applied job.
      </p>

      <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(10rem,auto)_1fr]">
        <div className="space-y-2">
          <label htmlFor="new-tracker-follow-up-date" className="text-xs font-medium">Due date</label>
          <input
            id="new-tracker-follow-up-date"
            aria-label="Follow-up due date"
            type="date"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          />
        </div>
        <div className="space-y-2">
          <label htmlFor="new-tracker-follow-up-note" className="text-xs font-medium">Private note (optional)</label>
          <textarea
            id="new-tracker-follow-up-note"
            aria-label="Follow-up note"
            maxLength={4000}
            value={draftNote}
            onChange={(event) => setDraftNote(event.target.value)}
            className="min-h-16 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            placeholder="For example, ask about the interview timeline…"
          />
        </div>
      </div>
      <Button
        type="button"
        size="sm"
        onClick={() => void addFollowUp()}
        disabled={loading || submitting || !dueDate}
      >
        Add follow-up
      </Button>

      {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
      {loading ? (
        <p role="status" className="mt-3 text-xs text-muted-foreground">Loading follow-ups…</p>
      ) : followUps.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">No follow-ups yet.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {followUps.map((followUp) => (
            <li
              key={followUp.id}
              data-testid={`tracker-follow-up-${followUp.id}`}
              className="rounded-md border border-border p-3"
            >
              {editingId === followUp.id ? (
                <div className="space-y-2">
                  <label htmlFor={`edit-follow-up-date-${followUp.id}`} className="text-xs font-medium">Due date</label>
                  <input
                    id={`edit-follow-up-date-${followUp.id}`}
                    aria-label="Edit follow-up due date"
                    type="date"
                    value={editDueDate}
                    onChange={(event) => setEditDueDate(event.target.value)}
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                  />
                  <label htmlFor={`edit-follow-up-note-${followUp.id}`} className="text-xs font-medium">Private note</label>
                  <textarea
                    id={`edit-follow-up-note-${followUp.id}`}
                    aria-label="Edit follow-up note"
                    maxLength={4000}
                    value={editNote}
                    onChange={(event) => setEditNote(event.target.value)}
                    className="min-h-16 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                  <div className="flex gap-2">
                    <Button type="button" size="sm" onClick={() => void saveFollowUp(followUp.id)} disabled={submitting || !editDueDate}>
                      Save follow-up
                    </Button>
                    <Button type="button" size="sm" variant="outline" onClick={() => setEditingId(null)} disabled={submitting}>
                      Cancel edit
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium">{displayDate(followUp.due_date)}</p>
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                      {STATUS_LABELS[followUp.status]}
                    </span>
                  </div>
                  {followUp.note_text && <p className="mt-2 whitespace-pre-wrap text-sm">{followUp.note_text}</p>}
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {followUp.completed_at ? `Completed ${new Date(followUp.completed_at).toLocaleString()}` : `Updated ${new Date(followUp.updated_at).toLocaleString()}`}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setEditingId(followUp.id)
                        setEditDueDate(followUp.due_date)
                        setEditNote(followUp.note_text ?? "")
                      }}
                      disabled={submitting}
                    >
                      Edit follow-up
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => void setCompleted(followUp, !followUp.completed_at)}
                      disabled={submitting}
                    >
                      {followUp.completed_at ? "Reopen follow-up" : "Complete follow-up"}
                    </Button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
