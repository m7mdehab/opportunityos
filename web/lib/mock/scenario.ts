/**
 * Selects which synthetic dataset the mock layer serves. Only read in the
 * browser, and only when `NEXT_PUBLIC_USE_MOCK_API=1`. Real code (the API
 * client, the pages, the components) never imports this module or knows it
 * exists — it is used exclusively by `lib/mock/handlers.ts`.
 */
export type MockScenario =
  | "default"
  | "no-truth-pack"
  | "invalid-truth-pack"
  | "no-opportunities"
  | "worker-idle"

const SCENARIOS: MockScenario[] = [
  "default",
  "no-truth-pack",
  "invalid-truth-pack",
  "no-opportunities",
  "worker-idle",
]

export function resolveScenario(): MockScenario {
  if (typeof window === "undefined") return "default"
  const fromQuery = new URLSearchParams(window.location.search).get(
    "mock_scenario"
  )
  if (fromQuery && SCENARIOS.includes(fromQuery as MockScenario)) {
    return fromQuery as MockScenario
  }
  return "default"
}
