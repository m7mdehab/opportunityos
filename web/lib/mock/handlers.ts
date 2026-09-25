/**
 * MSW request handlers implementing the FR-004 API contract against the
 * in-memory mock store. This is the entire mock surface — the rest of the
 * app only ever calls `fetch('/api/...')` via `lib/api/client.ts` and has
 * no idea this file exists.
 */
import { http, HttpResponse } from "msw"
import type { ActionType, ApplicationStage, FeedbackLabel, FeedQueryState, TrackerBucket, TrackerFollowUpBucket } from "@/lib/contract/types"
import { getStore } from "@/lib/mock/store"
import { resolveScenario } from "@/lib/mock/scenario"

const FEEDBACK_LABELS: FeedbackLabel[] = [
  "good_match",
  "bad_match",
  "eligibility_wrong",
  "seniority_wrong",
  "irrelevant_role",
  "source_quality_issue",
  "duplicate_issue",
  "review_required",
]

const ACTION_TYPES: ActionType[] = ["save", "mark_applied", "reject", "dismiss", "snooze", "set_stage"]

function store() {
  return getStore(resolveScenario())
}

function requireAuth(request: Request): boolean {
  return store().authenticated || request.headers.get("x-mock-bypass-auth") === "1"
}

const unauthorized = () =>
  HttpResponse.json({ detail: "not authenticated" }, { status: 401 })

