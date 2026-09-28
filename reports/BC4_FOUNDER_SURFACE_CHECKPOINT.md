# BC-4 Founder Surface Reset Checkpoint

Date: 2026-09-28
Base: `b900a446c4d4006d1c30c0abcf890a57384efd52`
Branch: `work/bc4-founder-surface`

## Scope

- Added primary For You, Saved, Applied, and Later navigation. For You sends the existing `recommendation_state=for_you` feed query; the remaining tabs use existing tracker activity values. Tab state is represented in the URL and restored on browser navigation.
- Kept search and Sort visible, grouped quick categorical facets inside a compact More filters dropdown, and placed Founder rules, facet diagnostics, manual source controls, and the tutoring tool under Diagnostics & tools.
- Moved source health/polling and detailed feed metadata fetches behind their secondary surfaces; source inventory options continue using the existing source overview contract.
- Simplified job cards to emphasize role family, location/work mode, Founder geography status, posted age, application access, reasons, and Apply/Save/Not for me actions. Removed the raw fit score and diagnostic flag chips from the default card.
- Kept qualification decisions and canonical fit score available under detail Diagnostics, with application access and geography status presented separately in the normal detail view.
- Preserved all feed, filter, tracker, activity, and action endpoints. No scoring, persistence, tracker transition, source policy, or Founder data contract changed.

## Verification

- `npm run lint` passed.
- `npm run build` passed, including TypeScript and static generation.
- Full mock Playwright suite passed: 33/33 tests, including 390px layout, primary list navigation, lazy diagnostics/source-health loading, filters, keyboard flow, and batch selection.
- `python scripts/check_repository.py` passed.
- `git diff --check` passed.
- Required PR CI remains the independent integration/regression gate.

## Runtime and safety

This checkpoint does not activate sources, run a backfill, change persisted Founder state, or claim authenticated production validation. BC-2 historical replay acceptance remains a BC-5 gate. BC-3 source discovery remains guarded and inactive until that gate.

## Next

Complete final focused tests and repository checks, open and merge the BC-4 PR through required CI, verify the staging deployment and hosted Founder flow where credentials permit, then proceed to BC-5 replay acceptance and production activation gates.
