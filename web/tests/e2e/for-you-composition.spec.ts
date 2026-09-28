import { expect, test } from "@playwright/test"

import { composeForYouRows } from "@/lib/feed/compose-for-you"

type Row = {
  opportunity_id: string
  family_key: string | null
  organization: string
  recommendation_priority: number
}

function row(id: string, company: string, rank: number, family: string | null = id): Row {
  return {
    opportunity_id: id,
    family_key: family,
    organization: company,
    recommendation_priority: 1000 - rank,
  }
}

test("For You keeps the best member of a family and applies deterministic employer caps", () => {
  const rows = [
    row("alpha-1", "Alpha", 1, "alpha-family"),
    row("alpha-1-location", "Alpha", 2, "alpha-family"),
    ...Array.from({ length: 10 }, (_, index) => row(`alpha-${index + 2}`, "Alpha", index + 3)),
    ...Array.from({ length: 10 }, (_, index) => row(`beta-${index + 1}`, "Beta", index + 20)),
    ...Array.from({ length: 10 }, (_, index) => row(`gamma-${index + 1}`, "Gamma", index + 40)),
    ...Array.from({ length: 10 }, (_, index) => row(`delta-${index + 1}`, "Delta", index + 60)),
    ...Array.from({ length: 10 }, (_, index) => row(`epsilon-${index + 1}`, "Epsilon", index + 80)),
  ]

  const composed = composeForYouRows(rows, 20)
  expect(composed).toHaveLength(20)
  expect(composed.some((item) => item.opportunity_id === "alpha-1")).toBe(true)
  expect(composed.some((item) => item.opportunity_id === "alpha-1-location")).toBe(false)
  expect(new Set(composed.map((item) => item.family_key)).size).toBe(composed.length)

  const companyCounts = composed.reduce<Record<string, number>>((counts, item) => {
    counts[item.organization] = (counts[item.organization] ?? 0) + 1
    return counts
  }, {})
  expect(Object.values(companyCounts).every((count) => count <= 4)).toBe(true)
  expect(composeForYouRows([...rows].reverse(), 20).map((item) => item.opportunity_id)).toEqual(
    composed.map((item) => item.opportunity_id),
  )
})

test("For You relaxes employer caps only when the requested range cannot otherwise fill", () => {
  const rows = Array.from({ length: 8 }, (_, index) => row(`only-${index}`, "Only Employer", index))
  expect(composeForYouRows(rows, 6)).toHaveLength(6)
  expect(composeForYouRows(rows, 3)).toHaveLength(3)
})
