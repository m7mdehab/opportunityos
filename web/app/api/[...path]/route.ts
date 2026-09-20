import { NextRequest, NextResponse } from "next/server";
import { getCloudflareContext } from "@opennextjs/cloudflare";

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

type RuntimeEnv = Record<string, string | undefined>;

function runtimeEnv(): RuntimeEnv {
  try {
    const cloudflareEnv = getCloudflareContext().env as unknown as RuntimeEnv;
    if (cloudflareEnv.OPPORTUNITYOS_CLOUD_EDGE === "1") return cloudflareEnv;
  } catch {
    // next dev / ordinary Node execution has no OpenNext Worker request context.
  }
  return process.env as RuntimeEnv;
}

function hostedConfig(env: RuntimeEnv = runtimeEnv()): HostedConfig | null {
  const raw = env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = (env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? env.NEXT_PUBLIC_SUPABASE_ANON_KEY)?.trim();
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
function parseJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try { return JSON.parse(value); } catch { return null; }
}
function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => typeof item === "string" ? item : typeof item?.text === "string" ? item.text : "").filter(Boolean) : [];
}
function policyHiddenReasons(value: unknown): string[] {
  const parsed = parseJson(value);
  const candidates = Array.isArray(parsed) ? parsed : String(value ?? "").split(/[\s,]+/);
  return candidates
    .map((item) => typeof item === "string" ? item.replace(/^[\[\]"{}]+|[\[\]"{}]+$/g, "") : "")
    .filter((item) => item && !item.startsWith("facet:"));
}
function hostedFeedRow(row: Record<string, unknown>) {
  const reasons = asStringArray(parseJson(row.reasons_json));
  return {
    id: String(row.opportunity_id ?? row.id ?? ""), title: row.title ?? "", organization: row.organization ?? "",
    source_id: row.source_id ?? "", source_url: row.source_url ?? "", track: row.track,
    decision: row.qualification_decision ?? null, fit_score: row.fit_score ?? null, top_reasons: reasons,
    deadline: row.deadline ?? null, posted_date: row.posted_date ?? null, is_stale: Boolean(row.is_stale),
    action_state: null, feedback_label: null, hidden_by: policyHiddenReasons(row.visibility_reason), flagged_by: [], work_mode: row.work_mode ?? "unspecified",
    work_mode_source: null, location_country: row.location_country ?? null, location_city: row.location_city ?? null,
    location_region: row.location_region ?? null, remote_scope: row.remote_scope ?? "unspecified", remote_scope_regions: [],
    employment_type: row.employment_type ?? "unspecified", seniority_level: row.seniority_level ?? "unspecified",
    compensation_min: null, compensation_max: null, compensation_currency: null, compensation_period: null,
    title_family: row.title_family ?? null, title_level: null, family_key: null, family_size: null,
    source_family: row.source_family ?? String(row.source_id ?? "").split(":")[0], reverified_at: row.reverified_at ?? null,
  };
}
function hostedDetail(row: Record<string, unknown>) {
  const detail = (parseJson(row.evaluation_detail_json) ?? {}) as Record<string, unknown>;
  const dimensions = parseJson(row.dimension_scores_json);
  const constraints = Array.isArray(detail.hard_constraints) ? detail.hard_constraints.map((item: unknown) => {
    const value = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    const passed = value.passed;
    return { constraint_name: String(value.constraint_name ?? "constraint"), outcome: passed === true ? "PASS" : passed === false ? "FAIL" : "UNKNOWN", reason: String(value.reason ?? ""), required_field: value.required_field ?? null, founder_fact: value.founder_fact ?? null, is_hard_failure: Boolean(value.is_hard_failure), provenance_pointer: value.provenance_pointer ?? null };
  }) : [];
  const dimensionScores = Array.isArray(dimensions) ? dimensions.map((item: unknown) => {
    const value = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    return { dimension: String(value.dimension_name ?? value.dimension ?? "unknown"), score: Number(value.raw_score ?? value.score ?? 0), weight: Number(value.weight ?? 0), weighted_score: Number(value.weighted_score ?? 0), rationale: String(value.explanation ?? value.rationale ?? "") };
  }) : [];
  const { evaluation_detail_json: _evaluationDetail, dimension_scores_json: _dimensionScores, reasons_json: _reasons, ...safeRow } = row;
  return { ...safeRow, fields: [], qualification: { decision: row.qualification_decision ?? null, constraints }, scoring: { fit_score: row.fit_score ?? null, dimension_scores: dimensionScores, strengths: asStringArray(detail.strengths), gaps: asStringArray(detail.gaps), unknowns: asStringArray(detail.unknowns), uncertainty_penalty: Number(detail.uncertainty_penalty ?? 0), explanation: String(detail.explanation ?? ""), policy_version: row.policy_version ?? "", evaluated_at: row.evaluated_at ?? "", truth_pack_hash: row.truth_pack_hash ?? null }, evidence_links: [], action_history: [], feedback_history: [] };
}

