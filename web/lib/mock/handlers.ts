/**
 * MSW request handlers implementing the FR-004 API contract against the
 * in-memory mock store. This is the entire mock surface — the rest of the
 * app only ever calls `fetch('/api/...')` via `lib/api/client.ts` and has
 * no idea this file exists.
 */
import { http, HttpResponse } from "msw"
import type { ActionType, FeedbackLabel, FeedQueryState } from "@/lib/contract/types"
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
  http.get("/api/feed/filter-metadata", ({ request }) => {
    if (!requireAuth(request)) return unauthorized()
    return HttpResponse.json(store().feedFilterMetadata())
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
