"use client"

import { useEffect, useState } from "react"
import { OpportunityCard } from "@/components/feed/opportunity-card"
import { Button } from "@/components/ui/button"
import { TRACKER_FOLLOW_UPS_CHANGED_EVENT } from "@/components/feed/tracker-followups"
import { api } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"
import type {
  OpportunityListItem,
  TrackerBucket,
  TrackerFollowUpBucket,
  TrackerFollowUpSummaryResponse,
  TrackerListResponse,
} from "@/lib/contract/types"

const PAGE_SIZE = 20
const BUCKETS: Array<{ value: TrackerBucket; label: string }> = [
  { value: "saved", label: "Saved" },
  { value: "applied", label: "Applied" },
  { value: "rejected", label: "Rejected / Closed" },
  { value: "all", label: "All Tracked" },
]
const FOLLOW_UP_BUCKETS: Array<{ value: TrackerFollowUpBucket; label: string }> = [
  { value: "due_today", label: "Due today" },
  { value: "overdue", label: "Overdue" },
  { value: "upcoming", label: "Upcoming" },
]

function requestError(error: unknown): string {
  if (error instanceof ApiError && error.body && typeof error.body === "object" && "detail" in error.body && typeof error.body.detail === "string") {
    return error.body.detail
  }
  return error instanceof Error ? error.message : "Could not load tracked jobs."
}