type HostedFacetDefinition = {
  facet_id: string;
  value_type: "enum" | "string" | "boolean" | "range" | "date-window";
  description: string;
  available?: boolean;
  unavailable_reason?: string | null;
};

const HOSTED_FACET_DEFINITIONS: HostedFacetDefinition[] = [
  { facet_id: "work_mode", value_type: "enum", description: "How the role is performed (remote/hybrid/onsite/unspecified)." },
  { facet_id: "location_country", value_type: "enum", description: "Opportunity's location country (ISO-2)." },
  { facet_id: "location_city", value_type: "string", description: "Opportunity's location city." },
  { facet_id: "remote_scope", value_type: "enum", description: "Geographic scope a remote posting is open to." },
  { facet_id: "employment_type", value_type: "enum", description: "Full-time / contract / etc." },
  { facet_id: "seniority_level", value_type: "enum", description: "Inferred seniority level." },
  { facet_id: "title_family", value_type: "enum", description: "Assigned title family." },
  { facet_id: "track", value_type: "enum", description: "Employment vs. procurement track." },
  { facet_id: "source_id", value_type: "enum", description: "Source adapter this opportunity came from." },
  { facet_id: "employer", value_type: "string", description: "Hiring organization." },
  { facet_id: "posted_within", value_type: "date-window", description: "How recently the opportunity was posted." },
  { facet_id: "compensation_stated", value_type: "boolean", description: "Whether any compensation amount was extracted." },
  { facet_id: "decision", value_type: "enum", description: "The latest qualification decision." },
  { facet_id: "fit_score", value_type: "range", description: "Fit score bucketed in quartiles." },
  {
    facet_id: "language",
    value_type: "enum",
    description: "Posting language.",
    available: false,
    unavailable_reason: "Posting language is not persisted in the current Founder Alpha storage contract.",
  },
];

function hostedFacetScalar(row: Record<string, unknown>, facetId: string): string {
  const unspecified = (value: unknown) => {
    const text = value == null ? "" : String(value).trim();
    return text || "unspecified";
  };
  if (facetId === "employer") return unspecified(row.organization);
  if (facetId === "decision") return unspecified(row.qualification_decision);
  if (facetId === "compensation_stated") {
    return row.compensation_min != null || row.compensation_max != null ? "yes" : "no";
  }
  if (facetId === "fit_score") {
    const score = typeof row.fit_score === "number" ? row.fit_score : Number(row.fit_score);
    if (!Number.isFinite(score)) return "unscored";
    if (score < 25) return "0-25";
    if (score < 50) return "25-50";
    if (score < 75) return "50-75";
    return "75-100";
  }
  if (facetId === "posted_within") {
    const raw = row.posted_date;
    if (!raw) return "unspecified";
    const posted = new Date(String(raw).slice(0, 10) + "T00:00:00Z");
    if (!Number.isFinite(posted.getTime())) return "unspecified";
    const ageDays = (Date.now() - posted.getTime()) / 86400000;
    if (ageDays < 1) return "last_24h";
    if (ageDays < 7) return "last_7d";
    if (ageDays < 30) return "last_30d";
    if (ageDays < 90) return "last_90d";
    return "older";
  }
  return unspecified(row[facetId]);
}

