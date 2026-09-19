import { NextRequest, NextResponse } from "next/server";

const ACCESS_COOKIE = "opos_sb_access";
const REFRESH_COOKIE = "opos_sb_refresh";
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

type JsonRecord = Record<string, unknown>;

function runtimeConfig(): { url: string; key: string } | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim().replace(/\/+$/, "");
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!url || !key || !url.startsWith("https://")) return null;
  return { url, key };
}

function json(body: unknown, status = 200) {
  return NextResponse.json(body, { status });
}

function safeJson<T>(value: unknown, fallback: T): T {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "object") return value as T;
  try {
    return JSON.parse(String(value)) as T;
  } catch {
    return fallback;
  }
}

function asStringArray(value: unknown): string[] {
  const parsed = safeJson<unknown>(value, []);
  return Array.isArray(parsed) ? parsed.map((item) => String(item)) : [];
}

function publicHeaders(config: { key: string }, token?: string, extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  headers.set("apikey", config.key);
  headers.set("Accept", headers.get("Accept") ?? "application/json");
  if (token) headers.set("Authorization", "Bearer " + token);
  return headers;
}

async function supabaseFetch(
  config: { url: string; key: string },
  path: string,
  init: RequestInit = {},
  token?: string
) {
  return fetch(config.url + path, {
    ...init,
    headers: publicHeaders(config, token, init.headers),
  });
}

function accessToken(request: NextRequest): string | null {
  const authorization = request.headers.get("authorization");
  if (authorization?.toLowerCase().startsWith("bearer ")) {
    return authorization.slice(7).trim() || null;
  }
  return request.cookies.get(ACCESS_COOKIE)?.value ?? null;
}

function setSessionCookies(response: NextResponse, payload: JsonRecord) {
  const access = typeof payload.access_token === "string" ? payload.access_token : "";
  const refresh = typeof payload.refresh_token === "string" ? payload.refresh_token : "";
  const expiresIn = Number(payload.expires_in ?? 3600);
  if (access) {
    response.cookies.set(ACCESS_COOKIE, access, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: Number.isFinite(expiresIn) && expiresIn > 0 ? expiresIn : 3600,
    });
  }
  if (refresh) {
    response.cookies.set(REFRESH_COOKIE, refresh, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 30,
    });
  }
}

