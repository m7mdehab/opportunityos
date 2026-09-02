"use client"

import { useCallback, useEffect, useState } from "react"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { Switch } from "@/components/ui/switch"
import { Separator } from "@/components/ui/separator"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { EyeOff, ArrowDownWideNarrow, Tag, PowerOff } from "lucide-react"
import { api } from "@/lib/api/client"
import { filterTitle } from "@/components/feed/filter-labels"
import type { FilterMode, FounderFilter } from "@/lib/contract/types"

const selectClasses =
  "h-7 rounded-lg border border-input bg-transparent px-2 text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

/** The status chip on each row. Three visually and textually distinct
 * states for "currently doing something" (hide / rank / label) plus a
 * fourth for "off", following the same icon + label + colour triple
 * encoding `constraint-outcome.tsx` uses to keep UNKNOWN unmistakable from
 * FAIL — here it is what keeps a `hide` filter unmistakable from a
 * `rank_only` or `label_only` one, which must never *look* like it removed
 * something. */
function FilterStatusChip({ filter }: { filter: FounderFilter }) {
  if (!filter.enabled) {
    return (
      <Badge
        data-filter-effect="off"
        data-affected-count={filter.affected_count}
        variant="outline"
        className="gap-1 border-border text-muted-foreground"
      >
        <PowerOff aria-hidden="true" className="size-3" />
        Off — would affect {filter.affected_count}
      </Badge>
    )
  }
  if (filter.mode === "hide") {
    return (
      <Badge
        data-filter-effect="hide"
        data-affected-count={filter.affected_count}
        variant="outline"
        className="gap-1 border-red-600/30 bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-300"
      >
        <EyeOff aria-hidden="true" className="size-3" />
        Hiding {filter.affected_count} now
      </Badge>
    )
  }
  if (filter.mode === "rank_only") {
    return (
      <Badge
        data-filter-effect="rank_only"
        data-affected-count={filter.affected_count}
        variant="outline"
        className="gap-1 border-sky-600/30 bg-sky-50 text-sky-800 dark:bg-sky-950 dark:text-sky-300"
      >
        <ArrowDownWideNarrow aria-hidden="true" className="size-3" />
        Ranking {filter.affected_count} lower
      </Badge>
    )
  }
  return (
    <Badge
      data-filter-effect="label_only"
      data-affected-count={filter.affected_count}
      variant="outline"
      className="gap-1 border-violet-600/30 bg-violet-50 text-violet-800 dark:bg-violet-950 dark:text-violet-300"
    >
      <Tag aria-hidden="true" className="size-3" />
      Labelling {filter.affected_count}
    </Badge>
  )
}

function FilterRow({
  filter,
  saving,
  onUpdate,
}: {
  filter: FounderFilter
  saving: boolean
  onUpdate: (
    filterId: string,
    body: { enabled?: boolean; mode?: FilterMode; params?: Record<string, unknown> }
  ) => void
}) {
  return (
    <li
      data-testid={`filter-row-${filter.filter_id}`}
      className="rounded-lg border border-border p-3"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Label
            htmlFor={`filter-switch-${filter.filter_id}`}
            className="text-sm font-medium text-foreground"
          >
            {filterTitle(filter.filter_id)}
          </Label>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {filter.description}
          </p>
        </div>
        <Switch
          id={`filter-switch-${filter.filter_id}`}
          checked={filter.enabled}
          disabled={saving}
          onCheckedChange={(enabled) => onUpdate(filter.filter_id, { enabled })}
        />
      </div>

      <div className="mt-2 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <Label
            htmlFor={`filter-mode-${filter.filter_id}`}
            className="text-[11px] text-muted-foreground"
          >
            Mode
          </Label>
          <select
            id={`filter-mode-${filter.filter_id}`}
            className={selectClasses}
            disabled={saving}
            value={filter.mode}
            onChange={(e) =>
              onUpdate(filter.filter_id, { mode: e.target.value as FilterMode })
            }
          >
            <option value="hide">Hide</option>
            <option value="rank_only">Rank only</option>
            <option value="label_only">Label only</option>
          </select>
        </div>

        {Object.entries(filter.params).map(([key, value]) => (
          <div key={key} className="flex flex-col gap-1">
            <Label
              htmlFor={`filter-param-${filter.filter_id}-${key}`}
              className="text-[11px] text-muted-foreground"
            >
              {key.replaceAll("_", " ")}
            </Label>
            <Input
              id={`filter-param-${filter.filter_id}-${key}`}
              className="h-7 w-24 text-xs"
              type={typeof value === "number" ? "number" : "text"}
              disabled={saving}
              defaultValue={String(value)}
              onBlur={(e) => {
                const next =
                  typeof value === "number"
                    ? Number(e.target.value)
                    : e.target.value
                if (next !== value && !(typeof next === "number" && Number.isNaN(next))) {
                  onUpdate(filter.filter_id, { params: { [key]: next } })
                }
              }}
            />
          </div>
        ))}

        <div className="ml-auto">
          <FilterStatusChip filter={filter} />
        </div>
      </div>
    </li>
  )
}

