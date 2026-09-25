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

export type Track =
  | "employment"
  | "contract"
  | "freelance"
  | "procurement"
  | "tutoring"

export type TutoringStatus =
  | "not_started"
  | "preparing_profile"
  | "ready_to_apply"
  | "applied"
  | "approved"
  | "rejected_unavailable"

export interface TutoringPlatform {
  id: string
  name: string
  acquisition_type: string
  track: string
  canonical_url: string
  policy_posture: string
  readiness_checklist: string[]
  checklist_state: Record<string, boolean>
  status: TutoringStatus
  next_action: string
  notes: string
  updated_at: string | null
}

export interface TutoringPlatformsResponse {
  platforms: TutoringPlatform[]
}

export interface TutoringProfileMaterialResponse {
  verified: boolean
  approved_summaries: string[]
  tutoring_skills: Array<{ name: string; proficiency: string }>
  languages: Array<{ language: string; proficiency: string }>
  evidence_ids: string[]
}

export type Decision = "qualified" | "ineligible" | "uncertain" | null

export type ConstraintOutcome = "PASS" | "FAIL" | "UNKNOWN"

export type TrackerState =
  | "to_review"
  | "saved"
  | "applied"
  | "recruiter_screen"
  | "assessment"
  | "interviewing"
  | "final_interview"
  | "offer"
  | "accepted"
  | "rejected_by_founder"
  | "rejected_by_employer"
  | "withdrawn"
  | "no_response"
  | "position_closed"
  | "archived"
  | "dismissed"
  | "snoozed"

export type ApplicationStage =
  | "applied"
  | "recruiter_screen"
  | "assessment"
  | "interviewing"
  | "final_interview"
  | "offer"
  | "accepted"
  | "rejected_by_employer"
  | "withdrawn"
  | "no_response"

export type TrackerBucket = "saved" | "applied" | "rejected" | "all"

export type TrackerFollowUpBucket = "due_today" | "overdue" | "upcoming"
export type TrackerFollowUpStatus = TrackerFollowUpBucket | "completed"

export type ActionState = TrackerState | "submitted" | null

export type FeedbackLabel =
  | "good_match"
  | "bad_match"
  | "eligibility_wrong"
  | "seniority_wrong"
  | "irrelevant_role"
  | "source_quality_issue"
  | "duplicate_issue"
  | "review_required"

/**
 * BRIEF-FR-006 C5: the founder's original complaint was "no card said
 * whether the job was remote, hybrid, or on-site, or where it was" — these
 * fields are how it gets fixed. Shared between `OpportunityListItem` and
 * `OpportunityDetail` because `api/serialization.py::serialize_opportunity_extraction_fields`
 * emits the identical shape into both.
 *
 * `work_mode = "unspecified"` is a real, storable value (47.8% of real
 * postings carry no work-mode signal at all) — render it as "not stated",
 * never coerce it to blank or hide the row's work-mode field entirely.
 * `work_mode_source` rides along whenever `work_mode` does, so the UI can
 * distinguish an extracted value from an inferred one.
 */
export interface OpportunityExtractionFields {
  work_mode: string
  work_mode_source: string | null
  location_country: string | null
  location_city: string | null
  location_region: string | null
  remote_scope: string
  remote_scope_regions: string[]
  employment_type: string
  seniority_level: string
  compensation_min: number | null
  compensation_max: number | null
  compensation_currency: string | null
  compensation_period: string | null
  title_family: string | null
  title_level: string | null
  family_key: string | null
  /** `OpportunityFamilyRecord.member_count` for this row's `family_key`.
   * `null` when the row is not part of a clustered family — never a
   * misleading `1`. */
  family_size: number | null
}

