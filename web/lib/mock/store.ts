/**
 * In-memory mutable state backing the mock API. One store per browser
 * session (module singleton); actions and feedback mutate it so the UI can
 * observe real state changes (dashboard counts, action_state, etc.) without
 * a server.
 */
import type {
  ActionState,
  ActionType,
  ApplicationStage,
  DashboardDay,
  DashboardResponse,
  Facet,
  FacetsResponse,
  FacetValueState,
  FeedFacetId,
  FeedFilterMetadataResponse,
  FeedMultiFacetId,
  FeedScoreId,
  FeedSortId,
  FeedQueryState,
  FeedbackLabel,
  FilterMode,
  FiltersResponse,
  FounderFilter,
  HiddenReason,
  HiddenReasonsResponse,
  OpportunityDetail,
  OpportunityExtractionFields,
  OpportunityListItem,
  OpportunityListResponse,
  SavedView,
  SavedViewsResponse,
  SourceHealth,
  SourcesHealthResponse,
  TruthStatusResponse,
  TrackerBucket,
  TrackerFollowUp,
  TrackerFollowUpBucket,
  TrackerFollowUpListResponse,
  TrackerFollowUpMutationResponse,
  TrackerFollowUpSummaryResponse,
  TrackerListResponse,
  TrackerNote,
  TrackerNoteListResponse,
  TrackerNoteMutationResponse,
  TrackerInterview,
  TrackerInterviewListResponse,
  TrackerInterviewMutationResponse,
  TrackerInterviewOutcome,
  TrackerInterviewSummaryResponse,
  TrackerState,
} from "@/lib/contract/types"
import {
  buildDefaultOpportunities,
  buildNoTruthPackOpportunities,
  buildSourcesHealth,
  evaluateFounderFilter,
  FOUNDER_FILTER_DEFINITIONS,
  truthSectionsComplete,
  truthSectionsMissing,
  truthValidatorOk,
  type SeedOpportunity,
} from "@/lib/mock/fixtures"
import type { MockScenario } from "@/lib/mock/scenario"

interface FilterSetting {
  enabled: boolean
  mode: FilterMode
  params: Record<string, unknown>
}

interface MockTrackerEvent {
  opportunity_id: string
  action_type: string
  from_state: string
  to_state: string
  event_at: string
  metadata_json?: string
}

interface MockTrackerNoteIdempotency {
  idempotency_key: string
  action_type: "tracker_note_created" | "tracker_note_updated" | "tracker_note_archived"
  opportunity_id: string
  note_id: string
}

interface MockTrackerFollowUpIdempotency {
  idempotency_key: string
  action_type: "follow_up_created" | "follow_up_updated" | "follow_up_completed" | "follow_up_reopened"
  opportunity_id: string
  follow_up_id: string
}

interface MockTrackerInterviewIdempotency {
  idempotency_key: string
  action_type: "interview_added" | "interview_updated" | "interview_completed"
  opportunity_id: string
  interview_id: string
}

const HIGH_FIT_THRESHOLD = 70

const FEED_FACETS: FeedFacetId[] = [
  "track", "decision", "work_mode", "location_country", "location_city",
  "remote_scope", "employment_type", "seniority_level", "target_tier",
  "title_family", "source_id",
]
const FEED_MULTI_FACETS: FeedMultiFacetId[] = [
  "work_mode", "location_country", "location_city", "remote_scope",
  "employment_type", "seniority_level", "target_tier", "title_family", "source_id",
]
const FEED_SCORES: FeedScoreId[] = ["fit_score", "preference_score", "confidence_score", "priority_score"]
const FEED_SORTS: Array<{ value: FeedSortId; label: string }> = [
  { value: "recommended", label: "Recommended" },
  { value: "fit_desc", label: "Fit score: high to low" },
  { value: "fit_asc", label: "Fit score: low to high" },
  { value: "newest_posted", label: "Newest posted" },
  { value: "oldest_posted", label: "Oldest posted" },
  { value: "remote_first", label: "Remote first" },
]
const MOCK_UNAVAILABLE_FEED_FILTERS = [
  { id: "tracking_state", label: "Tracking state", reason: "Saved, snoozed, dismissed, applied, and submitted states are outside the feed-query contract." },
  { id: "eligibility_evidence", label: "Eligibility evidence", reason: "Only the qualification decision is queryable; sponsorship and work-authorization evidence are not structured feed fields." },
  { id: "title_level_and_keywords", label: "Title level and exact title keywords", reason: "Title level and exact title keywords are not exposed as feed filters; general text search remains available." },
  { id: "location_region", label: "Location regions", reason: "Region text is not normalized into exact selectable values." },
  { id: "skill_match_and_gaps", label: "Skill match and gaps", reason: "Required, matched, missing, and preferred skills are not structured query fields." },
  { id: "experience_responsibility", label: "Experience and responsibility", reason: "Years of experience and responsibility evidence are not queryable feed fields." },
  { id: "work_authorization_relocation", label: "Work authorization and relocation", reason: "Authorization, sponsorship, relocation, and on-site cadence are not queryable feed fields." },
  { id: "compensation", label: "Compensation ranges", reason: "Comparable compensation amounts, currencies, and pay periods are not part of the feed-query projection." },
  { id: "company_attributes", label: "Company attributes", reason: "Industry, size, stage, ownership, funding, and employer-name dimensions are not normalized feed filters." },
  { id: "source_taxonomy_and_health", label: "Source family, ATS, and source health", reason: "Source ID is queryable; source family, ATS type, quality, health, and error rate are not normalized." },
  { id: "posting_health", label: "Posting freshness and health", reason: "Posted-date bounds are queryable; deadline, stale state, duplicate, and closed signals are not." },
  { id: "content_completeness", label: "Content completeness", reason: "Description coverage, length, structured-field coverage, and extraction confidence are not queryable." },
  { id: "education_certification", label: "Education and certification", reason: "Degree, education level, and certification requirements are not structured feed filters." },
  { id: "language_timezone_travel", label: "Language, time zone, and travel", reason: "Language, time-zone overlap, and travel requirements are not structured feed filters." },
  { id: "cv_application_readiness", label: "CV and application readiness", reason: "CV selection and application-artifact readiness are tracker concerns outside feed-query dimensions." },
  { id: "tracked_user_metadata", label: "Tracked-job user metadata", reason: "Notes, follow-up dates, application status, and user tags are not part of feed-query dimensions." },
]

/** C1 mock facet surface. A trimmed set of the real API's 15 facets,
 * bucketed over fields this mock's `SeedOpportunity` actually models
 * (track/source_id/organization/decision/fit_score) — this mock has no
 * modelled work_mode/location/compensation field, matching the fact that
 * the real API does not expose those on any opportunity response either
 * (see this order's return notes). `language` is unavailable here for the
 * same reason it is unavailable on the real API: no language is ever
 * persisted anywhere. */
interface MockFacetDef {
  facet_id: string
  value_type: Facet["value_type"]
  description: string
  available: boolean
  unavailable_reason: string | null
  valueOf: (o: SeedOpportunity) => string
}

const MOCK_FACET_DEFS: MockFacetDef[] = [
  {
    facet_id: "track",
    value_type: "enum",
    description: "Employment vs. procurement track.",
    available: true,
    unavailable_reason: null,
    valueOf: (o) => o.track,
  },
  {
    facet_id: "source_id",
    value_type: "enum",
    description: "Source adapter this opportunity came from.",
    available: true,
    unavailable_reason: null,
    valueOf: (o) => o.source_id,
  },
  {
    facet_id: "employer",
    value_type: "string",
    description: "Hiring organization.",
    available: true,
    unavailable_reason: null,
    valueOf: (o) => o.organization,
  },
  {
    facet_id: "decision",
    value_type: "enum",
    description: "The latest qualification decision.",
    available: true,
    unavailable_reason: null,
    valueOf: (o) => o.decision ?? "unspecified",
  },
  {
    facet_id: "fit_score",
    value_type: "range",
    description: "Fit score bucketed in quartiles.",
    available: true,
    unavailable_reason: null,
    valueOf: (o) => {
      const s = o.fit_score
      if (s === null) return "unscored"
      if (s < 25) return "0-25"
      if (s < 50) return "25-50"
      if (s < 75) return "50-75"
      return "75-100"
    },
  },
  {
    facet_id: "language",
    value_type: "enum",
    description: "Posting language.",
    available: false,
    unavailable_reason:
      "No language is ever persisted for an opportunity anywhere in the schema.",
    valueOf: () => "unspecified",
  },
]

function daysAgoUtc(n: number): string {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - n)
  return d.toISOString().slice(0, 10)
}

function isIsoCalendarDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00.000Z`)
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
}

function followUpStatus(dueDate: string, completedAt: string | null, today: string): TrackerFollowUp["status"] {
  if (completedAt) return "completed"
  if (dueDate < today) return "overdue"
  if (dueDate === today) return "due_today"
  return "upcoming"
}

const MOCK_INTERVIEW_TYPES = new Set(["recruiter_screen", "hiring_manager", "technical", "take_home", "live_coding", "case_study", "panel", "final", "other"])
const MOCK_INTERVIEW_FORMATS = new Set(["phone", "video", "in_person"])
const MOCK_INTERVIEW_OUTCOMES = new Set<TrackerInterviewOutcome>(["pending", "completed", "passed", "not_selected", "cancelled", "other"])
const MOCK_INTERVIEW_DONE = new Set<TrackerInterviewOutcome>(["completed", "passed", "not_selected", "cancelled"])
const MOCK_INTERVIEW_FIELDS = new Set(["scheduled_at", "round_label", "interview_type", "interview_format", "interviewer_name", "preparation_notes", "post_interview_notes", "outcome"])

function normalizeMockInterviewFields(fields: Record<string, unknown>): Partial<TrackerInterview> | "invalid_field" | "invalid_datetime" | "invalid_enum" | "invalid_text" {
  const normalized: Partial<TrackerInterview> = {}
  const lengths: Record<string, number> = { round_label: 64, interviewer_name: 128, preparation_notes: 4000, post_interview_notes: 4000 }
  for (const [field, value] of Object.entries(fields)) {
    if (!MOCK_INTERVIEW_FIELDS.has(field)) return "invalid_field"
    if (field === "scheduled_at") {
      if (value === null) normalized.scheduled_at = null
      else if (typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) && Number.isFinite(Date.parse(value))) normalized.scheduled_at = new Date(value).toISOString()
      else return "invalid_datetime"
    } else if (field in lengths) {
      if (value !== null && typeof value !== "string") return "invalid_text"
      const cleaned = typeof value === "string" ? value.trim() : ""
      if (cleaned.length > lengths[field]) return "invalid_text"
      ;(normalized as Record<string, unknown>)[field] = cleaned || null
    } else if (field === "interview_type") {
      if (value !== null && (typeof value !== "string" || !MOCK_INTERVIEW_TYPES.has(value))) return "invalid_enum"
      normalized.interview_type = value as TrackerInterview["interview_type"]
    } else if (field === "interview_format") {
      if (value !== null && (typeof value !== "string" || !MOCK_INTERVIEW_FORMATS.has(value))) return "invalid_enum"
      normalized.interview_format = value as TrackerInterview["interview_format"]
    } else if (field === "outcome") {
      if (value !== null && (typeof value !== "string" || !MOCK_INTERVIEW_OUTCOMES.has(value as TrackerInterviewOutcome))) return "invalid_enum"
      normalized.outcome = value as TrackerInterviewOutcome | null
    }
  }
  return normalized
}

export class MockStore {
  scenario: MockScenario
  authenticated = false
  failedLoginAttempts = 0

  opportunities: Map<string, SeedOpportunity>
  sources: SourceHealth[]
  truthLoaded: boolean
  truthValidator: TruthStatusResponse["validator"]
  truthSections: TruthStatusResponse["sections"]

  /** per-day counters, most recent first (today at index 0) */
  dailyCounters: DashboardDay[]

  /** D3 founder filter settings, one entry per `FOUNDER_FILTER_DEFINITIONS`
   * row, seeded from that table's defaults and mutated by `PUT
   * /api/filters/{filter_id}`. */
  filterSettings: Map<string, FilterSetting>

  /** C1 facet settings, one entry per `MOCK_FACET_DEFS` row that the
   * founder has actually touched — absent is the "off" state, matching the
   * real API's `FounderFacetRecord` semantics exactly. */
  facetSettings: Map<string, { include: string[]; exclude: string[] }>
  /** C1 saved views. */
  savedViews: SavedView[]
  /** Synthetic append-only event history used to mirror tracker transitions in mock flows. */
  private trackerEvents: MockTrackerEvent[] = []
  /** Synthetic private notes used only by authenticated mock browser flows. */
  private trackerNotes = new Map<string, TrackerNote[]>()
  private trackerNoteIdempotency: MockTrackerNoteIdempotency[] = []
  /** Synthetic follow-ups and request keys live only in mock local storage. */
  private trackerFollowUps = new Map<string, TrackerFollowUp[]>()
  private trackerFollowUpIdempotency: MockTrackerFollowUpIdempotency[] = []
  /** Synthetic interview records, private notes, and idempotency live in their own mock namespace. */
  private trackerInterviews = new Map<string, TrackerInterview[]>()
  private trackerInterviewIdempotency: MockTrackerInterviewIdempotency[] = []

  constructor(scenario: MockScenario) {
    this.scenario = scenario
    this.facetSettings = new Map()
    this.savedViews = []
    this.filterSettings = new Map(
      FOUNDER_FILTER_DEFINITIONS.map((f) => [
        f.filter_id,
        {
          enabled: f.default_enabled,
          mode: f.default_mode,
          params: { ...f.default_params },
        },
      ])
    )

    switch (scenario) {
      case "no-truth-pack": {
        this.opportunities = new Map(
          buildNoTruthPackOpportunities().map((o) => [o.id, o])
        )
        this.sources = buildSourcesHealth("polled")
        this.truthLoaded = false
        this.truthValidator = {
          ok: false,
          error_count: 0,
          findings: [
            "truth pack file not found at private/truth_pack.yaml",
          ],
        }
        this.truthSections = truthSectionsMissing()
        break
      }
      case "invalid-truth-pack": {
        this.opportunities = new Map(
          buildNoTruthPackOpportunities().map((o) => [o.id, o])
        )
        this.sources = buildSourcesHealth("polled")
        this.truthLoaded = false
        this.truthValidator = {
          ok: false,
          error_count: 3,
          findings: [
            "identity.full_name: required field is missing",
            "employment[0].evidence: at least one evidence link is required",
            "skills: must not be empty",
          ],
        }
        this.truthSections = truthSectionsMissing()
        break
      }
      case "no-opportunities": {
        this.opportunities = new Map()
        this.sources = buildSourcesHealth("polled")
        this.truthLoaded = true
        this.truthValidator = truthValidatorOk()
        this.truthSections = truthSectionsComplete()
        break
      }
      case "worker-idle": {
        this.opportunities = new Map()
        this.sources = buildSourcesHealth("idle")
        this.truthLoaded = true
        this.truthValidator = truthValidatorOk()
        this.truthSections = truthSectionsComplete()
        break
      }
      case "default":
      default: {
        this.opportunities = new Map(
          buildDefaultOpportunities().map((o) => [o.id, o])
        )
        this.sources = buildSourcesHealth("polled")
        this.truthLoaded = true
        this.truthValidator = truthValidatorOk()
        this.truthSections = truthSectionsComplete()
        break
      }
    }

    this.restoreTrackerState()
    this.restoreTrackerNotes()
    this.restoreTrackerFollowUps()
    this.restoreTrackerInterviews()
    this.dailyCounters = this.seedDailyCounters()
  }

  private trackerStorageKey() {
    return `opportunityos.mock.tracker.${this.scenario}`
  }

  private trackerEventsStorageKey() {
    return `opportunityos.mock.tracker-events.${this.scenario}`
  }

  private trackerNotesStorageKey() {
    return `opportunityos.mock.tracker-notes.${this.scenario}`
  }

  private trackerFollowUpsStorageKey() {
    return `opportunityos.mock.follow-ups.${this.scenario}`
  }

  private trackerInterviewsStorageKey() {
    return `opportunityos.mock.interviews.${this.scenario}`
  }

  private restoreTrackerState() {
    if (typeof window === "undefined") return
    try {
      const raw = window.localStorage.getItem(this.trackerStorageKey())
      if (raw) {
        const saved: unknown = JSON.parse(raw)
        if (Array.isArray(saved)) {
          const allowedStates = new Set([
            "saved", "submitted", "applied", "recruiter_screen", "assessment",
            "interviewing", "final_interview", "offer", "accepted",
            "rejected_by_founder", "rejected_by_employer", "withdrawn", "no_response",
            "position_closed", "archived", "dismissed", "snoozed",
          ])
          for (const entry of saved) {
            if (
              entry &&
              typeof entry === "object" &&
              "id" in entry &&
              typeof entry.id === "string" &&
              "action_state" in entry &&
              typeof entry.action_state === "string" &&
              allowedStates.has(entry.action_state)
            ) {
              const opportunity = this.opportunities.get(entry.id)
              if (opportunity) opportunity.action_state = entry.action_state as ActionState
            }
          }
        }
      }
      const eventRaw = window.localStorage.getItem(this.trackerEventsStorageKey())
      if (eventRaw) {
        const events: unknown = JSON.parse(eventRaw)
        if (Array.isArray(events)) {
          this.trackerEvents = events.filter((event): event is MockTrackerEvent =>
            Boolean(
              event &&
              typeof event === "object" &&
              "opportunity_id" in event && typeof event.opportunity_id === "string" &&
              "action_type" in event && typeof event.action_type === "string" &&
              "from_state" in event && typeof event.from_state === "string" &&
              "to_state" in event && typeof event.to_state === "string" &&
              "event_at" in event && typeof event.event_at === "string"
            )
          )
        }
      }
    } catch {
      // In-memory mock behavior remains usable if browser storage is blocked.
    }
  }

  private restoreTrackerNotes() {
    if (typeof window === "undefined") return
    try {
      const raw = window.localStorage.getItem(this.trackerNotesStorageKey())
      if (!raw) return
      const saved: unknown = JSON.parse(raw)
      if (!saved || typeof saved !== "object") return
      const object = saved as { notes?: unknown; idempotency?: unknown }
      if (Array.isArray(object.notes)) {
        for (const note of object.notes) {
          if (
            note && typeof note === "object" &&
            "id" in note && typeof note.id === "string" &&
            "opportunity_id" in note && typeof note.opportunity_id === "string" &&
            "note_text" in note && typeof note.note_text === "string" &&
            "created_at" in note && typeof note.created_at === "string" &&
            "updated_at" in note && typeof note.updated_at === "string" &&
            "archived_at" in note && (typeof note.archived_at === "string" || note.archived_at === null) &&
            this.opportunities.has(note.opportunity_id)
          ) {
            const rows = this.trackerNotes.get(note.opportunity_id) ?? []
            rows.push(note as TrackerNote)
            this.trackerNotes.set(note.opportunity_id, rows)
          }
        }
      }
      if (Array.isArray(object.idempotency)) {
        this.trackerNoteIdempotency = object.idempotency.filter((entry): entry is MockTrackerNoteIdempotency =>
          Boolean(
            entry && typeof entry === "object" &&
            "idempotency_key" in entry && typeof entry.idempotency_key === "string" &&
            "action_type" in entry && ["tracker_note_created", "tracker_note_updated", "tracker_note_archived"].includes(String(entry.action_type)) &&
            "opportunity_id" in entry && typeof entry.opportunity_id === "string" &&
            "note_id" in entry && typeof entry.note_id === "string"
          )
        )
      }
    } catch {
      // Synthetic notes remain usable in memory when browser storage is blocked.
    }
  }

  private persistTrackerNotes() {
    if (typeof window === "undefined") return
    try {
      const notes = [...this.trackerNotes.values()].flat()
      window.localStorage.setItem(this.trackerNotesStorageKey(), JSON.stringify({
        notes,
        idempotency: this.trackerNoteIdempotency,
      }))
    } catch {
      // Synthetic review state must not break the mock workflow.
    }
  }

  private eligibleFollowUpTrackerState(opportunityId: string): TrackerState | null {
    const opportunity = this.opportunities.get(opportunityId)
    if (!opportunity) return null
    const state = opportunity.action_state === "submitted" ? "applied" : opportunity.action_state
    const eligible = new Set<TrackerState>([
      "saved", "applied", "recruiter_screen", "assessment", "interviewing",
      "final_interview", "offer", "accepted",
    ])
    return state && eligible.has(state as TrackerState) ? state as TrackerState : null
  }

  private restoreTrackerFollowUps() {
    if (typeof window === "undefined") return
    try {
      const raw = window.localStorage.getItem(this.trackerFollowUpsStorageKey())
      if (!raw) return
      const saved: unknown = JSON.parse(raw)
      if (!saved || typeof saved !== "object") return
      const object = saved as { follow_ups?: unknown; idempotency?: unknown }
      if (Array.isArray(object.follow_ups)) {
        for (const entry of object.follow_ups) {
          if (
            entry && typeof entry === "object" &&
            "id" in entry && typeof entry.id === "string" &&
            "opportunity_id" in entry && typeof entry.opportunity_id === "string" &&
            "due_date" in entry && isIsoCalendarDate(entry.due_date) &&
            "note_text" in entry && (typeof entry.note_text === "string" || entry.note_text === null) &&
            "completed_at" in entry && (typeof entry.completed_at === "string" || entry.completed_at === null) &&
            "created_at" in entry && typeof entry.created_at === "string" &&
            "updated_at" in entry && typeof entry.updated_at === "string" &&
            this.opportunities.has(entry.opportunity_id)
          ) {
            const today = new Date().toISOString().slice(0, 10)
            const note: TrackerFollowUp = {
              id: entry.id,
              opportunity_id: entry.opportunity_id,
              due_date: entry.due_date,
              note_text: entry.note_text,
              completed_at: entry.completed_at,
              status: followUpStatus(entry.due_date, entry.completed_at, today),
              created_at: entry.created_at,
              updated_at: entry.updated_at,
            }
            const rows = this.trackerFollowUps.get(note.opportunity_id) ?? []
            rows.push(note)
            this.trackerFollowUps.set(note.opportunity_id, rows)
          }
        }
      }
      if (Array.isArray(object.idempotency)) {
        this.trackerFollowUpIdempotency = object.idempotency.filter((entry): entry is MockTrackerFollowUpIdempotency =>
          Boolean(
            entry && typeof entry === "object" &&
            "idempotency_key" in entry && typeof entry.idempotency_key === "string" &&
            "action_type" in entry && ["follow_up_created", "follow_up_updated", "follow_up_completed", "follow_up_reopened"].includes(String(entry.action_type)) &&
            "opportunity_id" in entry && typeof entry.opportunity_id === "string" &&
            "follow_up_id" in entry && typeof entry.follow_up_id === "string"
          )
        )
      }
    } catch {
      // Synthetic follow-ups remain usable in memory when storage is blocked.
    }
  }

  private persistTrackerFollowUps() {
    if (typeof window === "undefined") return
    try {
      window.localStorage.setItem(this.trackerFollowUpsStorageKey(), JSON.stringify({
        follow_ups: [...this.trackerFollowUps.values()].flat(),
        idempotency: this.trackerFollowUpIdempotency,
      }))
    } catch {
      // Synthetic review data must not break the mock workflow.
    }
  }

  private restoreTrackerInterviews() {
    if (typeof window === "undefined") return
    try {
      const raw = window.localStorage.getItem(this.trackerInterviewsStorageKey())
      if (!raw) return
      const saved: unknown = JSON.parse(raw)
      if (!saved || typeof saved !== "object") return
      const object = saved as { interviews?: unknown; idempotency?: unknown }
      if (Array.isArray(object.interviews)) {
        for (const entry of object.interviews) {
          if (
            entry && typeof entry === "object" &&
            "id" in entry && typeof entry.id === "string" &&
            "opportunity_id" in entry && typeof entry.opportunity_id === "string" &&
            "scheduled_at" in entry && (typeof entry.scheduled_at === "string" || entry.scheduled_at === null) &&
            "outcome" in entry && typeof entry.outcome === "string" &&
            "created_at" in entry && typeof entry.created_at === "string" &&
            "updated_at" in entry && typeof entry.updated_at === "string" &&
            this.opportunities.has(entry.opportunity_id)
          ) {
            const rows = this.trackerInterviews.get(entry.opportunity_id) ?? []
            rows.push(entry as TrackerInterview)
            this.trackerInterviews.set(entry.opportunity_id, rows)
          }
        }
      }
      if (Array.isArray(object.idempotency)) {
        this.trackerInterviewIdempotency = object.idempotency.filter((entry): entry is MockTrackerInterviewIdempotency =>
          Boolean(
            entry && typeof entry === "object" &&
            "idempotency_key" in entry && typeof entry.idempotency_key === "string" &&
            "action_type" in entry && ["interview_added", "interview_updated", "interview_completed"].includes(String(entry.action_type)) &&
            "opportunity_id" in entry && typeof entry.opportunity_id === "string" &&
            "interview_id" in entry && typeof entry.interview_id === "string"
          )
        )
      }
    } catch {
      // Keep synthetic interview flows usable when browser storage is blocked.
    }
  }

  private persistTrackerInterviews() {
    if (typeof window === "undefined") return
    try {
      window.localStorage.setItem(this.trackerInterviewsStorageKey(), JSON.stringify({
        interviews: [...this.trackerInterviews.values()].flat(),
        idempotency: this.trackerInterviewIdempotency,
      }))
    } catch {
      // Synthetic review data must not break the mock workflow.
    }
  }

  private applicationTrackerState(opportunityId: string): TrackerState | null {
    const opportunity = this.opportunities.get(opportunityId)
    if (!opportunity) return null
    const state = opportunity.action_state === "submitted" ? "applied" : opportunity.action_state
    const applicationStates = new Set<TrackerState>([
      "applied", "recruiter_screen", "assessment", "interviewing", "final_interview",
      "offer", "accepted", "rejected_by_employer", "withdrawn", "no_response",
    ])
    return state && applicationStates.has(state) ? state : null
  }

  private interviewTrackerState(opportunityId: string): TrackerState | null {
    const opportunity = this.opportunities.get(opportunityId)
    if (!opportunity) return null
    const state = opportunity.action_state === "submitted" ? "applied" : opportunity.action_state
    const appliedBucket = new Set<TrackerState>(["applied", "recruiter_screen", "assessment", "interviewing", "final_interview", "offer", "accepted"])
    return state && appliedBucket.has(state as TrackerState) ? state as TrackerState : null
  }

  listOpportunityTrackerInterviews(opportunityId: string, page = 1, pageSize = 50): TrackerInterviewListResponse | "not_found" | "not_tracked" {
    if (!this.opportunities.has(opportunityId)) return "not_found"
    if (!this.interviewTrackerState(opportunityId)) return "not_tracked"
    const rows = this.trackerInterviews.get(opportunityId) ?? []
    const normalizedPage = Math.max(1, Math.floor(page) || 1)
    const normalizedSize = Math.min(100, Math.max(1, Math.floor(pageSize) || 50))
    return {
      opportunity_id: opportunityId,
      page: normalizedPage,
      page_size: normalizedSize,
      total: rows.length,
      items: [...rows].sort((left, right) => {
        if (!left.scheduled_at) return right.scheduled_at ? 1 : left.id.localeCompare(right.id)
        if (!right.scheduled_at) return -1
        return left.scheduled_at.localeCompare(right.scheduled_at) || left.id.localeCompare(right.id)
      }).slice((normalizedPage - 1) * normalizedSize, normalizedPage * normalizedSize),
    }
  }

  listTrackerInterviews(bucket: string, page = 1, pageSize = 25): TrackerInterviewSummaryResponse | "invalid_bucket" {
    if (bucket !== "upcoming") return "invalid_bucket"
    const now = Date.now()
    const items = [...this.trackerInterviews.values()].flat()
      .filter((interview) => interview.scheduled_at && Date.parse(interview.scheduled_at) >= now && !MOCK_INTERVIEW_DONE.has(interview.outcome ?? "pending") && this.interviewTrackerState(interview.opportunity_id))
      .sort((left, right) => Date.parse(left.scheduled_at ?? "") - Date.parse(right.scheduled_at ?? "") || left.id.localeCompare(right.id))
      .flatMap((interview) => {
        const opportunity = this.opportunities.get(interview.opportunity_id)
        const trackerState = this.interviewTrackerState(interview.opportunity_id)
        if (!opportunity || !trackerState) return []
        const safeInterview = Object.fromEntries(
          Object.entries(interview).filter(([field]) => field !== "preparation_notes" && field !== "post_interview_notes")
        ) as Omit<TrackerInterview, "preparation_notes" | "post_interview_notes">
        return [{ ...safeInterview, opportunity: { id: opportunity.id, title: opportunity.title, organization: opportunity.organization, tracker_state: trackerState } }]
      })
    const normalizedPage = Math.max(1, Math.floor(page) || 1)
    const normalizedSize = Math.min(100, Math.max(1, Math.floor(pageSize) || 25))
    return { bucket: "upcoming", page: normalizedPage, page_size: normalizedSize, total: items.length, items: items.slice((normalizedPage - 1) * normalizedSize, normalizedPage * normalizedSize) }
  }

  createTrackerInterview(
    opportunityId: string,
    fields: Record<string, unknown>,
    idempotencyKey: string,
  ): TrackerInterviewMutationResponse | "not_found" | "not_tracked" | "invalid_datetime" | "invalid_enum" | "invalid_text" | "invalid_field" | "invalid_idempotency_key" | "idempotency_conflict" {
    if (!this.opportunities.has(opportunityId)) return "not_found"
    const state = this.interviewTrackerState(opportunityId)
    if (!state) return "not_tracked"
    const normalized = normalizeMockInterviewFields(fields)
    if (typeof normalized === "string") return normalized
    if (typeof idempotencyKey !== "string" || !idempotencyKey.trim() || idempotencyKey.length > 128) return "invalid_idempotency_key"
    const prior = this.trackerInterviewIdempotency.find((entry) => entry.idempotency_key === idempotencyKey)
    if (prior) {
      if (prior.action_type !== "interview_added" || prior.opportunity_id !== opportunityId) return "idempotency_conflict"
      const interview = (this.trackerInterviews.get(opportunityId) ?? []).find((entry) => entry.id === prior.interview_id)
      return interview ? { interview, changed: false } : "not_found"
    }
    const now = new Date().toISOString()
    const interview: TrackerInterview = {
      id: `mock-interview-${crypto.randomUUID()}`, opportunity_id: opportunityId,
      scheduled_at: normalized.scheduled_at ?? null, round_label: normalized.round_label ?? null,
      interview_type: normalized.interview_type ?? null, interview_format: normalized.interview_format ?? null,
      interviewer_name: normalized.interviewer_name ?? null, preparation_notes: normalized.preparation_notes ?? null,
      post_interview_notes: normalized.post_interview_notes ?? null, outcome: normalized.outcome ?? "pending",
      created_at: now, updated_at: now,
    }
    this.trackerInterviews.set(opportunityId, [...(this.trackerInterviews.get(opportunityId) ?? []), interview])
    this.trackerInterviewIdempotency.push({ idempotency_key: idempotencyKey, action_type: "interview_added", opportunity_id: opportunityId, interview_id: interview.id })
    this.persistTrackerInterviews()
    this.recordTrackerInterviewEvent(opportunityId, state, "interview_added", interview.id)
    return { interview, changed: true }
  }

  updateTrackerInterview(
    opportunityId: string,
    interviewId: string,
    fields: Record<string, unknown>,
    idempotencyKey: string,
  ): TrackerInterviewMutationResponse | "not_found" | "not_tracked" | "invalid_datetime" | "invalid_enum" | "invalid_text" | "invalid_field" | "invalid_update" | "invalid_idempotency_key" | "idempotency_conflict" {
    if (!this.opportunities.has(opportunityId)) return "not_found"
    const state = this.interviewTrackerState(opportunityId)
    if (!state) return "not_tracked"
    const interview = (this.trackerInterviews.get(opportunityId) ?? []).find((entry) => entry.id === interviewId)
    if (!interview) return "not_found"
    if (!Object.keys(fields).length) return "invalid_update"
    const normalized = normalizeMockInterviewFields(fields)
    if (typeof normalized === "string") return normalized
    if (typeof idempotencyKey !== "string" || !idempotencyKey.trim() || idempotencyKey.length > 128) return "invalid_idempotency_key"
    const nextOutcome = normalized.outcome === undefined ? interview.outcome : normalized.outcome
    const isCompletionTransition = (interview.outcome === null || interview.outcome === "pending") && nextOutcome !== null && nextOutcome !== undefined && ["completed", "passed", "not_selected"].includes(nextOutcome)
    const isCompletionReplay = Object.keys(normalized).length === 1 && normalized.outcome === interview.outcome && interview.outcome !== null && ["completed", "passed", "not_selected"].includes(interview.outcome)
    const actionType = isCompletionTransition || isCompletionReplay
      ? "interview_completed"
      : "interview_updated"
    const prior = this.trackerInterviewIdempotency.find((entry) => entry.idempotency_key === idempotencyKey)
    if (prior) {
      if (prior.action_type !== actionType || prior.opportunity_id !== opportunityId || prior.interview_id !== interviewId) return "idempotency_conflict"
      return { interview, changed: false }
    }
    if (Object.entries(normalized).every(([field, value]) => interview[field as keyof TrackerInterview] === value)) return { interview, changed: false }
    Object.assign(interview, normalized, { updated_at: new Date().toISOString() })
    this.trackerInterviewIdempotency.push({ idempotency_key: idempotencyKey, action_type: actionType, opportunity_id: opportunityId, interview_id: interviewId })
    this.persistTrackerInterviews()
    this.recordTrackerInterviewEvent(opportunityId, state, actionType, interviewId)
    return { interview, changed: true }
  }

  private recordTrackerInterviewEvent(opportunityId: string, state: TrackerState, actionType: string, interviewId: string) {
    const event: MockTrackerEvent = {
      opportunity_id: opportunityId, action_type: actionType, from_state: state, to_state: state,
      event_at: new Date().toISOString(), metadata_json: JSON.stringify({ interview_id: interviewId }),
    }
    this.trackerEvents.push(event)
    if (typeof window === "undefined") return
    try {
      window.localStorage.setItem(this.trackerEventsStorageKey(), JSON.stringify(this.trackerEvents))
    } catch {
      // Synthetic events are best-effort in the browser mock.
    }
  }

  private recordTrackerNoteEvent(
    opportunityId: string,
    state: TrackerState,
    actionType: MockTrackerEvent["action_type"],
    noteId: string
  ) {
    const event: MockTrackerEvent = {
      opportunity_id: opportunityId,
      action_type: actionType,
      from_state: state,
      to_state: state,
      event_at: new Date().toISOString(),
      metadata_json: JSON.stringify({ note_id: noteId }),
    }
    if (typeof window !== "undefined") {
      try {
        const key = this.trackerEventsStorageKey()
        const persisted: unknown = JSON.parse(window.localStorage.getItem(key) ?? "[]")
        const persistedEvents = Array.isArray(persisted)
          ? persisted.filter((entry): entry is MockTrackerEvent =>
              Boolean(
                entry && typeof entry === "object" &&
                "opportunity_id" in entry && typeof entry.opportunity_id === "string" &&
                "action_type" in entry && typeof entry.action_type === "string" &&
                "from_state" in entry && typeof entry.from_state === "string" &&
                "to_state" in entry && typeof entry.to_state === "string" &&
                "event_at" in entry && typeof entry.event_at === "string"
              )
            )
          : []
        const byEventIdentity = new Map<string, MockTrackerEvent>()
        for (const existing of [...persistedEvents, ...this.trackerEvents, event]) {
          const identity = [
            existing.opportunity_id,
            existing.action_type,
            existing.from_state,
            existing.to_state,
            existing.event_at,
            existing.metadata_json ?? "",
          ].join("\u0000")
          byEventIdentity.set(identity, existing)
        }
        this.trackerEvents = [...byEventIdentity.values()]
        window.localStorage.setItem(key, JSON.stringify(this.trackerEvents))
      } catch {
        // Synthetic history is best-effort in the browser mock.
      }
    } else {
      this.trackerEvents.push(event)
    }
  }

  private recordTrackerFollowUpEvent(
    opportunityId: string,
    state: TrackerState,
    actionType: MockTrackerEvent["action_type"],
    followUpId: string
  ) {
    const event: MockTrackerEvent = {
      opportunity_id: opportunityId,
      action_type: actionType,
      from_state: state,
      to_state: state,
      event_at: new Date().toISOString(),
      metadata_json: JSON.stringify({ follow_up_id: followUpId }),
    }
    if (typeof window === "undefined") {
      this.trackerEvents.push(event)
      return
    }
    try {
      const persisted: unknown = JSON.parse(window.localStorage.getItem(this.trackerEventsStorageKey()) ?? "[]")
      const persistedEvents = Array.isArray(persisted) ? persisted.filter((entry): entry is MockTrackerEvent =>
        Boolean(
          entry && typeof entry === "object" &&
          "opportunity_id" in entry && typeof entry.opportunity_id === "string" &&
          "action_type" in entry && typeof entry.action_type === "string" &&
          "from_state" in entry && typeof entry.from_state === "string" &&
          "to_state" in entry && typeof entry.to_state === "string" &&
          "event_at" in entry && typeof entry.event_at === "string"
        )
      ) : []
      const byEventIdentity = new Map<string, MockTrackerEvent>()
      for (const existing of [...persistedEvents, ...this.trackerEvents, event]) {
        const identity = [
          existing.opportunity_id,
          existing.action_type,
          existing.from_state,
          existing.to_state,
          existing.event_at,
          existing.metadata_json ?? "",
        ].join("\u0000")
        byEventIdentity.set(identity, existing)
      }
      this.trackerEvents = [...byEventIdentity.values()]
      window.localStorage.setItem(this.trackerEventsStorageKey(), JSON.stringify(this.trackerEvents))
    } catch {
      // Synthetic activity must not fail the mock follow-up workflow.
    }
  }

  listTrackerNotes(
    opportunityId: string,
    page = 1,
    pageSize = 50
  ): TrackerNoteListResponse | "not_found" | "not_tracked" {
    if (!this.opportunities.has(opportunityId)) return "not_found"
    if (!this.applicationTrackerState(opportunityId)) return "not_tracked"
    const active = (this.trackerNotes.get(opportunityId) ?? []).filter((note) => !note.archived_at)
    const normalizedPage = Math.max(1, Math.floor(page) || 1)
    const normalizedSize = Math.min(100, Math.max(1, Math.floor(pageSize) || 50))
    return {
      opportunity_id: opportunityId,
      page: normalizedPage,
      page_size: normalizedSize,
      total: active.length,
      items: [...active]
        .sort((left, right) => right.created_at.localeCompare(left.created_at))
        .slice((normalizedPage - 1) * normalizedSize, normalizedPage * normalizedSize),
    }
  }

  createTrackerNote(
    opportunityId: string,
    noteText: string,
    idempotencyKey: string
  ): TrackerNoteMutationResponse | "not_found" | "not_tracked" | "idempotency_conflict" {
    if (!this.opportunities.has(opportunityId)) return "not_found"
    const state = this.applicationTrackerState(opportunityId)
    if (!state) return "not_tracked"
    const prior = this.trackerNoteIdempotency.find((entry) => entry.idempotency_key === idempotencyKey)
    if (prior) {
      if (prior.action_type !== "tracker_note_created" || prior.opportunity_id !== opportunityId) {
        return "idempotency_conflict"
      }
      const note = (this.trackerNotes.get(opportunityId) ?? []).find((entry) => entry.id === prior.note_id)
      return note ? { note, changed: false } : "not_found"
    }
    const now = new Date().toISOString()
    const note: TrackerNote = {
      id: `mock-note-${crypto.randomUUID()}`,
      opportunity_id: opportunityId,
      note_text: noteText.trim(),
      created_at: now,
      updated_at: now,
      archived_at: null,
    }
    const notes = this.trackerNotes.get(opportunityId) ?? []
    notes.push(note)
    this.trackerNotes.set(opportunityId, notes)
    this.trackerNoteIdempotency.push({
      idempotency_key: idempotencyKey,
      action_type: "tracker_note_created",
      opportunity_id: opportunityId,
      note_id: note.id,
    })
    this.persistTrackerNotes()
    this.recordTrackerNoteEvent(opportunityId, state, "tracker_note_created", note.id)
    return { note, changed: true }
  }

  updateTrackerNote(
    opportunityId: string,
    noteId: string,
    idempotencyKey: string,
    update: { note_text?: string; archived?: true }
  ): TrackerNoteMutationResponse | "not_found" | "not_tracked" | "idempotency_conflict" | "archived" {
    if (!this.opportunities.has(opportunityId)) return "not_found"
    const state = this.applicationTrackerState(opportunityId)
    if (!state) return "not_tracked"
    const notes = this.trackerNotes.get(opportunityId) ?? []
    const note = notes.find((entry) => entry.id === noteId)
    if (!note) return "not_found"
    const actionType = update.archived ? "tracker_note_archived" : "tracker_note_updated"
    const prior = this.trackerNoteIdempotency.find((entry) => entry.idempotency_key === idempotencyKey)
    if (prior) {
      if (prior.action_type !== actionType || prior.opportunity_id !== opportunityId || prior.note_id !== noteId) {
        return "idempotency_conflict"
      }
      return { note, changed: false }
    }
    if (update.archived) {
      if (note.archived_at) return { note, changed: false }
      note.archived_at = new Date().toISOString()
    } else if (update.note_text !== undefined) {
      if (note.archived_at) return "archived"
      const cleaned = update.note_text.trim()
      if (cleaned === note.note_text) return { note, changed: false }
      note.note_text = cleaned
    } else {
      return "idempotency_conflict"
    }
    note.updated_at = new Date().toISOString()
    this.trackerNoteIdempotency.push({
      idempotency_key: idempotencyKey,
      action_type: actionType,
      opportunity_id: opportunityId,
      note_id: note.id,
    })
    this.persistTrackerNotes()
    this.recordTrackerNoteEvent(opportunityId, state, actionType, note.id)
    return { note, changed: true }
  }

  listOpportunityTrackerFollowUps(
    opportunityId: string,
    page = 1,
    pageSize = 50
  ): TrackerFollowUpListResponse | "not_found" | "not_tracked" {
    if (!this.opportunities.has(opportunityId)) return "not_found"
    if (!this.eligibleFollowUpTrackerState(opportunityId)) return "not_tracked"
    const rows = this.trackerFollowUps.get(opportunityId) ?? []
    const normalizedPage = Math.max(1, Math.floor(page) || 1)
    const normalizedSize = Math.min(100, Math.max(1, Math.floor(pageSize) || 50))
    return {
      opportunity_id: opportunityId,
      page: normalizedPage,
      page_size: normalizedSize,
      total: rows.length,
      items: [...rows]
        .sort((left, right) => left.due_date.localeCompare(right.due_date) || left.id.localeCompare(right.id))
        .slice((normalizedPage - 1) * normalizedSize, normalizedPage * normalizedSize),
    }
  }

  listTrackerFollowUps(
    bucket: TrackerFollowUpBucket,
    page = 1,
    pageSize = 25
  ): TrackerFollowUpSummaryResponse | "invalid_bucket" {
    if (!["due_today", "overdue", "upcoming"].includes(bucket)) return "invalid_bucket"
    const today = new Date().toISOString().slice(0, 10)
    const items = [...this.trackerFollowUps.values()].flat()
      .filter((followUp) => !followUp.completed_at && this.eligibleFollowUpTrackerState(followUp.opportunity_id))
      .map((followUp) => ({ followUp, status: followUpStatus(followUp.due_date, followUp.completed_at, today) }))
      .filter(({ status }) => status === bucket)
      .sort((left, right) => left.followUp.due_date.localeCompare(right.followUp.due_date) || left.followUp.id.localeCompare(right.followUp.id))
    const normalizedPage = Math.max(1, Math.floor(page) || 1)
    const normalizedSize = Math.min(100, Math.max(1, Math.floor(pageSize) || 25))
    return {
      bucket,
      page: normalizedPage,
      page_size: normalizedSize,
      total: items.length,
      items: items.slice((normalizedPage - 1) * normalizedSize, normalizedPage * normalizedSize).flatMap(({ followUp }) => {
        const opportunity = this.opportunities.get(followUp.opportunity_id)
        const trackerState = this.eligibleFollowUpTrackerState(followUp.opportunity_id)
        if (!opportunity || !trackerState) return []
        return [{
          id: followUp.id,
          opportunity_id: followUp.opportunity_id,
          due_date: followUp.due_date,
          completed_at: followUp.completed_at,
          status: followUpStatus(followUp.due_date, followUp.completed_at, today),
          created_at: followUp.created_at,
          updated_at: followUp.updated_at,
          opportunity: {
            id: opportunity.id,
            title: opportunity.title,
            organization: opportunity.organization,
            tracker_state: trackerState,
          },
        }]
      }),
    }
  }

  createTrackerFollowUp(
    opportunityId: string,
    dueDate: string,
    noteText: string | null | undefined,
    idempotencyKey: string
  ): TrackerFollowUpMutationResponse | "not_found" | "not_tracked" | "invalid_due_date" | "invalid_note_text" | "invalid_idempotency_key" | "idempotency_conflict" {
    if (!this.opportunities.has(opportunityId)) return "not_found"
    const state = this.eligibleFollowUpTrackerState(opportunityId)
    if (!state) return "not_tracked"
    if (!isIsoCalendarDate(dueDate)) return "invalid_due_date"
    if (typeof idempotencyKey !== "string" || !idempotencyKey.trim() || idempotencyKey.length > 128) return "invalid_idempotency_key"
    const cleanedNote = noteText?.trim() || null
    if (cleanedNote && cleanedNote.length > 4000) return "invalid_note_text"
    const prior = this.trackerFollowUpIdempotency.find((entry) => entry.idempotency_key === idempotencyKey)
    if (prior) {
      if (prior.action_type !== "follow_up_created" || prior.opportunity_id !== opportunityId) return "idempotency_conflict"
      const followUp = (this.trackerFollowUps.get(opportunityId) ?? []).find((entry) => entry.id === prior.follow_up_id)
      return followUp ? { follow_up: followUp, changed: false } : "not_found"
    }
    const now = new Date().toISOString()
    const followUp: TrackerFollowUp = {
      id: `mock-follow-up-${crypto.randomUUID()}`,
      opportunity_id: opportunityId,
      due_date: dueDate,
      note_text: cleanedNote,
      completed_at: null,
      status: followUpStatus(dueDate, null, now.slice(0, 10)),
      created_at: now,
      updated_at: now,
    }
    this.trackerFollowUps.set(opportunityId, [...(this.trackerFollowUps.get(opportunityId) ?? []), followUp])
    this.trackerFollowUpIdempotency.push({
      idempotency_key: idempotencyKey,
      action_type: "follow_up_created",
      opportunity_id: opportunityId,
      follow_up_id: followUp.id,
    })
    this.persistTrackerFollowUps()
    this.recordTrackerFollowUpEvent(opportunityId, state, "follow_up_created", followUp.id)
    return { follow_up: followUp, changed: true }
  }

  updateTrackerFollowUp(
    opportunityId: string,
    followUpId: string,
    idempotencyKey: string,
    update: { due_date?: string; note_text?: string | null; note_text_provided?: boolean; completed?: boolean }
  ): TrackerFollowUpMutationResponse | "not_found" | "not_tracked" | "invalid_due_date" | "invalid_note_text" | "invalid_idempotency_key" | "invalid_update" | "idempotency_conflict" {
    if (!this.opportunities.has(opportunityId)) return "not_found"
    const state = this.eligibleFollowUpTrackerState(opportunityId)
    if (!state) return "not_tracked"
    const followUp = (this.trackerFollowUps.get(opportunityId) ?? []).find((entry) => entry.id === followUpId)
    if (!followUp) return "not_found"
    const hasCompletion = update.completed !== undefined
    const hasDueDate = update.due_date !== undefined
    const hasNote = update.note_text_provided === true
    if (hasCompletion ? hasDueDate || hasNote : !hasDueDate && !hasNote) return "invalid_update"
    if (hasDueDate && !isIsoCalendarDate(update.due_date)) return "invalid_due_date"
    const cleanedNote = hasNote ? update.note_text?.trim() || null : undefined
    if (cleanedNote && cleanedNote.length > 4000) return "invalid_note_text"
    if (typeof idempotencyKey !== "string" || !idempotencyKey.trim() || idempotencyKey.length > 128) return "invalid_idempotency_key"
    const actionType = update.completed === true
      ? "follow_up_completed"
      : update.completed === false
        ? "follow_up_reopened"
        : "follow_up_updated"
    const prior = this.trackerFollowUpIdempotency.find((entry) => entry.idempotency_key === idempotencyKey)
    if (prior) {
      if (prior.action_type !== actionType || prior.opportunity_id !== opportunityId || prior.follow_up_id !== followUpId) return "idempotency_conflict"
      return { follow_up: followUp, changed: false }
    }
    const now = new Date().toISOString()
    let changed = false
    if (hasCompletion) {
      if (update.completed && !followUp.completed_at) {
        followUp.completed_at = now
        changed = true
      } else if (!update.completed && followUp.completed_at) {
        followUp.completed_at = null
        changed = true
      }
    } else {
      if (hasDueDate && update.due_date !== followUp.due_date) {
        followUp.due_date = update.due_date!
        changed = true
      }
      if (hasNote && cleanedNote !== followUp.note_text) {
        followUp.note_text = cleanedNote ?? null
        changed = true
      }
    }
    if (!changed) return { follow_up: followUp, changed: false }
    followUp.updated_at = now
    followUp.status = followUpStatus(followUp.due_date, followUp.completed_at, now.slice(0, 10))
    this.trackerFollowUpIdempotency.push({
      idempotency_key: idempotencyKey,
      action_type: actionType,
      opportunity_id: opportunityId,
      follow_up_id: followUpId,
    })
    this.persistTrackerFollowUps()
    this.recordTrackerFollowUpEvent(opportunityId, state, actionType, followUpId)
    return { follow_up: followUp, changed: true }
  }

  private persistTrackerState() {
    if (typeof window === "undefined") return
    const states = [...this.opportunities.values()]
      .filter((opportunity) => opportunity.action_state !== null)
      .map(({ id, action_state }) => ({ id, action_state }))
    try {
      window.localStorage.setItem(this.trackerStorageKey(), JSON.stringify(states))
    } catch {
      // This is synthetic review data; a blocked store must not fail the action.
    }
  }

  private recordTrackerTransition(
    opportunityId: string,
    fromState: string,
    toState: string,
    actionType: string
  ) {
    const event = {
      opportunity_id: opportunityId,
      action_type: actionType,
      from_state: fromState,
      to_state: toState,
      event_at: new Date().toISOString(),
    }
    this.trackerEvents.push(event)
    if (typeof window === "undefined") return
    try {
      window.localStorage.setItem(this.trackerEventsStorageKey(), JSON.stringify(this.trackerEvents))
    } catch {
      // Synthetic event persistence must not fail the mock action.
    }
  }

  getTrackerEvents(opportunityId: string) {
    return this.trackerEvents.filter((event) => event.opportunity_id === opportunityId)
  }

  private seedDailyCounters(): DashboardDay[] {
    const evaluated = [...this.opportunities.values()]
    const days: DashboardDay[] = []
    for (let i = 0; i < 7; i++) {
      const date = daysAgoUtc(i)
      if (i === 0) {
        const qualifiedToday = evaluated.filter(
          (o) => o.decision === "qualified"
        ).length
        const highFitToday = evaluated.filter(
          (o) => (o.fit_score ?? 0) >= HIGH_FIT_THRESHOLD
        ).length
        days.push({
          date,
          fetched: evaluated.length,
          unique_new: evaluated.length,
          qualified: qualifiedToday,
          high_fit: highFitToday,
          opened: 0,
          labelled: evaluated.filter((o) => o.feedback_label !== null).length,
          applied: evaluated.filter((o) => o.action_state === "submitted")
            .length,
          hidden_by_filters: this.hiddenCount(evaluated),
        })
      } else {
        days.push({
          date,
          fetched: 0,
          unique_new: 0,
          qualified: 0,
          high_fit: 0,
          opened: 0,
          labelled: 0,
          applied: 0,
          hidden_by_filters: 0,
        })
      }
    }
    return days
  }

  private today(): DashboardDay {
    return this.dailyCounters[0]
  }

  // ---- auth ----

  // A mock has no business enforcing a specific credential: the real
  // password check is api/routes_auth.py's job (covered by
  // api/test_api.py). This accepts any non-empty password and rejects only
  // the empty string, so the mock can still exercise the failed-login
  // (401/429) shape without hard-coding a credential-shaped literal.
  login(password: string): { ok: true } | { ok: false; status: 401 | 429 } {
    if (this.failedLoginAttempts >= 5) {
      return { ok: false, status: 429 }
    }
    if (password.length > 0) {
      this.authenticated = true
      this.failedLoginAttempts = 0
      return { ok: true }
    }
    this.failedLoginAttempts += 1
    return {
      ok: false,
      status: this.failedLoginAttempts >= 5 ? 429 : 401,
    }
  }

  logout() {
    this.authenticated = false
  }

  // ---- opportunities ----

  /** Per-item `hidden_by` / `flagged_by`, evaluated against the store's
   * live `filterSettings`. A disabled filter is not evaluated at all, per
   * the contract (§4): it contributes to neither list. Neither is a filter
   * with `default_unavailable_reason` set (council finding, D3 repair): its
   * predicate can never match anything in production regardless of
   * `enabled`/`mode`, so it never contributes here either — matching that
   * reality is what makes `flagged_by` chips trustworthy. */
  private matchingFilterIds(o: SeedOpportunity): {
    hidden_by: string[]
    flagged_by: string[]
    rankDemoted: boolean
  } {
    const hidden_by: string[] = []
    const flagged_by: string[] = []
    let rankDemoted = false
    for (const def of FOUNDER_FILTER_DEFINITIONS) {
      if (def.default_unavailable_reason !== null) continue
      const setting = this.filterSettings.get(def.filter_id)!
      if (!setting.enabled) continue
      if (!evaluateFounderFilter(def.filter_id, o, setting.params)) continue
      if (setting.mode === "hide") {
        hidden_by.push(def.filter_id)
      } else {
        flagged_by.push(def.filter_id)
        if (setting.mode === "rank_only") rankDemoted = true
      }
    }
    for (const fd of MOCK_FACET_DEFS) {
      if (!fd.available) continue
      const row = this.facetSettings.get(fd.facet_id)
      if (!row || (row.include.length === 0 && row.exclude.length === 0)) continue
      const value = fd.valueOf(o)
      const hides =
        (row.include.length > 0 && !row.include.includes(value)) ||
        row.exclude.includes(value)
      if (hides) hidden_by.push(`facet:${fd.facet_id}`)
    }
    return { hidden_by, flagged_by, rankDemoted }
  }

  // ---- facets (C1) ----

  listFacets(): FacetsResponse {
    const items = [...this.opportunities.values()]
    return {
      facets: MOCK_FACET_DEFS.map((fd) => {
        if (!fd.available) {
          return {
            facet_id: fd.facet_id,
            value_type: fd.value_type,
            description: fd.description,
            available: false,
            unavailable_reason: fd.unavailable_reason,
            values: [],
            excluded_count: 0,
            include: [],
            exclude: [],
          }
        }
        const row = this.facetSettings.get(fd.facet_id) ?? { include: [], exclude: [] }
        const counts = new Map<string, number>()
        let excluded = 0
        for (const o of items) {
          const value = fd.valueOf(o)
          counts.set(value, (counts.get(value) ?? 0) + 1)
          const hides =
            (row.include.length > 0 && !row.include.includes(value)) ||
            row.exclude.includes(value)
          if (hides) excluded += 1
        }
        const values = [...counts.entries()]
          .sort(([a], [b]) => (a < b ? -1 : 1))
          .map(([value, count]) => ({
            value,
            count,
            state: (row.include.includes(value)
              ? "include"
              : row.exclude.includes(value)
                ? "exclude"
                : "off") as FacetValueState,
          }))
        return {
          facet_id: fd.facet_id,
          value_type: fd.value_type,
          description: fd.description,
          available: true,
          unavailable_reason: null,
          values,
          excluded_count: excluded,
          include: row.include,
          exclude: row.exclude,
        }
      }),
    }
  }

  updateFacet(
    facetId: string,
    body: { include?: string[]; exclude?: string[] }
  ): Facet | "not_found" | "unavailable" {
    const fd = MOCK_FACET_DEFS.find((f) => f.facet_id === facetId)
    if (!fd) return "not_found"
    if (!fd.available) return "unavailable"
    const existing = this.facetSettings.get(facetId) ?? { include: [], exclude: [] }
    const include = body.include ?? existing.include
    const exclude = body.exclude ?? existing.exclude
    this.facetSettings.set(facetId, { include, exclude })
    return this.listFacets().facets.find((f) => f.facet_id === facetId)!
  }

  // ---- saved views (C1) ----

  listSavedViews(): SavedViewsResponse {
    return { views: this.savedViews }
  }

  createSavedView(body: {
    name: string
    facets: SavedView["facets"]
    search_query?: string | null
    feed_query?: FeedQueryState
    is_default?: boolean
  }): SavedView {
    if (body.is_default) {
      for (const v of this.savedViews) v.is_default = false
    }
    const view: SavedView = {
      id: `view-${this.savedViews.length + 1}-${Date.now()}`,
      name: body.name,
      facets: body.facets,
      search_query: body.search_query ?? null,
      feed_query: body.feed_query ?? null,
      is_default: body.is_default ?? false,
    }
    this.savedViews.push(view)
    return view
  }

  updateSavedView(
    viewId: string,
    body: {
      name?: string
      facets?: SavedView["facets"]
      search_query?: string | null
      feed_query?: FeedQueryState
      is_default?: boolean
    }
  ): SavedView | null {
    const view = this.savedViews.find((v) => v.id === viewId)
    if (!view) return null
    if (body.name !== undefined) view.name = body.name
    if (body.facets !== undefined) view.facets = body.facets
    if (body.search_query !== undefined) view.search_query = body.search_query
    if (body.feed_query !== undefined) view.feed_query = body.feed_query
    if (body.is_default) {
      for (const v of this.savedViews) v.is_default = false
      view.is_default = true
    } else if (body.is_default === false) {
      view.is_default = false
    }
    return view
  }

  deleteSavedView(viewId: string): boolean {
    const idx = this.savedViews.findIndex((v) => v.id === viewId)
    if (idx === -1) return false
    this.savedViews.splice(idx, 1)
    return true
  }

  // ---- hidden reasons (C4) ----

  hiddenReasonsAudit(): HiddenReasonsResponse {
    const counts = new Map<string, number>()
    for (const o of this.opportunities.values()) {
      const { hidden_by } = this.matchingFilterIds(o)
      for (const reason of hidden_by) {
        const label = reason.startsWith("facet:") ? `facet: ${reason.slice(6)}` : `filter: ${reason}`
        counts.set(label, (counts.get(label) ?? 0) + 1)
      }
    }
    const reasons: HiddenReason[] = [...counts.entries()]
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(([reason, count]) => ({ reason, count }))
    return { reasons }
  }

  unhideByReason(reason: string): boolean {
    if (reason.startsWith("facet: ")) {
      const facetId = reason.slice("facet: ".length)
      if (!MOCK_FACET_DEFS.some((f) => f.facet_id === facetId)) return false
      this.facetSettings.set(facetId, { include: [], exclude: [] })
      return true
    }
    if (reason.startsWith("filter: ")) {
      const filterId = reason.slice("filter: ".length)
      const setting = this.filterSettings.get(filterId)
      if (!setting) return false
      setting.enabled = false
      return true
    }
    return false
  }

  private hiddenCount(items: SeedOpportunity[]): number {
    return items.filter((o) => this.matchingFilterIds(o).hidden_by.length > 0)
      .length
  }

  feedFilterMetadata(): FeedFilterMetadataResponse {
    const items = [...this.opportunities.values()]
    const facets = {} as FeedFilterMetadataResponse["facets"]
    for (const facet of FEED_FACETS) {
      const counts = new Map<string, number>()
      for (const item of items) {
        const value = mockFacetValue(item, facet)
        counts.set(value, (counts.get(value) ?? 0) + 1)
      }
      const ordered = [...counts.entries()].sort(([leftValue, leftCount], [rightValue, rightCount]) =>
        rightCount - leftCount || leftValue.localeCompare(rightValue)
      )
      facets[facet] = {
        selection: facet === "track" || facet === "decision" ? "single" : "multiple",
        values: ordered.slice(0, 100).map(([value, count]) => ({ value, count })),
        option_count: ordered.length,
        truncated: ordered.length > 100,
      }
    }

    const ranges = {} as FeedFilterMetadataResponse["ranges"]
    for (const score of FEED_SCORES) {
      const scores = items.map((item) => mockFeedScore(item, score)).filter((value): value is number => value !== null)
      ranges[score] = {
        min: scores.length ? Math.min(...scores) : null,
        max: scores.length ? Math.max(...scores) : null,
        unknown_count: items.length - scores.length,
        threshold_counts: {
          "90+": scores.filter((value) => value >= 90).length,
          "80+": scores.filter((value) => value >= 80).length,
          "70+": scores.filter((value) => value >= 70).length,
          "60+": scores.filter((value) => value >= 60).length,
          "50+": scores.filter((value) => value >= 50).length,
        },
      }
    }
    const postedDates = items.map((item) => item.posted_date?.trim() ?? "").filter(Boolean).sort()
    ranges.posted_date = {
      min: postedDates[0] ?? null,
      max: postedDates[postedDates.length - 1] ?? null,
      unknown_count: items.length - postedDates.length,
    }

    return {
      truth_pack_hash: this.truthStatus().hash ?? "synthetic-mock-truth-pack",
      count_scope: {
        visible_only: true,
        independent_of_selected_filters: true,
        includes_tracked_and_ineligible: true,
      },
      facets,
      ranges,
      sorts: FEED_SORTS,
      unavailable_filters: MOCK_UNAVAILABLE_FEED_FILTERS,
    }
  }

  listOpportunities(filters: {
    track?: string
    decision?: string
    min_score?: number
    min_fit_score?: number
    max_fit_score?: number
    min_preference_score?: number
    max_preference_score?: number
    min_confidence_score?: number
    max_confidence_score?: number
    min_priority_score?: number
    max_priority_score?: number
    posted_from?: string
    posted_to?: string
    work_mode?: string[]
    location_country?: string[]
    location_city?: string[]
    remote_scope?: string[]
    employment_type?: string[]
    seniority_level?: string[]
    target_tier?: string[]
    title_family?: string[]
    source_id?: string[]
    sort_by?: FeedSortId
    q?: string
    page?: number
    page_size?: number
    /** Default `false`. `true` includes items an enabled `hide`-mode
     * filter matched, with `hidden_by` populated on them. */
    include_hidden?: boolean
  }): OpportunityListResponse {
    // Jobs / To Review is an inbox: completed triage actions leave only after
    // the mock store has recorded them, matching the durable API contract.
    let items = [...this.opportunities.values()].filter(
      (o) => ![
        "saved", "submitted", "applied", "recruiter_screen", "assessment",
        "interviewing", "final_interview", "offer", "accepted",
        "rejected_by_founder", "rejected_by_employer", "withdrawn", "no_response",
        "position_closed", "archived", "dismissed", "snoozed",
      ].includes(o.action_state ?? "")
    )

    if (filters.track) {
      items = items.filter((o) => o.track === filters.track)
    }
    if (filters.decision) {
      items = items.filter((o) => mockFacetValue(o, "decision") === filters.decision)
    }
    const multiSelections: Record<FeedMultiFacetId, string[] | undefined> = {
      work_mode: filters.work_mode,
      location_country: filters.location_country,
      location_city: filters.location_city,
      remote_scope: filters.remote_scope,
      employment_type: filters.employment_type,
      seniority_level: filters.seniority_level,
      target_tier: filters.target_tier,
      title_family: filters.title_family,
      source_id: filters.source_id,
    }
    for (const facet of FEED_MULTI_FACETS) {
      const selected = multiSelections[facet]
      if (selected?.length) items = items.filter((item) => selected.includes(mockFacetValue(item, facet)))
    }
    const scoreBounds: Array<[FeedScoreId, number | undefined, number | undefined]> = [
      ["fit_score", filters.min_fit_score ?? filters.min_score, filters.max_fit_score],
      ["preference_score", filters.min_preference_score, filters.max_preference_score],
      ["confidence_score", filters.min_confidence_score, filters.max_confidence_score],
      ["priority_score", filters.min_priority_score, filters.max_priority_score],
    ]
    for (const [scoreId, minimum, maximum] of scoreBounds) {
      if (minimum !== undefined && !Number.isNaN(minimum)) items = items.filter((item) => {
        const score = mockFeedScore(item, scoreId)
        return score !== null && score >= minimum
      })
      if (maximum !== undefined && !Number.isNaN(maximum)) items = items.filter((item) => {
        const score = mockFeedScore(item, scoreId)
        return score !== null && score <= maximum
      })
    }
    if (filters.q) {
      const q = filters.q.toLowerCase()
      items = items.filter(
        (o) =>
          o.title.toLowerCase().includes(q) ||
          o.organization.toLowerCase().includes(q)
      )
    }
    if (filters.posted_from) items = items.filter((item) => Boolean(item.posted_date && item.posted_date >= filters.posted_from!))
    if (filters.posted_to) items = items.filter((item) => Boolean(item.posted_date && item.posted_date <= filters.posted_to!))

    // Decorate every item with its current hidden_by/flagged_by before
    // deciding visibility, so hidden_count always reflects the full
    // filtered set regardless of include_hidden (contract §5's
    // "total"/"hidden_count" semantics).
    const decorated = items.map((o) => ({ o, ...this.matchingFilterIds(o) }))
    const hiddenCount = decorated.filter((d) => d.hidden_by.length > 0).length

    const visible = filters.include_hidden
      ? decorated
      : decorated.filter((d) => d.hidden_by.length === 0)

    // Existing key (fit_score desc nulls last, posted_date desc, id),
    // with a rank-adjustment term so rank_only-demoted items sort after
    // non-demoted ones at an equal score, per the contract's §4 sorting
    // rule. decision and fit_score themselves are never touched by any
    // filter — only this sort position and hidden_by/flagged_by are.
    const sortBy = filters.sort_by ?? "recommended"
    visible.sort((a, b) => {
      const ao = a.o
      const bo = b.o
      if (sortBy === "remote_first") {
        const aRemote = mockExtractionFields(ao).work_mode === "remote"
        const bRemote = mockExtractionFields(bo).work_mode === "remote"
        if (aRemote !== bRemote) return aRemote ? -1 : 1
      }
      if (sortBy === "newest_posted" || sortBy === "oldest_posted") {
        const ad = ao.posted_date ?? ""
        const bd = bo.posted_date ?? ""
        if (ad !== bd) {
          if (!ad) return 1
          if (!bd) return -1
          return sortBy === "newest_posted" ? (ad > bd ? -1 : 1) : (ad < bd ? -1 : 1)
        }
      }
      if (sortBy === "fit_asc" && ao.fit_score !== bo.fit_score) {
        if (ao.fit_score === null) return 1
        if (bo.fit_score === null) return -1
        return ao.fit_score - bo.fit_score
      }
      if (ao.fit_score === null && bo.fit_score !== null) return 1
      if (ao.fit_score !== null && bo.fit_score === null) return -1
      if (
        ao.fit_score !== null &&
        bo.fit_score !== null &&
        ao.fit_score !== bo.fit_score
      ) {
        return bo.fit_score - ao.fit_score
      }
      if (a.rankDemoted !== b.rankDemoted) return a.rankDemoted ? 1 : -1
      const ad = ao.posted_date ?? ""
      const bd = bo.posted_date ?? ""
      if (ad !== bd) return ad < bd ? 1 : -1
      return ao.id < bo.id ? -1 : 1
    })

    const page = filters.page ?? 1
    const pageSize = filters.page_size ?? 25
    const start = (page - 1) * pageSize
    const paged = visible.slice(start, start + pageSize)

    return {
      page,
      page_size: pageSize,
      total: visible.length,
      hidden_count: hiddenCount,
      items: paged.map((d) => toListItem(d.o, d.hidden_by, d.flagged_by)),
    }
  }

  listTracker(bucket: TrackerBucket, page = 1, pageSize = 25): TrackerListResponse {
    const appliedStates: TrackerState[] = [
      "applied", "recruiter_screen", "assessment", "interviewing",
      "final_interview", "offer", "accepted",
    ]
    const rejectedStates: TrackerState[] = [
      "rejected_by_founder", "rejected_by_employer", "withdrawn",
      "no_response", "position_closed", "archived", "dismissed",
    ]
    const tracked = [...this.opportunities.values()].flatMap((opportunity) => {
      const state: TrackerState | null = opportunity.action_state === "submitted"
        ? "applied"
        : opportunity.action_state
      if (!state || state === "snoozed") return []
      const inBucket = bucket === "all"
        ? state === "saved" || appliedStates.includes(state) || rejectedStates.includes(state)
        : bucket === "saved"
          ? state === "saved"
          : bucket === "applied"
            ? appliedStates.includes(state)
            : rejectedStates.includes(state)
      return inBucket ? [{ opportunity, state }] : []
    }).sort((left, right) => left.opportunity.id.localeCompare(right.opportunity.id))
    const normalizedPage = Math.max(1, page)
    const normalizedPageSize = Math.max(1, Math.min(pageSize, 100))
    const start = (normalizedPage - 1) * normalizedPageSize
    return {
      bucket,
      page: normalizedPage,
      page_size: normalizedPageSize,
      total: tracked.length,
      items: tracked.slice(start, start + normalizedPageSize).map(({ opportunity, state }) => ({
        ...toListItem(opportunity, [], []),
        tracker_state: state,
      })),
    }
  }

  getDetail(id: string): OpportunityDetail | null {
    const o = this.opportunities.get(id)
    if (!o) return null

    // Side effect per contract: a successful detail fetch records one
    // founder_opportunity_views row, which is what the dashboard's
    // `opened` counts.
    this.today().opened += 1

    return {
      id: o.id,
      title: o.title,
      organization: o.organization,
      source_id: o.source_id,
      source_url: o.source_url,
      track: o.track,
      description: o.description,
      deadline: o.deadline,
      posted_date: o.posted_date,
      is_stale: o.is_stale,
      reverified_at: o.reverified_at,
      fields: o.fields,
      qualification: { decision: o.decision, constraints: o.constraints },
      scoring: {
        fit_score: o.fit_score,
        dimension_scores: o.dimension_scores,
        strengths: o.strengths,
        gaps: o.gaps,
        unknowns: o.unknowns,
        uncertainty_penalty: o.uncertainty_penalty,
        explanation: o.explanation,
        policy_version: o.policy_version,
        evaluated_at: o.evaluated_at ?? "",
        truth_pack_hash: o.truth_pack_hash,
      },
      evidence_links: o.evidence_links,
      action_history: o.action_history,
      feedback_history: o.feedback_history,
      ...mockExtractionFields(o),
    }
  }

  submitFeedback(id: string, label: FeedbackLabel, note: string | null) {
    const o = this.opportunities.get(id)
    if (!o) return null
    const entry = {
      id: `fb-${id}-${o.feedback_history.length + 1}`,
      feedback_label: label,
      structured_reason: label,
      notes: note,
      created_at: new Date().toISOString(),
    }
    o.feedback_history.push(entry)
    o.feedback_label = label
    this.today().labelled += 1
    return entry
  }

  submitAction(
    id: string,
    type: ActionType,
    until: string | null,
    requestedStage?: string | null
  ) {
    const o = this.opportunities.get(id)
    if (!o) return null

    const previousState = o.action_state === "submitted"
      ? "applied"
      : o.action_state ?? "to_review"

    if (type === "set_stage") {
      const stageTargets: ApplicationStage[] = [
        "applied", "recruiter_screen", "assessment", "interviewing",
        "final_interview", "offer", "accepted", "rejected_by_employer",
        "withdrawn", "no_response",
      ]
      if (!requestedStage || !stageTargets.includes(requestedStage as ApplicationStage)) return null
      const stage = requestedStage as ApplicationStage
      const forwardStages: ApplicationStage[] = [
        "applied", "recruiter_screen", "assessment", "interviewing",
        "final_interview", "offer", "accepted",
      ]
      const terminalStages: ApplicationStage[] = ["rejected_by_employer", "withdrawn", "no_response"]
      if (previousState === stage) {
        return {
          opportunity_id: id,
          action_state: o.action_state,
          tracker_state: stage,
          action_id: null,
          until: null,
          created_at: new Date().toISOString(),
        }
      }
      const previousIndex = forwardStages.indexOf(previousState as ApplicationStage)
      const targetIndex = forwardStages.indexOf(stage)
      const canMoveForward = previousIndex >= 0 && targetIndex > previousIndex
      const canClose = terminalStages.includes(stage) && previousIndex >= 0
      if (!canMoveForward && !canClose) return null

      o.action_state = stage
      this.recordTrackerTransition(id, previousState, stage, "application_stage_updated")
      this.persistTrackerState()
      return {
        opportunity_id: id,
        action_state: stage,
        tracker_state: stage,
        action_id: null,
        until: null,
        created_at: new Date().toISOString(),
      }
    }

    if (type === "mark_applied") {
      if (o.action_state === "submitted") {
        const prior = [...o.action_history].reverse().find((entry) => entry.action_status === "submitted")
        return {
          opportunity_id: id,
          action_state: "submitted" as const,
          tracker_state: "applied" as const,
          action_id: prior?.action_id ?? null,
          until: null,
          created_at: prior?.created_at ?? new Date().toISOString(),
        }
      }
      if (!["to_review", "saved", "snoozed", "dismissed"].includes(previousState)) return null
      o.action_state = "submitted"
      const entry = {
        action_id: `act-${id}-${o.action_history.length + 1}`,
        action_status: "submitted",
        execution_mode: "dry_run",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        notes: "Founder-attested: applied outside the platform.",
      }
      o.action_history.push(entry)
      this.today().applied += 1
      this.recordTrackerTransition(id, previousState, "applied", "applied")
      this.persistTrackerState()
      return {
        opportunity_id: id,
        action_state: o.action_state,
        tracker_state: "applied",
        action_id: entry.action_id,
        until: null,
        created_at: entry.created_at,
      }
    }

    if (type === "save") {
      if (previousState === "saved") {
        return {
          opportunity_id: id,
          action_state: o.action_state,
          tracker_state: "saved" as const,
          action_id: null,
          until: null,
          created_at: new Date().toISOString(),
        }
      }
      if (previousState !== "to_review" && previousState !== "snoozed") return null
      o.action_state = "saved"
      this.recordTrackerTransition(id, previousState, "saved", "saved")
      this.persistTrackerState()
      return {
        opportunity_id: id,
        action_state: o.action_state,
        tracker_state: "saved" as const,
        action_id: null,
        until: null,
        created_at: new Date().toISOString(),
      }
    }

    if (type === "reject") {
      if (previousState === "rejected_by_founder") {
        return {
          opportunity_id: id,
          action_state: o.action_state,
          tracker_state: "rejected_by_founder" as const,
          action_id: null,
          until: null,
          created_at: new Date().toISOString(),
        }
      }
      if (!["to_review", "saved", "snoozed", "dismissed"].includes(previousState)) return null
      o.action_state = "rejected_by_founder"
      this.recordTrackerTransition(id, previousState, "rejected_by_founder", "rejected_by_founder")
      this.persistTrackerState()
      return {
        opportunity_id: id,
        action_state: o.action_state,
        tracker_state: "rejected_by_founder" as const,
        action_id: null,
        until: null,
        created_at: new Date().toISOString(),
      }
    }

    if (type === "dismiss") {
      if (previousState === "dismissed") return {
        opportunity_id: id,
        action_state: o.action_state,
        tracker_state: "dismissed" as const,
        action_id: null,
        until: null,
        created_at: new Date().toISOString(),
      }
      o.action_state = "dismissed"
      this.recordTrackerTransition(id, previousState, "dismissed", "dismissed")
      this.persistTrackerState()
      return {
        opportunity_id: id,
        action_state: o.action_state,
        tracker_state: "dismissed" as const,
        action_id: null,
        until: null,
        created_at: new Date().toISOString(),
      }
    }

    // snooze
    if (previousState === "snoozed") return {
      opportunity_id: id,
      action_state: o.action_state,
      tracker_state: "snoozed" as const,
      action_id: null,
      until,
      created_at: new Date().toISOString(),
    }
    if (previousState !== "to_review" && previousState !== "dismissed") return null
    o.action_state = "snoozed"
    this.recordTrackerTransition(id, previousState, "snoozed", "snoozed")
    this.persistTrackerState()
    return {
      opportunity_id: id,
      action_state: o.action_state,
      tracker_state: "snoozed" as const,
      action_id: null,
      until,
      created_at: new Date().toISOString(),
    }
  }

  artifactClaimsRejected(id: string): boolean {
    return this.opportunities.get(id)?.artifact_claims_rejected ?? false
  }

  // ---- filters (D3) ----

  listFilters(): FiltersResponse {
    const items = [...this.opportunities.values()]
    return {
      filters: FOUNDER_FILTER_DEFINITIONS.map((def) => {
        const setting = this.filterSettings.get(def.filter_id)!
        return {
          filter_id: def.filter_id,
          enabled: setting.enabled,
          mode: setting.mode,
          params: { ...setting.params },
          // Computed regardless of `enabled`, per the contract, so the
          // drawer can show what enabling a disabled filter would do. Held
          // at 0 (never shown by the drawer either way) when unavailable,
          // since the predicate cannot fire at all in that case.
          affected_count:
            def.default_unavailable_reason !== null
              ? 0
              : items.filter((o) =>
                  evaluateFounderFilter(def.filter_id, o, setting.params)
                ).length,
          description: def.description,
          unavailable_reason: def.default_unavailable_reason,
        }
      }),
    }
  }

  /** Returns the updated filter, or a string error tag the handler maps to
   * the contract's 404 / 422 responses. */
  updateFilter(
    filterId: string,
    body: { enabled?: boolean; mode?: string; params?: Record<string, unknown> }
  ): FounderFilter | "not_found" | "invalid_mode" | "invalid_params" {
    const def = FOUNDER_FILTER_DEFINITIONS.find((f) => f.filter_id === filterId)
    const setting = this.filterSettings.get(filterId)
    if (!def || !setting) return "not_found"

    if (
      body.mode !== undefined &&
      !(["hide", "rank_only", "label_only"] as const).includes(
        body.mode as FilterMode
      )
    ) {
      return "invalid_mode"
    }

    // Matches api/filters.py::_validate_min_fit_score_params /
    // _validate_compensation_floor_params exactly: min_score is a number
    // in [0, 100] (fit_score's documented scale); floor is a number >= 0.
    // A council-found repair on the real API side, mirrored here so the
    // mock and the real API reject the same malformed writes the same
    // way, rather than the mock silently accepting something the real
    // API would 422 on.
    if (body.params !== undefined) {
      if (filterId === "min_fit_score" && "min_score" in body.params) {
        const value = body.params.min_score
        if (typeof value !== "number" || value < 0 || value > 100) {
          return "invalid_params"
        }
      }
      if (filterId === "compensation_floor" && "floor" in body.params) {
        const value = body.params.floor
        if (typeof value !== "number" || value < 0) {
          return "invalid_params"
        }
      }
    }

    if (body.enabled !== undefined) setting.enabled = body.enabled
    if (body.mode !== undefined) setting.mode = body.mode as FilterMode
    if (body.params !== undefined) {
      setting.params = { ...setting.params, ...body.params }
    }

    const items = [...this.opportunities.values()]
    return {
      filter_id: filterId,
      enabled: setting.enabled,
      mode: setting.mode,
      params: { ...setting.params },
      affected_count:
        def.default_unavailable_reason !== null
          ? 0
          : items.filter((o) =>
              evaluateFounderFilter(filterId, o, setting.params)
            ).length,
      description: def.description,
      unavailable_reason: def.default_unavailable_reason,
    }
  }

  // ---- dashboard / sources / worker / truth ----

  dashboard(days: number): DashboardResponse {
    // `hidden_by_filters` for *today* (index 0) is recomputed live against
    // current filter/facet settings on every call -- matching the real
    // API's `dashboard_daily`, which re-runs `apply_filters` against
    // today's rows on every request rather than a value frozen at seed
    // time. Earlier days stay the static snapshot this mock has no
    // per-day history to recompute against.
    const series = this.dailyCounters.slice(0, days).map((day, i) =>
      i === 0
        ? { ...day, hidden_by_filters: this.hiddenCount([...this.opportunities.values()]) }
        : day
    )
    return {
      days,
      high_fit_threshold: HIGH_FIT_THRESHOLD,
      series,
    }
  }

  sourcesHealth(): SourcesHealthResponse {
    return { sources: this.sources }
  }

  pollNow() {
    const enqueued: { source_id: string; job_id: string }[] = []
    const skipped: { source_id: string; reason: "read_disabled_by_policy" }[] =
      []
    for (const s of this.sources) {
      if (s.read_policy === "allowed") {
        enqueued.push({ source_id: s.source_id, job_id: `job-${s.source_id}-${Date.now()}` })
        s.last_poll = new Date().toISOString()
        s.last_status = s.last_status ?? "ok"
        s.last_record_count = s.last_record_count ?? 0
      } else {
        skipped.push({ source_id: s.source_id, reason: "read_disabled_by_policy" })
      }
    }
    return { enqueued, skipped }
  }

  truthStatus(): TruthStatusResponse {
    return {
      loaded: this.truthLoaded,
      hash: this.truthLoaded ? "sha256:truthpack-mock-0001" : null,
      path: "private/truth_pack.yaml",
      validator: this.truthValidator,
      sections: this.truthSections,
    }
  }

  truthReload(): TruthStatusResponse {
    // The mock's synthetic scenarios are fixed; reload just re-reports the
    // current status, matching the contract's shape.
    return this.truthStatus()
  }
}

/** BRIEF-FR-006 C5: `SeedOpportunity` (fixtures.ts) predates the C5 order
 * and has no work_mode/location/compensation/family fields of its own —
 * rather than hand-add them to every one of its ~30 literal fixture
 * entries (out of this order's scope, and fixtures.ts is large enough that
 * doing so blind would risk silently changing an existing scenario's
 * facet/filter behaviour), this deterministically derives a plausible,
 * *varied* set of C5 fields from each opportunity's own `id` string so the
 * mock feed/detail can demonstrate every field the real API now returns.
 * This is synthetic mock-only data, not a claim about a real founder or
 * employer — the real values come from `api/serialization.py`. One row
 * (`id` ending in `0` mod the rotation) is deliberately `"unspecified"`,
 * matching the real corpus measurement that ~47.8% of postings carry no
 * work-mode signal. */
function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

const MOCK_WORK_MODES = ["remote", "hybrid", "onsite", "unspecified"] as const
const MOCK_LOCATIONS: Array<{ city: string | null; country: string | null; region: string | null }> = [
  { city: "Cairo", country: "EG", region: "MENA" },
  { city: null, country: null, region: null },
  { city: "Dubai", country: "AE", region: "MENA" },
  { city: "Berlin", country: "DE", region: "EU" },
]
const MOCK_EMPLOYMENT_TYPES = ["full_time", "contract", "part_time", "unspecified"] as const
const MOCK_SENIORITY_LEVELS = ["mid", "senior", "lead", "unspecified"] as const

function mockFacetValue(o: SeedOpportunity, facet: FeedFacetId): string {
  const extraction = mockExtractionFields(o)
  let raw: string | null | undefined
  switch (facet) {
    case "track": return o.track
    case "decision": raw = o.decision; break
    case "work_mode": raw = extraction.work_mode; break
    case "location_country": raw = extraction.location_country; break
    case "location_city": raw = extraction.location_city; break
    case "remote_scope": raw = extraction.remote_scope; break
    case "employment_type": raw = extraction.employment_type; break
    case "seniority_level": raw = extraction.seniority_level; break
    case "target_tier": raw = null; break
    case "title_family": raw = extraction.title_family; break
    case "source_id": raw = o.source_id; break
  }
  const normalized = raw?.trim() ?? ""
  if (!normalized || normalized.toLocaleLowerCase() === "unknown" || (facet === "title_family" && normalized.toLocaleLowerCase() === "other")) return "unknown"
  return normalized.toLocaleLowerCase()
}

function mockFeedScore(o: SeedOpportunity, score: FeedScoreId): number | null {
  if (score === "fit_score") return o.fit_score
  if (o.fit_score === null) return null
  const hash = hashString(o.id)
  if (score === "preference_score") return (hash * 17 + 31) % 101
  if (score === "confidence_score") return (hash * 13 + 47) % 101
  return Math.round((o.fit_score * 0.7 + ((hash * 19 + 13) % 101) * 0.3) * 100) / 100
}

function mockExtractionFields(o: SeedOpportunity): OpportunityExtractionFields {
  const h = hashString(o.id)
  const workMode = MOCK_WORK_MODES[h % MOCK_WORK_MODES.length]
  const location = MOCK_LOCATIONS[h % MOCK_LOCATIONS.length]
  const employmentType = MOCK_EMPLOYMENT_TYPES[h % MOCK_EMPLOYMENT_TYPES.length]
  const seniorityLevel = MOCK_SENIORITY_LEVELS[h % MOCK_SENIORITY_LEVELS.length]
  const isClustered = h % 5 === 0

  return {
    work_mode: workMode,
    work_mode_source: workMode === "unspecified" ? null : h % 3 === 0 ? "inferred" : "posting",
    location_country: location.country,
    location_city: location.city,
    location_region: location.region,
    remote_scope: workMode === "remote" ? "worldwide" : "unspecified",
    remote_scope_regions: workMode === "remote" && h % 2 === 0 ? ["EG", "AE"] : [],
    employment_type: employmentType,
    seniority_level: seniorityLevel,
    compensation_min: h % 4 === 0 ? null : 3000 + (h % 5000),
    compensation_max: h % 4 === 0 ? null : 6000 + (h % 5000),
    compensation_currency: h % 4 === 0 ? null : "USD",
    compensation_period: h % 4 === 0 ? null : "monthly",
    title_family: null,
    title_level: null,
    family_key: isClustered ? `fam-${h % 7}` : null,
    family_size: isClustered ? 2 + (h % 20) : null,
  }
}

function toListItem(
  o: SeedOpportunity,
  hidden_by: string[],
  flagged_by: string[]
): OpportunityListItem {
  return {
    id: o.id,
    title: o.title,
    organization: o.organization,
    source_id: o.source_id,
    source_url: o.source_url,
    track: o.track,
    decision: o.decision,
    fit_score: o.fit_score,
    top_reasons: o.top_reasons,
    deadline: o.deadline,
    posted_date: o.posted_date,
    is_stale: o.is_stale,
    action_state: o.action_state,
    feedback_label: o.feedback_label,
    hidden_by,
    flagged_by,
    ...mockExtractionFields(o),
  }
}

let singleton: MockStore | null = null

export function getStore(scenario: MockScenario): MockStore {
  if (!singleton || singleton.scenario !== scenario) {
    singleton = new MockStore(scenario)
  }
  return singleton
}
