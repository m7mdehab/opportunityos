"use client"

/**
 * C1 UI half — the generic 15-attribute facet panel (`GET /api/facets`,
 * `PUT /api/facets/{facet_id}`), plus saved views (`GET/POST/PUT
 * /api/saved-views`). Deliberately a *separate* control set from
 * `FiltersDrawer` (the ten policy filters): a facet is `include` / `exclude`
 * / `off` **per value**, never `hide` / `rank_only` / `label_only`, and one
 * of the ten policy filters carries an Overseer decision the facets must
 * never be merged into (Master's addition #3 to `orders/C3-cards.md`).
 *
 * `language` is permanently unavailable (no language is ever persisted
 * anywhere in the schema) and renders exactly like `filters-drawer.tsx`
 * renders an inert filter: its own visible reason, never hidden, never
 * rendered as though it works (Master's addition #2).
 */
import { useCallback, useEffect, useState } from "react"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { AlertTriangle, X, Star, StarOff } from "lucide-react"
import { api } from "@/lib/api/client"
import type { Facet, FacetValueState, SavedView } from "@/lib/contract/types"

const selectClasses =
  "h-7 rounded-lg border border-input bg-card text-foreground px-2 text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

function facetTitle(facetId: string): string {
  return facetId.replaceAll("_", " ")
}

function facetOnlyViews(views: SavedView[]): SavedView[] {
  return views.filter((view) => !view.feed_query)
}

function ValueRow({
  facet,
  value,
  saving,
  onUpdate,
}: {
  facet: Facet
  value: Facet["values"][number]
  saving: boolean
  onUpdate: (state: FacetValueState) => void
}) {
  return (
    <li
      data-testid={`facet-value-${facet.facet_id}-${value.value}`}
      className="flex items-center justify-between gap-2 rounded-md border border-border px-2 py-1"
    >
      <span className="min-w-0 truncate text-xs">
        {value.value} <span className="text-muted-foreground">({value.count})</span>
      </span>
      <select
        aria-label={`${facetTitle(facet.facet_id)}: ${value.value}`}
        className={selectClasses}
        disabled={saving}
        value={value.state}
        onChange={(e) => onUpdate(e.target.value as FacetValueState)}
      >
        <option value="off">Off</option>
        <option value="include">Include</option>
        <option value="exclude">Exclude</option>
      </select>
    </li>
  )
}