function clearSessionCookies(response: NextResponse) {
  response.cookies.set(ACCESS_COOKIE, "", {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  response.cookies.set(REFRESH_COOKIE, "", {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
}

async function readJsonBody(request: NextRequest): Promise<JsonRecord> {
  try {
    const body = await request.json();
    return body && typeof body === "object" ? (body as JsonRecord) : {};
  } catch {
    return {};
  }
}

async function login(request: NextRequest, config: { url: string; key: string }) {
  const body = await readJsonBody(request);
  const email = typeof body.email === "string" ? body.email.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!email || !password) return json({ detail: "email and password are required" }, 400);

  const auth = await supabaseFetch(
    config,
    "/auth/v1/token?grant_type=password",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }
  );
  if (!auth.ok) {
    return json({ detail: auth.status === 429 ? "too many attempts" : "invalid credentials" }, auth.status === 429 ? 429 : 401);
  }
  const payload = (await auth.json()) as JsonRecord;
  const response = json({ authenticated: true });
  setSessionCookies(response, payload);
  return response;
}

async function me(request: NextRequest, config: { url: string; key: string }) {
  const token = accessToken(request);
  if (token) {
    const current = await supabaseFetch(config, "/auth/v1/user", { method: "GET" }, token);
    if (current.ok) return json({ authenticated: true });
  }

  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  if (!refresh) {
    const response = json({ authenticated: false }, 401);
    clearSessionCookies(response);
    return response;
  }
  const refreshed = await supabaseFetch(
    config,
    "/auth/v1/token?grant_type=refresh_token",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    }
  );
  if (!refreshed.ok) {
    const response = json({ authenticated: false }, 401);
    clearSessionCookies(response);
    return response;
  }
  const payload = (await refreshed.json()) as JsonRecord;
  const response = json({ authenticated: true });
  setSessionCookies(response, payload);
  return response;
}

async function logout(request: NextRequest, config: { url: string; key: string }) {
  const token = accessToken(request);
  if (token) {
    await supabaseFetch(config, "/auth/v1/logout", { method: "POST" }, token).catch(() => undefined);
  }
  const response = json({ authenticated: false });
  clearSessionCookies(response);
  return response;
}

function topReasons(row: JsonRecord): string[] {
  const reasons = safeJson<Array<{ text?: unknown }>>(row.reasons_json, []);
  return Array.isArray(reasons)
    ? reasons.map((item) => String(item?.text ?? "")).filter(Boolean).slice(0, 5)
    : [];
}

function listItem(row: JsonRecord) {
  return {
    id: String(row.opportunity_id ?? row.id ?? ""),
    title: String(row.title ?? ""),
    organization: String(row.organization ?? ""),
    source_id: String(row.source_id ?? ""),
    source_url: String(row.source_url ?? ""),
    track: String(row.track ?? "employment"),
    decision: row.qualification_decision ?? null,
    fit_score: row.fit_score === null || row.fit_score === undefined ? null : Number(row.fit_score),
    top_reasons: topReasons(row),
    deadline: row.deadline ?? null,
    posted_date: row.posted_date ?? null,
    is_stale: Boolean(row.is_stale),
    action_state: null,
    feedback_label: null,
    hidden_by: row.visible === false ? asStringArray(row.visibility_reason) : [],
    flagged_by: [],
    work_mode: String(row.work_mode ?? "unspecified"),
    work_mode_source: null,
    location_country: row.location_country ?? null,
    location_city: row.location_city ?? null,
    location_region: row.location_region ?? null,
    remote_scope: String(row.remote_scope ?? "unspecified"),
    remote_scope_regions: asStringArray(row.remote_scope_regions),
    employment_type: String(row.employment_type ?? "unspecified"),
    seniority_level: String(row.seniority_level ?? "unspecified"),
    compensation_min: null,
    compensation_max: null,
    compensation_currency: null,
    compensation_period: null,
    title_family: row.title_family ?? null,
    title_level: null,
    family_key: null,
    family_size: null,
  };
}

function parseTotal(contentRange: string | null, fallback: number): number {
  if (!contentRange) return fallback;
  const slash = contentRange.lastIndexOf("/");
  if (slash < 0) return fallback;
  const raw = contentRange.slice(slash + 1);
  if (raw === "*") return fallback;
  const value = Number(raw);
  return Number.isFinite(value) ? value : fallback;
}

function sanitizedSearch(value: string): string {
  return value.replace(/[,%()]/g, " ").trim().slice(0, 160);
}

async function listOpportunities(request: NextRequest, config: { url: string; key: string }, token: string) {
  const url = new URL(request.url);
  const page = Math.max(1, Number(url.searchParams.get("page") ?? 1) || 1);
  const pageSize = Math.min(100, Math.max(1, Number(url.searchParams.get("page_size") ?? 50) || 50));
  const includeHidden = url.searchParams.get("include_hidden") === "true";
  const query = new URLSearchParams();
  query.set("select", "*");
  if (!includeHidden) query.set("visible", "eq.true");
  const track = url.searchParams.get("track");
  const decision = url.searchParams.get("decision");
  const minScore = url.searchParams.get("min_score");
  const search = sanitizedSearch(url.searchParams.get("q") ?? "");
  if (track) query.set("track", "eq." + track);
  if (decision) query.set("qualification_decision", "eq." + decision);
  if (minScore && Number.isFinite(Number(minScore))) query.set("fit_score", "gte." + String(Number(minScore)));
  if (search) query.set("or", "(title.ilike.*" + search + "*,organization.ilike.*" + search + "*)");
  query.set("order", "priority_score.desc.nullslast,projected_at.desc");
  query.set("limit", String(pageSize));
  query.set("offset", String((page - 1) * pageSize));

  const response = await supabaseFetch(
    config,
    "/rest/v1/founder_feed?" + query.toString(),
    { headers: { Prefer: "count=exact" } },
    token
  );
  if (!response.ok) return json({ detail: "feed unavailable" }, response.status === 401 ? 401 : 502);
  const rows = (await response.json()) as JsonRecord[];
  const total = parseTotal(response.headers.get("content-range"), rows.length);

  const hiddenQuery = new URLSearchParams({
    select: "opportunity_id",
    visible: "eq.false",
    limit: "1",
  });
  const hiddenResponse = await supabaseFetch(
    config,
    "/rest/v1/founder_feed?" + hiddenQuery.toString(),
    { headers: { Prefer: "count=exact", Range: "0-0" } },
    token
  );
  const hiddenCount = hiddenResponse.ok
    ? parseTotal(hiddenResponse.headers.get("content-range"), 0)
    : 0;

  return json({
    page,
    page_size: pageSize,
    total,
    hidden_count: hiddenCount,
    items: rows.map(listItem),
  });
}

function detailPayload(row: JsonRecord) {
  const evaluationDetail = safeJson<JsonRecord>(row.evaluation_detail_json, {});
  const hard = Array.isArray(evaluationDetail.hard_constraints)
    ? (evaluationDetail.hard_constraints as JsonRecord[])
    : [];
  const dimensions = safeJson<JsonRecord[]>(row.dimension_scores_json, []);
  const constraintPayload = hard.map((item) => ({
    constraint_name: String(item.constraint_name ?? ""),
    outcome: item.passed === true ? "PASS" : item.passed === false ? "FAIL" : "UNKNOWN",
    reason: String(item.reason ?? ""),
    required_field: item.required_field ?? null,
    founder_fact: item.founder_fact ?? null,
    is_hard_failure: Boolean(item.is_hard_failure),
    provenance_pointer: item.provenance_pointer ?? null,
  }));
  const dimensionPayload = (Array.isArray(dimensions) ? dimensions : []).map((item) => ({
    dimension: String(item.dimension_name ?? item.dimension ?? ""),
    score: Number(item.raw_score ?? item.score ?? 0),
    weight: Number(item.weight ?? 0),
    weighted_score: Number(item.weighted_score ?? 0),
    rationale: String(item.explanation ?? item.rationale ?? ""),
  }));

  return {
    ...listItem(row),
    description: String(row.description ?? ""),
    fields: [],
    qualification: {
      decision: row.qualification_decision ?? null,
      constraints: constraintPayload,
    },
    scoring: {
      fit_score: row.fit_score === null || row.fit_score === undefined ? null : Number(row.fit_score),
      dimension_scores: dimensionPayload,
      strengths: Array.isArray(evaluationDetail.strengths) ? evaluationDetail.strengths : [],
      gaps: Array.isArray(evaluationDetail.gaps) ? evaluationDetail.gaps : [],
      unknowns: Array.isArray(evaluationDetail.unknowns) ? evaluationDetail.unknowns : [],
      uncertainty_penalty: Number(evaluationDetail.uncertainty_penalty ?? 0),
      explanation: String(evaluationDetail.explanation ?? ""),
      policy_version: String(row.policy_version ?? ""),
      evaluated_at: String(row.evaluated_at ?? ""),
      truth_pack_hash: row.truth_pack_hash ?? null,
    },
    evidence_links: row.source_url ? [String(row.source_url)] : [],
    action_history: [],
    feedback_history: [],
    reverified_at: row.reverified_at ?? null,
  };
}

async function oneFeedRow(config: { url: string; key: string }, token: string, opportunityId: string, select = "*") {
  const query = new URLSearchParams({
    select,
    opportunity_id: "eq." + opportunityId,
    limit: "1",
  });
  const response = await supabaseFetch(config, "/rest/v1/founder_feed?" + query.toString(), {}, token);
  if (!response.ok) return { response, row: null as JsonRecord | null };
  const rows = (await response.json()) as JsonRecord[];
  return { response, row: rows[0] ?? null };
}

async function opportunityDetail(config: { url: string; key: string }, token: string, opportunityId: string) {
  const result = await oneFeedRow(config, token, opportunityId);
  if (!result.response.ok) return json({ detail: "detail unavailable" }, result.response.status === 401 ? 401 : 502);
  if (!result.row) return json({ detail: "opportunity not found" }, 404);
  return json(detailPayload(result.row));
}

async function pollNow(config: { url: string; key: string }, token: string, request: NextRequest) {
  const body = await readJsonBody(request);
  const sourceId = typeof body.source_id === "string" && body.source_id.trim() ? body.source_id.trim() : null;
  const response = await supabaseFetch(
    config,
    "/rest/v1/rpc/enqueue_poll_now",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ p_source_id: sourceId }),
    },
    token
  );
  if (!response.ok) return json({ detail: "poll enqueue failed" }, response.status === 401 ? 401 : 502);
  const rows = (await response.json()) as JsonRecord[];
  return json({
    enqueued: (Array.isArray(rows) ? rows : []).map((row) => ({
      source_id: sourceId ?? "due",
      job_id: String(row.job_id ?? ""),
    })),
    skipped: [],
  });
}

