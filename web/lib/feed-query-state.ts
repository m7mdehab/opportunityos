import type {
  FeedMultiFacetId,
  FeedQueryState,
  FeedScoreId,
  FeedSortId,
  FeedUnavailableFilter,
} from "@/lib/contract/types"

export const FEED_MULTI_FACET_IDS: FeedMultiFacetId[] = [
  "work_mode",
  "location_country",
  "location_city",
  "remote_scope",
  "employment_type",
  "seniority_level",
  "target_tier",
  "title_family",
  "source_id",
]

export const FEED_SCORE_IDS: FeedScoreId[] = [
  "fit_score",
  "preference_score",
  "confidence_score",
  "priority_score",
]

export const FEED_SORT_IDS: FeedSortId[] = [
  "recommended",
  "fit_desc",
  "fit_asc",
  "newest_posted",
  "oldest_posted",
  "remote_first",
]

export const FEED_SORT_LABELS: Record<FeedSortId, string> = {
  recommended: "Recommended / Best match",
  fit_desc: "Capability fit — high to low",
  fit_asc: "Capability fit — low to high",
  newest_posted: "Newest posted",
  oldest_posted: "Oldest posted",
  remote_first: "Remote first",
}

export const FEED_UNAVAILABLE_SORT_GROUPS = [
  {
    label: "Recommendation and score sorts",
    reason: "W5.1 exposes this score as a filter or within Recommended, but has no deterministic sort key for it.",
    options: [
      "Preference — high to low", "Preference — low to high",
      "Confidence — high to low", "Confidence — low to high",
      "Priority — high to low", "Priority — low to high",
      "Eligibility — most actionable first", "Eligibility — review-required first",
    ],
  },
  {
    label: "Match-dimension sorts",
    reason: "The individual match dimension is not exposed as a persisted W5.1 sort key.",
    options: [
      "Role/title-family fit — high to low", "Skill fit — high to low",
      "Experience/responsibility fit — high to low", "Seniority fit — high to low",
      "Domain fit — high to low", "Education/certification fit — high to low",
      "Geography/work-mode preference — high to low", "Compensation preference — high to low",
    ],
  },
  {
    label: "Work-arrangement sorts",
    reason: "Only Remote first is available; these additional arrangement and regional preferences have no W5.1 sort key.",
    options: ["Hybrid first", "On-site first", "Worldwide-remote first", "Egypt first", "GCC first", "Canada first"],
  },
  {
    label: "Time sorts",
    reason: "W5.1 supports posted-date order only; discovery, update, deadline, and reverified timestamps are not sort keys.",
    options: [
      "Newly discovered", "Oldest discovered", "Recently updated", "Deadline soonest",
      "Deadline latest", "Recently reverified", "Least recently reverified",
    ],
  },
  {
    label: "Compensation sorts",
    reason: "The W5.1 feed projection has no normalized, currency-and-period-comparable compensation sort field.",
    options: [
      "Compensation — high to low", "Compensation — low to high",
      "Maximum compensation — high to low", "Minimum compensation — high to low",
    ],
  },
  {
    label: "Role and company sorts",
    reason: "These attributes are not exposed as W5.1 sort keys; stable normalization/order is not available in the feed contract.",
    options: [
      "Seniority — low to high", "Seniority — high to low", "Job title A–Z", "Job title Z–A",
      "Company A–Z", "Company Z–A", "Location A–Z", "Source A–Z",
    ],
  },
  {
    label: "Tracker-only sorts",
    reason: "These timestamps and manual fields belong to the job tracker, not the W5.1 opportunity feed sort contract.",
    options: [
      "Recently saved", "Oldest saved", "Recently applied", "Oldest applied",
      "Stage recently changed", "Follow-up due soonest", "Follow-up due latest",
      "Interview date soonest", "Last activity newest", "Last activity oldest",
      "Interest / excitement — high to low", "Manual priority — high to low",
    ],
  },
] as const

