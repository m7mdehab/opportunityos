"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { HeaderStrip } from "@/components/feed/header-strip"
import { FilterBar, EMPTY_FILTERS, type FeedFilters } from "@/components/feed/filter-bar"
import { OpportunityCard } from "@/components/feed/opportunity-card"
import { DetailDrawer } from "@/components/feed/detail-drawer"
import { FiltersDrawer } from "@/components/feed/filters-drawer"
import { Button } from "@/components/ui/button"
import { EyeOff, Eye } from "lucide-react"
import {
  NoTruthPackState,
  InvalidTruthPackState,
  NoOpportunitiesYetState,
  WorkerIdleState,
  NoFilterMatchesState,
} from "@/components/feed/empty-states"
import { api } from "@/lib/api/client"
import { ApiError } from "@/lib/contract/types"
import type {
  ActionState,
  DashboardResponse,
  FeedbackLabel,
  OpportunityListItem,
  SourceHealth,
  TruthStatusResponse,
} from "@/lib/contract/types"

type AuthPhase = "checking" | "authenticated" | "redirecting"

export default function FeedPage() {
  const router = useRouter()
  const [authPhase, setAuthPhase] = useState<AuthPhase>("checking")

  const [truth, setTruth] = useState<TruthStatusResponse | null>(null)
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [sources, setSources] = useState<SourceHealth[] | null>(null)

  const [filters, setFilters] = useState<FeedFilters>(EMPTY_FILTERS)
  const [items, setItems] = useState<OpportunityListItem[] | null>(null)
  const [total, setTotal] = useState(0)
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
        page: 1,
        page_size: 50,
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
  }, [filters, includeHidden, router])

  useEffect(() => {
    if (authPhase !== "authenticated") return
    refreshTruth()
    refreshDashboard()
    refreshSources()
  }, [authPhase, refreshTruth, refreshDashboard, refreshSources])

  useEffect(() => {
    if (authPhase !== "authenticated") return
    if (!truth?.loaded) return
    // Standard data-fetching effect (React docs: "Fetching data" under
    // "You Might Not Need an Effect"): setting a loading flag synchronously
    // before the async call is the documented pattern, not an accidental
    // cascade — refetches are driven by `filters` changing, which is an
    // external input this effect is meant to synchronize against.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshList()
  }, [authPhase, truth?.loaded, refreshList])

  async function handlePollNow() {
    setPolling(true)
    try {
      await api.worker.pollNow()
      refreshSources()
      refreshList()
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

  const hasActiveFilters =
    filters.track !== "" ||
    filters.decision !== "" ||
    filters.minScore !== "" ||
    filters.q !== ""

  const workerIdle =
    !!sources && sources.length > 0 && sources.every((s) => s.last_poll === null)

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
      />

      {truth?.loaded && (
        <FilterBar
          filters={filters}
          onChange={setFilters}
          onOpenFounderFilters={() => setFiltersDrawerOpen(true)}
        />
      )}

      <main className="flex-1 px-4 py-4 sm:px-6">
        {!truth ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : !truth.loaded ? (
          truth.validator.error_count > 0 ? (
            <InvalidTruthPackState findings={truth.validator.findings} />
          ) : (
            <NoTruthPackState path={truth.path} />
          )
        ) : listLoading && !items ? (
          <p className="text-sm text-muted-foreground">Loading opportunities…</p>
        ) : listError ? (
          <p role="alert" className="text-sm text-destructive">
            {listError}
          </p>
        ) : items && items.length === 0 ? (
          hasActiveFilters ? (
            <NoFilterMatchesState onClear={() => setFilters(EMPTY_FILTERS)} />
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
              {items?.map((o) => (
                <OpportunityCard
                  key={o.id}
                  opportunity={o}
                  onOpen={() => setSelectedId(o.id)}
                />
              ))}
            </ul>
          </>
        )}

        {/* The founder's own visible, switchable control back to whatever
            a `hide`-mode filter removed — see d3-contract.md §6. Rendered
            outside the branches above so it survives even when a hide
            filter's default leaves nothing else on the page (an entirely
            hidden feed is exactly the case this control exists for). */}
        {truth?.loaded && !listLoading && !listError && (hiddenCount > 0 || includeHidden) && (
          <div className="mt-4 flex justify-center">
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-testid="toggle-hidden-opportunities"
              onClick={() => setIncludeHidden((v) => !v)}
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
          refreshList()
          refreshDashboard()
        }}
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
