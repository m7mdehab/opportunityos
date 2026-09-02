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
