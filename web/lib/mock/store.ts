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
  Facet,
  FacetsResponse,
  FacetValueState,
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
      is_default?: boolean
    }
  ): SavedView | null {
    const view = this.savedViews.find((v) => v.id === viewId)
    if (!view) return null
    if (body.name !== undefined) view.name = body.name
    if (body.facets !== undefined) view.facets = body.facets
    if (body.search_query !== undefined) view.search_query = body.search_query
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
    activity?: string
    feedback?: string
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
    if (filters.activity && filters.activity !== "any") {
      items = items.filter((o) => filters.activity === "has_feedback" ? o.feedback_label !== null : filters.activity === "any" ? (o.action_history.length > 0 || o.feedback_history.length > 0) : filters.activity === "to_review" ? o.action_state === null : filters.activity === "applied" ? o.action_state === "submitted" : o.action_state === filters.activity)
    }
    if (filters.feedback) {
      items = items.filter((o) => o.feedback_label === filters.feedback)
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

  submitAction(id: string, type: ActionType, until: string | null) {
    const o = this.opportunities.get(id)
    if (!o) return null

    if (type === "clear") {
      o.action_state = null
      return {
        opportunity_id: id,
        action_state: null,
        action_id: null,
        until: null,
        created_at: new Date().toISOString(),
      }
    }

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