export interface OpportunityListItem extends OpportunityExtractionFields {
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
  /** Present on tracker lists; current feed entries omit this field. */
  tracker_state?: TrackerState | null
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

export type FeedMultiFacetId =
  | "work_mode"
  | "location_country"
  | "location_city"
  | "remote_scope"
  | "employment_type"
  | "seniority_level"
  | "target_tier"
  | "title_family"
  | "source_id"

export type FeedFacetId = "track" | "decision" | FeedMultiFacetId
export type FeedScoreId = "fit_score" | "preference_score" | "confidence_score" | "priority_score"
export type FeedSortId =
  | "recommended"
  | "fit_desc"
  | "fit_asc"
  | "newest_posted"
  | "oldest_posted"
  | "remote_first"

export interface FeedScoreBounds {
  min: string
  max: string
}

/** Complete filter/sort state supported by the W5.1 SQL feed contract. */
export interface FeedQueryState {
  track: string
  decision: string
  q: string
  multi: Record<FeedMultiFacetId, string[]>
  scoreRanges: Record<FeedScoreId, FeedScoreBounds>
  postedFrom: string
  postedTo: string
  sortBy: FeedSortId
  includeHidden: boolean
}

export interface FeedFacetOptionCount {
  value: string
  count: number
}

export interface FeedFacetMetadata {
  selection: "single" | "multiple"
  values: FeedFacetOptionCount[]
  option_count: number
  truncated: boolean
}

export interface FeedScoreRangeMetadata {
  min: number | null
  max: number | null
  unknown_count: number
  threshold_counts: Record<"90+" | "80+" | "70+" | "60+" | "50+", number>
}

export interface FeedUnavailableFilter {
  id: string
  label: string
  reason: string
}

export interface FeedFilterMetadataResponse {
  truth_pack_hash: string
  count_scope: {
    visible_only: boolean
    independent_of_selected_filters: boolean
    includes_tracked_and_ineligible: boolean
  }
  facets: Record<FeedFacetId, FeedFacetMetadata>
  ranges: Record<FeedScoreId, FeedScoreRangeMetadata> & {
    posted_date: { min: string | null; max: string | null; unknown_count: number }
  }
  sorts: Array<{ value: FeedSortId; label: string }>
  unavailable_filters: FeedUnavailableFilter[]
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
   * would do before the founder flips the switch. Not meaningful (and not
   * to be shown) when `unavailable_reason` is set — see below. */
  affected_count: number
  description: string
  /** Non-null when this filter cannot match anything right now for a
   * reason unrelated to `enabled`/`mode` — e.g. the predicate depends on a
   * truth-pack assertion the founder's pack does not contain, or on a
   * signal nothing currently computes. When set, `affected_count` reads as
   * "0" for a reason that has nothing to do with the founder having no
   * matches, so the UI must render this filter as visibly inert (not
   * "enabled and protecting you", not "off") and show this text instead of
   * the count. Council finding, FR-005 D3 repair. */
  unavailable_reason: string | null
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

export interface ConfidenceFactor {
  name: string
  /** 0-100 scale, as returned by the evaluation detail API. */
  score: number
  explanation: string
}

export interface Scoring {
  /** 0-100 scale, unlike DimensionScore.score. */
  fit_score: number | null
  /** 0-100 scale; null when the evaluation has no preference result. */
  preference_score: number | null
  /** 0-100 scale; null when the evaluation has no confidence result. */
  confidence_score: number | null
  confidence_factors: ConfidenceFactor[]
  dimension_scores: DimensionScore[]
  strengths: string[]
  gaps: string[]
  unknowns: string[]
  uncertainty_penalty: number
  explanation: string
  policy_version: string | null
  evaluated_at: string | null
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

export interface OpportunityDetail extends OpportunityExtractionFields {
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

export type ActionType = "save" | "mark_applied" | "reject" | "dismiss" | "snooze" | "set_stage"

export interface ActionResponse {
  opportunity_id: string
  action_state: ActionState
  tracker_state?: TrackerState | null
  action_id: string | null
  undo_event_id?: string | null
  until: string | null
  created_at: string
}

export interface RestoreTrackerResponse {
  opportunity_id: string
  tracker_state: TrackerState
  action_state: ActionState
  created_at: string
}

export interface TrackerListResponse {
  bucket: TrackerBucket
  page: number
  page_size: number
  total: number
  items: OpportunityListItem[]
}

export interface TrackerNote {
  id: string
  opportunity_id: string
  note_text: string
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface TrackerNoteListResponse {
  opportunity_id: string
  page: number
  page_size: number
  total: number
  items: TrackerNote[]
}

export interface TrackerNoteMutationResponse {
  note: TrackerNote
  changed: boolean
}

export interface TrackerFollowUp {
  id: string
  opportunity_id: string
  due_date: string
  note_text: string | null
  completed_at: string | null
  status: TrackerFollowUpStatus
  created_at: string
  updated_at: string
}

export interface TrackerFollowUpListResponse {
  opportunity_id: string
  page: number
  page_size: number
  total: number
  items: TrackerFollowUp[]
}

export interface TrackerFollowUpSummaryItem extends Omit<TrackerFollowUp, "note_text"> {
  opportunity: {
    id: string
    title: string
    organization: string
    tracker_state: TrackerState
  }
}

export interface TrackerFollowUpSummaryResponse {
  bucket: TrackerFollowUpBucket
  page: number
  page_size: number
  total: number
  items: TrackerFollowUpSummaryItem[]
}

export interface TrackerFollowUpMutationResponse {
  follow_up: TrackerFollowUp
  changed: boolean
}

export type TrackerInterviewType = "recruiter_screen" | "hiring_manager" | "technical" | "take_home" | "live_coding" | "case_study" | "panel" | "final" | "other"
export type TrackerInterviewFormat = "phone" | "video" | "in_person"
export type TrackerInterviewOutcome = "pending" | "completed" | "passed" | "not_selected" | "cancelled" | "other"

export interface TrackerInterview {
  id: string
  opportunity_id: string
  scheduled_at: string | null
  round_label: string | null
  interview_type: TrackerInterviewType | null
  interview_format: TrackerInterviewFormat | null
  interviewer_name: string | null
  preparation_notes: string | null
  post_interview_notes: string | null
  outcome: TrackerInterviewOutcome | null
  created_at: string
  updated_at: string
}

export interface TrackerInterviewListResponse {
  opportunity_id: string
  page: number
  page_size: number
  total: number
  items: TrackerInterview[]
}

export interface TrackerInterviewSummaryItem extends Omit<TrackerInterview, "preparation_notes" | "post_interview_notes"> {
  opportunity: {
    id: string
    title: string
    organization: string
    tracker_state: TrackerState
  }
}

export interface TrackerInterviewSummaryResponse {
  bucket: "upcoming"
  page: number
  page_size: number
  total: number
  items: TrackerInterviewSummaryItem[]
}

export interface TrackerInterviewMutationResponse {
  interview: TrackerInterview
  changed: boolean
}

export type TrackerDocumentKind = "cv" | "cover_letter"

export interface TrackerDocumentCandidate {
  document_kind: TrackerDocumentKind
  document_id: string
  label: string
  format: "pdf" | "docx"
  recommended: boolean
  created_at?: string | null
}

export interface TrackerDocumentCandidateListResponse {
  opportunity_id: string
  page: number
  page_size: number
  total: number
  items: TrackerDocumentCandidate[]
}

export interface TrackerDocumentLink {
  id: string
  opportunity_id: string
  document_kind: TrackerDocumentKind
  document_id: string
  linked_at: string
  unlinked_at: string | null
}

export interface TrackerDocumentListResponse {
  opportunity_id: string
  page: number
  page_size: number
  total: number
  selected_cv_document_id: string | null
  selected_cover_letter_document_id: string | null
  items: TrackerDocumentLink[]
}

export interface TrackerDocumentMutationResponse {
  link: TrackerDocumentLink
  changed: boolean
}

export interface TrackerActivityEvent {
  id: string
  action_type: string
  from_state: string | null
  to_state: string | null
  event_at: string
}

export interface TrackerActivityListResponse {
  opportunity_id: string
  page: number
  page_size: number
  total: number
  items: TrackerActivityEvent[]
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
  reason: string
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

/** C1 — the 15-attribute generic facet surface (`GET /api/facets`),
 * deliberately separate from the ten `FounderFilter` policy filters above:
 * a facet uses `include` / `exclude` / `off` per value, never
 * `hide` / `rank_only` / `label_only`, and never touches `decision` or
 * `fit_score` — it only ever adds a `facet:<facet_id>` entry to an
 * opportunity's `hidden_by`. */
export type FacetValueState = "include" | "exclude" | "off"

export interface FacetValue {
  value: string
  count: number
  state: FacetValueState
}

export interface Facet {
  facet_id: string
  value_type: "enum" | "string" | "boolean" | "range" | "date-window"
  description: string
  /** `false` only for `language` today — no language is ever persisted
   * anywhere in the schema. Render as visibly unavailable with
   * `unavailable_reason`, exactly like `FounderFilter.unavailable_reason` —
   * never hidden, never rendered as though it works. */
  available: boolean
  unavailable_reason: string | null
  values: FacetValue[]
  /** How many currently policy-visible rows this facet's own current
   * include/exclude selection hides — exactly the number "Show N excluded
   * by <facet>" needs. */
  excluded_count: number
  include: string[]
  exclude: string[]
}

export interface FacetsResponse {
  facets: Facet[]
}

/** Body for `PUT /api/facets/{facet_id}`. Either key omitted leaves that
 * side unchanged; an empty array on both sides is the "off" state. */
export interface FacetUpdateRequest {
  include?: string[]
  exclude?: string[]
}

/** C1 — saved views: a named facet selection (+ free-text search query) the
 * founder can create, pick, and set as the default. */
export interface SavedView {
  id: string
  name: string
  facets: Record<string, { include: string[]; exclude: string[] }>
  search_query: string | null
  /** Present for FR-008 feed-query views; null for legacy facet-only views. */
  feed_query?: FeedQueryState | null
  is_default: boolean
}

export interface SavedViewsResponse {
  views: SavedView[]
}

export interface SavedViewCreateRequest {
  name: string
  facets: Record<string, { include: string[]; exclude: string[] }>
  search_query?: string | null
  feed_query?: FeedQueryState
  is_default?: boolean
}

export interface SavedViewUpdateRequest {
  name?: string
  facets?: Record<string, { include: string[]; exclude: string[] }>
  search_query?: string | null
  feed_query?: FeedQueryState
  is_default?: boolean
}

/** C4 — the hidden-reasons audit the dashboard's HIDDEN number links to.
 * `reason` is one of the specific strings `api/facets.py::hidden_reasons_for_context`
 * produces — `"red line: <rule>"`, `"excluded industry: <name>"`,
 * `"filter: <filter_id>"`, or `"facet: <facet_id>"` — never a generic label. */
export interface HiddenReason {
  reason: string
  count: number
}

export interface HiddenReasonsResponse {
  reasons: HiddenReason[]
}

export interface UnhideByReasonResponse {
  reason: string
  status: "unhidden"
}

export interface ApiErrorBody {
  detail: string
  [key: string]: unknown
}

/** BRIEF-FR-006 D2 — the three committed ATS-safe templates
 * (`matching/templates/__init__.py::TEMPLATES`). */
export type ArtifactTemplateId = "classic" | "compact" | "modern"

export const ARTIFACT_TEMPLATES: ArtifactTemplateId[] = [
  "classic",
  "compact",
  "modern",
]

/** A bullet, skill, summary variant, or entry the compiler considered but
 * did not select for this opportunity, with the reason
 * (`matching/models.py::OmittedItem`, "what was left out and why"). */
export interface OmittedItem {
  section_id: string
  text: string
  reason: string
  claim_id: string
}

export interface OmittedItemsResponse {
  template: ArtifactTemplateId
  omitted_items: OmittedItem[]
}

/** Shape of one entry in a 409 artifact-validation-rejection body's
 * `findings` array (`matching/artifact_validation.py`). */
export interface ArtifactValidationFinding {
  claim: string
  assertion_type: string
  rejection_reasons: string[]
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