async function sourceHealth(config: { url: string; key: string }, token: string) {
  const response = await supabaseFetch(
    config,
    "/rest/v1/founder_source_health?select=*&order=source_id.asc",
    {},
    token
  );
  if (!response.ok) return json({ detail: "source health unavailable" }, response.status === 401 ? 401 : 502);
  const rows = (await response.json()) as JsonRecord[];
  return json({
    sources: rows.map((row) => ({
      source_id: String(row.source_id ?? ""),
      name: String(row.source_id ?? ""),
      category: "registered",
      read_policy: row.read_allowed === true ? "allowed" : "disabled",
      last_poll: row.last_poll_finished_at ?? row.last_poll_started_at ?? null,
      last_status: row.last_poll_status ?? row.last_status ?? null,
      last_record_count: null,
    })),
  });
}

function facetDefinitions() {
  return [
    ["track", "Track"],
    ["opportunity_type", "Opportunity type"],
    ["title_family", "Title family"],
    ["seniority_level", "Seniority"],
    ["work_mode", "Work mode"],
    ["location_country", "Country"],
    ["location_city", "City"],
    ["location_region", "Region"],
    ["remote_scope", "Remote scope"],
    ["employment_type", "Employment type"],
    ["qualification_decision", "Decision"],
    ["source_id", "Source"],
    ["selected_cv_variant", "Selected CV"],
    ["organization", "Organization"],
  ] as const;
}

