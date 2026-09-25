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
    await expect(page.getByTestId(`opportunity-card-${savedId}`)).toHaveCount(0)
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

  test("a failed tracker-state storage write leaves the job in To Review", async ({ page }) => {
    await login(page)
    const card = page.locator('[data-testid^="opportunity-card-"]').first()
    const testId = await card.getAttribute("data-testid")
    if (!testId) throw new Error("first job card has no stable test id")
    const opportunityId = testId.replace("opportunity-card-", "")

    await page.evaluate(() => {
      const originalSetItem = Storage.prototype.setItem
      Storage.prototype.setItem = function (this: Storage, key: string, value: string) {
        if (key === "opportunityos.mock.tracker.default") {
          throw new DOMException("synthetic storage failure", "QuotaExceededError")
        }
        return originalSetItem.call(this, key, value)
      }
    })

    await card.click()
    const drawer = page.getByRole("dialog")
    const [response] = await Promise.all([
      page.waitForResponse((res) => res.request().method() === "POST" && res.url().includes("/actions")),
      drawer.getByRole("button", { name: "Save for later", exact: true }).click(),
    ])
    expect(response.status(), await response.text()).toBe(503)
    await expect(drawer.getByRole("alert")).toContainText("Could not persist tracker state")
    await page.keyboard.press("Escape")
    await expect(page.getByTestId(`opportunity-card-${opportunityId}`)).toBeVisible()

    await page.reload()
    await expect(page.getByTestId("workspace-jobs")).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${opportunityId}`)).toBeVisible()
    expect(await trackerEvents(page, opportunityId)).toHaveLength(0)
  })

  test("active snoozes stay out of To Review and expired snoozes resurface", async ({ page }) => {
    await login(page)
    const card = page.locator('[data-testid^="opportunity-card-"]').first()
    const testId = await card.getAttribute("data-testid")
    if (!testId) throw new Error("first job card has no stable test id")
    const opportunityId = testId.replace("opportunity-card-", "")
    const future = new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString().slice(0, 10)

    const status = await page.evaluate(async ({ id, until }) => {
      const response = await fetch(`/api/opportunities/${id}/actions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ type: "snooze", until }),
      })
      return response.status
    }, { id: opportunityId, until: future })
    expect(status).toBe(200)
    await page.reload()
    await expect(page.getByTestId(`opportunity-card-${opportunityId}`)).toHaveCount(0)

    const expired = new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString().slice(0, 10)
    await page.evaluate(({ id, until }) => {
      localStorage.setItem("opportunityos.mock.tracker.default", JSON.stringify([
        { id, action_state: "snoozed", snoozed_until: until },
      ]))
    }, { id: opportunityId, until: expired })
    await page.reload()
    const resurfaced = page.getByTestId(`opportunity-card-${opportunityId}`)
    await expect(resurfaced).toBeVisible()
    await expect(resurfaced.getByText("Snoozed", { exact: true })).toHaveCount(0)
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

  test("follow-ups create, reschedule, complete, reopen, and persist with private metadata", async ({ page }) => {
    await login(page)
    const opportunityId = await actOnFirstJob(page, "Save for later", "saved")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()

    const drawer = page.getByRole("dialog")
    const followUps = drawer.getByTestId("tracker-follow-ups")
    await expect(followUps).toBeVisible()
    const today = new Date().toISOString().slice(0, 10)
    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
    await followUps.getByLabel("Follow-up due date").fill(today)
    await followUps.getByLabel("Follow-up note").fill("Ask the recruiter about next steps")
    const [createResponse] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith(`/opportunities/${opportunityId}/follow-ups`)),
      followUps.getByRole("button", { name: "Add follow-up" }).click(),
    ])
    expect(createResponse.status(), await createResponse.text()).toBe(200)
    const row = followUps.locator('[data-testid^="tracker-follow-up-"]').filter({ hasText: "Ask the recruiter about next steps" }).first()
    await expect(row).toContainText("Due today")
    let events = await trackerEvents(page, opportunityId)
    expect(events.map((event) => event.action_type)).toEqual(["saved", "follow_up_created"])
    expect(JSON.parse(events[1].metadata_json ?? "{}")).toHaveProperty("follow_up_id")
    expect(events[1].metadata_json).not.toContain("recruiter")

    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
    await followUps.getByLabel("Follow-up due date").fill(yesterday)
    await followUps.getByLabel("Follow-up note").fill("Private overdue reminder")
    const [overdueCreateResponse] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith(`/opportunities/${opportunityId}/follow-ups`)),
      followUps.getByRole("button", { name: "Add follow-up" }).click(),
    ])
    expect(overdueCreateResponse.status()).toBe(200)
    const overdueRow = followUps.locator('[data-testid^="tracker-follow-up-"]').filter({ hasText: "Private overdue reminder" }).first()
    await expect(overdueRow).toContainText("Overdue")
    events = await trackerEvents(page, opportunityId)
    expect(events.map((event) => event.action_type)).toEqual(["saved", "follow_up_created", "follow_up_created"])
    expect(events.slice(1).every((event) => !event.metadata_json?.includes("Private"))).toBe(true)

    await page.keyboard.press("Escape")
    const dueTodaySummary = page.getByTestId("tracker-follow-ups-overview").locator('[data-testid^="tracker-follow-up-summary-"]').first()
    await expect(dueTodaySummary).toBeVisible()
    await expect(dueTodaySummary).not.toContainText("Ask the recruiter about next steps")
    await page.getByTestId("tracker-follow-up-bucket-overdue").click()
    const overdueSummary = page.getByTestId("tracker-follow-ups-overview").locator('[data-testid^="tracker-follow-up-summary-"]').first()
    await expect(overdueSummary).toBeVisible()
    await expect(overdueSummary).not.toContainText("Private overdue reminder")
    await overdueSummary.getByRole("button", { name: "Open job" }).click()
    await expect(page.getByRole("dialog").getByTestId("tracker-follow-ups")).toBeVisible()

    await row.getByRole("button", { name: "Edit follow-up" }).click()
    await followUps.getByLabel("Edit follow-up due date").fill(tomorrow)
    await followUps.getByLabel("Edit follow-up note").fill("Check back after the interview")
    const [updateResponse] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "PATCH" && response.url().includes(`/opportunities/${opportunityId}/follow-ups/`)),
      followUps.getByRole("button", { name: "Save follow-up" }).click(),
    ])
    expect(updateResponse.status()).toBe(200)
    await expect(followUps).toContainText("Check back after the interview")
    const movedRow = followUps.locator('[data-testid^="tracker-follow-up-"]').filter({ hasText: "Check back after the interview" }).first()
    await movedRow.getByRole("button", { name: "Edit follow-up" }).click()
    const [noopResponse] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "PATCH" && response.url().includes(`/opportunities/${opportunityId}/follow-ups/`)),
      followUps.getByRole("button", { name: "Save follow-up" }).click(),
    ])
    expect(noopResponse.status()).toBe(200)
    expect(await trackerEvents(page, opportunityId)).toHaveLength(4)

    await page.keyboard.press("Escape")
    await page.getByTestId("tracker-follow-up-bucket-upcoming").click()
    const summaryRow = page.locator('[data-testid^="tracker-follow-up-summary-"]').first()
    await expect(summaryRow).toBeVisible()
    await expect(summaryRow).not.toContainText("Check back after the interview")
    await summaryRow.getByRole("button", { name: "Open job" }).click()
    const reopenedDrawer = page.getByRole("dialog")
    const reopenedFollowUps = reopenedDrawer.getByTestId("tracker-follow-ups")
    const persistedRow = reopenedFollowUps.locator('[data-testid^="tracker-follow-up-"]').filter({ hasText: "Check back after the interview" }).first()
    await expect(persistedRow).toContainText("Upcoming")

    await persistedRow.getByRole("button", { name: "Complete follow-up" }).click()
    await expect(persistedRow).toContainText("Completed")
    events = await trackerEvents(page, opportunityId)
    expect(events.at(-1)?.action_type).toBe("follow_up_completed")
    expect(events.at(-1)?.metadata_json).not.toContain("interview")

    await persistedRow.getByRole("button", { name: "Reopen follow-up" }).click()
    await expect(persistedRow).toContainText("Upcoming")
    events = await trackerEvents(page, opportunityId)
    expect(events.slice(-2).map((event) => event.action_type)).toEqual(["follow_up_completed", "follow_up_reopened"])

    await page.reload()
    await expect(page.getByTestId("workspace-jobs")).toBeVisible()
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-saved").click()
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()
    const persistedAgain = page.getByRole("dialog").getByTestId("tracker-follow-ups")
    await expect(persistedAgain).toContainText("Check back after the interview")
    await expect(persistedAgain.locator('[data-testid^="tracker-follow-up-"]').filter({ hasText: "Check back after the interview" }).first()).toContainText("Upcoming")
    expect(await trackerEvents(page, opportunityId)).toHaveLength(6)
  })

  test("interviews create, edit, complete, persist, and stay private in the upcoming summary", async ({ page }) => {
    await login(page)
    const opportunityId = await actOnFirstJob(page, "Mark applied", "applied")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()

    const drawer = page.getByRole("dialog")
    const interviews = drawer.getByTestId("tracker-interviews")
    await expect(interviews).toBeVisible()
    const scheduledAt = await page.evaluate(() => {
      const future = new Date(Date.now() + 48 * 60 * 60 * 1000)
      return new Date(future.getTime() - future.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
    })
    await interviews.getByLabel("New interview schedule").fill(scheduledAt)
    await interviews.getByLabel("New interview round").fill("Technical round")
    await interviews.getByLabel("New interview type").selectOption("technical")
    await interviews.getByLabel("New interview format").selectOption("video")
    await interviews.getByLabel("New interviewer").fill("Synthetic interviewer")
    await interviews.getByLabel("New preparation notes").fill("PRIVATE PREPARATION NOTES")
    await interviews.getByLabel("New post-interview notes").fill("PRIVATE DEBRIEF NOTES")
    const [createResponse] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith(`/opportunities/${opportunityId}/interviews`)),
      interviews.getByRole("button", { name: "Add interview" }).click(),
    ])
    expect(createResponse.status(), await createResponse.text()).toBe(200)
    const interviewRow = interviews.locator('[data-testid^="tracker-interview-"]').first()
    const interviewTestId = await interviewRow.getAttribute("data-testid")
    const interviewId = interviewTestId?.replace("tracker-interview-", "")
    expect(interviewId).toBeTruthy()
    await expect(interviewRow).toContainText("Technical round")
    await expect(interviewRow).toContainText("PRIVATE PREPARATION NOTES")
    let events = await trackerEvents(page, opportunityId)
    expect(events.at(-1)?.action_type).toBe("interview_added")
    expect(JSON.parse(events.at(-1)?.metadata_json ?? "{}")).toEqual({ interview_id: interviewId })
    expect(events.at(-1)?.metadata_json).not.toContain("PRIVATE")

    await page.keyboard.press("Escape")
    const summary = page.getByTestId("tracker-interviews-overview").getByTestId(`tracker-interview-summary-${interviewId}`)
    await expect(summary).toBeVisible()
    await expect(summary).not.toContainText("PRIVATE PREPARATION NOTES")
    await expect(summary).not.toContainText("PRIVATE DEBRIEF NOTES")
    await summary.getByRole("button", { name: "Open job" }).click()
    const reopened = page.getByRole("dialog").getByTestId("tracker-interviews")
    const reopenedRow = reopened.getByTestId(`tracker-interview-${interviewId}`)
    await reopenedRow.getByRole("button", { name: "Edit interview" }).click()
    await reopened.getByLabel("Edit interviewer").fill("Updated synthetic interviewer")
    const [updateResponse] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "PATCH" && response.url().includes(`/opportunities/${opportunityId}/interviews/`)),
      reopened.getByRole("button", { name: "Save interview" }).click(),
    ])
    expect(updateResponse.status()).toBe(200)
    expect((await trackerEvents(page, opportunityId)).at(-1)?.action_type).toBe("interview_updated")

    await reopenedRow.getByRole("button", { name: "Edit interview" }).click()
    const [noOpResponse] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "PATCH" && response.url().includes(`/opportunities/${opportunityId}/interviews/`)),
      reopened.getByRole("button", { name: "Save interview" }).click(),
    ])
    expect(noOpResponse.status()).toBe(200)
    expect(await trackerEvents(page, opportunityId)).toHaveLength(3)

    await reopenedRow.getByRole("button", { name: "Complete interview" }).click()
    await expect(reopenedRow).toContainText("Completed")
    events = await trackerEvents(page, opportunityId)
    expect(events.at(-1)?.action_type).toBe("interview_completed")
    expect(JSON.parse(events.at(-1)?.metadata_json ?? "{}")).toEqual({ interview_id: interviewId })
    await page.keyboard.press("Escape")
    await expect(page.getByTestId("tracker-interviews-overview-empty")).toBeVisible()

    await page.reload()
    await expect(page.getByTestId("workspace-jobs")).toBeVisible()
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()
    const persisted = page.getByRole("dialog").getByTestId("tracker-interviews")
    const persistedRow = persisted.getByTestId(`tracker-interview-${interviewId}`)
    await expect(persistedRow).toContainText("Updated synthetic interviewer")
    await expect(persistedRow).toContainText("PRIVATE DEBRIEF NOTES")
    await expect(persistedRow).toContainText("Completed")
    expect(await trackerEvents(page, opportunityId)).toHaveLength(4)
  })

  test("application document links replace cleanly, persist, and record ID-only events", async ({ page }) => {
    await login(page)
    const opportunityId = await actOnFirstJob(page, "Mark applied", "applied")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    const candidatesResponsePromise = page.waitForResponse((response) => response.request().method() === "GET" && response.url().endsWith(`/opportunities/${opportunityId}/tracker-documents/candidates?page=1&page_size=50`))
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()

    const drawer = page.getByRole("dialog")
    const documents = drawer.getByTestId("tracker-documents")
    await expect(documents).toBeVisible()
    await expect(documents).toContainText("General résumé")
    const candidatePayload = await (await candidatesResponsePromise).json() as { items: Array<Record<string, unknown>> }
    expect(candidatePayload.items.length).toBeGreaterThan(0)
    expect(candidatePayload.items.every((candidate) => Object.keys(candidate).every((key) => ["document_kind", "document_id", "label", "format", "recommended", "created_at"].includes(key)))).toBe(true)
    expect(JSON.stringify(candidatePayload)).not.toMatch(/\.pdf|\.docx|object.?path|checksum|payload|storage.?key|PRIVATE/i)

    const cvSelect = documents.getByLabel("Available document")
    await expect(cvSelect).toHaveValue("mock-cv-general")
    const [firstLink] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith(`/opportunities/${opportunityId}/tracker-documents`)),
      documents.getByRole("button", { name: "Link selection" }).click(),
    ])
    expect(firstLink.status(), await firstLink.text()).toBe(200)
    await expect(documents.getByTestId("tracker-document-cv")).toContainText("General résumé")

    const [noopLink] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith(`/opportunities/${opportunityId}/tracker-documents`)),
      documents.getByRole("button", { name: "Link selection" }).click(),
    ])
    expect(noopLink.status()).toBe(200)
    expect((await noopLink.json() as { changed: boolean }).changed).toBe(false)
    expect((await trackerEvents(page, opportunityId)).filter((event) => event.action_type.startsWith("tracker_document_") )).toHaveLength(1)

    await cvSelect.selectOption("mock-cv-data")
    const [replacement] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith(`/opportunities/${opportunityId}/tracker-documents`)),
      documents.getByRole("button", { name: "Link selection" }).click(),
    ])
    expect(replacement.status()).toBe(200)
    await expect(documents.getByTestId("tracker-document-cv")).toContainText("Data résumé")
    await expect(documents.locator('[data-testid="tracker-document-cv"]')).toHaveCount(1)

    await documents.getByLabel("Document type").selectOption("cover_letter")
    await expect(documents.getByLabel("Available document")).toHaveValue(`mock-cover-letter-${opportunityId}`)
    const [coverLetterLink] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith(`/opportunities/${opportunityId}/tracker-documents`)),
      documents.getByRole("button", { name: "Link selection" }).click(),
    ])
    expect(coverLetterLink.status()).toBe(200)
    const linkedLetter = documents.getByTestId("tracker-document-cover_letter")
    await expect(linkedLetter).toContainText("Cover letter · Classic")
    const [unlinkResponse] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "PATCH" && response.url().includes(`/opportunities/${opportunityId}/tracker-documents/`)),
      linkedLetter.getByRole("button", { name: "Unlink cover letter" }).click(),
    ])
    expect(unlinkResponse.status()).toBe(200)
    await expect(documents.getByTestId("tracker-document-cover_letter")).toHaveCount(0)

    const events = await trackerEvents(page, opportunityId)
    expect(events.slice(-4).map((event) => event.action_type)).toEqual([
      "tracker_document_linked", "tracker_document_linked", "tracker_document_linked", "tracker_document_unlinked",
    ])
    expect(events.slice(-4).map((event) => JSON.parse(event.metadata_json ?? "{}"))).toEqual([
      { document_kind: "cv", document_id: "mock-cv-general" },
      { document_kind: "cv", document_id: "mock-cv-data" },
      { document_kind: "cover_letter", document_id: `mock-cover-letter-${opportunityId}` },
      { document_kind: "cover_letter", document_id: `mock-cover-letter-${opportunityId}` },
    ])
    const eventPayload = JSON.stringify(events.slice(-4))
    expect(eventPayload).not.toMatch(/\.pdf|\.docx|object.?path|checksum|PRIVATE/i)

    await page.keyboard.press("Escape")
    const trackerCard = page.getByTestId(`opportunity-card-${opportunityId}`)
    await expect(trackerCard).not.toContainText("Data résumé")
    await expect(trackerCard).not.toContainText("Cover letter")

    await page.reload()
    await expect(page.getByTestId("workspace-jobs")).toBeVisible()
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()
    const persistedDocuments = page.getByRole("dialog").getByTestId("tracker-documents")
    await expect(persistedDocuments.getByTestId("tracker-document-cv")).toContainText("Data résumé")
    await expect(persistedDocuments.getByTestId("tracker-document-cover_letter")).toHaveCount(0)
    expect(await trackerEvents(page, opportunityId)).toHaveLength(events.length)
  })

  test("activity timeline is private, newest-first, refreshes after tracker edits, and persists", async ({ page }) => {
    await login(page)
    const opportunityId = await actOnFirstJob(page, "Mark applied", "applied")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    const activityResponsePromise = page.waitForResponse((response) => response.request().method() === "GET" && response.url().endsWith(`/opportunities/${opportunityId}/tracker-events?page=1&page_size=50`))
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()

    const drawer = page.getByRole("dialog")
    const activity = drawer.getByTestId("tracker-activity-timeline")
    await expect(activity).toBeVisible()
    const initialPayload = await (await activityResponsePromise).json() as { items: Array<Record<string, unknown>> }
    expect(initialPayload.items).toHaveLength(1)
    expect(Object.keys(initialPayload.items[0]).sort()).toEqual(["action_type", "event_at", "from_state", "id", "to_state"])
    expect(JSON.stringify(initialPayload)).not.toMatch(/metadata_json|idempotency_key|note_text|PRIVATE/i)
    await expect(activity.getByTestId("tracker-activity-item").first()).toContainText("Marked as applied")

    await updateApplicationStage(page, "assessment")
    await expect(activity.getByTestId("tracker-activity-item").first()).toContainText("Application stage changed to Assessment")

    const notes = drawer.getByTestId("tracker-notes")
    await notes.getByLabel("New tracker note").fill("PRIVATE TIMELINE NOTE BODY")
    await notes.getByRole("button", { name: "Add note" }).click()
    await expect(activity.getByTestId("tracker-activity-item").first()).toContainText("Note added")
    await expect(activity).not.toContainText("PRIVATE TIMELINE NOTE BODY")

    const followUps = drawer.getByTestId("tracker-follow-ups")
    const dueDate = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
    await followUps.getByLabel("Follow-up due date").fill(dueDate)
    await followUps.getByLabel("Follow-up note").fill("PRIVATE TIMELINE REMINDER BODY")
    await followUps.getByRole("button", { name: "Add follow-up" }).click()
    await expect(activity.getByTestId("tracker-activity-item").first()).toContainText("Follow-up added")
    await expect(activity).not.toContainText("PRIVATE TIMELINE REMINDER BODY")

    const interviews = drawer.getByTestId("tracker-interviews")
    const scheduledAt = await page.evaluate(() => {
      const future = new Date(Date.now() + 72 * 60 * 60 * 1000)
      return new Date(future.getTime() - future.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
    })
    await interviews.getByLabel("New interview schedule").fill(scheduledAt)
    await interviews.getByLabel("New interview round").fill("Timeline synthetic interview")
    await interviews.getByLabel("New interview type").selectOption("technical")
    await interviews.getByLabel("New interview format").selectOption("video")
    await interviews.getByLabel("New preparation notes").fill("PRIVATE TIMELINE INTERVIEW BODY")
    await interviews.getByRole("button", { name: "Add interview" }).click()
    await expect(activity.getByTestId("tracker-activity-item").first()).toContainText("Interview added")
    await expect(activity).not.toContainText("PRIVATE TIMELINE INTERVIEW BODY")

    const documents = drawer.getByTestId("tracker-documents")
    await expect(documents.getByRole("button", { name: "Link selection" })).toBeEnabled()
    await documents.getByRole("button", { name: "Link selection" }).click()
    await expect(activity.getByTestId("tracker-activity-item").first()).toContainText("Application document linked")
    const eventTexts = await activity.getByTestId("tracker-activity-item").allTextContents()
    expect(eventTexts[0]).toContain("Application document linked")
    expect(eventTexts[1]).toContain("Interview added")
    expect(eventTexts[2]).toContain("Follow-up added")
    expect(eventTexts[3]).toContain("Note added")
    expect(eventTexts[4]).toContain("Application stage changed to Assessment")
    expect(eventTexts[5]).toContain("Marked as applied")
    expect(eventTexts.join(" ")).not.toMatch(/PRIVATE|mock-cv-|mock-cover-letter|tracker-event-/i)

    await page.keyboard.press("Escape")
    const trackerCard = page.getByTestId(`opportunity-card-${opportunityId}`)
    await expect(trackerCard).not.toContainText("Application document linked")
    await page.reload()
    await expect(page.getByTestId("workspace-jobs")).toBeVisible()
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await page.getByTestId(`opportunity-card-${opportunityId}`).click()
    const persistedTimeline = page.getByRole("dialog").getByTestId("tracker-activity-timeline")
    await expect(persistedTimeline.getByTestId("tracker-activity-item")).toHaveCount(6)
    await expect(persistedTimeline.getByTestId("tracker-activity-item").first()).toContainText("Application document linked")
    await expect(persistedTimeline).not.toContainText("PRIVATE TIMELINE")
  })
})
