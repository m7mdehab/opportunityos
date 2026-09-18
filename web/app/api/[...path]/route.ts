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

  let targetOrigin: string;
  if (configuredOrigin) {
    // Cloud / Staging proxy safety: MUST be HTTPS only!
    if (!configuredOrigin.startsWith("https://")) {
      return new NextResponse(
        JSON.stringify({
          error: "Configuration Error: OPPORTUNITYOS_API_ORIGIN must use HTTPS in staging/production.",
        }),
        { status: 500, headers: { "Content-Type": "application/json" } }
      );
    }
    targetOrigin = configuredOrigin.replace(/\/+$/, "");
  } else {
    // Fallback for local development if called directly without next.config rewrite
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
      // Forward all response headers including set-cookie, content-type, content-disposition
      if (!FORBIDDEN_HEADERS.has(lower)) {
        resHeaders.append(key, value);
      }
    });

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