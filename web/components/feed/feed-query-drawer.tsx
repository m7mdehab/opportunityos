"use client"

import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { api } from "@/lib/api/client"
import {
  EMPTY_FEED_QUERY,
  FEED_MULTI_FACET_IDS,
  FEED_SCORE_IDS,
  FEED_SORT_LABELS,
  FEED_UNAVAILABLE_FILTERS,
} from "@/lib/feed-query-state"
import type {
  FeedFilterMetadataResponse,
  FeedMultiFacetId,
  FeedQueryState,
  FeedScoreId,
  SavedView,
} from "@/lib/contract/types"

const FACET_LABELS: Record<FeedMultiFacetId, string> = {
  feedback_label: "Feedback",
  activity_type: "Activity",
  work_mode: "Work mode",
  location_country: "Country",
  location_city: "City",
  remote_scope: "Remote scope",
  employment_type: "Employment type",
  seniority_level: "Seniority",
  target_tier: "Target tier",
  title_family: "Title family",
  source_id: "Source",
}

const SCORE_LABELS: Record<FeedScoreId, string> = {
  fit_score: "Capability fit",
  preference_score: "Preference",
  confidence_score: "Confidence",
  priority_score: "Priority",
}

const THRESHOLDS = ["90+", "80+", "70+", "60+", "50+"] as const

function queryViews(views: SavedView[]) {
  return views.filter((view) => view.feed_query)
}

function updateMulti(
  value: FeedQueryState,
  facet: FeedMultiFacetId,
  option: string,
  checked: boolean
): FeedQueryState {
  const current = value.multi[facet]
  const selected = checked
    ? [...new Set([...current, option])]
    : current.filter((item) => item !== option)
  return { ...value, multi: { ...value.multi, [facet]: selected } }
}

export function FeedQueryChips({
  value,
  onChange,
}: {
  value: FeedQueryState
  onChange: (next: FeedQueryState) => void
}) {
  const chips: Array<{ key: string; label: string; remove: () => void }> = []
  for (const track of value.track) chips.push({ key: `track:${track}`, label: `Track: ${track}`, remove: () => onChange({ ...value, track: value.track.filter((item) => item !== track) }) })
  for (const decision of value.decision) chips.push({ key: `decision:${decision}`, label: `Decision: ${decision}`, remove: () => onChange({ ...value, decision: value.decision.filter((item) => item !== decision) }) })
  if (value.q.trim()) chips.push({ key: "q", label: `Search: ${value.q.trim()}`, remove: () => onChange({ ...value, q: "" }) })
  for (const facet of FEED_MULTI_FACET_IDS) {
    for (const option of value.multi[facet]) {
      chips.push({
        key: `${facet}:${option}`,
        label: `${FACET_LABELS[facet]}: ${option}`,
        remove: () => onChange(updateMulti(value, facet, option, false)),
      })
    }
  }
  for (const score of FEED_SCORE_IDS) {
    const { min, max } = value.scoreRanges[score]
    if (min) chips.push({ key: `${score}:min`, label: `${SCORE_LABELS[score]} ≥ ${min}`, remove: () => onChange({ ...value, scoreRanges: { ...value.scoreRanges, [score]: { ...value.scoreRanges[score], min: "" } } }) })
    if (max) chips.push({ key: `${score}:max`, label: `${SCORE_LABELS[score]} ≤ ${max}`, remove: () => onChange({ ...value, scoreRanges: { ...value.scoreRanges, [score]: { ...value.scoreRanges[score], max: "" } } }) })
  }
  if (value.postedFrom) chips.push({ key: "posted_from", label: `Posted from: ${value.postedFrom}`, remove: () => onChange({ ...value, postedFrom: "" }) })
  if (value.postedTo) chips.push({ key: "posted_to", label: `Posted to: ${value.postedTo}`, remove: () => onChange({ ...value, postedTo: "" }) })
  if (value.sortBy !== "recommended") chips.push({ key: "sort", label: `Sort: ${FEED_SORT_LABELS[value.sortBy]}`, remove: () => onChange({ ...value, sortBy: "recommended" }) })
  if (value.includeHidden) chips.push({ key: "include_hidden", label: "Including hidden", remove: () => onChange({ ...value, includeHidden: false }) })

  if (!chips.length) return null
  return (
    <div aria-label="Active feed filters" className="flex flex-wrap items-center gap-1.5 px-4 py-2 sm:px-6" data-testid="feed-query-chips">
      {chips.map((chip) => (
        <Badge key={chip.key} variant="secondary" className="gap-1 pr-1">
          {chip.label}
          <button type="button" aria-label={`Remove ${chip.label}`} onClick={chip.remove} className="rounded-full p-0.5 hover:bg-background">
            <X aria-hidden="true" className="size-3" />
          </button>
        </Badge>
      ))}
      <Button type="button" variant="ghost" size="xs" onClick={() => onChange(EMPTY_FEED_QUERY)}>Clear all</Button>
    </div>
  )
}

