"use client"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { SlidersHorizontal } from "lucide-react"
import type { Track, Decision, SourceOverview } from "@/lib/contract/types"

export interface FeedFilters {
  track: Track | ""
  decision: Exclude<Decision, null> | ""
  minScore: string
  q: string
  sourceFamily: string
  sourceId: string
}

export const EMPTY_FILTERS: FeedFilters = {
  track: "",
  decision: "",
  minScore: "",
  q: "",
  sourceFamily: "",
  sourceId: "",
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
  "h-9 rounded-lg border border-input bg-card text-foreground px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

export function FilterBar({
  filters,
  onChange,
  onOpenFounderFilters,
  onOpenManualSources,
  onOpenFacets,
  onToggleTutoringLane,
  tutoringActive = false,
  tutoringDisabled = false,
  sources,
}: {
  filters: FeedFilters
  onChange: (next: FeedFilters) => void
  /** Opens the founder-controlled Filters drawer (D3) — a separate concept
   * from the search-bar filters above: those narrow this query's request,
   * the drawer's filters decide what is hidden, ranked, or labelled across
   * every query. */
  onOpenFounderFilters: () => void
  onOpenManualSources: () => void
  onOpenFacets?: () => void
  onToggleTutoringLane?: () => void
  tutoringActive?: boolean
  tutoringDisabled?: boolean
  sources: SourceOverview[]
}) {
  const hasActiveFilters =
    filters.track !== "" ||
    filters.decision !== "" ||
    filters.minScore !== "" ||
    filters.q !== ""
    || filters.sourceFamily !== ""
    || filters.sourceId !== ""

  const families = [...new Set(sources.map((source) => source.source_family))].sort()
  const familyMeta = new Map(families.map((family) => {
    const rows = sources.filter((source) => source.source_family === family)
    return [family, {
      count: rows.reduce((total, row) => total + (row.manual_only ? 0 : row.opportunity_count), 0),
      manualOnly: rows.some((row) => row.manual_only),
    }]
  }))
  const sourceIds = sources.filter((source) => source.source_id && !source.manual_only && (!filters.sourceFamily || source.source_family === filters.sourceFamily))
  const selectedFamily = familyMeta.get(filters.sourceFamily)
  const allAutomatedCount = sources.reduce((total, row) => total + (row.manual_only ? 0 : row.opportunity_count), 0)

  return (
    <form
      role="search"
      aria-label="Filter opportunities"
      className="flex flex-wrap items-end gap-3 border-b border-border bg-background px-4 py-3 sm:px-6"
      onSubmit={(e) => e.preventDefault()}
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-track">Track</Label>
        <select
          id="filter-track"
          className={selectClasses}
          value={filters.track}
          onChange={(e) =>
            onChange({ ...filters, track: e.target.value as FeedFilters["track"] })
          }
        >
          <option value="">All tracks</option>
          {TRACKS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-decision">Decision</Label>
        <select
          id="filter-decision"
          className={selectClasses}
          value={filters.decision}
          onChange={(e) =>
            onChange({
              ...filters,
              decision: e.target.value as FeedFilters["decision"],
            })
          }
        >
          <option value="">All decisions</option>
          {DECISIONS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-min-score">Min score</Label>
        <Input
          id="filter-min-score"
          type="number"
          inputMode="numeric"
          min={0}
          max={100}
          className="h-9 w-24"
          value={filters.minScore}
          onChange={(e) => onChange({ ...filters, minScore: e.target.value })}
        />
      </div>

      <div className="flex flex-1 min-w-[10rem] flex-col gap-1">
        <Label htmlFor="filter-search">Search</Label>
        <Input
          id="filter-search"
          type="search"
          placeholder="Title or organization"
          className="h-9"
          value={filters.q}
          onChange={(e) => onChange({ ...filters, q: e.target.value })}
        />
      </div>

      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-source-family">Source</Label>
        <select id="filter-source-family" className={selectClasses} value={filters.sourceFamily} onChange={(e) => onChange({ ...filters, sourceFamily: e.target.value, sourceId: "" })}>
          <option value="">All sources ({allAutomatedCount})</option>
          {families.map((family) => { const meta = familyMeta.get(family)!; return <option key={family} value={family}>{family} ({meta.manualOnly ? "Manual only · 0 automated" : meta.count})</option> })}
        </select>
      </div>
      <Button type="button" variant="outline" size="lg" onClick={onOpenManualSources} data-testid="open-manual-sources-panel">Check manually</Button>
      {filters.sourceFamily && !selectedFamily?.manualOnly && sourceIds.length > 1 && (
        <div className="flex flex-col gap-1">
          <Label htmlFor="filter-source-id">Board</Label>
          <select id="filter-source-id" className={selectClasses} value={filters.sourceId} onChange={(e) => onChange({ ...filters, sourceId: e.target.value })}>
            <option value="">All {filters.sourceFamily}</option>
            {sourceIds.map((source) => <option key={source.source_id!} value={source.source_id!}>{source.source_id} ({source.opportunity_count})</option>)}
          </select>
        </div>
      )}

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
      {onOpenFacets && (
        <Button type="button" variant="outline" size="lg" onClick={onOpenFacets} data-testid="open-facets-panel">
          Facets
        </Button>
      )}
      {onToggleTutoringLane && (
        <Button type="button" variant={tutoringActive ? "secondary" : "outline"} size="lg" onClick={onToggleTutoringLane} disabled={tutoringDisabled} data-testid="toggle-tutoring-lane" aria-pressed={tutoringActive}>
          Tutoring Lane
        </Button>
      )}
    </form>
  )
}
