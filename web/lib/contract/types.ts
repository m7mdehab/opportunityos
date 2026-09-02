/**
 * Types mirroring the FR-004 API contract exactly (see contract.md, fixed by the
 * Master). Do not widen or coerce any of these unions — in particular:
 *
 *  - `decision` includes `null` (not yet evaluated) and `"uncertain"` is never
 *    coerced to `"ineligible"`.
 *  - constraint `outcome` is `"PASS" | "FAIL" | "UNKNOWN"` — `UNKNOWN` is
 *    structurally distinct from `FAIL` everywhere it is rendered.
 *  - `fit_score` and `min_score` are on a 0-100 scale. Per-dimension `score`
 *    (and `weighted_score`) inside `dimension_scores` are on a 0-1 scale and
 *    must be rendered as a percentage.
 */

export type Track = "employment" | "contract" | "freelance" | "procurement"

export type Decision = "qualified" | "ineligible" | "uncertain" | null

export type ConstraintOutcome = "PASS" | "FAIL" | "UNKNOWN"

export type ActionState = "submitted" | "dismissed" | "snoozed" | null

export type FeedbackLabel =
  | "good_match"
  | "bad_match"
  | "eligibility_wrong"
  | "seniority_wrong"
  | "irrelevant_role"
  | "source_quality_issue"
  | "duplicate_issue"
  | "review_required"

export interface OpportunityListItem {
  id: string
  title: string
  organization: string
  source_id: string
  source_url: string
  track: Track
  decision: Decision
  fit_score: number | null
  top_reasons: string[]
  deadline: string | null
  posted_date: string | null
  is_stale: boolean
  action_state: ActionState
  feedback_label: FeedbackLabel | null
  /** filter_ids in `hide` mode that currently match this item. Always
   * present, `[]` when empty — never `null`. Non-empty only when the item
   * is returned via `include_hidden=true`, since a `hide` match is
   * otherwise omitted from `items` entirely. */
  hidden_by: string[]
  /** filter_ids in `rank_only` or `label_only` mode that currently match
   * this item. Always present, `[]` when empty — never `null`. Rendered as
   * chips; never implies the item was removed or re-scored. */
  flagged_by: string[]
}

export interface OpportunityListResponse {
  page: number
  page_size: number
  total: number
  /** Count of opportunities currently hidden by an enabled `hide`-mode
   * filter, regardless of `include_hidden`. */
  hidden_count: number
  items: OpportunityListItem[]
}

/** D3 — founder-controlled filters (`founder_filter_settings`). A toggle
 * changes only whether a row is hidden, ranked, or merely labelled: it
 * never changes `decision` or `fit_score` on any `OpportunityListItem`. */
export type FilterMode = "hide" | "rank_only" | "label_only"

export interface FounderFilter {
  filter_id: string
  enabled: boolean
  mode: FilterMode
  /** Free-form per-filter parameters (e.g. `min_fit_score.threshold`,
   * `compensation_floor.monthly_minimum` + `currency`). Empty object when
   * the filter takes no parameters. */
  params: Record<string, unknown>
  /** Count of opportunities this filter currently matches, computed
   * regardless of `enabled` — so the drawer can show what enabling it
   * would do before the founder flips the switch. */
  affected_count: number
  description: string
}

export interface FiltersResponse {
  filters: FounderFilter[]
}

/** Body for `PUT /api/filters/{filter_id}`. All keys optional; an absent
 * key leaves that property unchanged. */
export interface FilterUpdateRequest {
  enabled?: boolean
  mode?: FilterMode
  params?: Record<string, unknown>
}

export interface OpportunityField {
  field_name: string
  value: string | null
  raw_value: string | null
  derivation_type: string
  raw_pointer: string | null
  rule_id: string | null
  record_checksum: string | null
}

export interface QualificationConstraint {
  constraint_name: string
  outcome: ConstraintOutcome
  reason: string
  required_field: string | null
  founder_fact: string | null
  is_hard_failure: boolean
  provenance_pointer: string | null
}

