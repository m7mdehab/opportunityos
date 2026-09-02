/**
 * In-memory mutable state backing the mock API. One store per browser
 * session (module singleton); actions and feedback mutate it so the UI can
 * observe real state changes (dashboard counts, action_state, etc.) without
 * a server.
 */
import type {
  ActionType,
  DashboardDay,
  DashboardResponse,
  FeedbackLabel,
  OpportunityDetail,
  OpportunityListItem,
  OpportunityListResponse,
  SourceHealth,
  SourcesHealthResponse,
  TruthStatusResponse,
} from "@/lib/contract/types"
import {
  buildDefaultOpportunities,
  buildNoTruthPackOpportunities,
  buildSourcesHealth,
  truthSectionsComplete,
  truthSectionsMissing,
  truthValidatorOk,
  type SeedOpportunity,
} from "@/lib/mock/fixtures"
import type { MockScenario } from "@/lib/mock/scenario"

const MOCK_PASSWORD = "founder-mock-pass"
const HIGH_FIT_THRESHOLD = 70

function daysAgoUtc(n: number): string {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - n)
  return d.toISOString().slice(0, 10)
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

  constructor(scenario: MockScenario) {
    this.scenario = scenario

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

    this.dailyCounters = this.seedDailyCounters()
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
        })
      }
    }
    return days
  }

  private today(): DashboardDay {
    return this.dailyCounters[0]
  }

  // ---- auth ----

  login(password: string): { ok: true } | { ok: false; status: 401 | 429 } {
    if (this.failedLoginAttempts >= 5) {
      return { ok: false, status: 429 }
    }
    if (password === MOCK_PASSWORD) {
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

  listOpportunities(filters: {
    track?: string
    decision?: string
    min_score?: number
    q?: string
    page?: number
    page_size?: number
  }): OpportunityListResponse {
    let items = [...this.opportunities.values()]

    if (filters.track) {
      items = items.filter((o) => o.track === filters.track)
    }
    if (filters.decision) {
      items = items.filter((o) => o.decision === filters.decision)
    }
    if (filters.min_score !== undefined && !Number.isNaN(filters.min_score)) {
      items = items.filter(
        (o) => o.fit_score !== null && o.fit_score >= filters.min_score!
      )
    }
    if (filters.q) {
      const q = filters.q.toLowerCase()
      items = items.filter(
        (o) =>
          o.title.toLowerCase().includes(q) ||
          o.organization.toLowerCase().includes(q)
      )
    }

    items.sort((a, b) => {
      if (a.fit_score === null && b.fit_score !== null) return 1
      if (a.fit_score !== null && b.fit_score === null) return -1
      if (a.fit_score !== null && b.fit_score !== null && a.fit_score !== b.fit_score) {
        return b.fit_score - a.fit_score
      }
      const ad = a.posted_date ?? ""
      const bd = b.posted_date ?? ""
      if (ad !== bd) return ad < bd ? 1 : -1
      return a.id < b.id ? -1 : 1
    })

    const page = filters.page ?? 1
    const pageSize = filters.page_size ?? 25
    const start = (page - 1) * pageSize
    const paged = items.slice(start, start + pageSize)

    return {
      page,
      page_size: pageSize,
      total: items.length,
      items: paged.map(toListItem),
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

  submitAction(id: string, type: ActionType, until: string | null) {
    const o = this.opportunities.get(id)
    if (!o) return null

    if (type === "mark_applied") {
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
      return {
        opportunity_id: id,
        action_state: o.action_state,
        action_id: entry.action_id,
        until: null,
        created_at: entry.created_at,
      }
    }

    if (type === "dismiss") {
      o.action_state = "dismissed"
      return {
        opportunity_id: id,
        action_state: o.action_state,
        action_id: null,
        until: null,
        created_at: new Date().toISOString(),
      }
    }

    // snooze
    o.action_state = "snoozed"
    return {
      opportunity_id: id,
      action_state: o.action_state,
      action_id: null,
      until,
      created_at: new Date().toISOString(),
    }
  }

  artifactClaimsRejected(id: string): boolean {
    return this.opportunities.get(id)?.artifact_claims_rejected ?? false
  }

  // ---- dashboard / sources / worker / truth ----

  dashboard(days: number): DashboardResponse {
    return {
      days,
      high_fit_threshold: HIGH_FIT_THRESHOLD,
      series: this.dailyCounters.slice(0, days),
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

function toListItem(o: SeedOpportunity): OpportunityListItem {
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
  }
}

let singleton: MockStore | null = null

export function getStore(scenario: MockScenario): MockStore {
  if (!singleton || singleton.scenario !== scenario) {
    singleton = new MockStore(scenario)
  }
  return singleton
}