export const handlers = [
  // ---- auth ----
  http.post("/api/auth/login", async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      password?: string
    }
    const result = store().login(body.password ?? "")
    if (result.ok) {
      return HttpResponse.json({ authenticated: true })
    }
    if (result.status === 429) {
      return HttpResponse.json(
        { detail: "too many attempts", retry_after_seconds: 30 },
        { status: 429 }
      )
    }
    return HttpResponse.json({ detail: "invalid credentials" }, { status: 401 })
  }),

  http.post("/api/auth/logout", () => {
    store().logout()
    return HttpResponse.json({ authenticated: false })
  }),

  http.get("/api/auth/me", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json({ authenticated: true })
  }),

  // ---- opportunities ----
  http.get("/api/feed/filter-metadata", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json(store().feedFilterMetadata())
  }),

  http.get("/api/tracker", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    const url = new URL(request.url)
    const bucket = url.searchParams.get("bucket") ?? "all"
    if (!["saved", "applied", "rejected", "all"].includes(bucket)) {
      return HttpResponse.json({ detail: "unknown tracker bucket" }, { status: 422 })
    }
    return HttpResponse.json(store().listTracker(
      bucket as TrackerBucket,
      Number(url.searchParams.get("page") ?? "1"),
      Number(url.searchParams.get("page_size") ?? "25")
    ))
  }),

  http.get("/api/tracker/follow-ups", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    const url = new URL(request.url)
    const bucket = url.searchParams.get("bucket") ?? "due_today"
    const page = Number(url.searchParams.get("page") ?? "1")
    const pageSize = Number(url.searchParams.get("page_size") ?? "25")
    if (!(["due_today", "overdue", "upcoming"] as string[]).includes(bucket)) {
      return HttpResponse.json({ detail: "unknown follow-up bucket" }, { status: 422 })
    }
    if (!Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1) {
      return HttpResponse.json({ detail: "page and page_size must be positive integers" }, { status: 422 })
    }
    const result = store().listTrackerFollowUps(bucket as TrackerFollowUpBucket, page, pageSize)
    if (result === "invalid_bucket") return HttpResponse.json({ detail: "unknown follow-up bucket" }, { status: 422 })
    return HttpResponse.json(result)
  }),

  http.get("/api/tracker/interviews", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    const url = new URL(request.url)
    const bucket = url.searchParams.get("bucket") ?? "upcoming"
    const page = Number(url.searchParams.get("page") ?? "1")
    const pageSize = Number(url.searchParams.get("page_size") ?? "25")
    if (!Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1) {
      return HttpResponse.json({ detail: "page and page_size must be positive integers" }, { status: 422 })
    }
    const result = store().listTrackerInterviews(bucket, page, pageSize)
    if (result === "invalid_bucket") return HttpResponse.json({ detail: "unknown interview bucket" }, { status: 422 })
    return HttpResponse.json(result)
  }),

  http.get("/api/opportunities", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    const url = new URL(request.url)
    const track = url.searchParams.get("track") ?? undefined
    const decision = url.searchParams.get("decision") ?? undefined
    const numberParam = (key: string) => {
      const raw = url.searchParams.get(key)
      return raw === null || raw === "" ? undefined : Number(raw)
    }
    const q = url.searchParams.get("q") ?? undefined
    const page = Number(url.searchParams.get("page") ?? "1")
    const pageSize = Number(url.searchParams.get("page_size") ?? "25")
    const includeHidden = url.searchParams.get("include_hidden") === "true"

    const result = store().listOpportunities({
      track,
      decision,
      min_score: numberParam("min_score"),
      min_fit_score: numberParam("min_fit_score"),
      max_fit_score: numberParam("max_fit_score"),
      min_preference_score: numberParam("min_preference_score"),
      max_preference_score: numberParam("max_preference_score"),
      min_confidence_score: numberParam("min_confidence_score"),
      max_confidence_score: numberParam("max_confidence_score"),
      min_priority_score: numberParam("min_priority_score"),
      max_priority_score: numberParam("max_priority_score"),
      posted_from: url.searchParams.get("posted_from") ?? undefined,
      posted_to: url.searchParams.get("posted_to") ?? undefined,
      work_mode: url.searchParams.getAll("work_mode"),
      location_country: url.searchParams.getAll("location_country"),
      location_city: url.searchParams.getAll("location_city"),
      remote_scope: url.searchParams.getAll("remote_scope"),
      employment_type: url.searchParams.getAll("employment_type"),
      seniority_level: url.searchParams.getAll("seniority_level"),
      target_tier: url.searchParams.getAll("target_tier"),
      title_family: url.searchParams.getAll("title_family"),
      source_id: url.searchParams.getAll("source_id"),
      sort_by: (url.searchParams.get("sort_by") ?? "recommended") as "recommended" | "fit_desc" | "fit_asc" | "newest_posted" | "oldest_posted" | "remote_first",
      q,
      page,
      page_size: pageSize,
      include_hidden: includeHidden,
    })
    return HttpResponse.json(result)
  }),

  http.get("/api/opportunities/:id", ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const detail = store().getDetail(String(params.id))
    if (!detail) {
      return HttpResponse.json(
        { detail: "opportunity not found" },
        { status: 404 }
      )
    }
    return HttpResponse.json(detail)
  }),

  http.get("/api/opportunities/:id/follow-ups", ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const url = new URL(request.url)
    const page = Number(url.searchParams.get("page") ?? "1")
    const pageSize = Number(url.searchParams.get("page_size") ?? "50")
    if (!Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1) {
      return HttpResponse.json({ detail: "page and page_size must be positive integers" }, { status: 422 })
    }
    const result = store().listOpportunityTrackerFollowUps(String(params.id), page, pageSize)
    if (result === "not_found") return HttpResponse.json({ detail: "opportunity not found" }, { status: 404 })
    if (result === "not_tracked") return HttpResponse.json({ detail: "follow-ups are available only for Saved and Applied jobs" }, { status: 409 })
    return HttpResponse.json(result)
  }),

  http.get("/api/opportunities/:id/interviews", ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const url = new URL(request.url)
    const page = Number(url.searchParams.get("page") ?? "1")
    const pageSize = Number(url.searchParams.get("page_size") ?? "50")
    if (!Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1) {
      return HttpResponse.json({ detail: "page and page_size must be positive integers" }, { status: 422 })
    }
    const result = store().listOpportunityTrackerInterviews(String(params.id), page, pageSize)
    if (result === "not_found") return HttpResponse.json({ detail: "opportunity not found" }, { status: 404 })
    if (result === "not_tracked") return HttpResponse.json({ detail: "interviews are available only for Applied jobs" }, { status: 409 })
    return HttpResponse.json(result)
  }),

  http.post("/api/opportunities/:id/interviews", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const idempotencyKey = body.idempotency_key
    if (typeof idempotencyKey !== "string" || !idempotencyKey.trim() || idempotencyKey.length > 128) {
      return HttpResponse.json({ detail: "idempotency_key is required and must be at most 128 characters" }, { status: 422 })
    }
    const fields = { ...body }
    delete fields.idempotency_key
    const result = store().createTrackerInterview(String(params.id), fields, idempotencyKey)
    if (result === "not_found") return HttpResponse.json({ detail: "opportunity not found" }, { status: 404 })
    if (result === "not_tracked") return HttpResponse.json({ detail: "interviews are available only for Applied jobs" }, { status: 409 })
    if (result === "invalid_idempotency_key") return HttpResponse.json({ detail: "idempotency_key is required and must be at most 128 characters" }, { status: 422 })
    if (result === "idempotency_conflict") return HttpResponse.json({ detail: "idempotency_key was already used for another interview operation" }, { status: 409 })
    if (result === "invalid_datetime") return HttpResponse.json({ detail: "scheduled_at must be an ISO 8601 datetime with an explicit UTC offset" }, { status: 422 })
    if (result === "invalid_enum") return HttpResponse.json({ detail: "unknown interview type, format, or outcome" }, { status: 422 })
    if (result === "invalid_text") return HttpResponse.json({ detail: "interview text exceeds its allowed length or has an invalid type" }, { status: 422 })
    if (result === "invalid_field") return HttpResponse.json({ detail: "unknown interview field" }, { status: 422 })
    return HttpResponse.json(result)
  }),

  http.patch("/api/opportunities/:id/interviews/:interviewId", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const idempotencyKey = body.idempotency_key
    if (typeof idempotencyKey !== "string" || !idempotencyKey.trim() || idempotencyKey.length > 128) {
      return HttpResponse.json({ detail: "idempotency_key is required and must be at most 128 characters" }, { status: 422 })
    }
    const fields = { ...body }
    delete fields.idempotency_key
    const result = store().updateTrackerInterview(String(params.id), String(params.interviewId), fields, idempotencyKey)
    if (result === "not_found") return HttpResponse.json({ detail: "interview or opportunity not found" }, { status: 404 })
    if (result === "not_tracked") return HttpResponse.json({ detail: "interviews are available only for Applied jobs" }, { status: 409 })
    if (result === "invalid_idempotency_key") return HttpResponse.json({ detail: "idempotency_key is required and must be at most 128 characters" }, { status: 422 })
    if (result === "idempotency_conflict") return HttpResponse.json({ detail: "idempotency_key was already used for another interview operation" }, { status: 409 })
    if (result === "invalid_update") return HttpResponse.json({ detail: "provide at least one interview field" }, { status: 422 })
    if (result === "invalid_datetime") return HttpResponse.json({ detail: "scheduled_at must be an ISO 8601 datetime with an explicit UTC offset" }, { status: 422 })
    if (result === "invalid_enum") return HttpResponse.json({ detail: "unknown interview type, format, or outcome" }, { status: 422 })
    if (result === "invalid_text") return HttpResponse.json({ detail: "interview text exceeds its allowed length or has an invalid type" }, { status: 422 })
    if (result === "invalid_field") return HttpResponse.json({ detail: "unknown interview field" }, { status: 422 })
    return HttpResponse.json(result)
  }),

  http.post("/api/opportunities/:id/follow-ups", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const body = (await request.json().catch(() => ({}))) as {
      due_date?: unknown
      note_text?: unknown
      idempotency_key?: unknown
    }
    if (typeof body.due_date !== "string") return HttpResponse.json({ detail: "due_date must use YYYY-MM-DD" }, { status: 422 })
    if (body.note_text !== undefined && body.note_text !== null && typeof body.note_text !== "string") {
      return HttpResponse.json({ detail: "note_text must be a string or null" }, { status: 422 })
    }
    if (typeof body.idempotency_key !== "string" || !body.idempotency_key.trim() || body.idempotency_key.length > 128) {
      return HttpResponse.json({ detail: "idempotency_key is required and must be at most 128 characters" }, { status: 422 })
    }
    const result = store().createTrackerFollowUp(
      String(params.id), body.due_date, body.note_text as string | null | undefined, body.idempotency_key
    )
    if (result === "not_found") return HttpResponse.json({ detail: "opportunity not found" }, { status: 404 })
    if (result === "not_tracked") return HttpResponse.json({ detail: "follow-ups are available only for Saved and Applied jobs" }, { status: 409 })
    if (result === "invalid_due_date") return HttpResponse.json({ detail: "due_date must use YYYY-MM-DD" }, { status: 422 })
    if (result === "invalid_note_text") return HttpResponse.json({ detail: "note_text cannot exceed 4000 characters" }, { status: 422 })
    if (result === "invalid_idempotency_key") return HttpResponse.json({ detail: "idempotency_key is required and must be at most 128 characters" }, { status: 422 })
    if (result === "idempotency_conflict") return HttpResponse.json({ detail: "idempotency_key was already used for another follow-up operation" }, { status: 409 })
    return HttpResponse.json(result)
  }),

  http.patch("/api/opportunities/:id/follow-ups/:followUpId", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const body = (await request.json().catch(() => ({}))) as {
      due_date?: unknown
      note_text?: unknown
      completed?: unknown
      idempotency_key?: unknown
    }
    const hasDueDate = "due_date" in body
    const hasNote = "note_text" in body
    const hasCompletion = "completed" in body
    if (hasDueDate && typeof body.due_date !== "string") return HttpResponse.json({ detail: "due_date must use YYYY-MM-DD" }, { status: 422 })
    if (hasNote && body.note_text !== null && typeof body.note_text !== "string") {
      return HttpResponse.json({ detail: "note_text must be a string or null" }, { status: 422 })
    }
    if (hasCompletion && typeof body.completed !== "boolean") return HttpResponse.json({ detail: "completed must be a boolean" }, { status: 422 })
    if (typeof body.idempotency_key !== "string" || !body.idempotency_key.trim() || body.idempotency_key.length > 128) {
      return HttpResponse.json({ detail: "idempotency_key is required and must be at most 128 characters" }, { status: 422 })
    }
    const result = store().updateTrackerFollowUp(
      String(params.id),
      String(params.followUpId),
      body.idempotency_key,
      {
        ...(hasDueDate ? { due_date: body.due_date as string } : {}),
        ...(hasNote ? { note_text: body.note_text as string | null, note_text_provided: true } : {}),
        ...(hasCompletion ? { completed: body.completed as boolean } : {}),
      },
    )
    if (result === "not_found") return HttpResponse.json({ detail: "follow-up or opportunity not found" }, { status: 404 })
    if (result === "not_tracked") return HttpResponse.json({ detail: "follow-ups are available only for Saved and Applied jobs" }, { status: 409 })
    if (result === "invalid_due_date") return HttpResponse.json({ detail: "due_date must use YYYY-MM-DD" }, { status: 422 })
    if (result === "invalid_note_text") return HttpResponse.json({ detail: "note_text cannot exceed 4000 characters" }, { status: 422 })
    if (result === "invalid_idempotency_key") return HttpResponse.json({ detail: "idempotency_key is required and must be at most 128 characters" }, { status: 422 })
    if (result === "invalid_update") return HttpResponse.json({ detail: "provide due_date/note_text changes or completed state" }, { status: 422 })
    if (result === "idempotency_conflict") return HttpResponse.json({ detail: "idempotency_key was already used for another follow-up operation" }, { status: 409 })
    return HttpResponse.json(result)
  }),

  http.get("/api/opportunities/:id/tracker-notes", ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const url = new URL(request.url)
    const page = Number(url.searchParams.get("page") ?? "1")
    const pageSize = Number(url.searchParams.get("page_size") ?? "50")
    if (!Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1) {
      return HttpResponse.json({ detail: "page and page_size must be positive integers" }, { status: 422 })
    }
    const result = store().listTrackerNotes(String(params.id), page, pageSize)
    if (result === "not_found") {
      return HttpResponse.json({ detail: "opportunity not found" }, { status: 404 })
    }
    if (result === "not_tracked") {
      return HttpResponse.json({ detail: "opportunity is not an application-tracked item" }, { status: 409 })
    }
    return HttpResponse.json(result)
  }),

  http.post("/api/opportunities/:id/tracker-notes", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const body = (await request.json().catch(() => ({}))) as {
      note_text?: unknown
      idempotency_key?: unknown
    }
    const noteText = typeof body.note_text === "string" ? body.note_text.trim() : ""
    if (!noteText || noteText.length > 4000) {
      return HttpResponse.json({ detail: "note_text must contain 1 to 4000 characters" }, { status: 422 })
    }
    if (typeof body.idempotency_key !== "string" || !body.idempotency_key.trim() || body.idempotency_key.length > 128) {
      return HttpResponse.json({ detail: "idempotency_key is required and must be at most 128 characters" }, { status: 422 })
    }
    const result = store().createTrackerNote(String(params.id), noteText, body.idempotency_key)
    if (result === "not_found") return HttpResponse.json({ detail: "opportunity not found" }, { status: 404 })
    if (result === "not_tracked") return HttpResponse.json({ detail: "opportunity is not an application-tracked item" }, { status: 409 })
    if (result === "idempotency_conflict") return HttpResponse.json({ detail: "idempotency_key was already used for another note operation" }, { status: 409 })
    return HttpResponse.json(result)
  }),

  http.patch("/api/opportunities/:id/tracker-notes/:noteId", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const body = (await request.json().catch(() => ({}))) as {
      note_text?: unknown
      archived?: unknown
      idempotency_key?: unknown
    }
    const hasText = body.note_text !== undefined
    const archiving = body.archived === true
    if (body.archived === false || hasText === archiving) {
      return HttpResponse.json({ detail: "provide note_text or archived=true" }, { status: 422 })
    }
    const noteText = typeof body.note_text === "string" ? body.note_text.trim() : ""
    if (hasText && (!noteText || noteText.length > 4000)) {
      return HttpResponse.json({ detail: "note_text must contain 1 to 4000 characters" }, { status: 422 })
    }
    if (typeof body.idempotency_key !== "string" || !body.idempotency_key.trim() || body.idempotency_key.length > 128) {
      return HttpResponse.json({ detail: "idempotency_key is required and must be at most 128 characters" }, { status: 422 })
    }
    const result = store().updateTrackerNote(
      String(params.id),
      String(params.noteId),
      body.idempotency_key,
      archiving ? { archived: true } : { note_text: noteText },
    )
    if (result === "not_found") return HttpResponse.json({ detail: "note or opportunity not found" }, { status: 404 })
    if (result === "not_tracked") return HttpResponse.json({ detail: "opportunity is not an application-tracked item" }, { status: 409 })
    if (result === "idempotency_conflict") return HttpResponse.json({ detail: "idempotency_key was already used for another note operation" }, { status: 409 })
    if (result === "archived") return HttpResponse.json({ detail: "archived notes cannot be edited" }, { status: 409 })
    return HttpResponse.json(result)
  }),

  // ---- artifacts ----
  http.get("/api/opportunities/:id/artifacts/cv.docx", ({ request, params }) =>
    artifactResponse(request, String(params.id), "cv")
  ),
  http.get(
    "/api/opportunities/:id/artifacts/cover-letter.docx",
    ({ request, params }) =>
      artifactResponse(request, String(params.id), "cover-letter")
  ),
  // BRIEF-FR-006 D2 — inline PDF preview + download variant.
  http.get("/api/opportunities/:id/artifacts/cv.pdf", ({ request, params }) =>
    artifactPdfResponse(request, String(params.id), "cv")
  ),
  http.get("/api/opportunities/:id/artifacts/cv-final.pdf", ({ request, params }) =>
    artifactPdfResponse(request, String(params.id), "cv")
  ),
  http.get(
    "/api/opportunities/:id/artifacts/cover-letter.pdf",
    ({ request, params }) =>
      artifactPdfResponse(request, String(params.id), "cover-letter")
  ),
  // D1's "what was left out and why" data, as JSON for the drawer's
  // artifacts panel.
  http.get(
    "/api/opportunities/:id/artifacts/:kind/omitted",
    ({ request, params }) =>
      omittedItemsResponse(
        request,
        String(params.id),
        params.kind as "cv" | "cover-letter"
      )
  ),

  // ---- feedback / actions ----
  http.post("/api/opportunities/:id/feedback", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const id = String(params.id)
    const body = (await request.json().catch(() => ({}))) as {
      label?: string
      note?: string | null
    }
    if (!body.label || !FEEDBACK_LABELS.includes(body.label as FeedbackLabel)) {
      return HttpResponse.json(
        { detail: "unknown feedback label", allowed: FEEDBACK_LABELS },
        { status: 422 }
      )
    }
    const entry = store().submitFeedback(
      id,
      body.label as FeedbackLabel,
      body.note ?? null
    )
    if (!entry) {
      return HttpResponse.json(
        { detail: "opportunity not found" },
        { status: 404 }
      )
    }
    return HttpResponse.json({ opportunity_id: id, ...entry })
  }),

  http.post("/api/opportunities/:id/actions", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const id = String(params.id)
    const body = (await request.json().catch(() => ({}))) as {
      type?: string
      until?: string | null
      stage?: string | null
    }
    if (!body.type || !ACTION_TYPES.includes(body.type as ActionType)) {
      return HttpResponse.json({ detail: "unknown action type" }, { status: 422 })
    }
    if (body.type === "snooze" && !body.until) {
      return HttpResponse.json(
        { detail: "snooze requires a future 'until' date" },
        { status: 422 }
      )
    }
    const applicationStages: ApplicationStage[] = [
      "applied", "recruiter_screen", "assessment", "interviewing",
      "final_interview", "offer", "accepted", "rejected_by_employer",
      "withdrawn", "no_response",
    ]
    if (body.type === "set_stage" && (!body.stage || !applicationStages.includes(body.stage as ApplicationStage))) {
      return HttpResponse.json({ detail: "set_stage requires a valid application stage" }, { status: 422 })
    }
    if (body.type !== "set_stage" && body.stage) {
      return HttpResponse.json({ detail: "stage is only valid for set_stage" }, { status: 422 })
    }
    const mockStore = store()
    const result = mockStore.submitAction(
      id,
      body.type as ActionType,
      body.until ?? null,
      body.stage
    )
    if (!result) {
      return HttpResponse.json(
        { detail: body.type === "set_stage" ? "invalid application stage transition" : "opportunity not found" },
        { status: body.type === "set_stage" && mockStore.opportunities.has(id) ? 409 : 404 }
      )
    }
    return HttpResponse.json(result)
  }),

  // ---- filters (D3) ----
  http.get("/api/filters", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json(store().listFilters())
  }),

  http.put("/api/filters/:filter_id", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const filterId = String(params.filter_id)
    const body = (await request.json().catch(() => ({}))) as {
      enabled?: boolean
      mode?: string
      params?: Record<string, unknown>
    }
    const result = store().updateFilter(filterId, body)
    if (result === "not_found") {
      return HttpResponse.json({ detail: "unknown filter_id" }, { status: 404 })
    }
    if (result === "invalid_mode") {
      return HttpResponse.json(
        { detail: "invalid mode", allowed: ["hide", "rank_only", "label_only"] },
        { status: 422 }
      )
    }
    if (result === "invalid_params") {
      return HttpResponse.json(
        { detail: `${filterId}: params out of range` },
        { status: 422 }
      )
    }
    return HttpResponse.json(result)
  }),

  // ---- facets (C1) ----
  http.get("/api/facets", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json(store().listFacets())
  }),

  http.put("/api/facets/:facet_id", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const facetId = String(params.facet_id)
    const body = (await request.json().catch(() => ({}))) as {
      include?: string[]
      exclude?: string[]
    }
    const result = store().updateFacet(facetId, body)
    if (result === "not_found") {
      return HttpResponse.json({ detail: "unknown facet_id" }, { status: 404 })
    }
    if (result === "unavailable") {
      return HttpResponse.json(
        { detail: "this facet has no data source yet" },
        { status: 422 }
      )
    }
    return HttpResponse.json(result)
  }),

  // ---- saved views (C1) ----
  http.get("/api/saved-views", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json(store().listSavedViews())
  }),

  http.post("/api/saved-views", async ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    const body = (await request.json().catch(() => ({}))) as {
      name?: string
      facets?: Record<string, { include: string[]; exclude: string[] }>
      search_query?: string | null
      feed_query?: FeedQueryState
      is_default?: boolean
    }
    return HttpResponse.json(
      store().createSavedView({
        name: body.name ?? "",
        facets: body.facets ?? {},
        search_query: body.search_query ?? null,
        feed_query: body.feed_query,
        is_default: body.is_default ?? false,
      })
    )
  }),

  http.put("/api/saved-views/:view_id", async ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const body = (await request.json().catch(() => ({}))) as {
      name?: string
      facets?: Record<string, { include: string[]; exclude: string[] }>
      search_query?: string | null
      feed_query?: FeedQueryState
      is_default?: boolean
    }
    const result = store().updateSavedView(String(params.view_id), body)
    if (!result) {
      return HttpResponse.json({ detail: "unknown saved view" }, { status: 404 })
    }
    return HttpResponse.json(result)
  }),

  http.delete("/api/saved-views/:view_id", ({ request, params }) => {
    if (!requireAuth(request)) return unauthorized()
    const ok = store().deleteSavedView(String(params.view_id))
    if (!ok) {
      return HttpResponse.json({ detail: "unknown saved view" }, { status: 404 })
    }
    return HttpResponse.json({ id: String(params.view_id), status: "deleted" })
  }),

  // ---- hidden reasons (C4) ----
  http.get("/api/hidden-reasons", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json(store().hiddenReasonsAudit())
  }),

  http.post("/api/hidden-reasons/unhide", async ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    const body = (await request.json().catch(() => ({}))) as { reason?: string }
    const ok = store().unhideByReason(body.reason ?? "")
    if (!ok) {
      return HttpResponse.json({ detail: "unrecognised reason" }, { status: 404 })
    }
    return HttpResponse.json({ reason: body.reason, status: "unhidden" })
  }),

  // ---- dashboard ----
  http.get("/api/dashboard/daily", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    const url = new URL(request.url)
    const days = Number(url.searchParams.get("days") ?? "7")
    return HttpResponse.json(store().dashboard(days))
  }),

  // ---- sources / worker ----
  http.get("/api/sources/health", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json(store().sourcesHealth())
  }),

  http.post("/api/worker/poll-now", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json(store().pollNow())
  }),

  // ---- truth ----
  http.get("/api/truth/status", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json(store().truthStatus())
  }),
  http.post("/api/truth/reload", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json(store().truthReload())
  }),
]

