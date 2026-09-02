/**
 * Browser-side MSW worker. Only imported by `components/mock-provider.tsx`,
 * and only when `NEXT_PUBLIC_USE_MOCK_API=1`. Phase 2 removes this file
 * (and `mock-provider.tsx`'s dynamic import of it) and nothing else changes
 * — every other module talks to `/api/*` the same way either phase.
 */
import { setupWorker } from "msw/browser"
import { handlers } from "@/lib/mock/handlers"

export const worker = setupWorker(...handlers)
