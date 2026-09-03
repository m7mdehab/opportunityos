/** Relative "posted age" text for the card (C3 requirement: "posted age").
 * `posted_date` is a `YYYY-MM-DD` (or full ISO) string on
 * `OpportunityListItem` — this only ever reads that existing field, never
 * a new API field. Returns `null` when there is nothing to compute from,
 * so the caller can render its own explicit "no date" state rather than a
 * placeholder that looks like a real age. */
export function postedAge(postedDate: string | null, now: Date = new Date()): string | null {
  if (!postedDate) return null
  const posted = new Date(`${postedDate.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(posted.getTime())) return null
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))
  const days = Math.round((today.getTime() - posted.getTime()) / 86_400_000)
  if (days < 0) return "posted in the future"
  if (days === 0) return "posted today"
  if (days === 1) return "posted 1 day ago"
  if (days < 30) return `posted ${days} days ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `posted ${months} month${months === 1 ? "" : "s"} ago`
  const years = Math.floor(months / 12)
  return `posted ${years} year${years === 1 ? "" : "s"} ago`
}

/** Best-effort employer domain from `source_url`, for the card's "employer
 * logo/domain when available" requirement. No network request is ever made
 * (no favicon fetch — that would be an unauthorized external call); this
 * only parses the URL the API already returned. Returns `null` for a
 * missing/unparseable URL rather than rendering a placeholder. */
export function employerDomain(sourceUrl: string | null | undefined): string | null {
  if (!sourceUrl) return null
  try {
    return new URL(sourceUrl).hostname.replace(/^www\./, "")
  } catch {
    return null
  }
}
