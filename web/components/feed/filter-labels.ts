/**
 * Shared display names for the ten named founder filters (D3,
 * `d3-contract.md` §3), used by both `filters-drawer.tsx` (the row titles)
 * and `opportunity-card.tsx` (the `flagged_by`/`hidden_by` chips) so the
 * two never drift into showing a different label for the same filter_id.
 */
export const FILTER_TITLE: Record<string, string> = {
  geo_eligibility: "Geographic eligibility",
  work_mode_onsite: "On-site work mode",
  red_lines: "Red lines",
  excluded_industries: "Excluded industries",
  track_preference: "Track preference",
  target_roles: "Target roles",
  premium_fulltime_onsite: "Premium full-time on-site",
  stale_postings: "Stale postings",
  min_fit_score: "Minimum fit score",
  compensation_floor: "Compensation floor",
}

/** Falls back to a de-slugged filter_id for anything not in the table
 * above, so a filter this build doesn't know the display name for still
 * renders instead of disappearing. */
export function filterTitle(filterId: string): string {
  return FILTER_TITLE[filterId] ?? filterId.replaceAll("_", " ")
}