export function TrackerView({
  onOpen,
  refreshKey,
}: {
  onOpen: (item: Pick<OpportunityListItem, "id" | "tracker_state" | "action_state">) => void
  refreshKey: number
}) {
  const [bucket, setBucket] = useState<TrackerBucket>("saved")
  const [page, setPage] = useState(1)
  const [result, setResult] = useState<TrackerListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [followUpBucket, setFollowUpBucket] = useState<TrackerFollowUpBucket>("due_today")
  const [followUpResult, setFollowUpResult] = useState<TrackerFollowUpSummaryResponse | null>(null)
  const [followUpError, setFollowUpError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.tracker
      .list({ bucket, page, page_size: PAGE_SIZE })
      .then((response) => {
        if (cancelled) return
        setResult(response)
        setError(null)
      })
      .catch((requestFailure: unknown) => {
        if (cancelled) return
        setError(requestError(requestFailure))
      })
    return () => {
      cancelled = true
    }
  }, [bucket, page, refreshKey])

  useEffect(() => {
    let cancelled = false
    const loadFollowUps = () => {
      api.tracker.followUps.overview(followUpBucket, { page: 1, page_size: 25 })
        .then((response) => {
          if (cancelled) return
          setFollowUpResult(response)
          setFollowUpError(null)
        })
        .catch((requestFailure: unknown) => {
          if (cancelled) return
          setFollowUpError(requestError(requestFailure))
        })
    }
    loadFollowUps()
    window.addEventListener(TRACKER_FOLLOW_UPS_CHANGED_EVENT, loadFollowUps)
    return () => {
      cancelled = true
      window.removeEventListener(TRACKER_FOLLOW_UPS_CHANGED_EVENT, loadFollowUps)
    }
  }, [followUpBucket, refreshKey])

  const currentResult = result?.bucket === bucket && result.page === page ? result : null
  const pageCount = Math.max(1, Math.ceil((currentResult?.total ?? 0) / PAGE_SIZE))
  const loading = currentResult === null && error === null

  return (
    <section aria-label="Job tracker" data-testid="tracker-view" className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Tracker</h2>
        <p className="text-sm text-muted-foreground">
          Keep saved and applied jobs together as they move through your search.
        </p>
      </div>

      <section aria-labelledby="tracker-follow-up-overview-heading" data-testid="tracker-follow-ups-overview" className="rounded-lg border p-4">
        <div>
          <h3 id="tracker-follow-up-overview-heading" className="text-sm font-semibold">Follow-up reminders</h3>
          <p className="mt-1 text-xs text-muted-foreground">Review dates for saved and applied jobs.</p>
        </div>
        <div role="tablist" aria-label="Follow-up reminder buckets" className="mt-3 flex flex-wrap gap-2">
          {FOLLOW_UP_BUCKETS.map((item) => (
            <Button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={followUpBucket === item.value}
              variant={followUpBucket === item.value ? "default" : "outline"}
              size="sm"
              data-testid={`tracker-follow-up-bucket-${item.value}`}
              onClick={() => {
                setFollowUpBucket(item.value)
                setFollowUpError(null)
              }}
            >
              {item.label}
            </Button>
          ))}
        </div>
        {followUpError && <p role="alert" className="mt-3 text-sm text-destructive">{followUpError}</p>}
        {!followUpError && (!followUpResult || followUpResult.bucket !== followUpBucket) && (
          <p role="status" className="mt-3 text-xs text-muted-foreground">Loading follow-ups…</p>
        )}
        {followUpResult?.bucket === followUpBucket && followUpResult.items.length === 0 && (
          <p data-testid="tracker-follow-ups-empty" className="mt-3 text-sm text-muted-foreground">
            {followUpBucket === "due_today"
              ? "No follow-ups due today."
              : followUpBucket === "overdue"
                ? "No overdue follow-ups."
                : "No upcoming follow-ups."}
          </p>
        )}
        {followUpResult?.bucket === followUpBucket && followUpResult.items.length > 0 && (
          <ul className="mt-3 divide-y">
            {followUpResult.items.map((item) => (
              <li key={item.id} data-testid={`tracker-follow-up-summary-${item.id}`} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                <div>
                  <p className="text-sm font-medium">{item.opportunity.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {item.opportunity.organization} · {new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone: "UTC" }).format(new Date(`${item.due_date}T00:00:00Z`))}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => onOpen({
                    id: item.opportunity.id,
                    tracker_state: item.opportunity.tracker_state,
                    action_state: item.opportunity.tracker_state,
                  })}
                >
                  Open job
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div role="tablist" aria-label="Tracker buckets" className="flex flex-wrap gap-2">
        {BUCKETS.map((item) => (
          <Button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={bucket === item.value}
            variant={bucket === item.value ? "default" : "outline"}
            size="sm"
            data-testid={`tracker-bucket-${item.value}`}
            onClick={() => {
              setBucket(item.value)
              setPage(1)
              setError(null)
            }}
          >
            {item.label}
          </Button>
        ))}
      </div>

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {loading && <p role="status" className="text-sm text-muted-foreground">Loading tracked jobs…</p>}
      {currentResult && currentResult.items.length === 0 && (
        <p data-testid="tracker-empty-state" className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
          {bucket === "saved"
            ? "No saved jobs yet. Save a job from Jobs / To Review to keep it here."
            : bucket === "applied"
              ? "No applied jobs yet. Mark a job applied after you submit an application."
              : bucket === "rejected"
                ? "No rejected or closed jobs yet."
                : "No tracked jobs yet. Save, apply, or reject a job to start your tracker."}
        </p>
      )}
      {currentResult && currentResult.items.length > 0 && (
        <>
          <p data-testid="tracker-count" className="text-xs text-muted-foreground">
            {currentResult.total} tracked job{currentResult.total === 1 ? "" : "s"}
          </p>
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {currentResult.items.map((item) => (
              <OpportunityCard
                key={item.id}
                opportunity={item}
                onOpen={() => onOpen(item)}
              />
            ))}
          </ul>
          {pageCount > 1 && (
            <nav aria-label="Tracker pages" className="mt-5 flex items-center justify-center gap-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                Previous
              </Button>
              <span className="text-xs text-muted-foreground" aria-live="polite">
                Page {page} of {pageCount}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page >= pageCount}
                onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
              >
                Next
              </Button>
            </nav>
          )}
        </>
      )}
    </section>
  )
}
