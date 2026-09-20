import { NextRequest, NextResponse } from "next/server"
import { getCloudflareContext } from "@opennextjs/cloudflare"

const ACCESS_COOKIE = "__Host-opos_access"
const REFRESH_COOKIE = "__Host-opos_refresh"
const MAX_PACK_BYTES = 2_000_000

type RuntimeEnv = Record<string, string | undefined>
type HostedSession = { access_token?: string; refresh_token?: string; expires_in?: number }
type HostedConfig = { origin: string; key: string }

function runtimeEnv(): RuntimeEnv {
  try {
    const env = getCloudflareContext().env as unknown as RuntimeEnv
    if (env.OPPORTUNITYOS_CLOUD_EDGE === "1") return env
  } catch {
    // Local Next.js execution has no Cloudflare request context.
  }
  return process.env as RuntimeEnv
}

function hostedConfig(env: RuntimeEnv = runtimeEnv()): HostedConfig | null {
  const raw = env.NEXT_PUBLIC_SUPABASE_URL?.trim()
  const key = (env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? env.NEXT_PUBLIC_SUPABASE_ANON_KEY)?.trim()
  if (!raw || !key) return null
  try {
    const url = new URL(raw)
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) return null
    return { origin: url.origin, key }
  } catch {
    return null
  }
}

function cookieOptions(maxAge?: number) {
  return {
    httpOnly: true,
    secure: true,
    sameSite: "lax" as const,
    path: "/",
    ...(maxAge === undefined ? {} : { maxAge }),
  }
}

async function supabaseFetch(cfg: HostedConfig, path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers)
  headers.set("apikey", cfg.key)
  return fetch(`${cfg.origin}${path}`, { ...init, headers, redirect: "manual" })
}

async function accessToken(
  request: NextRequest,
  cfg: HostedConfig,
): Promise<{ token: string; refreshed?: HostedSession } | null> {
  const access = request.cookies.get(ACCESS_COOKIE)?.value
  if (access) {
    const probe = await supabaseFetch(cfg, "/auth/v1/user", {
      headers: { Authorization: `Bearer ${access}` },
    })
    if (probe.ok) return { token: access }
  }

  const refresh = request.cookies.get(REFRESH_COOKIE)?.value
  if (!refresh) return null
  const refreshed = await supabaseFetch(cfg, "/auth/v1/token?grant_type=refresh_token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (!refreshed.ok) return null
  const session = (await refreshed.json()) as HostedSession
  return session.access_token ? { token: session.access_token, refreshed: session } : null
}

function applyRefreshCookies(response: NextResponse, session?: HostedSession) {
  if (!session) return
  if (session.access_token) {
    response.cookies.set(ACCESS_COOKIE, session.access_token, cookieOptions(session.expires_in ?? 3600))
  }
  if (session.refresh_token) {
    response.cookies.set(REFRESH_COOKIE, session.refresh_token, cookieOptions(60 * 60 * 24 * 30))
  }
}

export async function POST(request: NextRequest) {
  if (request.headers.get("x-opportunityos-csrf") !== "1") {
    return NextResponse.json({ detail: "CSRF validation failed" }, { status: 403 })
  }

  const cfg = hostedConfig()
  if (!cfg) return NextResponse.json({ detail: "hosted Supabase configuration unavailable" }, { status: 503 })

  const auth = await accessToken(request, cfg)
  if (!auth) return NextResponse.json({ detail: "authentication required" }, { status: 401 })

  const contentLength = Number(request.headers.get("content-length") ?? "0")
  if (Number.isFinite(contentLength) && contentLength > MAX_PACK_BYTES) {
    return NextResponse.json({ detail: "CV pack must be smaller than 2 MB" }, { status: 413 })
  }

  const body = await request.arrayBuffer()
  if (body.byteLength === 0 || body.byteLength > MAX_PACK_BYTES) {
    return NextResponse.json({ detail: "CV pack must be a non-empty ZIP smaller than 2 MB" }, { status: 422 })
  }

  const upstream = await supabaseFetch(cfg, "/functions/v1/cv-pack-import", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${auth.token}`,
      "Content-Type": "application/zip",
    },
    body,
  })

  const payload = await upstream.text()
  const response = new NextResponse(payload, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json; charset=utf-8" },
  })
  applyRefreshCookies(response, auth.refreshed)
  return response
}
