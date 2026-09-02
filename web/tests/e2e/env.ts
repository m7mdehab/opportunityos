/**
 * Small shared helper for the Playwright configs (mock and real-stack).
 *
 * `webServer.env` is typed `{ [key: string]: string }` (no `undefined`
 * values allowed), but `process.env` is `{ [key: string]: string |
 * undefined }` under TypeScript's lib types. This strips the `undefined`
 * entries so a config can spread the parent process's environment into
 * `webServer.env` and then override/add specific variables, without
 * relying on Playwright's own default-inherit behaviour (which only
 * applies when `env` is omitted entirely).
 */
export function definedProcessEnv(): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined) {
      result[key] = value
    }
  }
  return result
}

/**
 * A synthetic, non-credential value for a local-only alpha service secret
 * (session signing key, founder password for a throwaway test database).
 * Built at runtime from `Math.random()`, never a literal, so no assignment
 * site here can ever match `scripts/check_guard.py`'s
 * `ASSIGNED_SECRET` rule (a 12+ character quoted literal directly assigned
 * to a name containing api-key/secret/token/password) -- the rule is
 * right to reject that shape regardless of whether the value is real.
 */
export function syntheticSecret(prefix: string): string {
  return (
    `${prefix}-` +
    Math.random().toString(36).slice(2) +
    Math.random().toString(36).slice(2)
  )
}

/**
 * Ensures `process.env[name]` is set for the remainder of this process
 * (used for `E2E_FOUNDER_PASSWORD`, which `tests/e2e/smoke.spec.ts` reads
 * directly and which must equal the real API's configured founder
 * password for the real-stack config's login step to succeed). Returns
 * the resolved value either way.
 */
export function ensureEnv(name: string, fallback: () => string): string {
  const existing = process.env[name]
  if (existing) {
    return existing
  }
  const value = fallback()
  process.env[name] = value
  return value
}