async function facets(config: { url: string; key: string }, token: string) {
  const fields = facetDefinitions().map(([id]) => id).join(",");
  const response = await supabaseFetch(
    config,
    "/rest/v1/founder_feed?select=" + encodeURIComponent(fields) + "&limit=1000",
    {},
    token
  );
  if (!response.ok) return json({ detail: "facets unavailable" }, response.status === 401 ? 401 : 502);
  const rows = (await response.json()) as JsonRecord[];
  const payload = facetDefinitions().map(([id, description]) => {
    const counts = new Map<string, number>();
    for (const row of rows) {
      const raw = row[id];
      if (raw === null || raw === undefined || raw === "") continue;
      const value = String(raw);
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }
    return {
      facet_id: id,
      value_type: "enum",
      description,
      available: true,
      unavailable_reason: null,
      values: Array.from(counts.entries())
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .slice(0, 100)
        .map(([value, count]) => ({ value, count, state: "off" })),
      excluded_count: 0,
      include: [],
      exclude: [],
    };
  });
  payload.push({
    facet_id: "language",
    value_type: "string",
    description: "Language",
    available: false,
    unavailable_reason: "No language field is persisted on opportunities.",
    values: [],
    excluded_count: 0,
    include: [],
    exclude: [],
  });
  return json({ facets: payload });
}

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

async function authenticatedStorage(
  config: { url: string; key: string },
  token: string,
  bucket: string,
  objectPath: string
) {
  const path = objectPath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return fetch(
    config.url + "/storage/v1/object/authenticated/" + encodeURIComponent(bucket) + "/" + path,
    { headers: publicHeaders(config, token) }
  );
}

