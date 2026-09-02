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
  AuthenticatedResponse,
  DashboardResponse,
  FeedbackLabel,
  FeedbackResponse,
  FilterUpdateRequest,
  FiltersResponse,
  FounderFilter,
  OpportunityDetail,
  OpportunityListResponse,
  PollNowResponse,
  SourcesHealthResponse,
  TruthStatusResponse,
} from "@/lib/contract/types"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
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
    login: (password: string) =>
      request<{ authenticated: true }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ password }),
      }),
    logout: () =>
      request<AuthenticatedResponse>("/api/auth/logout", { method: "POST" }),
    me: () => request<AuthenticatedResponse>("/api/auth/me"),
  },

  opportunities: {
    list: (params: {
      track?: string
      decision?: string
      min_score?: number
      since?: string
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
        if (value !== undefined && value !== "" && value !== null) {
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
      `/api/opportunities/${id}/artifacts/${kind === "cv" ? "cv.docx" : "cover-letter.docx"}`,
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

  sources: {
    health: () => request<SourcesHealthResponse>("/api/sources/health"),
  },

  worker: {
    pollNow: () =>
      request<PollNowResponse>("/api/worker/poll-now", { method: "POST" }),
  },

  truth: {
    status: () => request<TruthStatusResponse>("/api/truth/status"),
    reload: () =>
      request<TruthStatusResponse>("/api/truth/reload", { method: "POST" }),
  },
}

/** Downloads a binary artifact, surfacing 409/412 as typed ApiErrors instead
 * of trying to parse binary content as JSON. */
export async function downloadArtifact(
  id: string,
  kind: "cv" | "cover-letter"
): Promise<{ blob: Blob; filename: string }> {
  const url = api.opportunities.artifactUrl(id, kind)
  const res = await fetch(url, { credentials: "same-origin" })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body)
  }

  const disposition = res.headers.get("content-disposition") ?? ""
  const match = /filename="?([^"]+)"?/.exec(disposition)
  const filename = match?.[1] ?? `${kind}-${id}.docx`
  const blob = await res.blob()
  return { blob, filename }
}
