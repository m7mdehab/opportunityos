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
import { EyeOff, ArrowDownWideNarrow, Tag, PowerOff, AlertTriangle } from "lucide-react"
import { api } from "@/lib/api/client"
import { filterTitle } from "@/components/feed/filter-labels"
import type { FilterMode, FounderFilter } from "@/lib/contract/types"

const selectClasses =
  "h-7 rounded-lg border border-input bg-card text-foreground px-2 text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

/** `unavailable_reason` is a repair landing after D3's original API/web
 * split, so a real API that has not deployed it yet will omit the key
 * entirely rather than send `null` — `res.filters` would then type-check
 * as `FounderFilter[]` but actually hand back `undefined` at runtime for
 * that field. Every place a `FounderFilter` enters this component's state
 * goes through here first, so `undefined` is treated exactly like `null`
 * (available) everywhere else in this file, and an older API can never
 * make a row throw or silently misrender as permanently unavailable. */
function normalizeUnavailableReason(filter: FounderFilter): FounderFilter {
  return { ...filter, unavailable_reason: filter.unavailable_reason ?? null }
}

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

/** Council finding (FR-005 D3 repair): a filter can be permanently inert
 * — its predicate can never match anything — while still reading
 * `enabled: true` with `affected_count: 0`, which the founder would
 * otherwise read as "you have none of these" rather than "this can't be
 * computed yet". `affected_count` is deliberately not shown here (the
 * contract holds it at 0, which is exactly the misleading number this
 * exists to replace); the reason is shown instead, with the same
 * icon + colour + text encoding as `constraint-outcome.tsx`'s UNKNOWN, so
 * this state is never mistaken for either "enabled and working" or
 * "switched off". */
function UnavailableNotice({ reason }: { reason: string }) {
  return (
    <div
      data-filter-effect="unavailable"
      className="flex items-start gap-1.5 rounded-md border border-amber-600/30 bg-amber-50 px-2 py-1.5 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200"
    >
      <AlertTriangle aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
      <p>
        <span className="font-medium">Unavailable — matches nothing right now.</span>{" "}
        {reason}
      </p>
    </div>
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
  const isUnavailable = filter.unavailable_reason !== null

  return (
    <li
      data-testid={`filter-row-${filter.filter_id}`}
      className={cn(
        "rounded-lg border p-3",
        // Distinct from both an ordinary row and a "hide"-tinted one — see
        // `UnavailableNotice` above for why this state needs its own
        // treatment rather than reading as "0 matches".
        isUnavailable
          ? "border-dashed border-amber-600/40 bg-amber-50/30 dark:bg-amber-950/10"
          : "border-border"
      )}
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
        {/* Still switchable even when unavailable — see the module doc on
            `FiltersDrawer` for why the toggle stays live rather than being
            disabled. */}
        <Switch
          id={`filter-switch-${filter.filter_id}`}
          checked={filter.enabled}
          disabled={saving}
          onCheckedChange={(enabled) => onUpdate(filter.filter_id, { enabled })}
        />
      </div>

      {isUnavailable && (
        <div className="mt-2">
          <UnavailableNotice reason={filter.unavailable_reason!} />
        </div>
      )}

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

        {/* Not shown when unavailable: "Ranking 0 lower" / "Off — would
            affect 0" would carry exactly the same false "I checked, there's
            nothing" signal the reason text above exists to replace. */}
        {!isUnavailable && (
          <div className="ml-auto">
            <FilterStatusChip filter={filter} />
          </div>
        )}
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
  tone = "default",
}: {
  title: string
  hint: string
  filters: FounderFilter[]
  saving: string | null
  onUpdate: (
    filterId: string,
    body: { enabled?: boolean; mode?: FilterMode; params?: Record<string, unknown> }
  ) => void
  tone?: "default" | "warning"
}) {
  if (filters.length === 0) return null
  return (
    <section>
      <h3
        className={cn(
          "flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide",
          tone === "warning"
            ? "text-amber-400"
            : "text-muted-foreground"
        )}
      >
        {tone === "warning" && (
          <AlertTriangle aria-hidden="true" className="size-3.5" />
        )}
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
 * by *live* effect — unavailable / currently hiding / ranking / labelling /
 * off — rather than a fixed order, so the founder can see at a glance that
 * normally only two of the ten filters hide anything, and immediately
 * notice if that ever changes. Toggling a switch, mode, or param calls
 * `PUT /api/filters/{filter_id}` and re-queries the feed (via
 * `onFiltersChanged`) — never a page reload.
 *
 * "Unavailable" (council finding, D3 repair) is rendered as its own section
 * first, ahead of "Hiding": a filter whose predicate can never match
 * anything yet must never be read as quietly doing its job just because it
 * shows `enabled: true` with nothing in the way. It is excluded from the
 * other four groups for the same reason — it would otherwise land in
 * "Hiding"/"Ranking"/"Labelling" purely from its stored `enabled`/`mode`,
 * which is exactly the false "protected" reading this exists to prevent.
 *
 * The on/off switch stays live (not `disabled`) even on an unavailable
 * row. Two options were on the table: disable the switch, since flipping
 * it currently has zero observable effect; or leave it switchable, since
 * `enabled`/`mode` here are still a real, durable founder preference that
 * the API happily persists regardless of availability, and will start
 * mattering the moment the underlying data shows up (a truth-pack
 * assertion gets added, a staleness write path ships) — without the
 * founder having to remember to come back and turn it on then. Disabling
 * the control would also read as a second, different kind of "you can't
 * touch this", when the actual message is narrower: "this can't act on
 * anything *yet*". Once the reason text above already says that plainly,
 * toggling the switch is no longer a misleading action, so it is left on.
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
      .then((res) => setFilters(res.filters.map(normalizeUnavailableReason)))
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
      const updated = normalizeUnavailableReason(
        await api.filters.update(filterId, body)
      )
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

  const unavailable = filters?.filter((f) => f.unavailable_reason !== null) ?? []
  const hiding =
    filters?.filter(
      (f) => f.unavailable_reason === null && f.enabled && f.mode === "hide"
    ) ?? []
  const ranking =
    filters?.filter(
      (f) =>
        f.unavailable_reason === null && f.enabled && f.mode === "rank_only"
    ) ?? []
  const labelling =
    filters?.filter(
      (f) =>
        f.unavailable_reason === null && f.enabled && f.mode === "label_only"
    ) ?? []
  const off =
    filters?.filter((f) => f.unavailable_reason === null && !f.enabled) ?? []

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
                title="Unavailable"
                hint="These can't match anything yet regardless of their switch — the reason is shown on each row. Not the same as &ldquo;off&rdquo;, and never counted as protection."
                filters={unavailable}
                saving={saving}
                onUpdate={handleUpdate}
                tone="warning"
              />
              <Separator className={cn(unavailable.length === 0 && "hidden")} />
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
              <Separator className={cn(labelling.length === 0 && "hidden")} />
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
