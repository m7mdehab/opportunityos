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

function extractAuthToken(request: NextRequest): string | null {
  const authHeader = request.headers.get("authorization");
  if (authHeader && authHeader.toLowerCase().startsWith("bearer ")) {
    return authHeader.slice(7).trim();
  }
  const cookies = request.cookies;
  const tokenCookie =
    cookies.get("sb-access-token")?.value ||
    cookies.get("sb_access_token")?.value ||
    cookies.get("session")?.value;
  return tokenCookie || null;
}

async function handleSupabaseNativeRequest(
  request: NextRequest,
  subpath: string,
  url: URL,
  supabaseUrl: string,
  anonKey: string
): Promise<NextResponse> {
  const method = request.method.toUpperCase();
  const token = extractAuthToken(request);

  // Common headers for Supabase API calls
  const supabaseHeaders: Record<string, string> = {
    apikey: anonKey,
    Accept: "application/json",
  };
  if (token) {
    supabaseHeaders["Authorization"] = `Bearer ${token}`;
  } else {
    supabaseHeaders["Authorization"] = `Bearer ${anonKey}`;
  }

  // 1. Auth: Login
  if (subpath === "auth/login" && method === "POST") {
    let body: { email?: string; password?: string } = {};
    try {
      body = (await request.json()) as { email?: string; password?: string };
    } catch {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }

    const email = body.email || process.env.E2E_FOUNDER_EMAIL || "founder@opportunityos.local";
    const password = body.password || "";

    if (!password) {
      return NextResponse.json({ error: "Password is required" }, { status: 400 });
    }

    const authRes = await fetch(`${supabaseUrl}/auth/v1/token?grant_type=password`, {
      method: "POST",
      headers: {
        apikey: anonKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, password }),
    });

    if (!authRes.ok) {
      return NextResponse.json({ error: "Invalid credentials" }, { status: 401 });
    }

    const authData = (await authRes.json()) as { access_token: string; refresh_token?: string };
    const res = NextResponse.json({
      authenticated: true,
      access_token: authData.access_token,
    });

    res.cookies.set("sb-access-token", authData.access_token, {
      httpOnly: true,
      secure: url.protocol === "https:",
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 7, // 7 days
    });

    return res;
  }

  // 2. Auth: Me
  if (subpath === "auth/me" && method === "GET") {
    if (!token) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const userRes = await fetch(`${supabaseUrl}/auth/v1/user`, {
      headers: {
        apikey: anonKey,
        Authorization: `Bearer ${token}`,
      },
    });

    if (!userRes.ok) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const userData = await userRes.json();
    return NextResponse.json({ authenticated: true, user: userData });
  }

  // 3. Auth: Logout
  if ((subpath === "auth/logout" || subpath === "auth/logout-all") && method === "POST") {
    if (token) {
      await fetch(`${supabaseUrl}/auth/v1/logout`, {
        method: "POST",
        headers: {
          apikey: anonKey,
          Authorization: `Bearer ${token}`,
        },
      }).catch(() => undefined);
    }

    const res = NextResponse.json({ authenticated: false });
    res.cookies.delete("sb-access-token");
    res.cookies.delete("session");
    return res;
  }

  // Enforce authentication for protected application endpoints
  if (!token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // 4. Opportunities: List & Pagination
  if (subpath === "opportunities" && method === "GET") {
    const page = parseInt(url.searchParams.get("page") || "1", 10);
    const pageSize = parseInt(url.searchParams.get("page_size") || "25", 10);
    const offset = Math.max(0, (page - 1) * pageSize);
    const q = url.searchParams.get("q");

    let queryParams = `select=*&limit=${pageSize}&offset=${offset}&order=fit_score.desc.nullslast`;
    if (q) {
      queryParams += `&title=ilike.*${encodeURIComponent(q)}*`;
    }

    const feedRes = await fetch(`${supabaseUrl}/rest/v1/founder_feed?${queryParams}`, {
      headers: {
        ...supabaseHeaders,
        Prefer: "count=exact",
      },
    });

    if (!feedRes.ok) {
      return NextResponse.json(
        { error: "Failed to fetch feed projection" },
        { status: feedRes.status }
      );
    }

    const items = (await feedRes.json()) as unknown[];
    const contentRange = feedRes.headers.get("content-range") || "";
    let total = items.length;
    if (contentRange.includes("/")) {
      const parsedTotal = parseInt(contentRange.split("/")[1], 10);
      if (!isNaN(parsedTotal)) total = parsedTotal;
    }

    return NextResponse.json({
      items,
      total,
      page,
      page_size: pageSize,
    });
  }

  // 5. Opportunities: Detail
  const detailMatch = /^opportunities\/([^/]+)$/.exec(subpath);
  if (detailMatch && method === "GET") {
    const id = detailMatch[1];
    const detailRes = await fetch(
      `${supabaseUrl}/rest/v1/founder_feed?id=eq.${encodeURIComponent(id)}&select=*`,
      { headers: supabaseHeaders }
    );
    if (!detailRes.ok) {
      return NextResponse.json({ error: "Opportunity not found" }, { status: detailRes.status });
    }
    const items = (await detailRes.json()) as unknown[];
    if (!Array.isArray(items) || items.length === 0) {
      return NextResponse.json({ error: "Opportunity not found" }, { status: 404 });
    }
    return NextResponse.json(items[0]);
  }

  // 6. Opportunities: Artifacts (Fixed CV & generated artifacts)
  const artifactMatch = /^opportunities\/([^/]+)\/artifacts\/(.+)$/.exec(subpath);
  if (artifactMatch && method === "GET") {
    const [, oppId, rawFilename] = artifactMatch;
    const isDownload = url.searchParams.get("download") === "true";
    const filename = rawFilename.split("?")[0];

    // Try opportunity-artifacts bucket first
    let storageRes = await fetch(
      `${supabaseUrl}/storage/v1/object/authenticated/opportunity-artifacts/${oppId}/${filename}`,
      { headers: supabaseHeaders }
    );

    // If 404 and looking for cv-final.pdf, check founder-truth-pack bucket
    if (!storageRes.ok && filename === "cv-final.pdf") {
      storageRes = await fetch(
        `${supabaseUrl}/storage/v1/object/authenticated/founder-truth-pack/cv-final.pdf`,
        { headers: supabaseHeaders }
      );
    }

    if (!storageRes.ok) {
      return NextResponse.json({ error: "Artifact not found" }, { status: 404 });
    }

    const contentType =
      storageRes.headers.get("content-type") ||
      (filename.endsWith(".pdf")
        ? "application/pdf"
        : filename.endsWith(".docx")
        ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        : "application/octet-stream");

    const disposition = isDownload
      ? `attachment; filename="${filename}"`
      : `inline; filename="${filename}"`;

    return new NextResponse(storageRes.body, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": disposition,
      },
    });
  }

  // 7. Worker: Async Poll Now
  if (subpath === "worker/poll-now" && method === "POST") {
    const pollRes = await fetch(`${supabaseUrl}/rest/v1/rpc/enqueue_poll_now`, {
      method: "POST",
      headers: {
        ...supabaseHeaders,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });

    if (!pollRes.ok) {
      return NextResponse.json(
        { error: "Failed to enqueue poll job" },
        { status: pollRes.status }
      );
    }

    return NextResponse.json({
      enqueued: ["poll_source"],
      skipped: [],
    });
  }

  // 8. Facets
  if (subpath === "facets" && method === "GET") {
    return NextResponse.json({
      facets: [
        { facet_id: "track", values: ["employment", "independent"] },
        { facet_id: "work_mode", values: ["remote", "hybrid", "onsite"] },
      ],
    });
  }

  // 9. Sources Health
  if (subpath === "sources/health" && method === "GET") {
    return NextResponse.json({
      status: "healthy",
      sources: [],
    });
  }

  // Fallback: PostgREST pass-through
  const restUrl = `${supabaseUrl}/rest/v1/${subpath}${url.search}`;
  const passRes = await fetch(restUrl, {
    method,
    headers: supabaseHeaders,
    body: method !== "GET" && method !== "HEAD" ? await request.arrayBuffer() : undefined,
  });

  return new NextResponse(passRes.body, {
    status: passRes.status,
    headers: {
      "Content-Type": passRes.headers.get("content-type") || "application/json",
    },
  });
}

