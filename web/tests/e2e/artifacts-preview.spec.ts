import { test, expect, type Page } from "@playwright/test"

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
    return {
      status: response.status,
      contentType: response.headers.get("content-type"),
      contentDisposition: response.headers.get("content-disposition"),
      prefix: Array.from(bytes.slice(0, 4)).map((v) => String.fromCharCode(v)).join(""),
      sha256: Array.from(digest).map((v) => v.toString(16).padStart(2, "0")).join(""),
    }
  }, url)
}

async function login(page: Page) {
  await page.goto("/")
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(/\/$/)
}

test.describe("fixed CV and generated cover-letter artifacts", () => {
  test("CV preview/download uses one immutable PDF with no template or DOCX mutation", async ({ page }) => {
    await login(page)
    await page.getByTestId("opportunity-card-opp-001").click()
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()

    const preview = drawer.getByTestId("artifact-pdf-preview")
    const src = await preview.getAttribute("src")
    expect(src).toContain("cv-final.pdf")
    expect(src).not.toContain("template=")

    const response = await fetchArtifactThroughPage(page, src!)
    expect(response.status).toBe(200)
    expect(response.contentType).toBe("application/pdf")
    expect(response.contentDisposition).toContain("inline")
    expect(response.prefix).toBe("%PDF")

    await expect(drawer.getByTestId("artifact-template-switcher")).toHaveCount(0)
    await expect(drawer.getByTestId("artifact-download-docx")).toHaveCount(0)

    const pdfDownloadPromise = page.waitForEvent("download")
    await drawer.getByTestId("artifact-download-pdf").click()
    const pdfDownload = await pdfDownloadPromise
    expect(pdfDownload.suggestedFilename().endsWith(".pdf")).toBe(true)
  })

  test("cover letter retains truth-locked templates and claim rejection", async ({ page }) => {
    await login(page)
    // opp-002 is intentionally a historical dismissed fixture. This artifact
    // test needs that fixture, not the default To Review inbox.
    await page.getByTestId("filter-activity").selectOption("any")
    const showHidden = page.getByTestId("toggle-hidden-opportunities")
    await showHidden.click()

    await page.getByTestId("opportunity-card-opp-002").click()
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()
    await drawer.getByTestId("artifact-kind-cover-letter").click()

    await expect(drawer.getByTestId("artifact-template-switcher")).toBeVisible()
    const rejection = drawer.getByTestId("artifact-validation-rejection")
    await expect(rejection).toBeVisible()
    await expect(rejection).toContainText("5+ years of directly relevant field experience")
    await expect(rejection).toContainText("no truth pack evidence supports this duration")
    await expect(drawer.getByTestId("artifact-pdf-preview")).toHaveCount(0)
  })
})
