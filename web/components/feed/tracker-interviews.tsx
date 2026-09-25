"use client"

import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"
import type { TrackerInterview, TrackerInterviewFormat, TrackerInterviewOutcome, TrackerInterviewType } from "@/lib/contract/types"

export const TRACKER_INTERVIEWS_CHANGED_EVENT = "opportunityos:tracker-interviews-changed"

type InterviewDraft = {
  scheduled_at: string
  round_label: string
  interview_type: TrackerInterviewType | ""
  interview_format: TrackerInterviewFormat | ""
  interviewer_name: string
  preparation_notes: string
  post_interview_notes: string
  outcome: TrackerInterviewOutcome
}

const EMPTY_DRAFT: InterviewDraft = {
  scheduled_at: "", round_label: "", interview_type: "", interview_format: "",
  interviewer_name: "", preparation_notes: "", post_interview_notes: "", outcome: "pending",
}

const TYPES: Array<[TrackerInterviewType, string]> = [
  ["recruiter_screen", "Recruiter screen"], ["hiring_manager", "Hiring manager"],
  ["technical", "Technical"], ["take_home", "Take home"], ["live_coding", "Live coding"],
  ["case_study", "Case study"], ["panel", "Panel"], ["final", "Final"], ["other", "Other"],
]
const FORMATS: Array<[TrackerInterviewFormat, string]> = [["phone", "Phone"], ["video", "Video"], ["in_person", "In person"]]
const OUTCOMES: Array<[TrackerInterviewOutcome, string]> = [
  ["pending", "Pending"], ["completed", "Completed"], ["passed", "Passed"],
  ["not_selected", "Not selected"], ["cancelled", "Cancelled"], ["other", "Other"],
]

function failureMessage(failure: unknown) {
  if (failure instanceof ApiError && failure.body && typeof failure.body === "object" && "detail" in failure.body && typeof failure.body.detail === "string") {
    return failure.body.detail
  }
  return failure instanceof Error ? failure.message : "Could not update interviews."
}