async function proxyRequest(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const subpath = path.join("/");
  const url = new URL(request.url);

  const configuredOrigin = process.env.OPPORTUNITYOS_API_ORIGIN?.trim();
  const cloudEdge = process.env.OPPORTUNITYOS_CLOUD_EDGE === "1";
  const supabaseUrl = (
    process.env.NEXT_PUBLIC_SUPABASE_URL ||
    process.env.SUPABASE_URL
  )?.trim();
  const supabaseAnonKey = (
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.SUPABASE_ANON_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
  )?.trim();

  // Route 1: Explicit HTTPS API Origin provided (e.g. standalone API host)
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
    const targetUrl = `${parsed.origin}/api/${subpath}${url.search}`;

    const forwardHeaders = new Headers();
    request.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (!FORBIDDEN_HEADERS.has(lower)) {
        forwardHeaders.set(key, value);
      }
    });

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

      const resHeaders = new Headers();
      upstreamRes.headers.forEach((value, key) => {
        const lower = key.toLowerCase();
        if (!FORBIDDEN_HEADERS.has(lower) && lower !== "set-cookie") {
          resHeaders.append(key, value);
        }
      });

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

  // Route 2: Supabase-native deployment path (ADR-0023 zero-dollar architecture)
  if (supabaseUrl && supabaseAnonKey) {
    return handleSupabaseNativeRequest(request, subpath, url, supabaseUrl, supabaseAnonKey);
  }

  // Route 3: Local-development fallback (when running outside cloud edge)
  if (!cloudEdge) {
    const port = process.env.OPPORTUNITYOS_API_PORT || "8000";
    const targetUrl = `http://localhost:${port}/api/${subpath}${url.search}`;

    const forwardHeaders = new Headers();
    request.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (!FORBIDDEN_HEADERS.has(lower)) {
        forwardHeaders.set(key, value);
      }
    });

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

      const resHeaders = new Headers();
      upstreamRes.headers.forEach((value, key) => {
        const lower = key.toLowerCase();
        if (!FORBIDDEN_HEADERS.has(lower) && lower !== "set-cookie") {
          resHeaders.append(key, value);
        }
      });

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
        JSON.stringify({ error: "Bad Gateway: Failed to reach local OpportunityOS API." }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
  }

  // Fail-closed on cloud edge when neither origin nor Supabase configuration is present
  return NextResponse.json(
    {
      error:
        "Configuration Error: No upstream API origin or Supabase configuration provided on cloud edge.",
    },
    { status: 500 }
  );
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
export const HEAD = proxyRequest;
export const OPTIONS = proxyRequest;