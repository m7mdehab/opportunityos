import type { DashboardDay } from "@/lib/contract/types"

/**
 * C4's "more than 10% of new rows in a poll were hidden" warning.
 *
 * `api/facets.py::poll_hide_fraction_warnings` is the real, per-poll,
 * filter-*and*-facet-aware pure function the brief describes (tested
 * "2/10 warns, 9/100 does not" — Master's addition #1 to
 * `orders/C3-cards.md`) — but no API route calls it, and every Python file
 * in this repository is frozen for this work order (`AGENTS.md`, the
 * order's "Frozen" section). Reporting that as a scope question rather
 * than silently doing nothing does not satisfy "the brief requires a
 * *visible* warning", so this derives an honest approximation from data
 * `GET /api/dashboard/daily` already exposes: today's `unique_new` and
 * `hidden_by_filters`.
 *
 * Two known, named divergences from the real function (see this order's
 * return notes for the full writeup):
 *  - Granularity is per-*day*, not per-*poll* (the dashboard has no
 *    per-poll breakdown).
 *  - `hidden_by_filters` (api/routes_api.py::dashboard_daily) only counts
 *    the ten policy filters — it does not call `apply_facets`, so a row
 *    hidden only by a C1 facet is not counted here and this warning can
 *    under-report relative to the real per-poll signal.
 * Strictly greater than 10%, never inclusive, matching the real function's
 * own documented threshold.
 */
export interface OverHidingWarning {
  hidden: number
  of: number
  fraction: number
}

export function computeOverHidingWarning(day: DashboardDay | undefined): OverHidingWarning | null {
  if (!day || day.unique_new <= 0) return null
  const fraction = day.hidden_by_filters / day.unique_new
  if (fraction <= 0.1) return null
  return { hidden: day.hidden_by_filters, of: day.unique_new, fraction }
}
