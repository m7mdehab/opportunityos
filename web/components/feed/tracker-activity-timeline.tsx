"use client"

import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"
import type { TrackerActivityEvent } from "@/lib/contract/types"
import { TRACKER_ACTIVITY_CHANGED_EVENT } from "@/lib/tracker-activity"

const STATE_LABELS: Record<string, string> = {
  to_review: "To Review",
  saved: "Saved",
  applied: "Applied",
  recruiter_screen: "Recruiter Screen",
  assessment: "Assessment",
  interviewing: "Interviewing",
  final_interview: "Final Interview",
  offer: "Offer",
  accepted: "Accepted",
  rejected_by_founder: "Rejected",
  rejected_by_employer: "Rejected by employer",
  withdrawn: "Withdrawn",
  no_response: "No response",
  dismissed: "Dismissed",
  snoozed: "Snoozed",
  archived: "Archived",
}

function stateLabel(state: string | null) {
  if (!state) return null
  return STATE_LABELS[state] ?? state.replaceAll("_", " ")
}

function activityLabel(activity: TrackerActivityEvent) {
  switch (activity.action_type) {
    case "saved": return "Saved job"
    case "unsaved": return "Removed from Saved"
    case "restored": return "Restored job"
    case "applied": return "Marked as applied"
    case "rejected_by_founder": return "Rejected job"
    case "rejected_by_employer": return "Rejected by employer"
    case "withdrawn": return "Withdrew application"
    case "no_response": return "Marked no response"
    case "accepted": return "Marked as accepted"
    case "dismissed": return "Dismissed job"
    case "snoozed": return "Snoozed job"
    case "application_stage_updated": return `Application stage changed${activity.to_state ? ` to ${stateLabel(activity.to_state)}` : ""}`
    case "follow_up_created": return "Follow-up added"
    case "follow_up_updated": return "Follow-up updated"
    case "follow_up_completed": return "Follow-up completed"
    case "follow_up_reopened": return "Follow-up reopened"
    case "tracker_note_created": return "Note added"
    case "tracker_note_updated": return "Note updated"
    case "tracker_note_archived": return "Note archived"
    case "interview_added": return "Interview added"
    case "interview_updated": return "Interview updated"
    case "interview_completed": return "Interview completed"
    case "tracker_document_linked": return "Application document linked"
    case "tracker_document_unlinked": return "Application document unlinked"
    default: return "Tracker activity recorded"
  }
}

function displayTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date)
}

function failureMessage(failure: unknown) {
  if (failure instanceof ApiError && failure.body && typeof failure.body === "object" && "detail" in failure.body && typeof failure.body.detail === "string") {
    return failure.body.detail
  }
  return failure instanceof Error ? failure.message : "Could not load activity."
}

export function TrackerActivityTimeline({ opportunityId }: { opportunityId: string }) {
  const [items, setItems] = useState<TrackerActivityEvent[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const response = await api.tracker.activity.list(opportunityId)
      setItems(response.items)
      setTotal(response.total)
      setPage(1)
      setError(null)
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setLoading(false)
    }
  }, [opportunityId])

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const response = await api.tracker.activity.list(opportunityId)
        if (!active) return
        setItems(response.items)
        setTotal(response.total)
        setPage(1)
        setError(null)
      } catch (failure) {
        if (active) setError(failureMessage(failure))
      } finally {
        if (active) setLoading(false)
      }
    }
    const refreshWhenChanged = () => { void refresh() }
    void load()
    window.addEventListener(TRACKER_ACTIVITY_CHANGED_EVENT, refreshWhenChanged)
    return () => {
      active = false
      window.removeEventListener(TRACKER_ACTIVITY_CHANGED_EVENT, refreshWhenChanged)
    }
  }, [opportunityId, refresh])

  async function loadOlder() {
    const nextPage = page + 1
    setLoadingOlder(true)
    setError(null)
    try {
      const response = await api.tracker.activity.list(opportunityId, { page: nextPage })
      setItems((current) => {
        const existing = new Set(current.map((item) => item.id))
        return [...current, ...response.items.filter((item) => !existing.has(item.id))]
      })
      setTotal(response.total)
      setPage(nextPage)
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setLoadingOlder(false)
    }
  }

  return (
    <section aria-labelledby="tracker-activity-heading" data-testid="tracker-activity-timeline">
      <h3 id="tracker-activity-heading" className="text-sm font-semibold">Activity</h3>
      <p className="mt-1 text-xs text-muted-foreground">Recent tracker changes for this job.</p>
      {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
      {loading && <p role="status" className="mt-3 text-xs text-muted-foreground">Loading activity…</p>}
      {!loading && items.length === 0 && <p data-testid="tracker-activity-empty" className="mt-3 text-xs text-muted-foreground">No activity recorded yet.</p>}
      {!loading && items.length > 0 && <ol className="mt-3 space-y-3 border-l pl-4">
        {items.map((item) => <li key={item.id} data-testid="tracker-activity-item" className="relative">
          <span className="absolute -left-[1.31rem] top-1.5 h-2 w-2 rounded-full bg-primary" aria-hidden="true" />
          <p className="text-sm font-medium">{activityLabel(item)}</p>
          {item.from_state && item.to_state && item.from_state !== item.to_state && <p className="text-xs text-muted-foreground">{stateLabel(item.from_state)} → {stateLabel(item.to_state)}</p>}
          <time className="text-[11px] text-muted-foreground" dateTime={item.event_at}>{displayTime(item.event_at)}</time>
        </li>)}
      </ol>}
      {!loading && items.length < total && <Button type="button" size="sm" variant="ghost" className="mt-3" disabled={loadingOlder} onClick={() => void loadOlder()}>{loadingOlder ? "Loading…" : "Load older activity"}</Button>}
    </section>
  )
}
