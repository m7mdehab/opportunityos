/**
 * MSW request handlers implementing the FR-004 API contract against the
 * in-memory mock store. This is the entire mock surface — the rest of the
 * app only ever calls `fetch('/api/...')` via `lib/api/client.ts` and has
 * no idea this file exists.
 */
import { http, HttpResponse } from "msw"
import type { ActionType, FeedbackLabel } from "@/lib/contract/types"
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

const ACTION_TYPES: ActionType[] = ["mark_applied", "dismiss", "snooze"]

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
  http.get("/api/opportunities", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    const url = new URL(request.url)
    const track = url.searchParams.get("track") ?? undefined
    const decision = url.searchParams.get("decision") ?? undefined
    const minScoreRaw = url.searchParams.get("min_score")
    const q = url.searchParams.get("q") ?? undefined
    const page = Number(url.searchParams.get("page") ?? "1")
    const pageSize = Number(url.searchParams.get("page_size") ?? "25")
    const includeHidden = url.searchParams.get("include_hidden") === "true"

    const result = store().listOpportunities({
      track,
      decision,
      min_score: minScoreRaw ? Number(minScoreRaw) : undefined,
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

  // ---- artifacts ----
  http.get("/api/opportunities/:id/artifacts/cv.docx", ({ request, params }) =>
    artifactResponse(request, String(params.id), "cv")
  ),
  http.get(
    "/api/opportunities/:id/artifacts/cover-letter.docx",
    ({ request, params }) =>
      artifactResponse(request, String(params.id), "cover-letter")
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
    const result = store().submitAction(
      id,
      body.type as ActionType,
      body.until ?? null
    )
    if (!result) {
      return HttpResponse.json(
        { detail: "opportunity not found" },
        { status: 404 }
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