export const FEED_UNAVAILABLE_FILTERS: FeedUnavailableFilter[] = [
  { id: "tracking_state", label: "Tracking state", reason: "Saved, snoozed, dismissed, applied, and submitted state combinations are not part of the W5.1 feed-filter contract." },
  { id: "eligibility_evidence", label: "Eligibility evidence", reason: "Qualification decision is available; explicit restriction, sponsorship, and work-authorization evidence is not a queryable projection field." },
  { id: "title_level_and_keywords", label: "Title level and exact title keywords", reason: "Title level and exact title-keyword filters are not exposed by the W5.1 query contract. General text search remains available separately." },
  { id: "location_region", label: "Location regions", reason: "Region text is stored as source-native text and is not normalized into exact selectable region values." },
  { id: "skill_match_and_gaps", label: "Skill match and gaps", reason: "Required, matched, missing, and preferred skills are not persisted as structured per-opportunity query fields." },
  { id: "experience_responsibility", label: "Experience and responsibility", reason: "Years-of-experience and responsibility-level evidence is not persisted in the feed projection query contract." },
  { id: "work_authorization_relocation", label: "Work authorization and relocation", reason: "Job-side authorization, sponsorship, relocation, and on-site cadence evidence is not exposed as queryable projection fields." },
  { id: "compensation", label: "Compensation ranges", reason: "Compensation provenance exists outside the feed-query projection, without normalized comparable amount, currency, and pay-period fields." },
  { id: "company_attributes", label: "Company attributes", reason: "Industry, size, stage, ownership, funding, and employer-name filters are not exposed as normalized W5.1 query dimensions." },
  { id: "source_taxonomy_and_health", label: "Source family, ATS, and source health", reason: "Source ID is queryable; source family, ATS type, source quality, polling health, and error-rate dimensions are not normalized in the feed contract." },
  { id: "posting_health", label: "Posting freshness and health", reason: "Posted-date bounds are queryable; deadline, discovery time, stale/reverified state, and duplicate/closed health signals are not persisted in this query contract." },
  { id: "content_completeness", label: "Content completeness", reason: "Description presence, description length, structured-field coverage, and extraction-confidence flags are not queryable projection fields." },
  { id: "education_certification", label: "Education and certification", reason: "Degree, education-level, and certification requirements are not persisted as structured feed-query fields." },
  { id: "language_timezone_travel", label: "Language, time zone, and travel", reason: "Language, working-hour overlap, time-zone, and travel requirements are not persisted as structured feed-query fields." },
  { id: "cv_application_readiness", label: "CV and application readiness", reason: "Canonical CV selection and application-artifact readiness are user/tracker concerns outside the W5.1 opportunity query dimensions." },
  { id: "tracked_user_metadata", label: "Tracked-job user metadata", reason: "Notes, follow-up dates, application status, and user-defined tags are tracker metadata and are not part of the feed projection." },
]

export const EMPTY_FEED_QUERY: FeedQueryState = {
  track: "",
  decision: "",
  q: "",
  multi: {
    work_mode: [],
    location_country: [],
    location_city: [],
    remote_scope: [],
    employment_type: [],
    seniority_level: [],
    target_tier: [],
    title_family: [],
    source_id: [],
  },
  scoreRanges: {
    fit_score: { min: "", max: "" },
    preference_score: { min: "", max: "" },
    confidence_score: { min: "", max: "" },
    priority_score: { min: "", max: "" },
  },
  postedFrom: "",
  postedTo: "",
  sortBy: "recommended",
  includeHidden: false,
}

export interface FeedQueryPageState {
  filters: FeedQueryState
  page: number
}

const QUERY_KEYS = [
  "track",
  "decision",
  "q",
  "min_score",
  "max_score",
  "min_fit_score",
  "max_fit_score",
  "min_preference_score",
  "max_preference_score",
  "min_confidence_score",
  "max_confidence_score",
  "min_priority_score",
  "max_priority_score",
  "posted_from",
  "posted_to",
  "sort_by",
  "include_hidden",
  "page",
  "page_size",
  ...FEED_MULTI_FACET_IDS,
]

function validScore(value: string | null): string {
  if (!value?.trim()) return ""
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 100
    ? String(parsed)
    : ""
}

function validDate(value: string | null): string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return ""
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value
    ? ""
    : value
}

export function parseFeedQueryParams(params: URLSearchParams): FeedQueryPageState {
  const sort = params.get("sort_by")
  const sortBy = FEED_SORT_IDS.includes(sort as FeedSortId)
    ? (sort as FeedSortId)
    : EMPTY_FEED_QUERY.sortBy
  const filters: FeedQueryState = {
    ...EMPTY_FEED_QUERY,
    multi: Object.fromEntries(
      FEED_MULTI_FACET_IDS.map((facet) => [facet, [...new Set(params.getAll(facet).filter(Boolean))]])
    ) as FeedQueryState["multi"],
    scoreRanges: {
      fit_score: {
        min: validScore(params.get("min_fit_score") ?? params.get("min_score")),
        max: validScore(params.get("max_fit_score") ?? params.get("max_score")),
      },
      preference_score: {
        min: validScore(params.get("min_preference_score")),
        max: validScore(params.get("max_preference_score")),
      },
      confidence_score: {
        min: validScore(params.get("min_confidence_score")),
        max: validScore(params.get("max_confidence_score")),
      },
      priority_score: {
        min: validScore(params.get("min_priority_score")),
        max: validScore(params.get("max_priority_score")),
      },
    },
    track: params.get("track") ?? "",
    decision: params.get("decision") ?? "",
    q: params.get("q") ?? "",
    postedFrom: validDate(params.get("posted_from")),
    postedTo: validDate(params.get("posted_to")),
    sortBy,
    includeHidden: params.get("include_hidden") === "true",
  }
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1)
  return { filters, page }
}