export interface Qualification {
  decision: Decision
  constraints: QualificationConstraint[]
}

export interface DimensionScore {
  dimension: string
  /** 0-1 scale. Render as a percentage. */
  score: number
  /** 0-1 scale. */
  weight: number
  /** 0-1 scale (score * weight). Render as a percentage. */
  weighted_score: number
  rationale: string
}

export interface Scoring {
  /** 0-100 scale, unlike DimensionScore.score. */
  fit_score: number | null
  dimension_scores: DimensionScore[]
  strengths: string[]
  gaps: string[]
  unknowns: string[]
  uncertainty_penalty: number
  explanation: string
  policy_version: string
  evaluated_at: string
  truth_pack_hash: string | null
}

export interface ActionHistoryEntry {
  action_id: string
  action_status: string
  execution_mode: string
  created_at: string
  updated_at: string
  notes: string | null
}

export interface FeedbackHistoryEntry {
  id: string
  feedback_label: FeedbackLabel
  structured_reason: string | null
  notes: string | null
  created_at: string
}

export interface OpportunityDetail {
  id: string
  title: string
  organization: string
  source_id: string
  source_url: string
  track: Track
  description: string
  deadline: string | null
  posted_date: string | null
  is_stale: boolean
  reverified_at: string | null
  fields: OpportunityField[]
  qualification: Qualification
  scoring: Scoring
  evidence_links: string[]
  action_history: ActionHistoryEntry[]
  feedback_history: FeedbackHistoryEntry[]
}

export interface ArtifactRejectionFinding {
  claim: string
  assertion_type: string
  rejection_reasons: string[]
}

export interface ArtifactRejection {
  detail: "claim validation failed"
  findings: ArtifactRejectionFinding[]
}

export interface NoTruthPackForArtifact {
  detail: "no truth pack loaded"
  reason: string
}

export interface FeedbackResponse {
  id: string
  opportunity_id: string
  feedback_label: FeedbackLabel
  structured_reason: string | null
  notes: string | null
  created_at: string
}

export type ActionType = "mark_applied" | "dismiss" | "snooze"

export interface ActionResponse {
  opportunity_id: string
  action_state: ActionState
  action_id: string | null
  until: string | null
  created_at: string
}

export interface DashboardDay {
  date: string
  fetched: number
  unique_new: number
  qualified: number
  high_fit: number
  opened: number
  labelled: number
  applied: number
  /** Count of opportunities hidden that day by an enabled `hide`-mode
   * founder filter (D3). */
  hidden_by_filters: number
}

export interface DashboardResponse {
  days: number
  high_fit_threshold: number
  series: DashboardDay[]
}

export type ReadPolicy = "allowed" | "disabled"

export interface SourceHealth {
  source_id: string
  name: string
  category: string
  read_policy: ReadPolicy
  last_poll: string | null
  last_status: string | null
  last_record_count: number | null
}

export interface SourcesHealthResponse {
  sources: SourceHealth[]
}

export interface PollNowEnqueued {
  source_id: string
  job_id: string
}

export interface PollNowSkipped {
  source_id: string
  reason: "read_disabled_by_policy"
}

export interface PollNowResponse {
  enqueued: PollNowEnqueued[]
  skipped: PollNowSkipped[]
}

export interface TruthValidatorSummary {
  ok: boolean
  error_count: number
  findings: string[]
}

export interface TruthSection {
  section: string
  present: boolean
  count: number
}

export interface TruthStatusResponse {
  loaded: boolean
  hash: string | null
  path: string
  validator: TruthValidatorSummary
  sections: TruthSection[]
}

export interface AuthenticatedResponse {
  authenticated: boolean
}

export interface ApiErrorBody {
  detail: string
  [key: string]: unknown
}

/** Thrown by the api client for any non-2xx response. Carries the parsed body
 * (when JSON) so callers can branch on `status` and `.body.detail` etc. */
export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `API error ${status}`)
    this.name = "ApiError"
    this.status = status
    this.body = body
  }
}
