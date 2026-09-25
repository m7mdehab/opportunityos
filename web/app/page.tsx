"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { HeaderStrip } from "@/components/feed/header-strip"
import { FilterBar, type FeedFilters } from "@/components/feed/filter-bar"
import { FeedQueryChips, FeedQueryDrawer } from "@/components/feed/feed-query-drawer"
import { OpportunityCard } from "@/components/feed/opportunity-card"
import { TrackerView } from "@/components/feed/tracker-view"
import { DetailDrawer } from "@/components/feed/detail-drawer"
import { FiltersDrawer } from "@/components/feed/filters-drawer"
import { FacetsPanel } from "@/components/feed/facets-panel"
import { HiddenReasonsPanel } from "@/components/feed/hidden-reasons-panel"
import { ManualSourcesPanel } from "@/components/feed/manual-sources-panel"
import { TutoringSurface } from "@/components/feed/tutoring-surface"
import { OverHidingWarningBanner } from "@/components/feed/over-hiding-warning"
import { Button } from "@/components/ui/button"
import { EyeOff, Eye, SlidersHorizontal, Search, GraduationCap } from "lucide-react"
import {
  NoTruthPackState,
  InvalidTruthPackState,
  NoOpportunitiesYetState,
  WorkerIdleState,
  NoFilterMatchesState,
} from "@/components/feed/empty-states"
import { api } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"
import type { ActionResponse, FeedFilterMetadataResponse, FeedQueryState } from "@/lib/contract/types"
import { notifyTrackerActivityChanged } from "@/lib/tracker-activity"
import {
  EMPTY_FEED_QUERY,
  hasActiveFeedQuery,
  parseFeedQueryParams,
  updateFeedUrlParams,
} from "@/lib/feed-query-state"
import { computeOverHidingWarning } from "@/lib/format/over-hiding"
import type {
  ActionState,
  DashboardResponse,
  FeedbackLabel,
  OpportunityListItem,
  SourceHealth,
  TruthStatusResponse,
} from "@/lib/contract/types"

type AuthPhase = "checking" | "authenticated" | "redirecting"
const PAGE_SIZE = 50
const UNDO_PROMPT_MS = 10_000

type UndoNotice = { opportunityId: string; eventId: string; label: string }

