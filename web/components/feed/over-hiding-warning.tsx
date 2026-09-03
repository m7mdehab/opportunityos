"use client"

import { AlertTriangle } from "lucide-react"
import type { OverHidingWarning } from "@/lib/format/over-hiding"

/** Master's addition #1 to `orders/C3-cards.md`: the >10% over-hiding
 * warning must be *visible*, not just a tested pure function. See
 * `lib/format/over-hiding.ts` for exactly what this is derived from and
 * how it differs from the real per-poll signal. */
export function OverHidingWarningBanner({ warning }: { warning: OverHidingWarning }) {
  const pct = Math.round(warning.fraction * 100)
  return (
    <div
      role="alert"
      data-testid="over-hiding-warning"
      className="mx-4 mt-3 flex items-start gap-2 rounded-md border border-amber-600/40 bg-amber-50 px-3 py-2 text-xs text-amber-900 sm:mx-6 dark:bg-amber-950 dark:text-amber-200"
    >
      <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <p>
        <span className="font-medium">
          More than 10% of today&apos;s new opportunities were hidden
        </span>{" "}
        by your filters ({warning.hidden} of {warning.of}, {pct}%). Check the
        hidden-reasons table before assuming nothing suitable came in today.
      </p>
    </div>
  )
}