async function verifiedStorageResponse(
  storageResponse: Response,
  expectedSha: string,
  filename: string,
  download: boolean,
  contentType = "application/octet-stream"
) {
  if (!storageResponse.ok) return json({ detail: "private artifact unavailable" }, storageResponse.status);
  const bytes = await storageResponse.arrayBuffer();
  const actualSha = await sha256Hex(bytes);
  if (!expectedSha || actualSha !== expectedSha.toLowerCase()) {
    return json({ detail: "artifact integrity verification failed" }, 409);
  }
  const headers = new Headers({
    "Content-Type": contentType,
    "Content-Length": String(bytes.byteLength),
    "Content-Disposition": (download ? "attachment" : "inline") + '; filename="' + filename.replace(/"/g, "") + '"',
    "Cache-Control": "private, no-store",
  });
  return new NextResponse(bytes, { status: 200, headers });
}

async function fixedCv(
  config: { url: string; key: string },
  token: string,
  opportunityId: string,
  download: boolean
) {
  const result = await oneFeedRow(
    config,
    token,
    opportunityId,
    "selected_cv_variant,selected_cv_object_path,selected_cv_sha256"
  );
  if (!result.response.ok) return json({ detail: "CV selection unavailable" }, 502);
  if (!result.row) return json({ detail: "opportunity not found" }, 404);
  const objectPath = String(result.row.selected_cv_object_path ?? "");
  const expectedSha = String(result.row.selected_cv_sha256 ?? "");
  if (!objectPath || !expectedSha) {
    return json({ detail: "fixed CV selection is not materialized for this opportunity" }, 409);
  }
  const storage = await authenticatedStorage(config, token, "founder-cv-portfolio", objectPath);
  const filename = objectPath.split("/").pop() || "OpportunityOS-CV.pdf";
  const response = await verifiedStorageResponse(storage, expectedSha, filename, download, "application/pdf");
  if (response.ok) {
    const clone = response.clone();
    const prefix = new Uint8Array(await clone.arrayBuffer()).slice(0, 4);
    if (prefix.length < 4 || prefix[0] !== 0x25 || prefix[1] !== 0x50 || prefix[2] !== 0x44 || prefix[3] !== 0x46) {
      return json({ detail: "fixed CV is not a valid PDF" }, 409);
    }
  }
  return response;
}

async function generatedArtifact(
  config: { url: string; key: string },
  token: string,
  opportunityId: string,
  kind: "cover-letter" | "cover-letter-pdf",
  template: string,
  download: boolean
) {
  const query = new URLSearchParams({
    select: "object_key,payload_sha256,size_bytes,content_type,storage_backend",
    opportunity_id: "eq." + opportunityId,
    artifact_kind: "eq." + kind,
    template_id: "eq." + template,
    order: "created_at.desc",
    limit: "1",
  });
  const meta = await supabaseFetch(
    config,
    "/rest/v1/founder_artifact_metadata?" + query.toString(),
    {},
    token
  );
  if (!meta.ok) return json({ detail: "artifact metadata unavailable" }, meta.status === 401 ? 401 : 502);
  const rows = (await meta.json()) as JsonRecord[];
  const row = rows[0];
  if (!row) return json({ detail: "artifact not generated" }, 404);
  if (row.storage_backend !== "supabase_storage" || !row.object_key || !row.payload_sha256) {
    return json({ detail: "artifact is not available in durable private storage" }, 409);
  }
  const storage = await authenticatedStorage(config, token, "opportunity-artifacts", String(row.object_key));
  const extension = kind === "cover-letter-pdf" ? "pdf" : "docx";
  return verifiedStorageResponse(
    storage,
    String(row.payload_sha256),
    "cover-letter-" + opportunityId + "." + extension,
    download,
    String(row.content_type ?? (extension === "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
  );
}

async function nativeRequest(
  request: NextRequest,
  subpath: string,
  config: { url: string; key: string }
) {
  const method = request.method.toUpperCase();

  if (subpath === "auth/login" && method === "POST") return login(request, config);
  if (subpath === "auth/me" && method === "GET") return me(request, config);
  if ((subpath === "auth/logout" || subpath === "auth/logout-all") && method === "POST") {
    return logout(request, config);
  }

  const token = accessToken(request);
  if (!token) return json({ detail: "authentication required" }, 401);

  if (subpath === "opportunities" && method === "GET") return listOpportunities(request, config, token);

  const detailMatch = /^opportunities\/([^/]+)$/.exec(subpath);
  if (detailMatch && method === "GET") {
    return opportunityDetail(config, token, decodeURIComponent(detailMatch[1]));
  }

  const cvMatch = /^opportunities\/([^/]+)\/artifacts\/cv-final\.pdf$/.exec(subpath);
  if (cvMatch && method === "GET") {
    const download = new URL(request.url).searchParams.get("download") === "true";
    return fixedCv(config, token, decodeURIComponent(cvMatch[1]), download);
  }

  const coverPdf = /^opportunities\/([^/]+)\/artifacts\/cover-letter\.pdf$/.exec(subpath);
  if (coverPdf && method === "GET") {
    const url = new URL(request.url);
    return generatedArtifact(
      config,
      token,
      decodeURIComponent(coverPdf[1]),
      "cover-letter-pdf",
      url.searchParams.get("template") || "classic",
      url.searchParams.get("download") === "true"
    );
  }

  const coverDocx = /^opportunities\/([^/]+)\/artifacts\/cover-letter\.docx$/.exec(subpath);
  if (coverDocx && method === "GET") {
    const url = new URL(request.url);
    return generatedArtifact(
      config,
      token,
      decodeURIComponent(coverDocx[1]),
      "cover-letter",
      url.searchParams.get("template") || "classic",
      true
    );
  }

  if (/^opportunities\/[^/]+\/artifacts\/cover-letter\/omitted$/.test(subpath) && method === "GET") {
    return json({ detail: "omitted-item metadata is not materialized in the hosted artifact index" }, 501);
  }

  if (subpath === "worker/poll-now" && method === "POST") return pollNow(config, token, request);
  if (subpath === "sources/health" && method === "GET") return sourceHealth(config, token);
  if (subpath === "facets" && method === "GET") return facets(config, token);
  if (/^facets\//.test(subpath) && method === "PUT") {
    return json({ detail: "hosted facet mutation is not yet available" }, 501);
  }
  if (subpath === "saved-views" && method === "GET") return json({ views: [] });
  if (/^saved-views/.test(subpath)) return json({ detail: "hosted saved-view mutation is not yet available" }, 501);
  if (subpath === "filters" && method === "GET") return json({ filters: [] });
  if (/^filters\//.test(subpath)) return json({ detail: "hosted filter mutation is not yet available" }, 501);
  if (subpath === "hidden-reasons" && method === "GET") return json({ reasons: [] });
  if (subpath === "dashboard/daily" && method === "GET") {
    const days = Math.min(90, Math.max(1, Number(new URL(request.url).searchParams.get("days") ?? 7) || 7));
    return json({ days, high_fit_threshold: 70, series: [] });
  }
  if ((subpath === "truth/status" || subpath === "truth/reload") && (method === "GET" || method === "POST")) {
    return json({
      loaded: true,
      hash: null,
      path: "repository:founder/truth_pack.yaml.gz.b64",
      validator: { ok: true, error_count: 0, findings: [] },
      sections: [],
    });
  }

  return json({ detail: "hosted route is not implemented" }, 501);
}

async function proxyRequest(
  request: NextRequest,
  subpath: string,
  targetOrigin: string
) {
  const url = new URL(request.url);
  const targetUrl = targetOrigin + "/api/" + subpath + url.search;
  const forwardHeaders = new Headers();
  request.headers.forEach((value, key) => {
    if (!FORBIDDEN_HEADERS.has(key.toLowerCase())) forwardHeaders.set(key, value);
  });
  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();
  try {
    const upstream = await fetch(targetUrl, { method, headers: forwardHeaders, body, redirect: "manual" });
    const responseHeaders = new Headers();
    upstream.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (!FORBIDDEN_HEADERS.has(lower) && lower !== "set-cookie") responseHeaders.append(key, value);
    });
    const cookies = upstream.headers as Headers & { getSetCookie?: () => string[] };
    for (const cookie of cookies.getSetCookie?.() ?? []) responseHeaders.append("set-cookie", cookie);
    if (!cookies.getSetCookie) {
      const cookie = upstream.headers.get("set-cookie");
      if (cookie) responseHeaders.append("set-cookie", cookie);
    }
    return new NextResponse(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers: responseHeaders });
  } catch {
    return json({ detail: "upstream API unavailable" }, 502);
  }
}

async function route(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const subpath = path.join("/");
  const configuredOrigin = process.env.OPPORTUNITYOS_API_ORIGIN?.trim();

  if (configuredOrigin) {
    try {
      const parsed = new URL(configuredOrigin);
      if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) {
        return json({ detail: "OPPORTUNITYOS_API_ORIGIN must be a credential-free HTTPS origin" }, 500);
      }
      return proxyRequest(request, subpath, parsed.origin);
    } catch {
      return json({ detail: "OPPORTUNITYOS_API_ORIGIN is invalid" }, 500);
    }
  }

  const config = runtimeConfig();
  if (config) return nativeRequest(request, subpath, config);

  if (process.env.OPPORTUNITYOS_CLOUD_EDGE === "1") {
    return json({ detail: "Supabase public runtime configuration is required on the cloud edge" }, 500);
  }
  const port = process.env.OPPORTUNITYOS_API_PORT || "8000";
  return proxyRequest(request, subpath, "http://localhost:" + port);
}

export const GET = route;
export const POST = route;
export const PUT = route;
export const PATCH = route;
export const DELETE = route;
export const HEAD = route;
export const OPTIONS = route;
