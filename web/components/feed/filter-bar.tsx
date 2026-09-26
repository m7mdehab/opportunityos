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
  sourceFamily: string[]
  sourceId: string[]
  activity: string[]
  feedback: string[]
}

export const EMPTY_FILTERS: FeedFilters = {
  track: [],
  decision: [],
  minScore: "",
  q: "",
  sourceFamily: [],
  sourceId: [],
  activity: [],
  feedback: [],
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
  emptyLabel = "All",
  formatValue = (value) => value,
}: {
  id: string
  label: string
  selected: T[]
  values: T[]
  onChange: (next: T[]) => void
  emptyLabel?: string
  formatValue?: (value: T) => string
}) {
  return (
    <details name="feed-quick-facet" data-testid={`filter-facet-${id}`} className="relative min-w-0 max-w-full">
      <summary
        id={`filter-${id}`}
        className={`${selectClasses} flex cursor-pointer list-none items-center justify-between gap-2`}
      >
        <span>{label}</span>
        <span className="text-xs text-muted-foreground">
          {selected.length ? selected.length : emptyLabel}
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
            <span className="truncate">{formatValue(value)}</span>
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
  onOpenManualSources,
  onOpenFacets,
  onToggleTutoringLane,
  tutoringActive = false,
  tutoringDisabled = false,
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
  onOpenManualSources: () => void
  onOpenFacets?: () => void
  onToggleTutoringLane?: () => void
  tutoringActive?: boolean
  tutoringDisabled?: boolean
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
    filters.sourceFamily.length > 0 ||
    filters.sourceId.length > 0 ||
    filters.activity.length > 0 ||
    filters.feedback.length > 0

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
  const sourceIds = sources.filter(
    (source) =>
      source.source_id &&
      !source.manual_only &&
      (
        filters.sourceFamily.length === 0 ||
        filters.sourceFamily.includes(source.source_family)
      )
  )
  const sourceIdValues = sourceIds
    .map((source) => source.source_id)
    .filter((sourceId): sourceId is string => Boolean(sourceId))
  const activityValues = [
    ...new Set([
      "any",
      "save",
      "mark_applied",
      "reject",
      "snooze",
      ...(metadata?.facets.activity_type.values.map((option) => option.value) ?? []),
    ]),
  ].sort()
  const feedbackValues = [
    ...new Set([
      "good_match",
      "bad_match",
      "eligibility_wrong",
      "seniority_wrong",
      "irrelevant_role",
      "source_quality_issue",
      "duplicate_issue",
      "review_required",
      ...(metadata?.facets.feedback_label.values.map((option) => option.value) ?? []),
    ]),
  ].sort()
  const humanize = (value: string) =>
    value.replaceAll("_", " ").replace(/^./, (character) => character.toUpperCase())
  const formatActivity = (value: string) =>
    value === "any" ? "Any activity" : humanize(value)

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

      <div className="flex min-w-0 max-w-full flex-col gap-1">
        <Label htmlFor="filter-source-family">Source</Label>
        <ChecklistFacet
          id="source-family"
          label="Source"
          selected={filters.sourceFamily}
          values={families}
          onChange={(sourceFamily) =>
            onChange({ ...filters, sourceFamily, sourceId: [] })
          }
        />
      </div>

      <div className="order-3 flex min-w-0 max-w-full flex-col gap-1">
        <Label htmlFor="filter-activity">Activity</Label>
        <ChecklistFacet
          id="activity"
          label="Activity"
          selected={filters.activity}
          values={activityValues}
          emptyLabel="To review"
          formatValue={formatActivity}
          onChange={(activity) => {
            const selectedAny = activity.includes("any")
            const previouslyAny = filters.activity.includes("any")
            const normalized = selectedAny && !previouslyAny
              ? ["any"]
              : previouslyAny
                ? activity.filter((value) => value !== "any")
                : activity
            onChange({ ...filters, activity: normalized })
          }}
        />
      </div>

      <div className="order-3 flex min-w-0 max-w-full flex-col gap-1">
        <Label htmlFor="filter-feedback">Feedback</Label>
        <ChecklistFacet
          id="feedback"
          label="Feedback"
          selected={filters.feedback}
          values={feedbackValues}
          formatValue={humanize}
          onChange={(feedback) => onChange({ ...filters, feedback })}
        />
      </div>

      {filters.sourceFamily.length > 0 && sourceIdValues.length > 1 && (
        <div className="flex min-w-0 max-w-full flex-col gap-1">
          <Label htmlFor="filter-source-id">Board</Label>
          <ChecklistFacet
            id="source-id"
            label="Board"
            selected={filters.sourceId}
            values={sourceIdValues}
            onChange={(sourceId) => onChange({ ...filters, sourceId })}
          />
        </div>
      )}

      <div className="order-3 flex flex-col gap-1">
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
          onClick={(event) => {
            event.currentTarget
              .closest("form")
              ?.querySelectorAll<HTMLDetailsElement>('details[name="feed-quick-facet"][open]')
              .forEach((details) => details.removeAttribute("open"))
            onChange(EMPTY_FILTERS)
          }}
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

      <div aria-hidden="true" className="order-2 h-0 basis-full" />
      <Button
        type="button"
        ref={onAdvancedTriggerRef}
        variant="outline"
        size="lg"
        className="order-3"
        data-testid="open-advanced-feed-filters"
        disabled={advancedDisabled}
        onClick={onOpenAdvanced}
      >
        <SlidersHorizontal aria-hidden="true" className="size-3.5" />
        Advanced
      </Button>

      {onOpenFacets && (
        <Button
          type="button"
          variant="outline"
          size="lg"
          data-testid="open-facets-panel"
          onClick={onOpenFacets}
        >
          Facets
        </Button>
      )}

      <Button
        type="button"
        variant="outline"
        size="lg"
        data-testid="open-manual-sources-panel"
        onClick={onOpenManualSources}
      >
        Check manually
      </Button>

      {onToggleTutoringLane && (
        <Button
          type="button"
          variant={tutoringActive ? "secondary" : "outline"}
          size="lg"
          data-testid="toggle-tutoring-lane"
          aria-pressed={tutoringActive}
          disabled={tutoringDisabled}
          onClick={onToggleTutoringLane}
        >
          Tutoring Lane
        </Button>
      )}
    </form>
  )
}
