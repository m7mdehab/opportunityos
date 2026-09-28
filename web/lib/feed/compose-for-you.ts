export type ForYouCompositionRow = {
  opportunity_id?: unknown
  id?: unknown
  family_key?: unknown
  organization?: unknown
  recommendation_priority?: unknown
}

function rowId(row: ForYouCompositionRow): string {
  return String(row.opportunity_id ?? row.id ?? "")
}

function rowPriority(row: ForYouCompositionRow): number {
  const value = Number(row.recommendation_priority)
  return Number.isFinite(value) ? value : Number.NEGATIVE_INFINITY
}

function compareRank(a: ForYouCompositionRow, b: ForYouCompositionRow): number {
  const rankDifference = rowPriority(b) - rowPriority(a)
  return rankDifference || rowId(a).localeCompare(rowId(b))
}

/**
 * Apply the deterministic family and employer diversity rules used by BC.
 * Input is already filtered by the hosted feed query; this only composes the
 * surviving For You rows before API pagination.
 */
export function composeForYouRows<T extends ForYouCompositionRow>(
  rows: readonly T[],
  limit: number,
): T[] {
  const bestByFamily = new Map<string, T>()
  const ungrouped: T[] = []

  for (const row of rows) {
    const family = typeof row.family_key === "string" ? row.family_key.trim() : ""
    if (!family) {
      ungrouped.push(row)
      continue
    }
    const previous = bestByFamily.get(family)
    if (!previous || compareRank(row, previous) < 0) bestByFamily.set(family, row)
  }

  const ranked = [...ungrouped, ...bestByFamily.values()].sort(compareRank)
  const selected: T[] = []
  const deferred: T[] = []
  const employerCounts = new Map<string, number>()

  for (const row of ranked) {
    const employer = String(row.organization ?? "").trim().toLocaleLowerCase()
    const rank = selected.length + 1
    const cap = rank <= 20 ? 4 : rank <= 50 ? 6 : null
    if (employer && cap !== null && (employerCounts.get(employer) ?? 0) >= cap) {
      deferred.push(row)
      continue
    }
    selected.push(row)
    if (employer) employerCounts.set(employer, (employerCounts.get(employer) ?? 0) + 1)
  }

  // Match the existing recommendation engine: relax the employer cap only
  // when the un-deferred inventory cannot fill the requested range.
  for (const row of deferred) {
    if (selected.length >= limit) break
    selected.push(row)
  }

  return selected.slice(0, Math.max(0, limit))
}
