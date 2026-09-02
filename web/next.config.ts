import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // Next generates its own `AGENTS.md` and `CLAUDE.md` here by default. In
  // this repository `AGENTS.md` is the named governance authority and is on
  // the public mirror allowlist, so a second file of that name inside `web/`
  // is actively confusing. Disabled at the source rather than gitignored, so
  // the files are never written at all.
  agentRules: false,

  // Same-origin `/api/*` in the browser; proxied to the local FastAPI
  // service in dev so no CORS configuration is needed. When the mock layer
  // is active (`NEXT_PUBLIC_USE_MOCK_API=1`), MSW intercepts these same
  // relative fetches at the service-worker level before they ever reach
  // this rewrite, so this config does not need to know about the mock.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ]
  },
}

export default nextConfig