function FacetSection({
  facet,
  saving,
  onUpdateValue,
  onReset,
}: {
  facet: Facet
  saving: boolean
  onUpdateValue: (value: string, state: FacetValueState) => void
  onReset: () => void
}) {
  if (!facet.available) {
    return (
      <li
        data-testid={`facet-row-${facet.facet_id}`}
        className="rounded-lg border border-dashed border-amber-600/40 bg-amber-50/30 p-3 dark:bg-amber-950/10"
      >
        <p className="text-sm font-medium">{facetTitle(facet.facet_id)}</p>
        <div
          data-facet-effect="unavailable"
          className="mt-2 flex items-start gap-1.5 rounded-md border border-amber-600/30 bg-amber-50 px-2 py-1.5 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200"
        >
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          <p>
            <span className="font-medium">Unavailable — matches nothing right now.</span>{" "}
            {facet.unavailable_reason}
          </p>
        </div>
      </li>
    )
  }

  const excludedValues = facet.values.filter((v) => v.state === "exclude")
  const includedValues = facet.values.filter((v) => v.state === "include")

  return (
    <li data-testid={`facet-row-${facet.facet_id}`} className="rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{facetTitle(facet.facet_id)}</p>
          <p className="text-[11px] text-muted-foreground">{facet.description}</p>
        </div>
        {facet.excluded_count > 0 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid={`facet-show-excluded-${facet.facet_id}`}
            onClick={onReset}
          >
            Show {facet.excluded_count} excluded by {facetTitle(facet.facet_id)}
          </Button>
        )}
      </div>

      {(includedValues.length > 0 || excludedValues.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {includedValues.map((v) => (
            <Badge
              key={v.value}
              data-testid={`facet-chip-include-${facet.facet_id}-${v.value}`}
              variant="outline"
              className="gap-1 border-emerald-600/30 bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
            >
              only: {v.value}
              <button
                type="button"
                aria-label={`Remove include ${v.value} from ${facetTitle(facet.facet_id)}`}
                onClick={() => onUpdateValue(v.value, "off")}
              >
                <X aria-hidden="true" className="size-3" />
              </button>
            </Badge>
          ))}
          {excludedValues.map((v) => (
            <Badge
              key={v.value}
              data-testid={`facet-chip-exclude-${facet.facet_id}-${v.value}`}
              variant="outline"
              className="gap-1 border-red-600/30 bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-300"
            >
              excluded: {v.value}
              <button
                type="button"
                aria-label={`Remove exclude ${v.value} from ${facetTitle(facet.facet_id)}`}
                onClick={() => onUpdateValue(v.value, "off")}
              >
                <X aria-hidden="true" className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      <ul className="mt-2 space-y-1">
        {facet.values.map((v) => (
          <ValueRow
            key={v.value}
            facet={facet}
            value={v}
            saving={saving}
            onUpdate={(state) => onUpdateValue(v.value, state)}
          />
        ))}
      </ul>
    </li>
  )
}

export function FacetsPanel({
  open,
  onOpenChange,
  onFacetsChanged,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onFacetsChanged: () => void
}) {
  const [facets, setFacets] = useState<Facet[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)

  const [views, setViews] = useState<SavedView[] | null>(null)
  const [newViewName, setNewViewName] = useState("")
  const [viewError, setViewError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([api.facets.list(), api.savedViews.list()])
      .then(([f, v]) => {
        setFacets(f.facets)
        setViews(facetOnlyViews(v.views))
      })
      .catch(() => setError("Could not load facets."))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    // Standard data-fetching effect (see filters-drawer.tsx's identical
    // pattern and its React-docs citation).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (open) refresh()
  }, [open, refresh])

  async function updateFacet(facetId: string, include: string[], exclude: string[]) {
    setSaving(facetId)
    try {
      await api.facets.update(facetId, { include, exclude })
      onFacetsChanged()
      refresh()
    } catch {
      setError(`Could not update "${facetTitle(facetId)}".`)
    } finally {
      setSaving(null)
    }
  }

  function handleUpdateValue(facet: Facet, value: string, state: FacetValueState) {
    const include = facet.include.filter((v) => v !== value)
    const exclude = facet.exclude.filter((v) => v !== value)
    if (state === "include") include.push(value)
    if (state === "exclude") exclude.push(value)
    updateFacet(facet.facet_id, include, exclude)
  }

  function handleReset(facet: Facet) {
    updateFacet(facet.facet_id, [], [])
  }

  function currentFacetSelection(): Record<string, { include: string[]; exclude: string[] }> {
    const out: Record<string, { include: string[]; exclude: string[] }> = {}
    for (const f of facets ?? []) {
      if (f.include.length > 0 || f.exclude.length > 0) {
        out[f.facet_id] = { include: f.include, exclude: f.exclude }
      }
    }
    return out
  }

  async function handleCreateView() {
    if (!newViewName.trim()) {
      setViewError("Name is required.")
      return
    }
    setViewError(null)
    try {
      await api.savedViews.create({
        name: newViewName.trim(),
        facets: currentFacetSelection(),
        is_default: false,
      })
      setNewViewName("")
      const res = await api.savedViews.list()
      setViews(facetOnlyViews(res.views))
    } catch {
      setViewError("Could not save this view.")
    }
  }

  async function handleApplyView(view: SavedView) {
    // Applying a view means every facet ends up exactly at the view's
    // stored selection — including facets the view left off (cleared),
    // not just the ones it explicitly set.
    const targets = new Set(Object.keys(view.facets))
    for (const f of facets ?? []) targets.add(f.facet_id)
    for (const facetId of targets) {
      const sel = view.facets[facetId] ?? { include: [], exclude: [] }
      await api.facets.update(facetId, { include: sel.include, exclude: sel.exclude })
    }
    onFacetsChanged()
    refresh()
  }

  async function handleSetDefault(view: SavedView) {
    await api.savedViews.update(view.id, { is_default: true })
    const res = await api.savedViews.list()
    setViews(facetOnlyViews(res.views))
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto sm:max-w-md"
        aria-describedby={undefined}
      >
        <SheetHeader>
          <SheetTitle>Facets</SheetTitle>
          <SheetDescription>
            Narrow the feed by any attribute — include, exclude, or leave off.
            Separate from Filters: nothing here changes decision or score.
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-4 px-4 pb-4">
          {loading && !facets && (
            <p className="text-sm text-muted-foreground">Loading facets…</p>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          <section aria-labelledby="saved-views-heading">
            <h3 id="saved-views-heading" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Saved views
            </h3>
            <ul className="mt-2 space-y-1">
              {(views ?? []).map((v) => (
                <li
                  key={v.id}
                  data-testid={`saved-view-${v.id}`}
                  className="flex items-center justify-between gap-2 rounded-md border border-border px-2 py-1"
                >
                  <button
                    type="button"
                    data-testid={`saved-view-select-${v.id}`}
                    className="min-w-0 truncate text-left text-xs font-medium underline-offset-2 hover:underline"
                    onClick={() => handleApplyView(v)}
                  >
                    {v.name}
                  </button>
                  <button
                    type="button"
                    aria-label={v.is_default ? `${v.name} is the default view` : `Set ${v.name} as default`}
                    aria-pressed={v.is_default}
                    data-testid={`saved-view-set-default-${v.id}`}
                    disabled={v.is_default}
                    onClick={() => handleSetDefault(v)}
                    className="shrink-0 text-amber-600 disabled:opacity-100"
                  >
                    {v.is_default ? (
                      <Star aria-hidden="true" className="size-4 fill-current" />
                    ) : (
                      <StarOff aria-hidden="true" className="size-4" />
                    )}
                  </button>
                </li>
              ))}
              {views && views.length === 0 && (
                <p className="text-xs text-muted-foreground">No saved views yet.</p>
              )}
            </ul>
            <div className="mt-2 flex items-end gap-2">
              <div className="flex flex-1 flex-col gap-1">
                <Label htmlFor="new-view-name" className="text-[11px] text-muted-foreground">
                  Save current selection as
                </Label>
                <Input
                  id="new-view-name"
                  data-testid="new-saved-view-name"
                  className="h-8 text-xs"
                  value={newViewName}
                  onChange={(e) => setNewViewName(e.target.value)}
                />
              </div>
              <Button
                type="button"
                size="sm"
                data-testid="create-saved-view"
                onClick={handleCreateView}
              >
                Save view
              </Button>
            </div>
            {viewError && (
              <p role="alert" className="mt-1 text-xs text-destructive">
                {viewError}
              </p>
            )}
          </section>

          <Separator />

          {facets && (
            <ul className="flex flex-col gap-3">
              {facets.map((f) => (
                <FacetSection
                  key={f.facet_id}
                  facet={f}
                  saving={saving === f.facet_id}
                  onUpdateValue={(value, state) => handleUpdateValue(f, value, state)}
                  onReset={() => handleReset(f)}
                />
              ))}
            </ul>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