function artifactResponse(
  request: Request,
  id: string,
  kind: "cv" | "cover-letter"
) {
  if (!requireAuth(request)) return unauthorized()
  const s = store()

  if (!s.truthStatus().loaded) {
    return HttpResponse.json(
      { detail: "no truth pack loaded", reason: "no founder truth pack is currently loaded" },
      { status: 412 }
    )
  }

  if (s.artifactClaimsRejected(id)) {
    return HttpResponse.json(
      {
        detail: "claim validation failed",
        findings: [
          {
            claim: "5+ years of directly relevant field experience",
            assertion_type: "experience_duration",
            rejection_reasons: [
              "no truth pack evidence supports this duration for the target field",
            ],
          },
        ],
      },
      { status: 409 }
    )
  }

  const filename = `${kind}-${id}.docx`
  // A minimal synthetic binary payload — never real generated content.
  const body = new TextEncoder().encode(
    `SYNTHETIC MOCK DOCX PLACEHOLDER (${kind}, ${id})`
  )
  return new HttpResponse(body, {
    status: 200,
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  })
}

const REJECTED_FINDINGS = [
  {
    claim: "5+ years of directly relevant field experience",
    assertion_type: "experience_duration",
    rejection_reasons: [
      "no truth pack evidence supports this duration for the target field",
    ],
  },
]

