/**
 * Thin fetch wrapper hitting same-origin `/api/*`. This is the only place
 * that talks to the network. In dev, `next.config.ts` rewrites `/api/*` to
 * the real FastAPI service at `localhost:8000`; in the mock phase, MSW
 * intercepts these same relative `fetch()` calls at the network boundary
 * (see `lib/mock/`). This file never branches on whether the mock is
 * active — that is the whole point of keeping the mock at the fetch
 * boundary.
 */
import { ApiError } from "@/lib/contract/types"
import type {
  ActionResponse,
  ActionType,
  ArtifactTemplateId,
  AuthenticatedResponse,
  DashboardResponse,
  FacetsResponse,
  FacetUpdateRequest,
  Facet,
  FeedbackLabel,
  FeedbackResponse,
  FeedFilterMetadataResponse,
  FilterUpdateRequest,
  FiltersResponse,
  FounderFilter,
  HiddenReasonsResponse,
  OmittedItemsResponse,
  OpportunityDetail,
  OpportunityListResponse,
  PollNowResponse,
  SavedView,
  SavedViewCreateRequest,
  SavedViewsResponse,
  SavedViewUpdateRequest,
  SourcesHealthResponse,
  TruthStatusResponse,
  TutoringPlatform,
  TutoringPlatformsResponse,
  TutoringProfileMaterialResponse,
  TutoringStatus,
  UnhideByReasonResponse,
} from "@/lib/contract/types"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase()
  const mockSession = process.env.NEXT_PUBLIC_USE_MOCK_API === "1" &&
    typeof window !== "undefined" &&
    window.localStorage.getItem("opportunityos.mock.authenticated") === "1"
  const res = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(method !== "GET" && method !== "HEAD" && method !== "OPTIONS"
        ? { "X-OpportunityOS-CSRF": "1" }
        : {}),
      ...(mockSession ? { "X-Mock-Bypass-Auth": "1" } : {}),
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  })

  if (res.status === 204) {
    return undefined as T
  }

  const contentType = res.headers.get("content-type") ?? ""
  const isJson = contentType.includes("application/json")
  const body = isJson ? await res.json().catch(() => null) : null

  if (!res.ok) {
    throw new ApiError(res.status, body)
  }

  return body as T
}