function FacetOptions({
  facet,
  values,
  selected,
  disabled,
  truncated,
  onToggle,
}: {
  facet: FeedMultiFacetId
  values: Array<{ value: string; count: number }>
  selected: string[]
  disabled: boolean
  truncated: boolean
  onToggle: (option: string, checked: boolean) => void
}) {
  const [search, setSearch] = useState("")
  const shownValues = useMemo(() => {
    const options = [...values]
    for (const current of selected) {
      if (!options.some((option) => option.value === current)) options.unshift({ value: current, count: 0 })
    }
    const needle = search.trim().toLocaleLowerCase()
    return needle ? options.filter((option) => option.value.toLocaleLowerCase().includes(needle)) : options
  }, [values, selected, search])

  return (
    <details className="rounded-lg border border-border p-3" data-testid={`feed-facet-${facet}`}>
      <summary className="cursor-pointer text-sm font-medium">{FACET_LABELS[facet]} <span className="text-xs font-normal text-muted-foreground">{selected.length ? `(${selected.length} selected)` : `(${values.length} options)`}</span></summary>
      <div className="mt-3 space-y-2">
        <Input aria-label={`Search ${FACET_LABELS[facet]} options`} placeholder={`Search ${FACET_LABELS[facet].toLowerCase()}`} value={search} onChange={(event) => setSearch(event.target.value)} disabled={disabled} className="h-8" />
        {truncated && <p className="text-xs text-muted-foreground">Showing up to 100 values. Search within the loaded list.</p>}
        {!shownValues.length ? <p className="text-xs text-muted-foreground">No matching values.</p> : (
          <ul className="max-h-52 space-y-1 overflow-auto">
            {shownValues.map((option) => (
              <li key={option.value}>
                <label className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm hover:bg-muted/50">
                  <input type="checkbox" checked={selected.includes(option.value)} disabled={disabled} onChange={(event) => onToggle(option.value, event.target.checked)} />
                  <span className="min-w-0 flex-1 truncate">{option.value}</span>
                  <span className="text-xs text-muted-foreground">{option.count}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  )
}

export function FeedQueryDrawer({
  open,
  onOpenChange,
  value,
  onChange,
  metadata,
  metadataError,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  value: FeedQueryState
  onChange: (next: FeedQueryState) => void
  metadata: FeedFilterMetadataResponse | null
  metadataError: string | null
}) {
  const [views, setViews] = useState<SavedView[]>([])
  const [name, setName] = useState("")
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const feeds = queryViews(views)
  const advancedDisabled = !metadata

  useEffect(() => {
    if (!open) return
    api.savedViews.list().then((response) => setViews(queryViews(response.views))).catch(() => setViews([]))
  }, [open])

  async function saveQuery(defaultView = false) {
    if (!name.trim()) return
    setSaving(true)
    setSaveError(null)
    try {
      const created = await api.savedViews.create({ name: name.trim(), facets: {}, search_query: value.q || null, feed_query: value, is_default: defaultView })
      setViews((current) => [...queryViews(current), created])
      setName("")
    } catch {
      setSaveError("Could not save this feed view.")
    } finally {
      setSaving(false)
    }
  }

  async function setDefault(view: SavedView) {
    try {
      const updated = await api.savedViews.update(view.id, { is_default: true })
      setViews((current) => queryViews(current.map((item) => item.id === updated.id ? updated : { ...item, is_default: false })))
    } catch {
      setSaveError("Could not set this feed view as default.")
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl" data-testid="feed-query-drawer">
        <SheetHeader>
          <SheetTitle>Advanced feed filters</SheetTitle>
          <SheetDescription>Filter the opportunity feed. Counts describe visible opportunities and do not change with your current selections; tracked and ineligible opportunities are included.</SheetDescription>
        </SheetHeader>
        <div className="space-y-4 overflow-y-auto px-4 pb-3">
          {metadataError && (
            <div role="status" className="flex gap-2 rounded-md border border-amber-600/40 bg-amber-50 p-3 text-xs text-amber-950 dark:bg-amber-950/20 dark:text-amber-100">
              <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              <p>{metadataError} Advanced filters and sorting are disabled until this adapter supports them.</p>
            </div>
          )}
          {!metadataError && !metadata && <p role="status" className="text-xs text-muted-foreground">Loading available filter values…</p>}

          <section aria-labelledby="feed-score-heading" className="space-y-3">
            <h3 id="feed-score-heading" className="text-sm font-semibold">Score ranges</h3>
            {FEED_SCORE_IDS.map((score) => {
              const stats = metadata?.ranges[score]
              return (
                <div key={score} className="rounded-lg border border-border p-3">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-medium">{SCORE_LABELS[score]}</p>
                    <p className="text-xs text-muted-foreground">{stats ? `${stats.min ?? "—"} to ${stats.max ?? "—"}; ${stats.unknown_count} unscored` : "Metadata unavailable"}</p>
                  </div>
                  <div className="flex gap-2">
                    <div className="flex-1"><Label htmlFor={`${score}-min`} className="text-xs">Minimum</Label><Input id={`${score}-min`} aria-label={`${SCORE_LABELS[score]} minimum`} type="number" min={0} max={100} value={value.scoreRanges[score].min} disabled={advancedDisabled} onChange={(event) => onChange({ ...value, scoreRanges: { ...value.scoreRanges, [score]: { ...value.scoreRanges[score], min: event.target.value } } })} /></div>
                    <div className="flex-1"><Label htmlFor={`${score}-max`} className="text-xs">Maximum</Label><Input id={`${score}-max`} aria-label={`${SCORE_LABELS[score]} maximum`} type="number" min={0} max={100} value={value.scoreRanges[score].max} disabled={advancedDisabled} onChange={(event) => onChange({ ...value, scoreRanges: { ...value.scoreRanges, [score]: { ...value.scoreRanges[score], max: event.target.value } } })} /></div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5" aria-label={`${SCORE_LABELS[score]} quick thresholds`}>
                    {THRESHOLDS.map((threshold) => (
                      <Button key={threshold} type="button" variant={value.scoreRanges[score].min === threshold.slice(0, -1) ? "secondary" : "outline"} size="xs" disabled={advancedDisabled} onClick={() => onChange({ ...value, scoreRanges: { ...value.scoreRanges, [score]: { ...value.scoreRanges[score], min: threshold.slice(0, -1) } } })}>
                        {threshold}{stats ? ` · ${stats.threshold_counts[threshold]}` : ""}
                      </Button>
                    ))}
                  </div>
                </div>
              )
            })}
          </section>

          <section aria-labelledby="feed-posted-heading" className="space-y-2">
            <h3 id="feed-posted-heading" className="text-sm font-semibold">Posted date</h3>
            <p className="text-xs text-muted-foreground">Available range: {metadata?.ranges.posted_date.min ?? "unknown"} to {metadata?.ranges.posted_date.max ?? "unknown"}; {metadata?.ranges.posted_date.unknown_count ?? "—"} with no posted date.</p>
            <div className="flex gap-2">
              <div className="flex-1"><Label htmlFor="posted-from">From</Label><Input id="posted-from" aria-label="Posted from" type="date" value={value.postedFrom} disabled={advancedDisabled} onChange={(event) => onChange({ ...value, postedFrom: event.target.value })} /></div>
              <div className="flex-1"><Label htmlFor="posted-to">To</Label><Input id="posted-to" aria-label="Posted to" type="date" value={value.postedTo} disabled={advancedDisabled} onChange={(event) => onChange({ ...value, postedTo: event.target.value })} /></div>
            </div>
          </section>

          <section aria-labelledby="feed-dimensions-heading" className="space-y-2">
            <h3 id="feed-dimensions-heading" className="text-sm font-semibold">Opportunity details</h3>
            {FEED_MULTI_FACET_IDS.map((facet) => {
              const details = metadata?.facets[facet]
              return <FacetOptions key={facet} facet={facet} values={details?.values ?? []} selected={value.multi[facet]} disabled={advancedDisabled} truncated={details?.truncated ?? false} onToggle={(option, checked) => onChange(updateMulti(value, facet, option, checked))} />
            })}
          </section>

          <section aria-labelledby="feed-unavailable-heading" className="space-y-2">
            <h3 id="feed-unavailable-heading" className="text-sm font-semibold">Unavailable filters</h3>
            {(metadata?.unavailable_filters ?? FEED_UNAVAILABLE_FILTERS).map((filter) => (
              <div key={filter.id} className="rounded-lg border border-dashed border-border p-3 text-xs">
                <Label className="flex items-center gap-2 text-muted-foreground"><input type="checkbox" disabled />{filter.label}</Label>
                <p className="mt-1 text-muted-foreground">Unavailable — {filter.reason}</p>
              </div>
            ))}
            {metadata && metadata.unavailable_filters.length === 0 && <p className="text-xs text-muted-foreground">No other unavailable filters are listed.</p>}
          </section>

          <section aria-labelledby="saved-feed-views-heading" className="space-y-2 rounded-lg border border-border p-3">
            <h3 id="saved-feed-views-heading" className="text-sm font-semibold">Saved feed views</h3>
            {feeds.length ? (
              <ul className="space-y-2">
                {feeds.map((view) => (
                  <li key={view.id} className="flex flex-wrap items-center gap-2 rounded border border-border p-2">
                    <Button type="button" variant="ghost" size="sm" className="min-w-0 flex-1 justify-start truncate" disabled={Boolean(metadataError)} title={metadataError ?? undefined} onClick={() => { if (view.feed_query) { onChange(view.feed_query); onOpenChange(false) } }}>{view.name}{view.is_default ? " · Default" : ""}</Button>
                    {!view.is_default && <Button type="button" variant="outline" size="xs" disabled={saving || Boolean(metadataError)} onClick={() => void setDefault(view)}>Set default</Button>}
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-muted-foreground">No saved feed views yet. Legacy facet-only views remain in the separate Facets panel.</p>}
            {metadataError && <p className="text-xs text-muted-foreground">Saved feed-view actions are disabled while this adapter reports advanced feed filtering as unsupported.</p>}
            <div className="flex gap-2">
              <Input aria-label="Saved feed view name" placeholder="Name this feed view" value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
              <Button type="button" size="sm" disabled={!name.trim() || saving || Boolean(metadataError)} onClick={() => void saveQuery()}>{saving ? "Saving…" : "Save view"}</Button>
            </div>
            {saveError && <p role="alert" className="text-xs text-destructive">{saveError}</p>}
          </section>
        </div>
        <SheetFooter>
          <Button type="button" variant="outline" onClick={() => onChange(EMPTY_FEED_QUERY)}>Clear all</Button>
          <Button type="button" onClick={() => onOpenChange(false)}>Apply filters</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