export default function FeedPage() {
  const router = useRouter()
  const [authPhase, setAuthPhase] = useState<AuthPhase>("checking")

  const [truth, setTruth] = useState<TruthStatusResponse | null>(null)
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [sources, setSources] = useState<SourceHealth[] | null>(null)

  const [query, setQuery] = useState<FeedQueryState>(EMPTY_FEED_QUERY)
  const [queryReady, setQueryReady] = useState(false)
  const [feedMetadata, setFeedMetadata] = useState<FeedFilterMetadataResponse | null>(null)
  const [feedMetadataError, setFeedMetadataError] = useState<string | null>(null)
  const [items, setItems] = useState<OpportunityListItem[] | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedActionState, setSelectedActionState] = useState<ActionState>(null)
  const [activeWorkspace, setActiveWorkspace] = useState<"jobs" | "tracker">("jobs")
  const [trackerRefreshKey, setTrackerRefreshKey] = useState(0)
  const [polling, setPolling] = useState(false)
  const [undoNotice, setUndoNotice] = useState<UndoNotice | null>(null)
  const [undoError, setUndoError] = useState<string | null>(null)
  const [undoSubmitting, setUndoSubmitting] = useState(false)
  const [triagePendingId, setTriagePendingId] = useState<string | null>(null)
  const [triageError, setTriageError] = useState<{ id: string; message: string } | null>(null)

  // ---- D3 founder-controlled filters ----
  const [filtersDrawerOpen, setFiltersDrawerOpen] = useState(false)
  const [hiddenCount, setHiddenCount] = useState(0)
  // "Show N hidden" — a deliberate, visible, switchable control per the
  // founder's stated requirement (see d3-contract.md §6): nothing that a
  // `hide`-mode filter removes stays removed without a way back to it.

  // ---- C1 facets panel / C4 hidden-reasons / E23 manual sources ----
  const [facetsPanelOpen, setFacetsPanelOpen] = useState(false)
  const [feedQueryDrawerOpen, setFeedQueryDrawerOpen] = useState(false)
  const advancedFeedTriggerRef = useRef<HTMLButtonElement | null>(null)
  const previousFeedQueryDrawerOpen = useRef(false)
  const [hiddenReasonsOpen, setHiddenReasonsOpen] = useState(false)
  const [manualSourcesOpen, setManualSourcesOpen] = useState(false)

  // ---- keyboard navigation (C3 required behaviour #4: j/k/o/a/x) ----
  const [focusedIndex, setFocusedIndex] = useState(0)
  const cardRefs = useRef<Map<string, HTMLButtonElement>>(new Map())
  const anyPanelOpen =
    filtersDrawerOpen ||
    feedQueryDrawerOpen ||
    facetsPanelOpen ||
    hiddenReasonsOpen ||
    manualSourcesOpen ||
    selectedId !== null

  // ---- auth gate ----
  useEffect(() => {
    let cancelled = false
    api.auth
      .me()
      .then(() => {
        if (!cancelled) setAuthPhase("authenticated")
      })
      .catch(() => {
        if (!cancelled) {
          setAuthPhase("redirecting")
          router.replace("/login")
        }
      })
    return () => {
      cancelled = true
    }
  }, [router])

  // Hydrate the shareable feed query before the first list request, and
  // restore it when the browser moves backward or forward in history.
  useEffect(() => {
    const restore = () => {
      const parsed = parseFeedQueryParams(new URLSearchParams(window.location.search))
      setQuery(parsed.filters)
      setPage(parsed.page)
      setQueryReady(true)
    }
    restore()
    window.addEventListener("popstate", restore)
    return () => window.removeEventListener("popstate", restore)
  }, [])

  useEffect(() => {
    if (authPhase !== "authenticated") return
    api.feedFilterMetadata.get().then(setFeedMetadata).catch((error: unknown) => {
      setFeedMetadata(null)
      const detail = error instanceof ApiError && error.body && typeof error.body === "object" && "detail" in error.body && typeof error.body.detail === "string"
        ? error.body.detail
        : error instanceof Error ? error.message : "Advanced feed metadata is unavailable from this API adapter."
      setFeedMetadataError(detail)
    })
  }, [authPhase])

  useEffect(() => {
    if (!queryReady) return
    const timer = window.setTimeout(() => {
      const current = new URLSearchParams(window.location.search)
      const next = updateFeedUrlParams(current, query, page, PAGE_SIZE)
      if (next.toString() === current.toString()) return
      const search = next.toString()
      window.history.pushState({ feedQuery: true }, "", `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [page, query, queryReady])

  const filters: FeedFilters = {
    track: query.track as FeedFilters["track"],
    decision: query.decision as FeedFilters["decision"],
    minScore: query.scoreRanges.fit_score.min,
    q: query.q,
  }

  const handleQueryChange = useCallback((next: FeedQueryState) => {
    setPage(1)
    setQuery(next)
  }, [])

  const refreshDashboard = useCallback(() => {
    api.dashboard.daily(7).then(setDashboard).catch(() => undefined)
  }, [])

  const refreshSources = useCallback(() => {
    api.sources
      .health()
      .then((r) => setSources(r.sources))
      .catch(() => undefined)
  }, [])

  const refreshTruth = useCallback(() => {
    api.truth.status().then(setTruth).catch(() => undefined)
  }, [])

  const refreshList = useCallback(() => {
    setListLoading(true)
    setListError(null)
    api.opportunities
      .list({
        track: query.track || undefined,
        decision: query.decision || undefined,
        min_score: query.scoreRanges.fit_score.min ? Number(query.scoreRanges.fit_score.min) : undefined,
        min_fit_score: query.scoreRanges.fit_score.min ? Number(query.scoreRanges.fit_score.min) : undefined,
        max_fit_score: query.scoreRanges.fit_score.max ? Number(query.scoreRanges.fit_score.max) : undefined,
        min_preference_score: query.scoreRanges.preference_score.min ? Number(query.scoreRanges.preference_score.min) : undefined,
        max_preference_score: query.scoreRanges.preference_score.max ? Number(query.scoreRanges.preference_score.max) : undefined,
        min_confidence_score: query.scoreRanges.confidence_score.min ? Number(query.scoreRanges.confidence_score.min) : undefined,
        max_confidence_score: query.scoreRanges.confidence_score.max ? Number(query.scoreRanges.confidence_score.max) : undefined,
        min_priority_score: query.scoreRanges.priority_score.min ? Number(query.scoreRanges.priority_score.min) : undefined,
        max_priority_score: query.scoreRanges.priority_score.max ? Number(query.scoreRanges.priority_score.max) : undefined,
        posted_from: query.postedFrom || undefined,
        posted_to: query.postedTo || undefined,
        ...query.multi,
        sort_by: query.sortBy,
        q: query.q || undefined,
        page,
        page_size: PAGE_SIZE,
        include_hidden: query.includeHidden,
      })
      .then((res) => {
        setItems(res.items)
        setTotal(res.total)
        setHiddenCount(res.hidden_count)
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login")
          return
        }
        const detail = err instanceof ApiError && err.body && typeof err.body === "object" && "detail" in err.body && typeof err.body.detail === "string"
          ? err.body.detail
          : "Could not load opportunities."
        setListError(detail)
      })
      .finally(() => setListLoading(false))
  }, [query, page, router])

  const refreshFromFirstPage = useCallback(() => {
    if (page === 1) refreshList()
    else setPage(1)
  }, [page, refreshList])

  useEffect(() => {
    if (authPhase !== "authenticated") return
    refreshTruth()
    refreshSources()
  }, [authPhase, refreshTruth, refreshSources])

  useEffect(() => {
    if (authPhase !== "authenticated" || !queryReady) return
    // Standard data-fetching effect (React docs: "Fetching data" under
    // "You Might Not Need an Effect"): setting the loading flag synchronously
    // before the async call is the documented pattern, not an accidental
    // cascade — refetches are driven by the feed query changing, which is an
    // external input this effect is meant to synchronize against.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshList()
  }, [authPhase, queryReady, refreshList])

  // On a production-sized corpus both endpoints perform exact founder-policy
  // matching. Let the founder-visible feed finish first instead of making the
  // initial dashboard request compete with it for the reverse proxy's request
  // window. Subsequent action/feedback refreshes remain immediate below.
  useEffect(() => {
    if (authPhase !== "authenticated" || items === null || dashboard !== null) return
    refreshDashboard()
  }, [authPhase, dashboard, items, refreshDashboard])

  // Keep the j/k cursor inside the current item list (a new query result,
  // toggling "Show hidden", etc. can shrink it).
  useEffect(() => {
    if (!items) return
    // Standard data-fetching-adjacent effect (React docs: "Fetching data"
    // under "You Might Not Need an Effect") — clamping the cursor when an
    // external input (`items`, driven by the query) changes shape.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFocusedIndex((i) => Math.min(i, Math.max(items.length - 1, 0)))
  }, [items])

  useEffect(() => {
    if (!undoNotice) return
    const timer = window.setTimeout(() => {
      setUndoNotice((current) => current?.eventId === undoNotice.eventId ? null : current)
    }, UNDO_PROMPT_MS)
    return () => window.clearTimeout(timer)
  }, [undoNotice])

  // Actual DOM focus follows the cursor ("focus is visible and managed" —
  // required behaviour #4), not a CSS-only highlight left somewhere the
  // browser's own focus isn't.
  useEffect(() => {
    if (anyPanelOpen) return
    const id = items?.[focusedIndex]?.id
    if (!id) return
    cardRefs.current.get(id)?.focus()
  }, [focusedIndex, items, anyPanelOpen])

  useEffect(() => {
    if (previousFeedQueryDrawerOpen.current && !feedQueryDrawerOpen) {
      window.setTimeout(() => advancedFeedTriggerRef.current?.focus(), 0)
    }
    previousFeedQueryDrawerOpen.current = feedQueryDrawerOpen
  }, [feedQueryDrawerOpen])

  // j/k/o/a/x (required behaviour #4). Disabled while a text input has
  // focus or any drawer/panel is open, so the shortcuts never fight a
  // field the founder is typing into or a dialog with its own keyboard
  // handling. `handleActionSubmitted` is read via closure deliberately
  // (its identity is not stable across renders, unlike `items`); the
  // functional `setItems` update it performs is correct regardless of
  // which render's closure fired it.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (anyPanelOpen) return
      const target = e.target as HTMLElement | null
      const tag = target?.tagName
      const focusedCard = target?.closest('[data-testid^="opportunity-card-"]')
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target?.isContentEditable ||
        (target?.closest("button, a, [role='button'], [role='link']") && !focusedCard)
      ) {
        return
      }
      if (!items || items.length === 0) return
      const current = items[focusedIndex]
      if (e.key === "j") {
        e.preventDefault()
        setFocusedIndex((i) => Math.min(i + 1, items.length - 1))
      } else if (e.key === "k") {
        e.preventDefault()
        setFocusedIndex((i) => Math.max(i - 1, 0))
      } else if (e.key === "o") {
        if (current) setSelectedId(current.id)
      } else if (e.key === "a") {
        if (current) {
          api.opportunities
            .submitAction(current.id, "mark_applied", null, crypto.randomUUID())
            .then((res) => handleActionSubmitted(current.id, res.tracker_state ?? res.action_state, res))
        }
      } else if (e.key === "x") {
        if (current) {
          api.opportunities
            .submitAction(current.id, "reject", null, crypto.randomUUID())
            .then((res) => handleActionSubmitted(current.id, res.tracker_state ?? res.action_state, res))
        }
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, focusedIndex, anyPanelOpen])

  async function handlePollNow() {
    setPolling(true)
    try {
      await api.worker.pollNow()
      refreshSources()
      refreshFromFirstPage()
      refreshDashboard()
    } finally {
      setPolling(false)
    }
  }

  function handleFeedbackSubmitted(id: string, label: FeedbackLabel) {
    setItems((prev) =>
      prev
        ? prev.map((o) => (o.id === id ? { ...o, feedback_label: label } : o))
        : prev
    )
    refreshDashboard()
  }

  function handleActionSubmitted(id: string, state: ActionState, response?: ActionResponse) {
    const wasInToReview = items?.some((item) => item.id === id) ?? false
    setSelectedActionState(state)
    const eventId = response?.undo_event_id
    const label = state === "saved" ? "Saved" : state === "applied" || state === "submitted" ? "Marked applied" : state === "rejected_by_founder" ? "Rejected" : "Updated"
    setUndoNotice(eventId ? { opportunityId: id, eventId, label } : null)
    setUndoError(null)
    setItems((prev) => prev?.filter((o) => o.id !== id) ?? prev)
    if (wasInToReview) setTotal((previous) => Math.max(0, previous - 1))
    setTrackerRefreshKey((previous) => previous + 1)
    refreshDashboard()
    refreshFromFirstPage()
  }

  async function handleCardTriage(id: string, type: "save" | "mark_applied" | "reject") {
    setTriagePendingId(id)
    setTriageError(null)
    setUndoNotice(null)
    setUndoError(null)
    try {
      const response = await api.opportunities.submitAction(id, type, null, crypto.randomUUID())
      handleActionSubmitted(id, response.tracker_state ?? response.action_state, response)
      notifyTrackerActivityChanged()
    } catch (failure) {
      const detail = failure instanceof ApiError && failure.body && typeof failure.body === "object" && "detail" in failure.body && typeof failure.body.detail === "string"
        ? failure.body.detail
        : failure instanceof Error ? failure.message : "Could not update this tracker state."
      setTriageError({ id, message: detail })
    } finally {
      setTriagePendingId(null)
    }
  }

  async function handleUndo() {
    if (!undoNotice || undoSubmitting) return
    setUndoSubmitting(true)
    setUndoError(null)
    try {
      const response = await api.opportunities.restoreAction(
        undoNotice.opportunityId,
        undoNotice.eventId,
        crypto.randomUUID()
      )
      if (undoNotice.opportunityId === selectedId) setSelectedActionState(response.action_state)
      setUndoNotice(null)
      setTrackerRefreshKey((previous) => previous + 1)
      refreshDashboard()
      refreshFromFirstPage()
      notifyTrackerActivityChanged()
    } catch (failure) {
      const detail = failure instanceof ApiError && failure.body && typeof failure.body === "object" && "detail" in failure.body && typeof failure.body.detail === "string"
        ? failure.body.detail
        : failure instanceof Error ? failure.message : "Could not undo this tracker action."
      setUndoError(detail)
      if (failure instanceof ApiError && failure.status === 409) setUndoNotice(null)
    } finally {
      setUndoSubmitting(false)
    }
  }

  const selectedItem = useMemo(
    () => items?.find((o) => o.id === selectedId) ?? null,
    [items, selectedId]
  )

  const overHidingWarning = useMemo(
    () => computeOverHidingWarning(dashboard?.series[0]),
    [dashboard]
  )

  const hasActiveFilters = hasActiveFeedQuery(query)

  const workerIdle =
    !!sources && sources.length > 0 && sources.every((s) => s.last_poll === null)
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  if (authPhase !== "authenticated") {
    return (
      <main className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        Checking session…
      </main>
    )
  }

  return (
    <div className="flex min-h-screen flex-col">
      <HeaderStrip
        dashboard={dashboard}
        sources={sources}
        onPollNow={handlePollNow}
        polling={polling}
        onOpenHiddenReasons={() => setHiddenReasonsOpen(true)}
      />

      <nav aria-label="Opportunity workspace" className="flex flex-wrap gap-2 border-b border-border bg-background px-4 py-2 sm:px-6">
        <Button
          type="button"
          size="sm"
          variant={activeWorkspace === "jobs" ? "default" : "outline"}
          aria-pressed={activeWorkspace === "jobs"}
          data-testid="workspace-jobs"
          onClick={() => setActiveWorkspace("jobs")}
        >
          Jobs / To Review
        </Button>
        <Button
          type="button"
          size="sm"
          variant={activeWorkspace === "tracker" ? "default" : "outline"}
          aria-pressed={activeWorkspace === "tracker"}
          data-testid="workspace-tracker"
          onClick={() => setActiveWorkspace("tracker")}
        >
          Tracker
        </Button>
      </nav>

      {/* Master's addition #1: the >10% over-hiding warning must be
          visible, not just a tested pure function. See
          lib/format/over-hiding.ts for what this is derived from. */}
      {activeWorkspace === "jobs" && overHidingWarning && <OverHidingWarningBanner warning={overHidingWarning} />}

      {truth && activeWorkspace === "jobs" && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-background px-4 py-2 sm:px-6">
          <FilterBar
            filters={filters}
            onChange={(nextFilters) => handleQueryChange({
              ...query,
              track: nextFilters.track,
              decision: nextFilters.decision,
              q: nextFilters.q,
              scoreRanges: { ...query.scoreRanges, fit_score: { ...query.scoreRanges.fit_score, min: nextFilters.minScore } },
            })}
            onOpenFounderFilters={() => setFiltersDrawerOpen(true)}
            sortBy={query.sortBy}
            onSortChange={(sortBy) => handleQueryChange({ ...query, sortBy })}
            onOpenAdvanced={() => setFeedQueryDrawerOpen(true)}
            onAdvancedTriggerRef={(element) => {
              advancedFeedTriggerRef.current = element
            }}
            advancedDisabled={!feedMetadata}
            metadata={feedMetadata}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="open-facets-panel"
            onClick={() => setFacetsPanelOpen(true)}
          >
            <SlidersHorizontal aria-hidden="true" className="size-3.5" />
            Facets
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="open-manual-sources-panel"
            onClick={() => setManualSourcesOpen(true)}
          >
            <Search aria-hidden="true" className="size-3.5" />
            Check manually
          </Button>
          <Button
            type="button"
            variant={query.track === "tutoring" ? "default" : "outline"}
            size="sm"
            data-testid="toggle-tutoring-lane"
            disabled={!truth.loaded}
            title={!truth.loaded ? "A validated founder profile is required for tutoring materials" : undefined}
            onClick={() => {
              handleQueryChange({ ...query, track: query.track === "tutoring" ? "" : "tutoring" })
            }}
          >
            <GraduationCap aria-hidden="true" className="size-3.5" />
            Tutoring Lane
          </Button>
        </div>
      )}

      {activeWorkspace === "jobs" && <FeedQueryChips value={query} onChange={handleQueryChange} />}
      {activeWorkspace === "jobs" && feedMetadataError && (
        <p role="status" className="border-b border-amber-600/30 bg-amber-50 px-4 py-2 text-xs text-amber-950 dark:bg-amber-950/20 dark:text-amber-100 sm:px-6">
          Advanced feed filtering is unsupported by this API adapter: {feedMetadataError} Track, decision, fit minimum, and search remain available.
        </p>
      )}

      <main className="flex-1 px-4 py-4 sm:px-6">
        {undoNotice && !selectedId && (
          <div role="status" data-testid="tracker-undo-notice" className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border bg-card px-4 py-3 text-sm">
            <span>{undoNotice.label}.</span>
            <Button type="button" size="sm" variant="outline" data-testid="undo-tracker-action" disabled={undoSubmitting} onClick={() => void handleUndo()}>
              {undoSubmitting ? "Undoing…" : "Undo"}
            </Button>
          </div>
        )}
        {undoError && !selectedId && <p role="alert" data-testid="tracker-undo-error" className="mb-4 text-sm text-destructive">{undoError}</p>}
        {activeWorkspace === "tracker" ? (
          <TrackerView
            refreshKey={trackerRefreshKey}
            onOpen={(item) => {
              setSelectedActionState(item.tracker_state ?? item.action_state)
              setSelectedId(item.id)
            }}
          />
        ) : <>
        {truth && !truth.loaded && (
          truth.validator.error_count > 0 ? (
            <InvalidTruthPackState findings={truth.validator.findings} />
          ) : (
            <NoTruthPackState path={truth.path} />
          )
        )}

        {!truth ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : query.track === "tutoring" ? (
          <TutoringSurface />
        ) : listLoading && !items ? (
          <p className="text-sm text-muted-foreground">Loading opportunities…</p>
        ) : listError ? (
          <p role="alert" className="text-sm text-destructive">
            {listError}
          </p>
        ) : items && items.length === 0 ? (
          hasActiveFilters ? (
            <NoFilterMatchesState
              onClear={() => {
                setPage(1)
                handleQueryChange(EMPTY_FEED_QUERY)
              }}
            />
          ) : workerIdle ? (
            <WorkerIdleState onPollNow={handlePollNow} />
          ) : (
            <NoOpportunitiesYetState onPollNow={handlePollNow} />
          )
        ) : (
          <>
            <p
              data-testid="opportunity-count"
              className="mb-3 text-xs text-muted-foreground"
            >
              {total} opportunit{total === 1 ? "y" : "ies"}
              {query.includeHidden && " (including hidden)"}
            </p>
            <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {items?.map((o, idx) => (
                <OpportunityCard
                  key={o.id}
                  ref={(el) => {
                    if (el) cardRefs.current.set(o.id, el)
                    else cardRefs.current.delete(o.id)
                  }}
                  opportunity={o}
                  keyboardFocused={idx === focusedIndex}
                  onTriageAction={(type) => void handleCardTriage(o.id, type)}
                  triagePending={triagePendingId === o.id}
                  triageError={triageError?.id === o.id ? triageError.message : null}
                  onOpen={() => {
                    setFocusedIndex(idx)
                    setSelectedActionState(o.action_state)
                    setSelectedId(o.id)
                  }}
                />
              ))}
            </ul>
            {pageCount > 1 && (
              <nav
                aria-label="Opportunity pages"
                className="mt-5 flex items-center justify-center gap-3"
                data-testid="opportunity-pagination"
              >
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={page <= 1 || listLoading}
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
                  disabled={page >= pageCount || listLoading}
                  onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                >
                  Next
                </Button>
              </nav>
            )}
          </>
        )}

        {/* The founder's own visible, switchable control back to whatever
            a `hide`-mode filter removed — see d3-contract.md §6. Rendered
            outside the branches above so it survives even when a hide
            filter's default leaves nothing else on the page (an entirely
            hidden feed is exactly the case this control exists for). */}
        {truth && !listLoading && !listError && (hiddenCount > 0 || query.includeHidden) && (
          <div className="mt-4 flex justify-center">
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-testid="toggle-hidden-opportunities"
              onClick={() => handleQueryChange({ ...query, includeHidden: !query.includeHidden })}
            >
              {query.includeHidden ? (
                <>
                  <EyeOff aria-hidden="true" className="size-3.5" />
                  Hide hidden opportunities
                </>
              ) : (
                <>
                  <Eye aria-hidden="true" className="size-3.5" />
                  Show {hiddenCount} hidden
                </>
              )}
            </Button>
          </div>
        )}
        </>}
      </main>

      <FiltersDrawer
        open={filtersDrawerOpen}
        onOpenChange={setFiltersDrawerOpen}
        onFiltersChanged={() => {
          refreshFromFirstPage()
          refreshDashboard()
        }}
      />

      <FeedQueryDrawer
        open={feedQueryDrawerOpen}
        onOpenChange={setFeedQueryDrawerOpen}
        value={query}
        onChange={handleQueryChange}
        metadata={feedMetadata}
        metadataError={feedMetadataError}
      />

      <FacetsPanel
        open={facetsPanelOpen}
        onOpenChange={setFacetsPanelOpen}
        onFacetsChanged={() => {
          refreshFromFirstPage()
          refreshDashboard()
        }}
      />

      <HiddenReasonsPanel
        open={hiddenReasonsOpen}
        onOpenChange={setHiddenReasonsOpen}
        onUnhidden={() => {
          refreshFromFirstPage()
          refreshDashboard()
        }}
      />

      <ManualSourcesPanel
        open={manualSourcesOpen}
        onOpenChange={setManualSourcesOpen}
      />

      <DetailDrawer
        opportunityId={selectedId}
        initialActionState={selectedItem?.action_state ?? selectedActionState}
        initialFeedbackLabel={selectedItem?.feedback_label ?? null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedId(null)
            setSelectedActionState(null)
          }
        }}
        onOpened={refreshDashboard}
        onFeedbackSubmitted={handleFeedbackSubmitted}
        onActionSubmitted={handleActionSubmitted}
        undoNotice={undoNotice}
        undoSubmitting={undoSubmitting}
        undoError={undoError}
        onUndo={() => void handleUndo()}
      />
    </div>
  )
}
