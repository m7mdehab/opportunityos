import { test, expect, type Page } from "@playwright/test"

const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

async function login(page: Page) {
  await page.goto("/")
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByTestId("workspace-jobs")).toBeVisible()
  await expect(page.locator('[data-testid^="opportunity-card-"]').first()).toBeVisible()
}

async function actOnFirstJob(page: Page, label: string, expectedState: string) {
  const card = page.locator('[data-testid^="opportunity-card-"]').first()
  await expect(card).toBeVisible()
  const testId = await card.getAttribute("data-testid")
  if (!testId) throw new Error("first job card has no stable test id")
  const opportunityId = testId.replace("opportunity-card-", "")

  await card.click()
  const drawer = page.getByRole("dialog")
  const [response] = await Promise.all([
    page.waitForResponse((res) => res.request().method() === "POST" && res.url().includes("/actions")),
    drawer.getByRole("button", { name: label, exact: true }).click(),
  ])
  expect(response.status(), await response.text()).toBe(200)
  const body = (await response.json()) as { tracker_state: string }
  expect(body.tracker_state).toBe(expectedState)
  await expect(page.locator(`[data-testid="opportunity-card-${opportunityId}"]`)).toHaveCount(0)
  await page.keyboard.press("Escape")
  await expect(drawer).not.toBeVisible()
  return opportunityId
}

async function updateApplicationStage(page: Page, stage: string) {
  const drawer = page.getByRole("dialog")
  await drawer.getByLabel("Application stage").selectOption(stage)
  const [response] = await Promise.all([
    page.waitForResponse((res) => res.request().method() === "POST" && res.url().includes("/actions")),
    drawer.getByRole("button", { name: "Update stage", exact: true }).click(),
  ])
  expect(response.status(), await response.text()).toBe(200)
  const body = (await response.json()) as { tracker_state: string }
  expect(body.tracker_state).toBe(stage)
}

async function trackerEvents(page: Page, opportunityId: string) {
  return page.evaluate((id) => {
    const scenario = new URLSearchParams(window.location.search).get("mock_scenario") ?? "default"
    const key = `opportunityos.mock.tracker-events.${scenario}`
    const events = JSON.parse(window.localStorage.getItem(key) ?? "[]") as Array<{
      opportunity_id: string
      action_type: string
      from_state: string
      to_state: string
      metadata_json?: string
    }>
    return events.filter((event) => event.opportunity_id === id)
  }, opportunityId)
}

