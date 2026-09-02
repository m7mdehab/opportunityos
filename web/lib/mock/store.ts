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
  FilterMode,
  FiltersResponse,
  FounderFilter,
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

  /** D3 founder filter settings, one entry per `FOUNDER_FILTER_DEFINITIONS`
   * row, seeded from that table's defaults and mutated by `PUT
   * /api/filters/{filter_id}`. */
  filterSettings: Map<string, FilterSetting>

  constructor(scenario: MockScenario) {
    this.scenario = scenario
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
   * the contract (§4): it contributes to neither list. */
  private matchingFilterIds(o: SeedOpportunity): {
    hidden_by: string[]
    flagged_by: string[]
    rankDemoted: boolean
  } {
    const hidden_by: string[] = []
    const flagged_by: string[] = []
    let rankDemoted = false
    for (const def of FOUNDER_FILTER_DEFINITIONS) {
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
    return { hidden_by, flagged_by, rankDemoted }
  }

  private hiddenCount(items: SeedOpportunity[]): number {
    return items.filter((o) => this.matchingFilterIds(o).hidden_by.length > 0)
      .length
  }

  listOpportunities(filters: {
    track?: string
    decision?: string
    min_score?: number
    q?: string
    page?: number
    page_size?: number
    /** Default `false`. `true` includes items an enabled `hide`-mode
     * filter matched, with `hidden_by` populated on them. */
    include_hidden?: boolean
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
    visible.sort((a, b) => {
      const ao = a.o
      const bo = b.o
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
          // drawer can show what enabling a disabled filter would do.
          affected_count: items.filter((o) =>
            evaluateFounderFilter(def.filter_id, o, setting.params)
          ).length,
          description: def.description,
        }
      }),
    }
  }

  /** Returns the updated filter, or a string error tag the handler maps to
   * the contract's 404 / 422 responses. */
  updateFilter(
    filterId: string,
    body: { enabled?: boolean; mode?: string; params?: Record<string, unknown> }
  ): FounderFilter | "not_found" | "invalid_mode" {
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
      affected_count: items.filter((o) =>
        evaluateFounderFilter(filterId, o, setting.params)
      ).length,
      description: def.description,
    }
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
  }
}

let singleton: MockStore | null = null

export function getStore(scenario: MockScenario): MockStore {
  if (!singleton || singleton.scenario !== scenario) {
    singleton = new MockStore(scenario)
  }
  return singleton
}
