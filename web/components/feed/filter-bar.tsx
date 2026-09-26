"use client"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { SlidersHorizontal } from "lucide-react"
import type { Track, Decision } from "@/lib/contract/types"
import { FEED_SORT_IDS, FEED_SORT_LABELS, FEED_UNAVAILABLE_SORT_GROUPS } from "@/lib/feed-query-state"
import type { FeedFilterMetadataResponse, FeedSortId } from "@/lib/contract/types"

export interface FeedFilters {
  track: Track[]
  decision: Exclude<Decision, null>[]
  minScore: string
  q: string
}

export const EMPTY_FILTERS: FeedFilters = {
  track: [],
  decision: [],
  minScore: "",
  q: "",
}

const TRACKS: Track[] = [
  "employment",
  "contract",
  "freelance",
  "procurement",
  "tutoring",
]
const DECISIONS: Exclude<Decision, null>[] = [
  "qualified",
  "ineligible",
  "uncertain",
]

const selectClasses =
  "h-8 w-40 max-w-full rounded-lg border border-input bg-card text-foreground px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

export function FilterBar({
  filters,
  onChange,
  onOpenFounderFilters,
  sortBy,
  onSortChange,
  onOpenAdvanced,
  onAdvancedTriggerRef,
  advancedDisabled = false,
  metadata,
}: {
  filters: FeedFilters
  onChange: (next: FeedFilters) => void
  /** Opens the founder-controlled Filters drawer (D3) — a separate concept
   * from the search-bar filters above: those narrow this query's request,
   * the drawer's filters decide what is hidden, ranked, or labelled across
   * every query. */
  onOpenFounderFilters: () => void
  sortBy: FeedSortId
  onSortChange: (next: FeedSortId) => void
  onOpenAdvanced: () => void
  onAdvancedTriggerRef?: (element: HTMLButtonElement | null) => void
  advancedDisabled?: boolean
  metadata?: FeedFilterMetadataResponse | null
}) {
  const hasActiveFilters =
    filters.track.length > 0 ||
    filters.decision.length > 0 ||
    filters.minScore !== "" ||
    filters.q !== ""
  const trackValues = [...new Set([...TRACKS, ...(metadata?.facets.track.values.map((option) => option.value as Track) ?? [])])]
  const decisionValues = [...new Set([...DECISIONS, ...(metadata?.facets.decision.values.map((option) => option.value as Exclude<Decision, null>) ?? [])])]
  const toggle = <T extends string>(selected: T[], value: T, checked: boolean) => checked ? [...new Set([...selected, value])] : selected.filter((item) => item !== value)
  const facet = <T extends string>(label: string, selected: T[], values: T[], setSelected: (next: T[]) => void, id: string) => (
    <details name="primary-feed-facet" data-testid={`filter-facet-${id.replace("filter-", "")}`} className="relative min-w-0 max-w-full">
      <summary id={id} className={`${selectClasses} flex cursor-pointer list-none items-center`}>{label}{selected.length ? ` (${selected.length})` : ""}</summary>
      <div className="absolute left-0 z-20 mt-1 max-h-64 w-40 max-w-[calc(100vw-2rem)] overflow-auto rounded-lg border border-border bg-card p-2 shadow-lg">
        <div className="mb-1 flex justify-end"><Button type="button" size="xs" variant="ghost" onClick={(event) => { setSelected([]); event.currentTarget.closest("details")?.removeAttribute("open") }}>Clear</Button></div>
        {values.map((value) => <label key={value} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted"><input type="checkbox" checked={selected.includes(value)} onChange={(event) => setSelected(toggle(selected, value, event.target.checked))} />{value}</label>)}
      </div>
    </details>
  )

  return (
    <form
      role="search"
      aria-label="Filter opportunities"
      className="flex flex-wrap items-end gap-3 border-b border-border bg-background px-4 py-3 sm:px-6"
      onSubmit={(e) => e.preventDefault()}
    >
      <div className="flex min-w-0 max-w-full flex-col gap-1">
        <Label htmlFor="filter-track">Track</Label>
        {facet("Track", filters.track, trackValues, (track) => onChange({ ...filters, track }), "filter-track")}
      </div>

      <div className="flex min-w-0 max-w-full flex-col gap-1">
        <Label htmlFor="filter-decision">Decision</Label>
        {facet("Decision", filters.decision, decisionValues, (decision) => onChange({ ...filters, decision }), "filter-decision")}
      </div>

      <div className="flex min-w-0 max-w-full flex-col gap-1">
        <Label htmlFor="filter-min-score">Min score</Label>
        <Input
          id="filter-min-score"
          type="number"
          inputMode="numeric"
          min={0}
          max={100}
          className="h-8 w-24"
          value={filters.minScore}
          onChange={(e) => onChange({ ...filters, minScore: e.target.value })}
        />
      </div>

      <div className="flex min-w-[10rem] max-w-full flex-1 flex-col gap-1">
        <Label htmlFor="filter-search">Search</Label>
        <Input
          id="filter-search"
          type="search"
          placeholder="Title or organization"
          className="h-8"
          value={filters.q}
          onChange={(e) => onChange({ ...filters, q: e.target.value })}
        />
      </div>

      <div className="flex min-w-0 max-w-full flex-col gap-1">
        <Label htmlFor="feed-sort">Sort</Label>
        <select
          id="feed-sort"
          className={selectClasses}
          value={sortBy}
          disabled={advancedDisabled}
          title={advancedDisabled ? "Sort is unavailable on this API adapter" : undefined}
          onChange={(e) => onSortChange(e.target.value as FeedSortId)}
        >
          <optgroup label="Available">
            {FEED_SORT_IDS.map((sort) => (
              <option key={sort} value={sort}>{FEED_SORT_LABELS[sort]}</option>
            ))}
          </optgroup>
          {FEED_UNAVAILABLE_SORT_GROUPS.map((group) => (
            <optgroup key={group.label} label={`${group.label} — unavailable`}>
              {group.options.map((label) => (
                <option key={label} disabled title={group.reason}>
                  {label} — unavailable: {group.reason}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      {hasActiveFilters && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onChange(EMPTY_FILTERS)}
        >
          Clear filters
        </Button>
      )}

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="ml-auto"
        onClick={onOpenFounderFilters}
      >
        <SlidersHorizontal aria-hidden="true" className="size-3.5" />
        Filters
      </Button>

      <Button
        type="button"
        ref={onAdvancedTriggerRef}
        variant="outline"
        size="sm"
        data-testid="open-advanced-feed-filters"
        title={advancedDisabled ? "Advanced filtering is unsupported by this API adapter" : undefined}
        onClick={onOpenAdvanced}
      >
        <SlidersHorizontal aria-hidden="true" className="size-3.5" />
        More filters
      </Button>
    </form>
  )
}