function localInputValue(value: string | null) {
  if (!value) return ""
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ""
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function displaySchedule(value: string | null) {
  if (!value) return "Time not set"
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : `${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(date)} UTC`
}

function requestBody(draft: InterviewDraft) {
  return {
    scheduled_at: draft.scheduled_at ? new Date(draft.scheduled_at).toISOString() : null,
    round_label: draft.round_label.trim() || null,
    interview_type: draft.interview_type || null,
    interview_format: draft.interview_format || null,
    interviewer_name: draft.interviewer_name.trim() || null,
    preparation_notes: draft.preparation_notes.trim() || null,
    post_interview_notes: draft.post_interview_notes.trim() || null,
    outcome: draft.outcome,
  }
}

function draftFromInterview(interview: TrackerInterview): InterviewDraft {
  return {
    scheduled_at: localInputValue(interview.scheduled_at),
    round_label: interview.round_label ?? "",
    interview_type: interview.interview_type ?? "",
    interview_format: interview.interview_format ?? "",
    interviewer_name: interview.interviewer_name ?? "",
    preparation_notes: interview.preparation_notes ?? "",
    post_interview_notes: interview.post_interview_notes ?? "",
    outcome: interview.outcome ?? "pending",
  }
}

export function TrackerInterviews({ opportunityId }: { opportunityId: string }) {
  const [interviews, setInterviews] = useState<TrackerInterview[]>([])
  const [draft, setDraft] = useState<InterviewDraft>(EMPTY_DRAFT)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<InterviewDraft>(EMPTY_DRAFT)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const response = await api.tracker.interviews.list(opportunityId)
    setInterviews(response.items)
    setLoading(false)
  }, [opportunityId])

  useEffect(() => {
    let cancelled = false
    api.tracker.interviews.list(opportunityId)
      .then((response) => { if (!cancelled) setInterviews(response.items) })
      .catch((failure: unknown) => { if (!cancelled) setError(failureMessage(failure)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [opportunityId])

  async function submitCreate() {
    setError(null)
    setSubmitting(true)
    try {
      await api.tracker.interviews.create(opportunityId, requestBody(draft), crypto.randomUUID())
      setDraft(EMPTY_DRAFT)
      await refresh()
      window.dispatchEvent(new Event(TRACKER_INTERVIEWS_CHANGED_EVENT))
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  async function submitUpdate(interviewId: string, nextDraft = editDraft) {
    setError(null)
    setSubmitting(true)
    try {
      await api.tracker.interviews.update(opportunityId, interviewId, requestBody(nextDraft), crypto.randomUUID())
      setEditingId(null)
      await refresh()
      window.dispatchEvent(new Event(TRACKER_INTERVIEWS_CHANGED_EVENT))
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  function fields(prefix: string, value: InterviewDraft, setValue: (draft: InterviewDraft) => void) {
    const id = (name: string) => `${prefix}-interview-${name}`
    return (
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-xs font-medium">Schedule (your local time)
          <input id={id("scheduled-at")} aria-label={`${prefix} interview schedule`} type="datetime-local" value={value.scheduled_at} onChange={(event) => setValue({ ...value, scheduled_at: event.target.value })} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm font-normal" />
        </label>
        <label className="space-y-1 text-xs font-medium">Round
          <input id={id("round-label")} aria-label={`${prefix} interview round`} maxLength={64} value={value.round_label} onChange={(event) => setValue({ ...value, round_label: event.target.value })} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm font-normal" placeholder="Round 1" />
        </label>
        <label className="space-y-1 text-xs font-medium">Interview type
          <select id={id("type")} aria-label={`${prefix} interview type`} value={value.interview_type} onChange={(event) => setValue({ ...value, interview_type: event.target.value as InterviewDraft["interview_type"] })} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm font-normal">
            <option value="">Choose type</option>{TYPES.map(([type, label]) => <option key={type} value={type}>{label}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium">Format
          <select id={id("format")} aria-label={`${prefix} interview format`} value={value.interview_format} onChange={(event) => setValue({ ...value, interview_format: event.target.value as InterviewDraft["interview_format"] })} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm font-normal">
            <option value="">Choose format</option>{FORMATS.map(([format, label]) => <option key={format} value={format}>{label}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium">Interviewer
          <input id={id("interviewer")} aria-label={`${prefix} interviewer`} maxLength={128} value={value.interviewer_name} onChange={(event) => setValue({ ...value, interviewer_name: event.target.value })} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm font-normal" />
        </label>
        <label className="space-y-1 text-xs font-medium">Outcome
          <select id={id("outcome")} aria-label={`${prefix} interview outcome`} value={value.outcome} onChange={(event) => setValue({ ...value, outcome: event.target.value as TrackerInterviewOutcome })} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm font-normal">
            {OUTCOMES.map(([outcome, label]) => <option key={outcome} value={outcome}>{label}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium sm:col-span-2">Private preparation notes
          <textarea id={id("preparation-notes")} aria-label={`${prefix} preparation notes`} maxLength={4000} value={value.preparation_notes} onChange={(event) => setValue({ ...value, preparation_notes: event.target.value })} className="min-h-16 w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-normal" />
        </label>
        <label className="space-y-1 text-xs font-medium sm:col-span-2">Private post-interview notes
          <textarea id={id("post-interview-notes")} aria-label={`${prefix} post-interview notes`} maxLength={4000} value={value.post_interview_notes} onChange={(event) => setValue({ ...value, post_interview_notes: event.target.value })} className="min-h-16 w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-normal" />
        </label>
      </div>
    )
  }

  return (
    <section aria-labelledby="tracker-interviews-heading" data-testid="tracker-interviews">
      <h3 id="tracker-interviews-heading" className="text-sm font-semibold">Interviews</h3>
      <p className="mt-1 text-xs text-muted-foreground">Track interview rounds and keep preparation and debrief notes private to this job.</p>
      {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
      {loading && <p role="status" className="mt-3 text-xs text-muted-foreground">Loading interviews…</p>}
      {!loading && interviews.length === 0 && <p data-testid="tracker-interviews-empty" className="mt-3 text-xs text-muted-foreground">No interviews recorded yet.</p>}
      {interviews.length > 0 && <ul className="mt-3 space-y-3">
        {interviews.map((interview) => <li key={interview.id} data-testid={`tracker-interview-${interview.id}`} className="rounded-md border p-3">
          {editingId === interview.id ? <>
            {fields("Edit", editDraft, setEditDraft)}
            <div className="mt-3 flex gap-2">
              <Button type="button" size="sm" onClick={() => void submitUpdate(interview.id)} disabled={submitting}>Save interview</Button>
              <Button type="button" size="sm" variant="outline" onClick={() => setEditingId(null)} disabled={submitting}>Cancel edit</Button>
            </div>
          </> : <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-medium">{interview.round_label || (interview.interview_type ? TYPES.find(([type]) => type === interview.interview_type)?.[1] : null) || "Interview"}</p>
                <p className="text-xs text-muted-foreground">{displaySchedule(interview.scheduled_at)}{interview.interviewer_name ? ` · ${interview.interviewer_name}` : ""}</p>
              </div>
              <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{OUTCOMES.find(([outcome]) => outcome === interview.outcome)?.[1] ?? "Pending"}</span>
            </div>
            {interview.preparation_notes && <p className="mt-2 whitespace-pre-wrap text-sm"><span className="font-medium">Preparation:</span> {interview.preparation_notes}</p>}
            {interview.post_interview_notes && <p className="mt-2 whitespace-pre-wrap text-sm"><span className="font-medium">Debrief:</span> {interview.post_interview_notes}</p>}
            <div className="mt-3 flex flex-wrap gap-2">
              <Button type="button" size="sm" variant="outline" disabled={submitting} onClick={() => { setEditingId(interview.id); setEditDraft(draftFromInterview(interview)) }}>Edit interview</Button>
              {interview.outcome === "pending" && <Button type="button" size="sm" variant="ghost" disabled={submitting} onClick={() => void submitUpdate(interview.id, { ...draftFromInterview(interview), outcome: "completed" })}>Complete interview</Button>}
            </div>
          </>}
        </li>)}
      </ul>}
      <div className="mt-4 border-t pt-3">
        <h4 className="text-xs font-semibold">Add an interview</h4>
        {fields("New", draft, setDraft)}
        <Button type="button" size="sm" className="mt-3" disabled={submitting} onClick={() => void submitCreate()}>Add interview</Button>
      </div>
    </section>
  )
}
