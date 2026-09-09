"use client"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { SlidersHorizontal } from "lucide-react"
import type { Track, Decision } from "@/lib/contract/types"

export interface FeedFilters {
  track: Track | ""
  decision: Exclude<Decision, null> | ""
  minScore: string
  q: string
}

export const EMPTY_FILTERS: FeedFilters = {
  track: "",
  decision: "",
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
  "h-8 rounded-lg border border-input bg-card text-foreground px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

export function FilterBar({
  filters,
  onChange,
  onOpenFounderFilters,
}: {
  filters: FeedFilters
  onChange: (next: FeedFilters) => void
  /** Opens the founder-controlled Filters drawer (D3) — a separate concept
   * from the search-bar filters above: those narrow this query's request,
   * the drawer's filters decide what is hidden, ranked, or labelled across
   * every query. */
  onOpenFounderFilters: () => void
}) {
  const hasActiveFilters =
    filters.track !== "" ||
    filters.decision !== "" ||
    filters.minScore !== "" ||
    filters.q !== ""

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
          className="h-8 w-24"
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
          className="h-8"
          value={filters.q}
          onChange={(e) => onChange({ ...filters, q: e.target.value })}
        />
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
    </form>
  )
}