export const api = {
  auth: {
    login: async (password: string, email?: string) => {
      return request<AuthenticatedResponse>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ password, email }),
      })
    },
    logout: async () => {
      const result = await request<AuthenticatedResponse>("/api/auth/logout", { method: "POST" })
      if (process.env.NEXT_PUBLIC_USE_MOCK_API === "1" && typeof window !== "undefined") {
        window.localStorage.removeItem("opportunityos.mock.authenticated")
      }
      return result
    },
    logoutAll: () =>
      request<AuthenticatedResponse>("/api/auth/logout-all", { method: "POST" }),
    me: () => request<AuthenticatedResponse>("/api/auth/me"),
  },

  opportunities: {
    list: (params: {
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
      since?: string
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
      sort_by?: string
      q?: string
      page?: number
      page_size?: number
      /** Default `false`. When `true`, items hidden by an enabled
       * `hide`-mode filter are included in `items` (and `hidden_by` is
       * populated on them) instead of being omitted. */
      include_hidden?: boolean
    }) => {
      const search = new URLSearchParams()
      for (const [key, value] of Object.entries(params)) {
        if (Array.isArray(value)) {
          for (const item of value) {
            if (item !== "") search.append(key, String(item))
          }
        } else if (value !== undefined && value !== "" && value !== null && value !== false) {
          search.set(key, String(value))
        }
      }
      const qs = search.toString()
      return request<OpportunityListResponse>(
        `/api/opportunities${qs ? `?${qs}` : ""}`
      )
    },
    detail: (id: string) =>
      request<OpportunityDetail>(`/api/opportunities/${id}`),
    artifactUrl: (id: string, kind: "cv" | "cover-letter") =>
      kind === "cv"
        ? `/api/opportunities/${id}/artifacts/cv-final.pdf?download=true`
        : `/api/opportunities/${id}/artifacts/cover-letter.docx`,
    // BRIEF-FR-006 D2 — inline preview URL for the drawer's embedded PDF
    // viewer (`<embed src=...>`). No `download` param: inline is the
    // default per the deliverable text.
    artifactPdfUrl: (
      id: string,
      kind: "cv" | "cover-letter",
      template: ArtifactTemplateId = "classic"
    ) =>
      kind === "cv"
        ? `/api/opportunities/${id}/artifacts/cv-final.pdf`
        : `/api/opportunities/${id}/artifacts/cover-letter.pdf?template=${template}`,
    omittedItems: (
      id: string,
      kind: "cv" | "cover-letter",
      template: ArtifactTemplateId = "classic"
    ) =>
      request<OmittedItemsResponse>(
        `/api/opportunities/${id}/artifacts/${kind}/omitted?template=${template}`
      ),
    submitFeedback: (id: string, label: FeedbackLabel, note: string | null) =>
      request<FeedbackResponse>(`/api/opportunities/${id}/feedback`, {
        method: "POST",
        body: JSON.stringify({ label, note }),
      }),
    submitAction: (id: string, type: ActionType, until: string | null) =>
      request<ActionResponse>(`/api/opportunities/${id}/actions`, {
        method: "POST",
        body: JSON.stringify({ type, until }),
      }),
  },

  feedFilterMetadata: {
    get: () => request<FeedFilterMetadataResponse>("/api/feed/filter-metadata"),
  },

  dashboard: {
    daily: (days = 7) =>
      request<DashboardResponse>(`/api/dashboard/daily?days=${days}`),
  },

  filters: {
    list: () => request<FiltersResponse>("/api/filters"),
    update: (filterId: string, body: FilterUpdateRequest) =>
      request<FounderFilter>(`/api/filters/${filterId}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
  },

  // C1 — the 15-attribute generic facet surface. Separate control set from
  // `filters` above: `include` / `exclude` / `off` per value, never
  // `hide` / `rank_only` / `label_only`.
  facets: {
    list: () => request<FacetsResponse>("/api/facets"),
    update: (facetId: string, body: FacetUpdateRequest) =>
      request<Pick<Facet, "facet_id" | "include" | "exclude"> & { mode: string }>(
        `/api/facets/${facetId}`,
        { method: "PUT", body: JSON.stringify(body) }
      ),
  },

  savedViews: {
    list: () => request<SavedViewsResponse>("/api/saved-views"),
    create: (body: SavedViewCreateRequest) =>
      request<SavedView>("/api/saved-views", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    update: (viewId: string, body: SavedViewUpdateRequest) =>
      request<SavedView>(`/api/saved-views/${viewId}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    delete: (viewId: string) =>
      request<{ id: string; status: string }>(`/api/saved-views/${viewId}`, {
        method: "DELETE",
      }),
  },

  // C4 — the audit table the dashboard's HIDDEN number links to.
  hiddenReasons: {
    list: () => request<HiddenReasonsResponse>("/api/hidden-reasons"),
    unhide: (reason: string) =>
      request<UnhideByReasonResponse>("/api/hidden-reasons/unhide", {
        method: "POST",
        body: JSON.stringify({ reason }),
      }),
  },

  sources: {
    health: () => request<SourcesHealthResponse>("/api/sources/health"),
  },

  worker: {
    pollNow: () => request<PollNowResponse>("/api/worker/poll-now", { method: "POST", body: JSON.stringify({}) }),
  },

  truth: {
    status: () => request<TruthStatusResponse>("/api/truth/status"),
    reload: () =>
      request<TruthStatusResponse>("/api/truth/reload", { method: "POST" }),
  },

  tutoring: {
    platforms: () => request<TutoringPlatformsResponse>("/api/tutoring/platforms"),
    updatePlatform: (
      id: string,
      payload: {
        status?: TutoringStatus
        checklist?: Record<string, boolean>
        notes?: string
      }
    ) =>
      request<TutoringPlatform>(`/api/tutoring/platforms/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    profileMaterial: () =>
      request<TutoringProfileMaterialResponse>("/api/tutoring/profile-material"),
  },
}

/** Downloads a binary artifact, surfacing 409/412 as typed ApiErrors instead
 * of trying to parse binary content as JSON. `format` defaults to `"docx"`
 * (the pre-existing behaviour); `"pdf"` fetches
 * `?download=true` so the PDF route returns `attachment`, not the
 * preview's `inline` (BRIEF-FR-006 D2 requirement 1). */
export async function downloadArtifact(
  id: string,
  kind: "cv" | "cover-letter",
  options?: { format?: "docx" | "pdf"; template?: ArtifactTemplateId }
): Promise<{ blob: Blob; filename: string }> {
  const requestedFormat = options?.format ?? "docx"
  const format = kind === "cv" ? "pdf" : requestedFormat
  const template = options?.template ?? "classic"
  const url =
    kind === "cv"
      ? api.opportunities.artifactUrl(id, kind)
      : format === "docx"
        ? `${api.opportunities.artifactUrl(id, kind)}?template=${template}`
        : `${api.opportunities.artifactPdfUrl(id, kind, template)}&download=true`
  const res = await fetch(url, { credentials: "same-origin" })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body)
  }

  const disposition = res.headers.get("content-disposition") ?? ""
  const match = /filename="?([^"]+)"?/.exec(disposition)
  const filename = match?.[1] ?? `${kind}-${id}.${format}`
  const blob = await res.blob()
  return { blob, filename }
}
