import { NextRequest, NextResponse } from "next/server";

// Hop-by-hop headers that should not be forwarded
const FORBIDDEN_HEADERS = new Set([
  "host",
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);


const ACCESS_COOKIE = "__Host-opos_access";
const REFRESH_COOKIE = "__Host-opos_refresh";
type HostedConfig = { origin: string; key: string };

type HostedSession = { access_token?: string; refresh_token?: string; expires_in?: number };

function hostedConfig(): HostedConfig | null {
  const raw = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = (process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)?.trim();
  if (!raw || !key) return null;
  try { const url = new URL(raw); if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) return null; return { origin: url.origin, key }; } catch { return null; }
}
function hostedError(detail: string, status: number): NextResponse { return NextResponse.json({ detail }, { status }); }
function cookieOptions(maxAge?: number) { return { httpOnly: true, secure: true, sameSite: "lax" as const, path: "/", ...(maxAge === undefined ? {} : { maxAge }) }; }
function setSessionCookies(response: NextResponse, session: HostedSession) { if (session.access_token) response.cookies.set(ACCESS_COOKIE, session.access_token, cookieOptions(session.expires_in ?? 3600)); if (session.refresh_token) response.cookies.set(REFRESH_COOKIE, session.refresh_token, cookieOptions(60 * 60 * 24 * 30)); }
function clearSessionCookies(response: NextResponse) { response.cookies.set(ACCESS_COOKIE, "", cookieOptions(0)); response.cookies.set(REFRESH_COOKIE, "", cookieOptions(0)); }
async function hostedFetch(config: HostedConfig, path: string, init: RequestInit = {}) { const headers = new Headers(init.headers); headers.set("apikey", config.key); headers.set("Accept", "application/json"); if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json"); return fetch(`${config.origin}${path}`, { ...init, headers, redirect: "manual" }); }
async function refreshHosted(config: HostedConfig, refresh: string): Promise<HostedSession | null> { const response = await hostedFetch(config, "/auth/v1/token?grant_type=refresh_token", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) }); return response.ok ? await response.json() as HostedSession : null; }
async function hostedAccess(request: NextRequest, config: HostedConfig): Promise<{ token: string; refreshed?: HostedSession } | NextResponse> {
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  if (access) { const probe = await hostedFetch(config, "/auth/v1/user", { headers: { Authorization: `Bearer ${access}` } }); if (probe.ok) return { token: access }; }
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value; if (!refresh) return hostedError("authentication required", 401);
  const session = await refreshHosted(config, refresh); if (!session?.access_token) return hostedError("authentication required", 401);
  return { token: session.access_token, refreshed: session };
}
function hostedFeedRow(row: Record<string, unknown>) { let reasons: string[] = []; const raw = row.reasons_json; if (typeof raw === "string") { try { const parsed = JSON.parse(raw); if (Array.isArray(parsed)) reasons = parsed.map((x) => typeof x === "string" ? x : typeof x?.text === "string" ? x.text : "").filter(Boolean); } catch {} } return { id: String(row.opportunity_id ?? row.id ?? ""), title: row.title ?? "", organization: row.organization ?? "", source_id: row.source_id ?? "", source_url: row.source_url ?? "", track: row.track, decision: row.qualification_decision ?? null, fit_score: row.fit_score ?? null, top_reasons: reasons, deadline: row.deadline ?? null, posted_date: row.posted_date ?? null, is_stale: false, action_state: null, feedback_label: null, hidden_by: [], flagged_by: [], work_mode: row.work_mode ?? "unspecified", work_mode_source: null, location_country: row.location_country ?? null, location_city: row.location_city ?? null, location_region: row.location_region ?? null, remote_scope: row.remote_scope ?? "unspecified", remote_scope_regions: [], employment_type: row.employment_type ?? "unspecified", seniority_level: row.seniority_level ?? "unspecified", compensation_min: null, compensation_max: null, compensation_currency: null, compensation_period: null, title_family: row.title_family ?? null, title_level: null, family_key: null, family_size: null }; }
async function hostedContract(request: NextRequest, path: string[], token: string, config: HostedConfig): Promise<NextResponse> {
  const subpath = path.join("/"); const method = request.method.toUpperCase(); const url = new URL(request.url);
  if (subpath === "opportunities" && method === "GET") {
    const page = Math.max(1, Number(url.searchParams.get("page") ?? "1") || 1); const pageSize = Math.min(200, Math.max(1, Number(url.searchParams.get("page_size") ?? "25") || 25));
    const q = new URL(`${config.origin}/rest/v1/founder_feed`); q.searchParams.set("select", "*"); q.searchParams.set("order", "priority_score.desc,opportunity_id.asc"); q.searchParams.set("offset", String((page - 1) * pageSize)); q.searchParams.set("limit", String(pageSize));
    for (const [key, column, op] of [["track", "track", "eq"], ["decision", "qualification_decision", "eq"], ["min_score", "fit_score", "gte"]] as const) { const value = url.searchParams.get(key); if (value) q.searchParams.set(column, `${op}.${value}`); }
    const text = url.searchParams.get("q"); if (text) { const safe = text.replace(/[(),]/g, " "); q.searchParams.set("or", `(title.ilike.*${safe}*,organization.ilike.*${safe}*)`); }
    const response = await hostedFetch(config, `${q.pathname}${q.search}`, { headers: { Authorization: `Bearer ${token}`, Prefer: "count=exact" } }); const rows = await response.json().catch(() => []); if (!response.ok) return NextResponse.json(rows, { status: response.status });
    const range = response.headers.get("content-range") ?? "*/0"; const total = Number(range.split("/")[1] ?? "0") || 0; return NextResponse.json({ page, page_size: pageSize, total, hidden_count: 0, items: Array.isArray(rows) ? rows.map(hostedFeedRow) : [] });
  }
  if (subpath === "worker/poll-now" && method === "POST") { const response = await hostedFetch(config, "/rest/v1/rpc/enqueue_poll_now", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: await request.text() || "{}" }); const payload = await response.json().catch(() => null); if (!response.ok) return NextResponse.json(payload, { status: response.status }); const object = payload && typeof payload === "object" && !Array.isArray(payload) ? payload as Record<string, unknown> : {}; const enqueued = Array.isArray(object.enqueued) ? object.enqueued.filter((item: unknown) => item && typeof item === "object" && "source_id" in item && "job_id" in item) : []; const skipped = Array.isArray(object.skipped) ? object.skipped.filter((item: unknown) => item && typeof item === "object" && "source_id" in item && "reason" in item) : []; return NextResponse.json({ enqueued, skipped }); }
  if (subpath === "sources/health" && method === "GET") { const response = await hostedFetch(config, "/rest/v1/founder_source_health?select=*&order=source_id.asc", { headers: { Authorization: `Bearer ${token}` } }); const rows = await response.json().catch(() => []); if (!response.ok) return NextResponse.json(rows, { status: response.status }); return NextResponse.json({ sources: Array.isArray(rows) ? rows.map((row: Record<string, unknown>) => ({ source_id: row.source_id, name: row.source_id, category: "", read_policy: "allowed", last_poll: row.last_poll_finished_at ?? null, last_status: row.last_poll_status ?? row.last_status ?? null, last_record_count: null })) : [] }); }
  if (subpath.startsWith("opportunities/") && path.length === 2 && method === "GET") { const id = encodeURIComponent(path[1]); const response = await hostedFetch(config, `/rest/v1/founder_opportunity_detail?id=eq.${id}&select=*`, { headers: { Authorization: `Bearer ${token}` } }); const rows = await response.json().catch(() => []); if (!response.ok) return NextResponse.json(rows, { status: response.status }); if (!Array.isArray(rows) || !rows.length) return hostedError("opportunity not found", 404); const row = rows[0] as Record<string, unknown>; return NextResponse.json({ ...row, fields: [], qualification: { decision: row.qualification_decision ?? null, constraints: [] }, scoring: { fit_score: row.fit_score ?? null, dimension_scores: [], strengths: [], gaps: [], unknowns: [], uncertainty_penalty: 0, explanation: "", policy_version: row.policy_version ?? "", evaluated_at: row.evaluated_at ?? "", truth_pack_hash: row.truth_pack_hash ?? null }, evidence_links: [], action_history: [], feedback_history: [] }); }
  if (["filters", "facets", "saved-views"].includes(subpath) && method === "GET") {
    const view = subpath === "filters" ? "founder_filters" : subpath === "facets" ? "founder_facet_settings_view" : "founder_saved_view_records";
    const response = await hostedFetch(config, `/rest/v1/${view}?select=*`, { headers: { Authorization: `Bearer ${token}` } });
    const rows = await response.json().catch(() => []); if (!response.ok) return NextResponse.json(rows, { status: response.status });
    if (subpath === "filters") return NextResponse.json({ filters: Array.isArray(rows) ? rows.map((row: Record<string, unknown>) => ({ filter_id: row.filter_id, enabled: Boolean(row.enabled), mode: row.mode, params: typeof row.params_json === "string" ? JSON.parse(row.params_json) : {}, affected_count: 0, description: "", unavailable_reason: null })) : [] });
    if (subpath === "facets") return NextResponse.json({ facets: Array.isArray(rows) ? rows.map((row: Record<string, unknown>) => ({ facet_id: row.facet_id, value_type: "enum", description: "", available: true, unavailable_reason: null, values: [], excluded_count: 0, include: [], exclude: [] })) : [] });
    return NextResponse.json({ views: Array.isArray(rows) ? rows.map((row: Record<string, unknown>) => ({ id: row.id, name: row.name, facets: typeof row.facets_json === "string" ? JSON.parse(row.facets_json) : {}, search_query: row.search_query ?? null, is_default: Boolean(row.is_default) })) : [] });
  }
  if (subpath === "truth/status" && method === "GET") {
    const hash = process.env.NEXT_PUBLIC_TRUTH_PACK_HASH?.trim() || null;
    return NextResponse.json({ loaded: Boolean(hash), hash, path: "hosted-private-truth-pack", validator: { ok: Boolean(hash), error_count: 0, findings: [] }, sections: [] });
  }
  if (subpath === "dashboard/daily" && method === "GET") {
    const days = Math.max(1, Math.min(31, Number(new URL(request.url).searchParams.get("days") ?? "7") || 7));
    return NextResponse.json({ days, high_fit_threshold: 80, series: [] });
  }
  if (subpath.startsWith("opportunities/") && path.length >= 4 && path[2] === "artifacts" && method === "GET") {
    const opportunityId = encodeURIComponent(path[1]);
    const requested = path.slice(3).join("/").toLowerCase();
    const isCv = requested.includes("cv");
    let bucket = "opportunity-artifacts";
    let objectKey: string | null = null;
    let expectedHash: string | null = null;
    let expectedSize: number | null = null;
    let contentType = "application/octet-stream";
    if (isCv) {
      bucket = "founder-cv-portfolio";
      const metadata = await hostedFetch(config, `/rest/v1/founder_cv_selection?opportunity_id=eq.${opportunityId}&select=object_path,sha256`, { headers: { Authorization: `Bearer ${token}` } });
      const rows = await metadata.json().catch(() => []);
      if (!metadata.ok) return NextResponse.json(rows, { status: metadata.status });
      const row = Array.isArray(rows) ? rows[0] as Record<string, unknown> | undefined : undefined;
      objectKey = typeof row?.object_path === "string" ? row.object_path : null;
      expectedHash = typeof row?.sha256 === "string" ? row.sha256 : null;
      contentType = "application/pdf";
    } else {
      const metadata = await hostedFetch(config, `/rest/v1/founder_artifact_metadata?opportunity_id=eq.${opportunityId}&select=*`, { headers: { Authorization: `Bearer ${token}` } });
      const rows = await metadata.json().catch(() => []);
      if (!metadata.ok) return NextResponse.json(rows, { status: metadata.status });
      const row = Array.isArray(rows) ? rows.find((value: unknown) => typeof value === "object" && value !== null && String((value as Record<string, unknown>).artifact_kind ?? "").toLowerCase().includes(requested.includes("cover") ? "cover" : "")) as Record<string, unknown> | undefined : undefined;
      objectKey = typeof row?.object_key === "string" ? row.object_key : null;
      expectedHash = typeof row?.payload_sha256 === "string" ? row.payload_sha256 : null;
      expectedSize = typeof row?.size_bytes === "number" ? row.size_bytes : null;
      contentType = typeof row?.content_type === "string" ? row.content_type : contentType;
    }
    if (!objectKey) return hostedError("artifact metadata unavailable", 404);
    const objectResponse = await hostedFetch(config, `/storage/v1/object/${encodeURIComponent(bucket)}/${objectKey.split("/").map(encodeURIComponent).join("/")}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!objectResponse.ok) return hostedError("artifact body unavailable", objectResponse.status === 404 ? 404 : 502);
    const bytes = await objectResponse.arrayBuffer();
    if (isCv && new Uint8Array(bytes.slice(0, 5)).toString() !== new Uint8Array(new TextEncoder().encode("%PDF-")).toString()) return hostedError("artifact content type mismatch", 412);
    if (expectedSize !== null && bytes.byteLength !== expectedSize) return hostedError("artifact size mismatch", 412);
    if (expectedHash) { const digest = await crypto.subtle.digest("SHA-256", bytes); const actual = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join(""); if (actual !== expectedHash) return hostedError("artifact checksum mismatch", 412); }
    return new NextResponse(bytes, { status: 200, headers: { "Content-Type": contentType, "Cache-Control": "private, no-store", "Content-Disposition": requested.includes("pdf") ? "inline" : "attachment" } });
  }
  return hostedError("hosted API route is unsupported", 404);
}

async function hostedRequest(request: NextRequest, path: string[]): Promise<NextResponse> {
  const config = hostedConfig(); if (!config) return hostedError("hosted Supabase configuration is unavailable", 503);
  const method = request.method.toUpperCase(); if (method !== "GET" && method !== "HEAD" && request.headers.get("x-opportunityos-csrf") !== "1") return hostedError("CSRF validation failed", 403);
  const subpath = path.join("/");
  if (subpath === "auth/login" && method === "POST") { const payload = await request.json().catch(() => null) as { email?: unknown; password?: unknown } | null; if (!payload || typeof payload.email !== "string" || typeof payload.password !== "string") return hostedError("email and password are required", 400); const auth = await hostedFetch(config, "/auth/v1/token?grant_type=password", { method: "POST", body: JSON.stringify({ email: payload.email, password: payload.password }) }); if (!auth.ok) return hostedError("authentication failed", 401); const response = NextResponse.json({ authenticated: true }); setSessionCookies(response, await auth.json() as HostedSession); return response; }
  if (subpath === "auth/logout" && method === "POST") { const token = request.cookies.get(ACCESS_COOKIE)?.value; if (token) await hostedFetch(config, "/auth/v1/logout", { method: "POST", headers: { Authorization: `Bearer ${token}` } }).catch(() => undefined); const response = NextResponse.json({ authenticated: false }); clearSessionCookies(response); return response; }
  if (subpath === "auth/me" && method === "GET") { const auth = await hostedAccess(request, config); if (auth instanceof NextResponse) return auth; const response = NextResponse.json({ authenticated: true }); if (auth.refreshed) setSessionCookies(response, auth.refreshed); return response; }
  const auth = await hostedAccess(request, config); if (auth instanceof NextResponse) return auth; const response = await hostedContract(request, path, auth.token, config); if (auth.refreshed) setSessionCookies(response, auth.refreshed); return response;
}

async function proxyRequest(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const subpath = path.join("/");

  // Determine target API origin:
  // 1. In Cloudflare runtime / environment: process.env.OPPORTUNITYOS_API_ORIGIN
  // 2. In local dev fallback: http://localhost:<OPPORTUNITYOS_API_PORT || 8000>
  const configuredOrigin = process.env.OPPORTUNITYOS_API_ORIGIN?.trim();
  const cloudEdge = process.env.OPPORTUNITYOS_CLOUD_EDGE === "1";

  let targetOrigin: string;
  if (configuredOrigin) {
    let parsed: URL;
    try {
      parsed = new URL(configuredOrigin);
    } catch {
      return NextResponse.json(
        { error: "Configuration Error: OPPORTUNITYOS_API_ORIGIN is invalid." },
        { status: 500 }
      );
    }
    if (
      parsed.protocol !== "https:" ||
      parsed.username ||
      parsed.password ||
      parsed.pathname !== "/" ||
      parsed.search ||
      parsed.hash
    ) {
      return NextResponse.json(
        {
          error:
            "Configuration Error: OPPORTUNITYOS_API_ORIGIN must be a credential-free HTTPS origin.",
        },
        { status: 500 }
      );
    }
    targetOrigin = parsed.origin;
  } else {
    if (cloudEdge) return hostedRequest(request, path);
    // Local-development fallback only. Cloudflare staging sets
    // OPPORTUNITYOS_CLOUD_EDGE=1 and therefore can never reach localhost.
    const port = process.env.OPPORTUNITYOS_API_PORT || "8000";
    targetOrigin = `http://localhost:${port}`;
  }

  // Preserve search query params
  const url = new URL(request.url);
  const targetUrl = `${targetOrigin}/api/${subpath}${url.search}`;

  // Forward headers safely:
  // - Omit hop-by-hop headers and Host header
  // - Preserve cookie, authorization, content-type, accept, etc.
  const forwardHeaders = new Headers();
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (!FORBIDDEN_HEADERS.has(lower)) {
      forwardHeaders.set(key, value);
    }
  });

  // Body handling: GET and HEAD cannot have a body in fetch
  const method = request.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD";
  const body = hasBody ? await request.arrayBuffer() : undefined;

  try {
    const upstreamRes = await fetch(targetUrl, {
      method,
      headers: forwardHeaders,
      body,
      redirect: "manual",
    });

    // Build downstream response
    const resHeaders = new Headers();
    upstreamRes.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (!FORBIDDEN_HEADERS.has(lower) && lower !== "set-cookie") {
        resHeaders.append(key, value);
      }
    });

    // Preserve multiple Set-Cookie headers independently when the runtime
    // exposes getSetCookie(); collapsing them can corrupt auth/session state.
    const cookieHeaders = upstreamRes.headers as Headers & {
      getSetCookie?: () => string[];
    };
    const setCookies = cookieHeaders.getSetCookie?.() ?? [];
    if (setCookies.length > 0) {
      for (const cookie of setCookies) resHeaders.append("set-cookie", cookie);
    } else {
      const cookie = upstreamRes.headers.get("set-cookie");
      if (cookie) resHeaders.append("set-cookie", cookie);
    }

    return new NextResponse(upstreamRes.body, {
      status: upstreamRes.status,
      statusText: upstreamRes.statusText,
      headers: resHeaders,
    });
  } catch {
    return new NextResponse(
      JSON.stringify({ error: "Bad Gateway: Failed to reach upstream OpportunityOS API." }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    );
  }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
export const HEAD = proxyRequest;
export const OPTIONS = proxyRequest;
