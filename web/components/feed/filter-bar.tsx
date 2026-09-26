"use client"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { SlidersHorizontal } from "lucide-react"
import type {
  Decision,
  FeedFilterMetadataResponse,
  FeedSortId,
  SourceOverview,
  Track,
} from "@/lib/contract/types"
import {
  FEED_SORT_IDS,
  FEED_SORT_LABELS,
  FEED_UNAVAILABLE_SORT_GROUPS,
} from "@/lib/feed-query-state"

export interface FeedFilters {
  track: Track[]
  decision: Exclude<Decision, null>[]
  minScore: string
  q: string
  sourceFamily: string
  sourceId: string
  activity: string
  feedback: string
}

export const EMPTY_FILTERS: FeedFilters = {
  track: [],
  decision: [],
  minScore: "",
  q: "",
  sourceFamily: "",
  sourceId: "",
  activity: "to_review",
  feedback: "",
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
  "h-9 min-w-0 max-w-full rounded-lg border border-input bg-card px-2.5 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

function toggleValue<T extends string>(selected: T[], value: T, checked: boolean): T[] {
  return checked
    ? [...new Set([...selected, value])]
    : selected.filter((item) => item !== value)
}

function ChecklistFacet<T extends string>({
  id,
  label,
  selected,
  values,
  onChange,
}: {
  id: string
  label: string
  selected: T[]
  values: T[]
  onChange: (next: T[]) => void
}) {
  return (
    <details data-testid={`filter-facet-${id}`} className="relative min-w-0 max-w-full">
      <summary
        id={`filter-${id}`}
        className={`${selectClasses} flex cursor-pointer list-none items-center justify-between gap-2`}
      >
        <span>{label}</span>
        <span className="text-xs text-muted-foreground">
          {selected.length ? selected.length : "All"}
        </span>
      </summary>
      <div className="absolute left-0 z-30 mt-1 max-h-72 w-52 max-w-[calc(100vw-2rem)] overflow-auto rounded-lg border border-border bg-card p-2 shadow-lg">
        <div className="mb-1 flex justify-end">
          <Button
            type="button"
            size="xs"
            variant="ghost"
            onClick={(event) => {
              onChange([])
              event.currentTarget.closest("details")?.removeAttribute("open")
            }}
          >
            Clear
          </Button>
        </div>
        {values.map((value) => (
          <label
            key={value}
            className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted"
          >
            <input
              type="checkbox"
              checked={selected.includes(value)}
              onChange={(event) => onChange(toggleValue(selected, value, event.target.checked))}
            />
            <span className="truncate">{value}</span>
          </label>
        ))}
      </div>
    </details>
  )
}

export function FilterBar({
  filters,
  onChange,
  onOpenFounderFilters,
  onOpenAdvanced,
  onAdvancedTriggerRef,
  sortBy,
  onSortChange,
  advancedDisabled = false,
  metadata,
  sources,
}: {
  filters: FeedFilters
  onChange: (next: FeedFilters) => void
  onOpenFounderFilters: () => void
  onOpenAdvanced: () => void
  onAdvancedTriggerRef?: (element: HTMLButtonElement | null) => void
  sortBy: FeedSortId
  onSortChange: (next: FeedSortId) => void
  advancedDisabled?: boolean
  metadata?: FeedFilterMetadataResponse | null
  sources: SourceOverview[]
}) {
  const hasActiveFilters =
    filters.track.length > 0 ||
    filters.decision.length > 0 ||
    filters.minScore !== "" ||
    filters.q !== "" ||
    filters.sourceFamily !== "" ||
    filters.sourceId !== "" ||
    filters.activity !== "to_review" ||
    filters.feedback !== ""

  const trackValues = [
    ...new Set([
      ...TRACKS,
      ...(metadata?.facets.track.values.map((option) => option.value as Track) ?? []),
    ]),
  ]
  const decisionValues = [
    ...new Set([
      ...DECISIONS,
      ...(metadata?.facets.decision.values.map(
        (option) => option.value as Exclude<Decision, null>
      ) ?? []),
    ]),
  ]

  const families = [...new Set(sources.map((source) => source.source_family))].sort()
  const familyMeta = new Map(
    families.map((family) => {
      const rows = sources.filter((source) => source.source_family === family)
      return [
        family,
        {
          count: rows.reduce(
            (total, row) => total + (row.manual_only ? 0 : row.opportunity_count),
            0
          ),
          manualOnly: rows.some((row) => row.manual_only),
        },
      ] as const
    })
  )
  const sourceIds = sources.filter(
    (source) =>
      source.source_id &&
      !source.manual_only &&
      (!filters.sourceFamily || source.source_family === filters.sourceFamily)
  )
  const allAutomatedCount = sources.reduce(
    (total, row) => total + (row.manual_only ? 0 : row.opportunity_count),
    0
  )

  return (
    <form
      role="search"
      aria-label="Filter opportunities"
      className="flex flex-wrap items-end gap-3 border-b border-border bg-background px-4 py-3 sm:px-6"
      onSubmit={(event) => event.preventDefault()}
    >
      <div className="flex min-w-0 max-w-full flex-col gap-1">
        <Label htmlFor="filter-track">Track</Label>
        <ChecklistFacet
          id="track"
          label="Track"
          selected={filters.track}
          values={trackValues}
          onChange={(track) => onChange({ ...filters, track })}
        />
      </div>

      <div className="flex min-w-0 max-w-full flex-col gap-1">
        <Label htmlFor="filter-decision">Decision</Label>
        <ChecklistFacet
          id="decision"
          label="Decision"
          selected={filters.decision}
          values={decisionValues}
          onChange={(decision) => onChange({ ...filters, decision })}
        />
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
          onChange={(event) => onChange({ ...filters, minScore: event.target.value })}
        />
      </div>

      <div className="flex min-w-[10rem] flex-1 flex-col gap-1">
        <Label htmlFor="filter-search">Search</Label>
        <Input
          id="filter-search"
          type="search"
          placeholder="Title or organization"
          className="h-9"
          value={filters.q}
          onChange={(event) => onChange({ ...filters, q: event.target.value })}
        />
      </div>

      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-source-family">Source</Label>
        <select
          id="filter-source-family"
          className={selectClasses}
          value={filters.sourceFamily}
          onChange={(event) =>
            onChange({ ...filters, sourceFamily: event.target.value, sourceId: "" })
          }
        >
          <option value="">All sources ({allAutomatedCount})</option>
          {families.map((family) => {
            const info = familyMeta.get(family)!
            return (
              <option key={family} value={family}>
                {family} ({info.manualOnly ? "Manual only · 0 automated" : info.count})
              </option>
            )
          })}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-activity">Activity</Label>
        <select
          id="filter-activity"
          data-testid="filter-activity"
          className={selectClasses}
          value={filters.activity}
          onChange={(event) => onChange({ ...filters, activity: event.target.value })}
        >
          <option value="to_review">To review</option>
          <option value="any">Any activity</option>
          <option value="applied">Applied</option>
          <option value="snoozed">Snoozed</option>
          <option value="dismissed">Dismissed</option>
          <option value="has_feedback">Has feedback</option>
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-feedback">Feedback</Label>
        <select
          id="filter-feedback"
          data-testid="filter-feedback"
          className={selectClasses}
          value={filters.feedback}
          onChange={(event) => onChange({ ...filters, feedback: event.target.value })}
        >
          <option value="">All feedback states</option>
          <option value="good_match">Good match</option>
          <option value="bad_match">Bad match</option>
          <option value="eligibility_wrong">Not eligible</option>
          <option value="irrelevant_role">Wrong track</option>
          <option value="duplicate_issue">Duplicate</option>
        </select>
      </div>

      {filters.sourceFamily && sourceIds.length > 1 && (
        <div className="flex flex-col gap-1">
          <Label htmlFor="filter-source-id">Board</Label>
          <select
            id="filter-source-id"
            className={selectClasses}
            value={filters.sourceId}
            onChange={(event) => onChange({ ...filters, sourceId: event.target.value })}
          >
            <option value="">All {filters.sourceFamily}</option>
            {sourceIds.map((source) => (
              <option key={source.source_id!} value={source.source_id!}>
                {source.source_id} ({source.opportunity_count})
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="flex flex-col gap-1">
        <Label htmlFor="feed-sort">Sort</Label>
        <select
          id="feed-sort"
          className={selectClasses}
          value={sortBy}
          disabled={advancedDisabled}
          onChange={(event) => onSortChange(event.target.value as FeedSortId)}
        >
          <optgroup label="Available">
            {FEED_SORT_IDS.map((sort) => (
              <option key={sort} value={sort}>
                {FEED_SORT_LABELS[sort]}
              </option>
            ))}
          </optgroup>
          {FEED_UNAVAILABLE_SORT_GROUPS.map((group) => (
            <optgroup key={group.label} label={`${group.label} — unavailable`}>
              {group.options.map((label) => (
                <option key={label} disabled>
                  {label}
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
          size="lg"
          onClick={() => onChange(EMPTY_FILTERS)}
        >
          Clear filters
        </Button>
      )}

      <Button
        type="button"
        variant="outline"
        size="lg"
        className="ml-auto"
        data-testid="open-founder-filters"
        onClick={onOpenFounderFilters}
      >
        <SlidersHorizontal aria-hidden="true" className="size-3.5" />
        Filters
      </Button>

      <Button
        type="button"
        ref={onAdvancedTriggerRef}
        variant="outline"
        size="lg"
        data-testid="open-advanced-feed-filters"
        disabled={advancedDisabled}
        onClick={onOpenAdvanced}
      >
        <SlidersHorizontal aria-hidden="true" className="size-3.5" />
        Advanced
      </Button>
    </form>
  )
}
