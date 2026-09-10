import { test, expect, type Page } from "@playwright/test"

/**
 * BRIEF-FR-006 D2 acceptance (D2.6): open a card, see the PDF preview
 * render, switch template and see it change, download DOCX. Every
 * assertion below is on the *rendered result* (actual response bytes
 * fetched through the browser page, an actually-different `<embed>`
 * `src`, an actual `download` event with the expected filename) — never
 * merely "no error was thrown".
 *
 * The mock layer is a browser service worker. Playwright's `page.request`
 * uses a separate APIRequestContext and therefore bypasses that service
 * worker. Artifact bytes are deliberately fetched inside the page context
 * so this spec exercises the same authenticated/service-worker path as the
 * Founder UI instead of testing an unrelated network client.
 */
const FOUNDER_PASSWORD =
  process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

type BrowserArtifactResponse = {
  status: number
  contentType: string | null
  contentDisposition: string | null
  prefix: string
  sha256: string
}

async function fetchArtifactThroughPage(
  page: Page,
  url: string
): Promise<BrowserArtifactResponse> {
  return page.evaluate(async (artifactUrl) => {
    const response = await fetch(artifactUrl, { credentials: "same-origin" })
    const bytes = new Uint8Array(await response.arrayBuffer())
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))
    const sha256 = Array.from(digest)
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("")
    const prefix = Array.from(bytes.slice(0, 4))
      .map((value) => String.fromCharCode(value))
      .join("")

    return {
      status: response.status,
      contentType: response.headers.get("content-type"),
      contentDisposition: response.headers.get("content-disposition"),
      prefix,
      sha256,
    }
  }, url)
}

async function login(page: Page) {
  await page.goto("/")
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible()
}

test.describe("D2 artifacts panel: PDF preview, template switch, DOCX download", () => {
  test("preview renders, template switch changes it, DOCX downloads", async ({
    page,
  }) => {
    await login(page)

    await page.getByTestId("opportunity-card-opp-001").click()
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()

    const preview = drawer.getByTestId("artifact-pdf-preview")
    await expect(preview).toBeVisible()

    const classicSrc = await preview.getAttribute("src")
    expect(classicSrc).toBeTruthy()
    expect(classicSrc).toContain("cv.pdf")
    expect(classicSrc).toContain("template=classic")

    // Fetch through the browser page, not page.request: MSW is a service
    // worker and only the page fetch traverses the same path as the UI.
    const classicResponse = await fetchArtifactThroughPage(page, classicSrc!)
    expect(classicResponse.status).toBe(200)
    expect(classicResponse.contentType).toBe("application/pdf")
    expect(classicResponse.contentDisposition).toContain("inline")
    expect(classicResponse.prefix).toBe("%PDF")

    // "What was left out and why" is visible alongside the preview.
    await expect(drawer.getByTestId("artifact-omitted-panel")).toBeVisible()

    // ---- switch template ----
    await drawer.getByTestId("artifact-template-switcher").click()
    await page.getByTestId("artifact-template-option-modern").click()

    await expect(preview).toHaveAttribute("src", /template=modern/)
    const modernSrc = await preview.getAttribute("src")

    const modernResponse = await fetchArtifactThroughPage(page, modernSrc!)
    expect(modernResponse.status).toBe(200)
    expect(modernResponse.contentType).toBe("application/pdf")
    expect(modernResponse.prefix).toBe("%PDF")
    // The actual rendered document changed, not merely the request URL.
    expect(modernResponse.sha256).not.toBe(classicResponse.sha256)

    // ---- download DOCX ----
    const downloadPromise = page.waitForEvent("download")
    await drawer.getByTestId("artifact-download-docx").click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toContain("cv-opp-001")
    expect(download.suggestedFilename().endsWith(".docx")).toBe(true)

    // ---- download PDF (the other required download button) ----
    const pdfDownloadPromise = page.waitForEvent("download")
    await drawer.getByTestId("artifact-download-pdf").click()
    const pdfDownload = await pdfDownloadPromise
    expect(pdfDownload.suggestedFilename()).toContain("cv-opp-001")
    expect(pdfDownload.suggestedFilename().endsWith(".pdf")).toBe(true)
  })

  test("a 409 claim-validation rejection shows the claim and reason in plain language", async ({
    page,
  }) => {
    await login(page)

    // opp-002 is the fixture's rejected-claims case, already exercised for
    // the DOCX 409 path elsewhere in this suite's mock store. It is hidden
    // by default, so expose hidden opportunities through the same accessible
    // UI control a founder would use before opening the card.
    const showHidden = page.getByRole("button", { name: /show \d+ hidden/i })
    if (await showHidden.count()) {
      await showHidden.click()
    }
    await page.getByTestId("opportunity-card-opp-002").click()
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()

    const rejection = drawer.getByTestId("artifact-validation-rejection")
    await expect(rejection).toBeVisible()
    // The founder must see *which sentence* could not be supported, not a
    // bare error — the claim text itself is rendered.
    await expect(rejection).toContainText(
      "5+ years of directly relevant field experience"
    )
    await expect(rejection).toContainText(
      "no truth pack evidence supports this duration"
    )
    // No preview is shown in place of an unsupported document.
    await expect(drawer.getByTestId("artifact-pdf-preview")).toHaveCount(0)
  })
})
