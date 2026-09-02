"use client"

import { useEffect, useState } from "react"

/**
 * The single switch between the mock layer and the real API.
 *
 * When `NEXT_PUBLIC_USE_MOCK_API=1`, this starts the MSW browser worker
 * before rendering children, so no component ever races a real `fetch()`
 * against an unregistered service worker. When the flag is unset (phase 2),
 * this component renders children immediately and never imports MSW at
 * all — the mock code is not even in the bundle.
 */
export function MockProvider({ children }: { children: React.ReactNode }) {
  const useMock = process.env.NEXT_PUBLIC_USE_MOCK_API === "1"
  const [ready, setReady] = useState(!useMock)

  useEffect(() => {
    if (!useMock) return
    let cancelled = false
    import("@/lib/mock/browser").then(({ startMockWorker }) =>
      startMockWorker().then(() => {
        if (!cancelled) setReady(true)
      })
    )
    return () => {
      cancelled = true
    }
  }, [useMock])

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Starting mock API…
      </div>
    )
  }

  return <>{children}</>
}