/** A tiny, syntactically valid one-page PDF (Chromium's built-in viewer can
 * render it) whose page text embeds `label`, so different templates
 * produce genuinely different response bytes -- not merely a different
 * request URL (BRIEF-FR-006 D2.6: "assert the rendered result, not the
 * absence of an error"). */
function minimalPdfBytes(label: string): Uint8Array {
  const content = `BT /F1 18 Tf 50 700 Td (OpportunityOS mock: ${label}) Tj ET`
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
  ]
  let body = "%PDF-1.4\n"
  const offsets: number[] = []
  objects.forEach((obj, i) => {
    offsets.push(body.length)
    body += `${i + 1} 0 obj\n${obj}\nendobj\n`
  })
  const xrefStart = body.length
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  for (const off of offsets) {
    body += `${off.toString().padStart(10, "0")} 00000 n \n`
  }
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF`
  return new TextEncoder().encode(body)
}

function artifactPdfResponse(
  request: Request,
  id: string,
  kind: "cv" | "cover-letter"
) {
  if (!requireAuth(request)) return unauthorized()
  const s = store()

  if (!s.truthStatus().loaded) {
    return HttpResponse.json(
      {
        detail: "no truth pack loaded",
        reason: "no founder truth pack is currently loaded",
      },
      { status: 412 }
    )
  }

  if (s.artifactClaimsRejected(id)) {
    return HttpResponse.json(
      { detail: "claim validation failed", findings: REJECTED_FINDINGS },
      { status: 409 }
    )
  }

  const url = new URL(request.url)
  const template = url.searchParams.get("template") ?? "classic"
  const download = url.searchParams.get("download") === "true"
  const filename = `${kind}-${id}.pdf`
  const body = minimalPdfBytes(`${kind}, ${id}, ${template}`)
  return new HttpResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `${download ? "attachment" : "inline"}; filename="${filename}"`,
    },
  })
}

function omittedItemsResponse(
  request: Request,
  id: string,
  kind: "cv" | "cover-letter"
) {
  if (!requireAuth(request)) return unauthorized()
  const s = store()

  if (!s.truthStatus().loaded) {
    return HttpResponse.json(
      {
        detail: "no truth pack loaded",
        reason: "no founder truth pack is currently loaded",
      },
      { status: 412 }
    )
  }

  if (s.artifactClaimsRejected(id)) {
    return HttpResponse.json(
      { detail: "claim validation failed", findings: REJECTED_FINDINGS },
      { status: 409 }
    )
  }

  const url = new URL(request.url)
  const template = url.searchParams.get("template") ?? "classic"
  return HttpResponse.json({
    template,
    omitted_items: [
      {
        section_id: kind === "cv" ? "skills" : "summary",
        text:
          kind === "cv"
            ? "Rust (advanced)"
            : "A sentence about a certification not in the truth pack",
        reason:
          "Not enough truth-pack evidence to support this at the strength the source posting implies; kept out rather than overstated.",
        claim_id: `claim-${kind}-omitted-1`,
      },
    ],
  })
}
