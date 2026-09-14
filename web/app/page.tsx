"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { HeaderStrip } from "@/components/feed/header-strip"
import { FilterBar, EMPTY_FILTERS, type FeedFilters } from "@/components/feed/filter-bar"
import { OpportunityCard } from "@/components/feed/opportunity-card"
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

export default function FeedPage() {
  const router = useRouter()
  const [authPhase, setAuthPhase] = useState<AuthPhase>("checking")

  const [truth, setTruth] = useState<TruthStatusResponse | null>(null)
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [sources, setSources] = useState<SourceHealth[] | null>(null)

  const [filters, setFilters] = useState<FeedFilters>(EMPTY_FILTERS)
  const [items, setItems] = useState<OpportunityListItem[] | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [polling, setPolling] = useState(false)

  // ---- D3 founder-controlled filters ----
  const [filtersDrawerOpen, setFiltersDrawerOpen] = useState(false)
  const [hiddenCount, setHiddenCount] = useState(0)
  // "Show N hidden" — a deliberate, visible, switchable control per the
  // founder's stated requirement (see d3-contract.md §6): nothing that a
  // `hide`-mode filter removes stays removed without a way back to it.
  const [includeHidden, setIncludeHidden] = useState(false)

  // ---- C1 facets panel / C4 hidden-reasons / E23 manual sources ----
  const [facetsPanelOpen, setFacetsPanelOpen] = useState(false)
  const [hiddenReasonsOpen, setHiddenReasonsOpen] = useState(false)
  const [manualSourcesOpen, setManualSourcesOpen] = useState(false)

  // ---- keyboard navigation (C3 required behaviour #4: j/k/o/a/x) ----
  const [focusedIndex, setFocusedIndex] = useState(0)
  const cardRefs = useRef<Map<string, HTMLButtonElement>>(new Map())
  const anyPanelOpen =
    filtersDrawerOpen ||
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
        track: filters.track || undefined,
        decision: filters.decision || undefined,
        min_score: filters.minScore ? Number(filters.minScore) : undefined,
        q: filters.q || undefined,
        page,
        page_size: PAGE_SIZE,
        include_hidden: includeHidden,
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
        setListError("Could not load opportunities.")
      })
      .finally(() => setListLoading(false))
  }, [filters, includeHidden, page, router])

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
    if (authPhase !== "authenticated") return
    // Standard data-fetching effect (React docs: "Fetching data" under
    // "You Might Not Need an Effect"): setting the loading flag synchronously
    // before the async call is the documented pattern, not an accidental
    // cascade — refetches are driven by `filters` changing, which is an
    // external input this effect is meant to synchronize against.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshList()
  }, [authPhase, refreshList])

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

  // Actual DOM focus follows the cursor ("focus is visible and managed" —
  // required behaviour #4), not a CSS-only highlight left somewhere the
  // browser's own focus isn't.
  useEffect(() => {
    if (anyPanelOpen) return
    const id = items?.[focusedIndex]?.id
    if (!id) return
    cardRefs.current.get(id)?.focus()
  }, [focusedIndex, items, anyPanelOpen])

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
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target?.isContentEditable
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
            .submitAction(current.id, "mark_applied", null)
            .then((res) => handleActionSubmitted(current.id, res.action_state))
        }
      } else if (e.key === "x") {
        if (current) {
          api.opportunities
            .submitAction(current.id, "dismiss", null)
            .then((res) => handleActionSubmitted(current.id, res.action_state))
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

  function handleActionSubmitted(id: string, state: ActionState) {
    setItems((prev) =>
      prev
        ? prev.map((o) => (o.id === id ? { ...o, action_state: state } : o))
        : prev
    )
    refreshDashboard()
  }

  const selectedItem = useMemo(
    () => items?.find((o) => o.id === selectedId) ?? null,
    [items, selectedId]
  )

  const overHidingWarning = useMemo(
    () => computeOverHidingWarning(dashboard?.series[0]),
    [dashboard]
  )

  const hasActiveFilters =
    filters.track !== "" ||
    filters.decision !== "" ||
    filters.minScore !== "" ||
    filters.q !== ""

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

      {/* Master's addition #1: the >10% over-hiding warning must be
          visible, not just a tested pure function. See
          lib/format/over-hiding.ts for what this is derived from. */}
      {overHidingWarning && <OverHidingWarningBanner warning={overHidingWarning} />}

      {truth && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-background px-4 py-2 sm:px-6">
          <FilterBar
            filters={filters}
            onChange={(nextFilters) => {
              setPage(1)
              setFilters(nextFilters)
            }}
            onOpenFounderFilters={() => setFiltersDrawerOpen(true)}
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
            variant={filters.track === "tutoring" ? "default" : "outline"}
            size="sm"
            data-testid="toggle-tutoring-lane"
            disabled={!truth.loaded}
            title={!truth.loaded ? "A validated founder profile is required for tutoring materials" : undefined}
            onClick={() => {
              setPage(1)
              setFilters({
                ...filters,
                track: filters.track === "tutoring" ? "" : "tutoring",
              })
            }}
          >
            <GraduationCap aria-hidden="true" className="size-3.5" />
            Tutoring Lane
          </Button>
        </div>
      )}

      <main className="flex-1 px-4 py-4 sm:px-6">
        {truth && !truth.loaded && (
          truth.validator.error_count > 0 ? (
            <InvalidTruthPackState findings={truth.validator.findings} />
          ) : (
            <NoTruthPackState path={truth.path} />
          )
        )}

        {!truth ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : filters.track === "tutoring" ? (
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
                setFilters(EMPTY_FILTERS)
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
              {includeHidden && " (including hidden)"}
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
                  onOpen={() => {
                    setFocusedIndex(idx)
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
        {truth && !listLoading && !listError && (hiddenCount > 0 || includeHidden) && (
          <div className="mt-4 flex justify-center">
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-testid="toggle-hidden-opportunities"
              onClick={() => {
                setPage(1)
                setIncludeHidden((v) => !v)
              }}
            >
              {includeHidden ? (
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
      </main>

      <FiltersDrawer
        open={filtersDrawerOpen}
        onOpenChange={setFiltersDrawerOpen}
        onFiltersChanged={() => {
          refreshFromFirstPage()
          refreshDashboard()
        }}
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
        initialActionState={selectedItem?.action_state ?? null}
        initialFeedbackLabel={selectedItem?.feedback_label ?? null}
        onOpenChange={(open) => {
          if (!open) setSelectedId(null)
        }}
        onOpened={refreshDashboard}
        onFeedbackSubmitted={handleFeedbackSubmitted}
        onActionSubmitted={handleActionSubmitted}
      />
    </div>
  )
}
