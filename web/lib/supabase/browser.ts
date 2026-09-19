import type { OpportunityListResponse, AuthenticatedResponse, PollNowResponse } from "@/lib/contract/types"

type Session = {
  access_token: string
  refresh_token: string
  expires_at?: number
  user?: { id: string; email?: string }
}

const SESSION_KEY = "opportunityos.supabase.session"

function config() {
  const origin = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim().replace(/\/$/, "")
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim()
  if (!origin || !anonKey) return null
  try {
    const parsed = new URL(origin)
    if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash) return null
    return { origin: parsed.origin, anonKey }
  } catch {
    return null
  }
}

export function isSupabaseBrowserConfigured(): boolean {
  return typeof window !== "undefined" && config() !== null
}

function readSession(): Session | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Session
    return parsed.access_token && parsed.refresh_token ? parsed : null
  } catch {
    return null
  }
}

function writeSession(session: Session | null) {
  if (typeof window === "undefined") return
  if (session) window.localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  else window.localStorage.removeItem(SESSION_KEY)
}

async function supabaseFetch<T>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
  const settings = config()
  if (!settings) throw new Error("Supabase browser configuration is unavailable")
  const session = auth ? readSession() : null
  const headers = new Headers(init.headers)
  headers.set("apikey", settings.anonKey)
  headers.set("Accept", "application/json")
  if (session?.access_token) headers.set("Authorization", `Bearer ${session.access_token}`)
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json")
  const response = await fetch(`${settings.origin}${path}`, { ...init, headers })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const message = body && typeof body === "object" && "msg" in body && typeof body.msg === "string"
      ? body.msg
      : "Supabase request failed"
    const error = new Error(message) as Error & { status?: number; body?: unknown }
    error.status = response.status
    error.body = body
    throw error
  }
  return body as T
}

export async function signIn(email: string, password: string): Promise<AuthenticatedResponse> {
  const settings = config()
  if (!settings) throw new Error("Supabase browser configuration is unavailable")
  const session = await supabaseFetch<Session>("/auth/v1/token?grant_type=password", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  }, false)
  writeSession(session)
  return { authenticated: true }
}

export async function signOut(): Promise<AuthenticatedResponse> {
  const session = readSession()
  if (session) {
    await supabaseFetch<unknown>("/auth/v1/logout", { method: "POST" }).catch(() => undefined)
  }
  writeSession(null)
  return { authenticated: false }
}

export async function currentUser(): Promise<AuthenticatedResponse> {
  const session = readSession()
  if (!session) throw new Error("No Supabase session")
  await supabaseFetch<unknown>("/auth/v1/user")
  return { authenticated: true }
}

function parseReasons(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string")
  if (typeof value === "string") {
    try { return parseReasons(JSON.parse(value)) } catch { return [] }
  }
  return []
}

function mapFeedRow(row: Record<string, unknown>): OpportunityListResponse["items"][number] {
  return {
    id: String(row.id ?? row.opportunity_id),
    title: String(row.title ?? ""),
    organization: String(row.organization ?? ""),
    source_id: String(row.source_id ?? ""),
    source_url: String(row.source_url ?? ""),
    track: row.track,
    decision: row.qualification_decision ?? row.decision ?? null,
    fit_score: row.fit_score ?? null,
    top_reasons: parseReasons(row.reasons_json ?? row.top_reasons),
    deadline: row.deadline ?? null,
    posted_date: row.posted_date ?? null,
    is_stale: Boolean(row.is_stale),
    action_state: row.action_state ?? null,
    feedback_label: row.feedback_label ?? null,
    hidden_by: Array.isArray(row.hidden_by) ? row.hidden_by : [],
    flagged_by: Array.isArray(row.flagged_by) ? row.flagged_by : [],
    work_mode: String(row.work_mode ?? "unspecified"),
    work_mode_source: row.work_mode_source ?? null,
    location_country: row.location_country ?? null,
    location_city: row.location_city ?? null,
    location_region: row.location_region ?? null,
    remote_scope: String(row.remote_scope ?? "unspecified"),
    remote_scope_regions: Array.isArray(row.remote_scope_regions) ? row.remote_scope_regions : [],
    employment_type: String(row.employment_type ?? "unspecified"),
    seniority_level: String(row.seniority_level ?? "unspecified"),
    compensation_min: row.compensation_min ?? null,
    compensation_max: row.compensation_max ?? null,
    compensation_currency: row.compensation_currency ?? null,
    compensation_period: row.compensation_period ?? null,
    title_family: row.title_family ?? null,
    title_level: row.title_level ?? null,
    family_key: row.family_key ?? null,
    family_size: row.family_size ?? null,
  } as OpportunityListResponse["items"][number]
}

export async function listOpportunities(params: Record<string, string | number | boolean | undefined>): Promise<OpportunityListResponse> {
  const search = new URLSearchParams({ select: "*", order: "priority_score.desc,opportunity_id.asc" })
  const page = Number(params.page ?? 1)
  const pageSize = Number(params.page_size ?? 50)
  search.set("offset", String((page - 1) * pageSize))
  search.set("limit", String(pageSize))
  if (params.track) search.set("track", `eq.${params.track}`)
  if (params.decision) search.set("qualification_decision", `eq.${params.decision}`)
  if (params.min_score !== undefined) search.set("fit_score", `gte.${params.min_score}`)
  if (params.q) {
    const q = String(params.q).replace(/[(),]/g, " ")
    search.set("or", `(title.ilike.*${q}*,organization.ilike.*${q}*)`)
  }
  const rows = await supabaseFetch<Record<string, unknown>[]>(`/rest/v1/founder_feed?${search.toString()}`)
  return { page, page_size: pageSize, total: rows.length, hidden_count: 0, items: rows.map(mapFeedRow) }
}

export async function enqueuePollNow(): Promise<PollNowResponse> {
  const rows = await supabaseFetch<PollNowResponse[]>("/rest/v1/rpc/enqueue_poll_now", {
    method: "POST", body: JSON.stringify({}),
  })
  return Array.isArray(rows) ? (rows[0] ?? { enqueued: [], skipped: [] }) : rows
}
