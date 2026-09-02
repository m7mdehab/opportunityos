/**
 * Browser-side MSW worker. Only imported by `components/mock-provider.tsx`,
 * and only when `NEXT_PUBLIC_USE_MOCK_API=1`. Phase 2 removes this file
 * (and `mock-provider.tsx`'s dynamic import of it) and nothing else changes
 * — every other module talks to `/api/*` the same way either phase.
 */
import { setupWorker } from "msw/browser"
import { handlers } from "@/lib/mock/handlers"

export const worker = setupWorker(...handlers)

// `worker.start()` is not itself idempotent — calling it a second time while
// already active throws ("cannot configure an already enabled network"),
// which React's Strict Mode double-effect-invocation (and Fast Refresh) in
// dev will trigger. Memoize the start promise so every caller shares one
// real start.
let startPromise: ReturnType<typeof worker.start> | null = null

export function startMockWorker(): ReturnType<typeof worker.start> {
  if (!startPromise) {
    startPromise = worker.start({
      onUnhandledRequest: "bypass",
      quiet: true,
    })
  }
  return startPromise
}
