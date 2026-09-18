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
    if (cloudEdge) {
      return NextResponse.json(
        {
          error:
            "Configuration Error: OPPORTUNITYOS_API_ORIGIN is required on the cloud edge.",
        },
        { status: 500 }
      );
    }
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