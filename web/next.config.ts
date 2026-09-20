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
  //
  // The target port reads `OPPORTUNITYOS_API_PORT`, falling back to `8000`
  // (the default `scripts/alpha.py` and every existing dev workflow already
  // assume) so this rewrite is unchanged for every caller that does not set
  // the variable. Playwright's real-stack config sets it to `8210` so a
  // parallel run does not collide with another instance on this shared
  // host. Evaluated at `next build`/`next dev` startup, not per-request.
  async rewrites() {
    // Cloudflare/OpenNext owns /api through the App Router route handler.
    // The localhost rewrite is strictly a local-development compatibility path.
    if (process.env.OPPORTUNITYOS_CLOUD_EDGE === "1") return []

    const apiPort = process.env.OPPORTUNITYOS_API_PORT || "8000"
    return [
      {
        source: "/api/:path*",
        destination: `http://localhost:${apiPort}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
