"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"
import type { TrackerDocumentCandidate, TrackerDocumentKind, TrackerDocumentLink } from "@/lib/contract/types"

export const TRACKER_DOCUMENTS_CHANGED_EVENT = "opportunityos:tracker-documents-changed"

function failureMessage(failure: unknown) {
  if (failure instanceof ApiError && failure.body && typeof failure.body === "object" && "detail" in failure.body && typeof failure.body.detail === "string") {
    return failure.body.detail
  }
  return failure instanceof Error ? failure.message : "Could not update application documents."
}

function candidateLabel(candidate: TrackerDocumentCandidate) {
  return `${candidate.label} · ${candidate.format.toUpperCase()}${candidate.recommended ? " · Recommended" : ""}`
}

export function TrackerDocuments({ opportunityId }: { opportunityId: string }) {
  const [links, setLinks] = useState<TrackerDocumentLink[]>([])
  const [candidates, setCandidates] = useState<TrackerDocumentCandidate[]>([])
  const [kind, setKind] = useState<TrackerDocumentKind>("cv")
  const [documentId, setDocumentId] = useState("")
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const visibleCandidates = useMemo(() => candidates.filter((candidate) => candidate.document_kind === kind), [candidates, kind])
  const candidateById = useMemo(() => new Map(candidates.map((candidate) => [candidate.document_id, candidate])), [candidates])

  const refresh = useCallback(async () => {
    const [documents, available] = await Promise.all([
      api.tracker.documents.list(opportunityId),
      api.tracker.documents.candidates(opportunityId),
    ])
    setLinks(documents.items)
    setCandidates(available.items)
    setDocumentId((current) => {
      const choices = available.items.filter((candidate) => candidate.document_kind === kind)
      return choices.some((candidate) => candidate.document_id === current)
        ? current
        : choices.find((candidate) => candidate.recommended)?.document_id ?? choices[0]?.document_id ?? ""
    })
    setLoading(false)
  }, [kind, opportunityId])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      api.tracker.documents.list(opportunityId),
      api.tracker.documents.candidates(opportunityId),
    ])
      .then(([documents, available]) => {
        if (cancelled) return
        setLinks(documents.items)
        setCandidates(available.items)
        const initialKind: TrackerDocumentKind = "cv"
        const choices = available.items.filter((candidate) => candidate.document_kind === initialKind)
        setDocumentId(choices.find((candidate) => candidate.recommended)?.document_id ?? choices[0]?.document_id ?? "")
      })
      .catch((failure: unknown) => { if (!cancelled) setError(failureMessage(failure)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [opportunityId])

  async function linkSelection() {
    if (!documentId) return
    setError(null)
    setSubmitting(true)
    try {
      await api.tracker.documents.link(opportunityId, kind, documentId, crypto.randomUUID())
      await refresh()
      window.dispatchEvent(new Event(TRACKER_DOCUMENTS_CHANGED_EVENT))
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  async function unlink(linkId: string) {
    setError(null)
    setSubmitting(true)
    try {
      await api.tracker.documents.unlink(opportunityId, linkId, crypto.randomUUID())
      await refresh()
      window.dispatchEvent(new Event(TRACKER_DOCUMENTS_CHANGED_EVENT))
    } catch (failure) {
      setError(failureMessage(failure))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section aria-labelledby="tracker-documents-heading" data-testid="tracker-documents">
      <h3 id="tracker-documents-heading" className="text-sm font-semibold">Application documents</h3>
      <p className="mt-1 text-xs text-muted-foreground">Choose the résumé or cover letter associated with this application. Files stay in their existing storage.</p>
      {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
      {loading && <p role="status" className="mt-3 text-xs text-muted-foreground">Loading application documents…</p>}
      {!loading && links.length === 0 && <p data-testid="tracker-documents-empty" className="mt-3 text-xs text-muted-foreground">No documents selected yet.</p>}
      {!loading && links.length > 0 && <ul className="mt-3 space-y-2">
        {links.map((link) => {
          const candidate = candidateById.get(link.document_id)
          const label = candidate?.label ?? (link.document_kind === "cv" ? "Résumé selection" : "Cover letter selection")
          const kindLabel = link.document_kind === "cv" ? "Résumé" : "Cover letter"
          return <li key={link.id} data-testid={`tracker-document-${link.document_kind}`} className="flex items-center justify-between gap-3 rounded-md border p-3">
            <div className="min-w-0">
              <p className="text-xs font-medium">{kindLabel}</p>
              <p className="truncate text-sm">{label}</p>
            </div>
            <Button type="button" size="sm" variant="outline" disabled={submitting} aria-label={`Unlink ${kindLabel.toLowerCase()}`} onClick={() => void unlink(link.id)}>Unlink</Button>
          </li>
        })}
      </ul>}
      <div className="mt-4 grid gap-3 border-t pt-3 sm:grid-cols-[minmax(9rem,0.7fr)_minmax(0,1.3fr)_auto] sm:items-end">
        <label className="space-y-1 text-xs font-medium">Document type
          <select aria-label="Document type" value={kind} onChange={(event) => {
            const nextKind = event.target.value as TrackerDocumentKind
            setKind(nextKind)
            const choices = candidates.filter((candidate) => candidate.document_kind === nextKind)
            setDocumentId(choices.find((candidate) => candidate.recommended)?.document_id ?? choices[0]?.document_id ?? "")
          }} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm font-normal">
            <option value="cv">Résumé</option>
            <option value="cover_letter">Cover letter</option>
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium">Available selection
          <select aria-label="Available document" value={documentId} onChange={(event) => setDocumentId(event.target.value)} disabled={loading || visibleCandidates.length === 0} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm font-normal">
            {visibleCandidates.length === 0 && <option value="">No candidates available</option>}
            {visibleCandidates.map((candidate) => <option key={candidate.document_id} value={candidate.document_id}>{candidateLabel(candidate)}</option>)}
          </select>
        </label>
        <Button type="button" size="sm" disabled={loading || submitting || !documentId} onClick={() => void linkSelection()}>Link selection</Button>
      </div>
    </section>
  )
}
