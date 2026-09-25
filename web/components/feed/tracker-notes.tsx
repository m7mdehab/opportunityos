"use client"

import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"
import type { TrackerNote } from "@/lib/contract/types"

function failureMessage(failure: unknown) {
  if (
    failure instanceof ApiError &&
    failure.body && typeof failure.body === "object" &&
    "detail" in failure.body && typeof failure.body.detail === "string"
  ) {
    return failure.body.detail
  }
  return failure instanceof Error ? failure.message : "Could not update tracker notes."
}

export function TrackerNotes({ opportunityId }: { opportunityId: string }) {
  const [notes, setNotes] = useState<TrackerNote[]>([])
  const [draft, setDraft] = useState("")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState("")
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const response = await api.tracker.notes.list(opportunityId)
    setNotes(response.items)
    setLoading(false)
  }, [opportunityId])

  useEffect(() => {
    let cancelled = false
    api.tracker.notes.list(opportunityId)
      .then((response) => {
        if (!cancelled) setNotes(response.items)
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

  async function addNote() {
    setError(null)
    setSubmitting(true)
    try {
      await api.tracker.notes.create(opportunityId, draft, crypto.randomUUID())
      setDraft("")
      await refresh()
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  async function saveEdit(noteId: string) {
    setError(null)
    setSubmitting(true)
    try {
      await api.tracker.notes.update(
        opportunityId,
        noteId,
        { note_text: editDraft },
        crypto.randomUUID()
      )
      setEditingId(null)
      setEditDraft("")
      await refresh()
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  async function archiveNote(noteId: string) {
    setError(null)
    setSubmitting(true)
    try {
      await api.tracker.notes.update(
        opportunityId,
        noteId,
        { archived: true },
        crypto.randomUUID()
      )
      if (editingId === noteId) setEditingId(null)
      await refresh()
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section aria-labelledby="tracker-notes-heading" data-testid="tracker-notes">
      <h3 id="tracker-notes-heading" className="text-sm font-semibold">Notes</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Private notes for this application. They are not used for job matching.
      </p>

      <div className="mt-3 space-y-2">
        <label htmlFor="new-tracker-note" className="text-xs font-medium">
          Add a note
        </label>
        <textarea
          id="new-tracker-note"
          aria-label="New tracker note"
          maxLength={4000}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          className="min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          placeholder="Record a private application note…"
        />
        <Button
          type="button"
          size="sm"
          onClick={() => void addNote()}
          disabled={loading || submitting || !draft.trim()}
        >
          Add note
        </Button>
      </div>

      {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
      {loading ? (
        <p className="mt-3 text-xs text-muted-foreground">Loading notes…</p>
      ) : notes.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">No notes yet.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {notes.map((note) => (
            <li
              key={note.id}
              data-testid={`tracker-note-${note.id}`}
              className="rounded-md border border-border p-3"
            >
              {editingId === note.id ? (
                <div className="space-y-2">
                  <label htmlFor={`edit-tracker-note-${note.id}`} className="sr-only">
                    Edit note
                  </label>
                  <textarea
                    id={`edit-tracker-note-${note.id}`}
                    aria-label="Edit note"
                    maxLength={4000}
                    value={editDraft}
                    onChange={(event) => setEditDraft(event.target.value)}
                    className="min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => void saveEdit(note.id)}
                      disabled={submitting || !editDraft.trim()}
                    >
                      Save note
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setEditingId(null)
                        setEditDraft("")
                      }}
                      disabled={submitting}
                    >
                      Cancel edit
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <p className="whitespace-pre-wrap text-sm">{note.note_text}</p>
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Updated {new Date(note.updated_at).toLocaleString()}
                  </p>
                  <div className="mt-2 flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setEditingId(note.id)
                        setEditDraft(note.note_text)
                      }}
                      disabled={submitting}
                    >
                      Edit note
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => void archiveNote(note.id)}
                      disabled={submitting}
                    >
                      Archive note
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