test.describe("FR-008 basic triage tracker", () => {
  test("save, explicit apply, reject, bucket placement, and source-link truthfulness", async ({ page }) => {
    await login(page)

    let actionRequests = 0
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/actions")) actionRequests += 1
    })
    await page.context().route("https://example.invalid/**", (route) => route.abort())

    const sourceCard = page.locator('[data-testid^="opportunity-card-"]').first()
    const sourceId = await sourceCard.getAttribute("data-testid")
    await sourceCard.click()
    const [sourcePage] = await Promise.all([
      page.waitForEvent("popup"),
      page.getByRole("link", { name: "View original source" }).click(),
    ])
    await sourcePage.close()
    expect(actionRequests).toBe(0)
    await expect(page.locator(`[data-testid="${sourceId}"]`)).toBeVisible()
    await page.keyboard.press("Escape")

    const savedId = await actOnFirstJob(page, "Save for later", "saved")
    await page.getByTestId("workspace-tracker").click()
    await expect(page.getByTestId("tracker-view")).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${savedId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${savedId}`).getByText("Saved", { exact: true })).toBeVisible()

    await page.reload()
    await expect(page.getByTestId("workspace-jobs")).toBeVisible()
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-saved").click()
    await expect(page.getByTestId(`opportunity-card-${savedId}`)).toBeVisible()

    await page.getByTestId("workspace-jobs").click()
    const appliedId = await actOnFirstJob(page, "Mark applied", "applied")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await expect(page.getByTestId(`opportunity-card-${appliedId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${appliedId}`).getByText("Applied", { exact: true })).toBeVisible()

    await page.getByTestId("workspace-jobs").click()
    const rejectedId = await actOnFirstJob(page, "Reject", "rejected_by_founder")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-rejected").click()
    await expect(page.getByTestId(`opportunity-card-${rejectedId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${rejectedId}`).getByText("Rejected", { exact: true })).toBeVisible()

    await page.getByTestId("tracker-bucket-all").click()
    await expect(page.getByTestId(`opportunity-card-${savedId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${appliedId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${rejectedId}`)).toBeVisible()
  })

  test("application pipeline moves forward, records one event per stage, and closes jobs", async ({ page }) => {
    await login(page)

    const acceptedId = await actOnFirstJob(page, "Mark applied", "applied")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await page.getByTestId(`opportunity-card-${acceptedId}`).click()

    await updateApplicationStage(page, "assessment")
    const afterAssessment = await trackerEvents(page, acceptedId)
    expect(afterAssessment).toHaveLength(2)
    expect(afterAssessment[1]).toMatchObject({
      action_type: "application_stage_updated",
      from_state: "applied",
      to_state: "assessment",
    })

    await updateApplicationStage(page, "assessment")
    expect(await trackerEvents(page, acceptedId)).toHaveLength(2)

    await updateApplicationStage(page, "offer")
    await updateApplicationStage(page, "accepted")
    await expect(page.getByTestId(`opportunity-card-${acceptedId}`).getByText("Accepted", { exact: true })).toBeVisible()
    await expect(page.getByRole("dialog").getByRole("button", { name: "Update stage" })).toHaveCount(0)
    expect(await trackerEvents(page, acceptedId)).toHaveLength(4)
    await page.keyboard.press("Escape")

    await page.getByTestId("workspace-jobs").click()
    const rejectedId = await actOnFirstJob(page, "Mark applied", "applied")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await page.getByTestId(`opportunity-card-${rejectedId}`).click()
    await updateApplicationStage(page, "rejected_by_employer")
    await page.keyboard.press("Escape")
    await page.getByTestId("tracker-bucket-rejected").click()
    const rejectedCard = page.getByTestId(`opportunity-card-${rejectedId}`)
    await expect(rejectedCard.getByText("Rejected by employer", { exact: true })).toBeVisible()
    await rejectedCard.click()
    await expect(page.getByRole("dialog").getByRole("button", { name: "Update stage" })).toHaveCount(0)
  })

  test("private application notes create, edit, archive, and persist without duplicate events", async ({ page }) => {
    await login(page)
    const opportunityId = await actOnFirstJob(page, "Mark applied", "applied")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()

    const drawer = page.getByRole("dialog")
    const notes = drawer.getByTestId("tracker-notes")
    await expect(notes).toBeVisible()
    await notes.getByLabel("New tracker note").fill("Prepare a focused recruiter follow-up")
    await notes.getByRole("button", { name: "Add note" }).click()
    const note = notes.locator('[data-testid^="tracker-note-"]').first()
    await expect(note).toContainText("Prepare a focused recruiter follow-up")

    const afterCreate = await trackerEvents(page, opportunityId)
    expect(afterCreate).toHaveLength(2)
    expect(afterCreate[1].action_type).toBe("tracker_note_created")
    expect(JSON.parse(afterCreate[1].metadata_json ?? "{}")).toHaveProperty("note_id")
    expect(afterCreate[1].metadata_json).not.toContain("Prepare a focused recruiter follow-up")

    await page.reload()
    await expect(page.getByTestId("workspace-jobs")).toBeVisible()
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()
    const restoredNotes = page.getByRole("dialog").getByTestId("tracker-notes")
    const restoredNote = restoredNotes.locator('[data-testid^="tracker-note-"]').first()
    await expect(restoredNote).toContainText("Prepare a focused recruiter follow-up")

    await restoredNote.getByRole("button", { name: "Edit note" }).click()
    await restoredNotes.getByLabel("Edit note").fill("Prepare a focused recruiter follow-up")
    await restoredNotes.getByRole("button", { name: "Save note" }).click()
    expect(await trackerEvents(page, opportunityId)).toHaveLength(2)

    const currentNote = restoredNotes.locator('[data-testid^="tracker-note-"]').first()
    await currentNote.getByRole("button", { name: "Edit note" }).click()
    await restoredNotes.getByLabel("Edit note").fill("Send recruiter a concise follow-up")
    const [updateResponse] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "PATCH" && response.url().includes("tracker-notes")),
      restoredNotes.getByRole("button", { name: "Save note" }).click(),
    ])
    expect(updateResponse.status()).toBe(200)
    await expect(restoredNotes).toContainText("Send recruiter a concise follow-up")
    expect(await trackerEvents(page, opportunityId)).toHaveLength(3)

    await restoredNotes.getByRole("button", { name: "Archive note" }).click()
    await expect(restoredNotes).toContainText("No notes yet.")
    expect(await trackerEvents(page, opportunityId)).toHaveLength(4)
    const noteEvents = await trackerEvents(page, opportunityId)
    expect(noteEvents.slice(1).map((event) => event.action_type)).toEqual([
      "tracker_note_created", "tracker_note_updated", "tracker_note_archived",
    ])
    for (const event of noteEvents.slice(1)) {
      expect(JSON.parse(event.metadata_json ?? "{}")).toHaveProperty("note_id")
      expect(event.metadata_json).not.toContain("recruiter")
    }

    await page.reload()
    await expect(page.getByTestId("workspace-jobs")).toBeVisible()
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()
    const archivedNotes = page.getByRole("dialog").getByTestId("tracker-notes")
    await expect(archivedNotes).toContainText("No notes yet.")
    expect(await trackerEvents(page, opportunityId)).toHaveLength(4)
  })
})
