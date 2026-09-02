import type { NextConfig } from "next"

const nextConfig: NextConfig = {
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
