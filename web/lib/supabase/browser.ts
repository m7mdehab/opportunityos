/**
 * Same-origin hosted runtime client.
 *
 * Authentication tokens are deliberately never exposed to browser JavaScript.
 * The `/api` edge adapter owns the Supabase session and stores access/refresh
 * tokens in HTTP-only cookies. Keeping this module as a thin same-origin
 * wrapper means local development and hosted runtime exercise one contract.
 */
import type { AuthenticatedResponse, OpportunityListResponse, PollNowResponse } from "@/lib/contract/types"

export function isSupabaseBrowserConfigured(): boolean {
  // Compatibility probe retained for older callers. Browser credentials never
  // select a transport; the server route owns the hosted session.
  return typeof window !== "undefined"
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase()
  const headers = new Headers(init.headers)
  headers.set("Accept", "application/json")
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") headers.set("X-OpportunityOS-CSRF", "1")
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json")
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const message = body && typeof body === "object" && "detail" in body
      ? String((body as { detail?: unknown }).detail ?? "Request failed")
      : "Request failed"
    const error = new Error(message) as Error & { status?: number; body?: unknown }
    error.status = response.status
    error.body = body
    throw error
  }
  return body as T
}

export function signIn(email: string, password: string): Promise<AuthenticatedResponse> {
  return request<AuthenticatedResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  })
}

export function signOut(): Promise<AuthenticatedResponse> {
  return request<AuthenticatedResponse>("/api/auth/logout", { method: "POST" })
}

export function currentUser(): Promise<AuthenticatedResponse> {
  return request<AuthenticatedResponse>("/api/auth/me")
}

export function listOpportunities(
  params: Record<string, string | number | boolean | undefined>,
): Promise<OpportunityListResponse> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "" && value !== null) query.set(key, String(value))
  }
  const suffix = query.toString() ? `?${query.toString()}` : ""
  return request<OpportunityListResponse>(`/api/opportunities${suffix}`)
}

export function enqueuePollNow(): Promise<PollNowResponse> {
  return request<PollNowResponse>("/api/worker/poll-now", { method: "POST", body: JSON.stringify({}) })
}
