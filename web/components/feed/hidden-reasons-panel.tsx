"use client"

/**
 * C4 UI half — the audit table the dashboard's HIDDEN number links to
 * (`GET /api/hidden-reasons`), with one-click "unhide all by this reason"
 * (`POST /api/hidden-reasons/unhide`). `reason` strings come straight from
 * `api/facets.py::hidden_reasons_for_context` — `"red line: <rule>"`,
 * `"excluded industry: <name>"`, `"filter: <filter_id>"`, or
 * `"facet: <facet_id>"` — rendered verbatim, never relabelled generically.
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
import { api } from "@/lib/api/client"
import type { HiddenReason } from "@/lib/contract/types"

export function HiddenReasonsPanel({
  open,
  onOpenChange,
  onUnhidden,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onUnhidden: () => void
}) {
  const [reasons, setReasons] = useState<HiddenReason[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [unhiding, setUnhiding] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    setError(null)
    api.hiddenReasons
      .list()
      .then((res) => setReasons(res.reasons))
      .catch(() => setError("Could not load hidden reasons."))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    // Standard data-fetching effect (see filters-drawer.tsx's identical
    // pattern and its React-docs citation).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (open) refresh()
  }, [open, refresh])

  async function handleUnhide(reason: string) {
    setUnhiding(reason)
    try {
      await api.hiddenReasons.unhide(reason)
      onUnhidden()
      refresh()
    } catch {
      setError(`Could not unhide "${reason}".`)
    } finally {
      setUnhiding(null)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto sm:max-w-md"
        aria-describedby={undefined}
      >
        <SheetHeader>
          <SheetTitle>Why opportunities are hidden</SheetTitle>
          <SheetDescription>
            One row per specific reason currently hiding something — a red
            line, an excluded industry, a policy filter, or a facet
            exclusion. Unhiding a reason turns off whichever single control
            caused it.
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-2 px-4 pb-4">
          {loading && !reasons && (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          {reasons && reasons.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Nothing is currently hidden.
            </p>
          )}
          {reasons && reasons.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th scope="col" className="pb-1">Reason</th>
                  <th scope="col" className="pb-1 text-right">Count</th>
                  <th scope="col" className="pb-1" />
                </tr>
              </thead>
              <tbody>
                {reasons.map((r) => (
                  <tr
                    key={r.reason}
                    data-testid={`hidden-reason-row-${r.reason}`}
                    className="border-t border-border"
                  >
                    <td className="py-1.5 pr-2">{r.reason}</td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">{r.count}</td>
                    <td className="py-1.5 text-right">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={unhiding === r.reason}
                        data-testid={`unhide-reason-${r.reason}`}
                        onClick={() => handleUnhide(r.reason)}
                      >
                        Unhide all
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