export function buildFeedQueryParams(
  filters: FeedQueryState,
  page: number,
  pageSize: number
): URLSearchParams {
  const params = new URLSearchParams()
  const add = (key: string, value: string | number | undefined) => {
    if (value !== undefined && String(value) !== "") params.set(key, String(value))
  }

  add("track", filters.track)
  add("decision", filters.decision)
  add("q", filters.q.trim())
  add("min_score", filters.scoreRanges.fit_score.min)
  add("min_fit_score", filters.scoreRanges.fit_score.min)
  add("max_fit_score", filters.scoreRanges.fit_score.max)
  add("min_preference_score", filters.scoreRanges.preference_score.min)
  add("max_preference_score", filters.scoreRanges.preference_score.max)
  add("min_confidence_score", filters.scoreRanges.confidence_score.min)
  add("max_confidence_score", filters.scoreRanges.confidence_score.max)
  add("min_priority_score", filters.scoreRanges.priority_score.min)
  add("max_priority_score", filters.scoreRanges.priority_score.max)
  add("posted_from", filters.postedFrom)
  add("posted_to", filters.postedTo)
  add("sort_by", filters.sortBy)
  if (filters.includeHidden) add("include_hidden", "true")
  for (const facet of FEED_MULTI_FACET_IDS) {
    for (const value of filters.multi[facet]) params.append(facet, value)
  }
  add("page", page)
  add("page_size", pageSize)
  return params
}

export function updateFeedUrlParams(
  current: URLSearchParams,
  filters: FeedQueryState,
  page: number,
  pageSize: number
): URLSearchParams {
  const next = new URLSearchParams(current)
  for (const key of QUERY_KEYS) next.delete(key)
  const query = buildFeedQueryParams(filters, page, pageSize)
  query.forEach((value, key) => next.append(key, value))
  return next
}

export function hasActiveFeedQuery(filters: FeedQueryState): boolean {
  const hasScoreRange = FEED_SCORE_IDS.some((score) =>
    Boolean(filters.scoreRanges[score].min || filters.scoreRanges[score].max)
  )
  return Boolean(
    filters.track ||
      filters.decision ||
      filters.q.trim() ||
      filters.postedFrom ||
      filters.postedTo ||
      filters.includeHidden ||
      filters.sortBy !== "recommended" ||
      FEED_MULTI_FACET_IDS.some((facet) => filters.multi[facet].length > 0) ||
      hasScoreRange
  )
}

export function hasAdvancedFeedQuery(filters: FeedQueryState): boolean {
  return Boolean(
    FEED_MULTI_FACET_IDS.some((facet) => filters.multi[facet].length > 0) ||
      filters.postedFrom ||
      filters.postedTo ||
      filters.includeHidden ||
      filters.sortBy !== "recommended" ||
      filters.scoreRanges.fit_score.max ||
      filters.scoreRanges.preference_score.min ||
      filters.scoreRanges.preference_score.max ||
      filters.scoreRanges.confidence_score.min ||
      filters.scoreRanges.confidence_score.max ||
      filters.scoreRanges.priority_score.min ||
      filters.scoreRanges.priority_score.max
  )
}

export function feedQueryValidationError(filters: FeedQueryState): string | null {
  for (const score of FEED_SCORE_IDS) {
    const { min, max } = filters.scoreRanges[score]
    if (min && (!Number.isFinite(Number(min)) || Number(min) < 0 || Number(min) > 100)) {
      return `${score.replaceAll("_", " ")} minimum must be from 0 to 100.`
    }
    if (max && (!Number.isFinite(Number(max)) || Number(max) < 0 || Number(max) > 100)) {
      return `${score.replaceAll("_", " ")} maximum must be from 0 to 100.`
    }
    if (min && max && Number(min) > Number(max)) {
      return `${score.replaceAll("_", " ")} minimum cannot exceed its maximum.`
    }
  }
  if (filters.postedFrom && filters.postedTo && filters.postedFrom > filters.postedTo) {
    return "Posted-from date cannot be later than posted-to date."
  }
  return null
}