function FilterSection({
  title,
  hint,
  filters,
  saving,
  onUpdate,
}: {
  title: string
  hint: string
  filters: FounderFilter[]
  saving: string | null
  onUpdate: (
    filterId: string,
    body: { enabled?: boolean; mode?: FilterMode; params?: Record<string, unknown> }
  ) => void
}) {
  if (filters.length === 0) return null
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title} ({filters.length})
      </h3>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>
      <ul className="mt-2 space-y-2">
        {filters.map((f) => (
          <FilterRow
            key={f.filter_id}
            filter={f}
            saving={saving === f.filter_id}
            onUpdate={onUpdate}
          />
        ))}
      </ul>
    </section>
  )
}

/**
 * The founder-controlled filters drawer (D3, `d3-contract.md` §6). Grouped
 * by *live* effect — currently hiding / ranking / labelling / off — rather
 * than a fixed order, so the founder can see at a glance that normally only
 * two of the ten filters hide anything, and immediately notice if that
 * ever changes. Toggling a switch, mode, or param calls `PUT
 * /api/filters/{filter_id}` and re-queries the feed (via `onFiltersChanged`)
 * — never a page reload.
 */
export function FiltersDrawer({
  open,
  onOpenChange,
  onFiltersChanged,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onFiltersChanged: () => void
}) {
  const [filters, setFilters] = useState<FounderFilter[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    setError(null)
    api.filters
      .list()
      .then((res) => setFilters(res.filters))
      .catch(() => setError("Could not load filters."))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    // Standard data-fetching effect (React docs: "Fetching data" under "You
    // Might Not Need an Effect") — refetching when `open` flips true is the
    // documented pattern, matching `detail-drawer.tsx` and `page.tsx`.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (open) refresh()
  }, [open, refresh])

  async function handleUpdate(
    filterId: string,
    body: { enabled?: boolean; mode?: FilterMode; params?: Record<string, unknown> }
  ) {
    setSaving(filterId)
    try {
      const updated = await api.filters.update(filterId, body)
      setFilters((prev) =>
        prev
          ? prev.map((f) => (f.filter_id === filterId ? updated : f))
          : prev
      )
      // No page reload: the feed re-queries itself in response.
      onFiltersChanged()
    } catch {
      setError(`Could not update "${filterTitle(filterId)}".`)
    } finally {
      setSaving(null)
    }
  }

  const hiding = filters?.filter((f) => f.enabled && f.mode === "hide") ?? []
  const ranking = filters?.filter((f) => f.enabled && f.mode === "rank_only") ?? []
  const labelling = filters?.filter((f) => f.enabled && f.mode === "label_only") ?? []
  const off = filters?.filter((f) => !f.enabled) ?? []

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto sm:max-w-md"
        aria-describedby={undefined}
      >
        <SheetHeader>
          <SheetTitle>Filters</SheetTitle>
          <SheetDescription>
            Nothing leaves the feed without a switch here. Only filters set to
            &ldquo;Hide&rdquo; and switched on remove a row; everything else
            only ranks or labels.
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-5 px-4 pb-4">
          {loading && !filters && (
            <p className="text-sm text-muted-foreground">Loading filters…</p>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          {filters && (
            <>
              <FilterSection
                title="Hiding"
                hint="Enabled and set to Hide — these remove rows from the feed. Only red lines and excluded industries hide by default."
                filters={hiding}
                saving={saving}
                onUpdate={handleUpdate}
              />
              <Separator className={cn(hiding.length === 0 && "hidden")} />
              <FilterSection
                title="Ranking"
                hint="Enabled and set to Rank only — visible, just reordered. Score and decision are untouched."
                filters={ranking}
                saving={saving}
                onUpdate={handleUpdate}
              />
              <Separator className={cn(ranking.length === 0 && "hidden")} />
              <FilterSection
                title="Labelling"
                hint="Enabled and set to Label only — visible, same order, just flagged on the card."
                filters={labelling}
                saving={saving}
                onUpdate={handleUpdate}
              />
              <Separator className={cn(off.length === 0 && "hidden")} />
              <FilterSection
                title="Off"
                hint="Not evaluated at all right now — the affected count shown is what turning it on would do."
                filters={off}
                saving={saving}
                onUpdate={handleUpdate}
              />
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