function hostedFacetSettings(rows: unknown[]): Map<string, { include: string[]; exclude: string[] }> {
  const result = new Map<string, { include: string[]; exclude: string[] }>();
  for (const raw of rows) {
    if (!raw || typeof raw !== "object") continue;
    const row = raw as Record<string, unknown>;
    const facetId = typeof row.facet_id === "string" ? row.facet_id : "";
    if (!facetId) continue;
    let parsed: unknown = row.values_json;
    if (typeof parsed === "string") {
      try { parsed = JSON.parse(parsed); } catch { parsed = {}; }
    }
    const object = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
    const include = Array.isArray(object.include) ? object.include.map(String) : [];
    const exclude = Array.isArray(object.exclude) ? object.exclude.map(String) : [];
    result.set(facetId, { include, exclude });
  }
  return result;
}

async function hostedFacetPayload(config: HostedConfig, token: string): Promise<NextResponse> {
  const auth = { Authorization: `Bearer ${token}` };
  const settingsResponse = await hostedFetch(
    config,
    "/rest/v1/founder_facet_settings_view?select=facet_id,values_json&order=facet_id.asc",
    { headers: auth }
  );
  const settingsRows = await settingsResponse.json().catch(() => []);
  if (!settingsResponse.ok) return NextResponse.json(settingsRows, { status: settingsResponse.status });
  const settings = hostedFacetSettings(Array.isArray(settingsRows) ? settingsRows : []);

  const selected = [
    "posted_date","work_mode","location_country","location_city","remote_scope",
    "employment_type","seniority_level","title_family","track","source_id","organization",
    "qualification_decision","fit_score","compensation_min","compensation_max"
  ].join(",");
  const rows: Record<string, unknown>[] = [];
  const pageSize = 500;
  for (let offset = 0; offset < 5000; offset += pageSize) {
    const response = await hostedFetch(
      config,
      `/rest/v1/founder_opportunity_detail?select=${selected}&order=id.asc&offset=${offset}&limit=${pageSize}`,
      { headers: auth }
    );
    const batch = await response.json().catch(() => []);
    if (!response.ok) return NextResponse.json(batch, { status: response.status });
    if (!Array.isArray(batch)) break;
    for (const row of batch) if (row && typeof row === "object") rows.push(row as Record<string, unknown>);
    if (batch.length < pageSize) break;
  }

  const facets = HOSTED_FACET_DEFINITIONS.map((definition) => {
    if (definition.available === false) {
      return {
        facet_id: definition.facet_id,
        value_type: definition.value_type,
        description: definition.description,
        available: false,
        unavailable_reason: definition.unavailable_reason ?? "Unavailable",
        values: [],
        excluded_count: 0,
        include: [],
        exclude: [],
      };
    }

    const current = settings.get(definition.facet_id) ?? { include: [], exclude: [] };
    const counts = new Map<string, number>();
    let excludedCount = 0;
    for (const row of rows) {
      const value = hostedFacetScalar(row, definition.facet_id);
      counts.set(value, (counts.get(value) ?? 0) + 1);
      const hidden = (current.include.length > 0 && !current.include.includes(value)) || current.exclude.includes(value);
      if (hidden) excludedCount += 1;
    }
    const values = [...counts.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([value, count]) => ({
        value,
        count,
        state: current.include.includes(value) ? "include" : current.exclude.includes(value) ? "exclude" : "off",
      }));

    return {
      facet_id: definition.facet_id,
      value_type: definition.value_type,
      description: definition.description,
      available: true,
      unavailable_reason: null,
      values,
      excluded_count: excludedCount,
      include: current.include,
      exclude: current.exclude,
    };
  });
  return NextResponse.json({ facets });
}
async function hostedContract(request: NextRequest, path: string[], token: string, config: HostedConfig): Promise<NextResponse> {
  const subpath = path.join("/"); const method = request.method.toUpperCase(); const url = new URL(request.url);
  if (subpath === "opportunities" && method === "GET") {
    const page = Math.max(1, Number(url.searchParams.get("page") ?? "1") || 1);
    const pageSize = Math.min(200, Math.max(1, Number(url.searchParams.get("page_size") ?? "25") || 25));
    const includeHidden = url.searchParams.get("include_hidden") === "true";
    const buildFeedQuery = (visibility?: "visible" | "hidden") => {
      const query = new URL(`${config.origin}/rest/v1/founder_feed`);
      query.searchParams.set("select", "*");
      query.searchParams.set("is_stale", "eq.false");
      if (visibility === "visible") query.searchParams.set("visible", "eq.true");
      if (visibility === "hidden") query.searchParams.set("visible", "eq.false");
      query.searchParams.set("order", "priority_score.desc.nullslast,fit_score.desc.nullslast,projected_at.desc,opportunity_id.asc");
      for (const [key, column, op] of [["track", "track", "eq"], ["decision", "qualification_decision", "eq"], ["min_score", "fit_score", "gte"], ["source_family", "source_family", "eq"], ["source_id", "source_id", "eq"]] as const) {
        const value = url.searchParams.get(key); if (value) query.searchParams.set(column, `${op}.${value}`);
      }
      const text = url.searchParams.get("q");
      if (text) { const safe = text.replace(/[(),]/g, " "); query.searchParams.set("or", `(title.ilike.*${safe}*,organization.ilike.*${safe}*)`); }
      return query;
    };
    const q = buildFeedQuery(includeHidden ? undefined : "visible");
    q.searchParams.set("offset", String((page - 1) * pageSize)); q.searchParams.set("limit", String(pageSize));
    const response = await hostedFetch(config, `${q.pathname}${q.search}`, { headers: { Authorization: `Bearer ${token}`, Prefer: "count=exact" } });
    const rows = await response.json().catch(() => []); if (!response.ok) return NextResponse.json(rows, { status: response.status });
    const range = response.headers.get("content-range") ?? "*/0"; const total = Number(range.split("/")[1] ?? "0") || 0;
    const hiddenQuery = buildFeedQuery("hidden");
    hiddenQuery.searchParams.set("select", "opportunity_id"); hiddenQuery.searchParams.set("limit", "1");
    const hiddenResponse = await hostedFetch(config, `${hiddenQuery.pathname}${hiddenQuery.search}`, { headers: { Authorization: `Bearer ${token}`, Prefer: "count=exact" } });
    const hiddenRange = hiddenResponse.headers.get("content-range") ?? "*/0";
    const hiddenCount = Number(hiddenRange.split("/")[1] ?? "0") || 0;
    return NextResponse.json({ page, page_size: pageSize, total, hidden_count: hiddenCount, items: Array.isArray(rows) ? rows.map(hostedFeedRow) : [] });
  }
  if (subpath === "worker/poll-now" && method === "POST") { const response = await hostedFetch(config, "/rest/v1/rpc/enqueue_poll_now", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: await request.text() || "{}" }); const payload = await response.json().catch(() => null); if (!response.ok) return NextResponse.json(payload, { status: response.status }); const object = payload && typeof payload === "object" && !Array.isArray(payload) ? payload as Record<string, unknown> : {}; const enqueued = Array.isArray(object.enqueued) ? object.enqueued.filter((item: unknown) => item && typeof item === "object" && "source_id" in item && "job_id" in item) : []; const skipped = Array.isArray(object.skipped) ? object.skipped.filter((item: unknown) => item && typeof item === "object" && "source_id" in item && "reason" in item) : []; return NextResponse.json({ enqueued, skipped }); }
  if (subpath === "sources/health" && method === "GET") { const response = await hostedFetch(config, "/rest/v1/founder_source_health?select=*&order=source_id.asc", { headers: { Authorization: `Bearer ${token}` } }); const rows = await response.json().catch(() => []); if (!response.ok) return NextResponse.json(rows, { status: response.status }); return NextResponse.json({ sources: Array.isArray(rows) ? rows.map((row: Record<string, unknown>) => ({ source_id: row.source_id, name: row.source_id, category: "", read_policy: "allowed", last_poll: row.last_poll_finished_at ?? null, last_status: row.last_poll_status ?? row.last_status ?? null, last_record_count: row.last_raw_ingested ?? null })) : [] }); }
  if (subpath === "sources/overview" && method === "GET") { const response = await hostedFetch(config, "/rest/v1/founder_source_overview?select=*&order=source_family.asc,source_id.asc", { headers: { Authorization: `Bearer ${token}` } }); const rows = await response.json().catch(() => []); if (!response.ok) return NextResponse.json(rows, { status: response.status }); return NextResponse.json({ sources: Array.isArray(rows) ? rows.map((row: Record<string, unknown>) => ({ source_family: row.source_family, source_id: row.source_id ?? null, opportunity_count: Number(row.opportunity_count ?? 0), hidden_count: Number(row.hidden_count ?? 0), last_success_at: row.last_success_at ?? null, last_status: row.last_status ?? null, manual_only: Boolean(row.manual_only) })) : [] }); }
  if (subpath.startsWith("opportunities/") && path.length === 2 && method === "GET") { const id = encodeURIComponent(path[1]); const response = await hostedFetch(config, `/rest/v1/founder_opportunity_detail?id=eq.${id}&select=*`, { headers: { Authorization: `Bearer ${token}` } }); const rows = await response.json().catch(() => []); if (!response.ok) return NextResponse.json(rows, { status: response.status }); if (!Array.isArray(rows) || !rows.length) return hostedError("opportunity not found", 404); return NextResponse.json(hostedDetail(rows[0] as Record<string, unknown>)); }
  if (["filters", "facets", "saved-views"].includes(subpath) && method === "GET") {
    const view = subpath === "filters" ? "founder_filters" : subpath === "facets" ? "founder_facet_settings_view" : "founder_saved_view_records";
    const response = await hostedFetch(config, `/rest/v1/${view}?select=*`, { headers: { Authorization: `Bearer ${token}` } });
    const rows = await response.json().catch(() => []); if (!response.ok) return NextResponse.json(rows, { status: response.status });
    if (subpath === "filters") return NextResponse.json({ filters: Array.isArray(rows) ? rows.map((row: Record<string, unknown>) => ({ filter_id: row.filter_id, enabled: Boolean(row.enabled), mode: row.mode, params: typeof row.params_json === "string" ? JSON.parse(row.params_json) : {}, affected_count: 0, description: "", unavailable_reason: null })) : [] });
    if (subpath === "facets") return hostedFacetPayload(config, token);
    return NextResponse.json({ views: Array.isArray(rows) ? rows.map((row: Record<string, unknown>) => ({ id: row.id, name: row.name, facets: typeof row.facets_json === "string" ? JSON.parse(row.facets_json) : {}, search_query: row.search_query ?? null, is_default: Boolean(row.is_default) })) : [] });
  }
  if (subpath === "truth/status" && method === "GET") {
    const hash = runtimeEnv().NEXT_PUBLIC_TRUTH_PACK_HASH?.trim() || null;
    return NextResponse.json({ loaded: Boolean(hash), hash, path: "hosted-private-truth-pack", validator: { ok: Boolean(hash), error_count: 0, findings: [] }, sections: [] });
  }
  if (subpath === "dashboard/daily" && method === "GET") {
    const days = Math.max(1, Math.min(31, Number(new URL(request.url).searchParams.get("days") ?? "7") || 7));
    const response = await hostedFetch(config, "/rest/v1/rpc/founder_dashboard_daily", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify({ p_days: days, p_high_fit_threshold: 80 }) });
    const rows = await response.json().catch(() => []); if (!response.ok) return NextResponse.json(rows, { status: response.status });
    return NextResponse.json({ days, high_fit_threshold: 80, series: Array.isArray(rows) ? rows.map((row: Record<string, unknown>) => ({ date: row.date, fetched: Number(row.fetched ?? 0), unique_new: Number(row.unique_new ?? 0), qualified: Number(row.qualified ?? 0), high_fit: Number(row.high_fit ?? 0), opened: Number(row.opened ?? 0), labelled: Number(row.labelled ?? 0), applied: Number(row.applied ?? 0), hidden_by_filters: Number(row.hidden_by_filters ?? 0) })) : [] });
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
    const download = new URL(request.url).searchParams.get("download") === "true";
    const extension = requested.includes("pdf") ? "pdf" : requested.includes("docx") ? "docx" : "bin";
    const disposition = download || !requested.includes("pdf")
      ? `attachment; filename="opportunity-${path[1]}-${isCv ? "cv" : "artifact"}.${extension}"`
      : "inline";
    return new NextResponse(bytes, { status: 200, headers: { "Content-Type": contentType, "Cache-Control": "private, no-store", "Content-Disposition": disposition } });
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
  const env = runtimeEnv();
  const configuredOrigin = env.OPPORTUNITYOS_API_ORIGIN?.trim();
  const cloudEdge = env.OPPORTUNITYOS_CLOUD_EDGE === "1";

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
    const port = env.OPPORTUNITYOS_API_PORT || "8000";
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
