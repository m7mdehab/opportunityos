# Founder Alpha production verification — 2026-09-16

This record contains non-secret production acceptance evidence only. Private
configuration, credentials, Founder profile data, database dumps, and generated
artifact contents remain machine-local and gitignored.

## Code and deployment

- PR #90 fixed long source-native identity hashing and merged as
  `f448fd6418f838f1640f57a1f148853938bf4b8b`.
- A bounded follow-up found that live Himalayas rows without `id` or `slug`
  still used the positional empty-ID fallback. PR #91 made their
  posting-specific URL the fallback identity and merged as
  `1618b5246f6546c866d0b6ab27b270ea79a7dace`.
- Required PR and post-merge workflows passed for both fixes.
- The production checkout and running stack use `1618b5246f6546c866d0b6ab27b270ea79a7dace`.

## Production identity repair

- A fresh PostgreSQL custom-format backup was created and its restore catalog
  was verified before each mutation.
- We Work Remotely naturally grew to 1,423 historical rows across 178 posting
  URLs before maintenance. One atomic repair retained 178 canonical rows and
  removed 1,245 superseded identities. It preserved 22 Founder view events,
  removed only derived evaluations/artifact caches, and left zero WWR duplicate
  URL groups.
- A governed post-repair WWR scheduler/worker poll parsed 88 opportunities:
  zero inserted, 88 unchanged, zero updated. WWR remained at 178 rows and 178
  URLs with zero duplicate groups.
- Himalayas had 1,222 positional identities across 1,212 posting URLs. A second
  atomic repair retained 1,212 canonical rows and removed 10 superseded
  identities. No Founder-authored/action state existed on those rows.
- A governed post-repair Himalayas scheduler/worker poll parsed 20
  opportunities: zero inserted, 20 unchanged, zero updated. Himalayas remained
  at 1,212 rows and 1,212 URLs with zero duplicate groups.
- Post-repair checks found no orphan provenance, evaluation, or Founder-view
  records; no duplicate opportunity/Truth-Pack evaluation pairs; and no ID over
  the 64-character storage limit.

## Derived state and pipeline

- The private Founder Truth Pack passed the repository-native validator and was
  loaded by the live API. Career and Capability profile sections were present.
- Current-profile evaluation coverage was 33,039 of 33,039 opportunities:
  618 qualified, 2,871 uncertain, and 29,550 ineligible. Three qualified rows
  scored at least 70.
- The durable queue had no pending, retry, running, or stale-leased jobs after
  completion. The 33 dead-letter rows are historical poll attempts; no source's
  latest poll job was dead-lettered, and the affected sources have later
  successful poll evidence.
- Latest persisted poll health was `ok` for 343 sources. The authenticated
  source-health API returned all 396 registry entries.

## Public smoke

- Public URL: <https://opportunityos.m7mdehab.com>
- HTTPS login returned 200; protected APIs returned 401 without a session.
- Authenticated login and `/api/auth/me` succeeded. Truth status reported a
  loaded, valid pack with zero findings.
- The real production feed returned 27,518 visible opportunities. Page 1 and
  page 2 each returned 50 rows with zero overlap. Search returned 18,673
  matching rows; qualified/high-fit filtering returned three rows.
- Filters (10), facets (15), source health (396), detail, original-source links,
  honest work-mode/location fields, and the artifact panel were exercised.
- A qualified cover-letter PDF rendered successfully. A CV path with unsupported
  claims was rejected with HTTP 409, preserving the truth lock.
- Headless desktop and 390 px mobile smoke passed. The mobile document width
  equalled the viewport width, with no horizontal page overflow.
- No mock-service marker or private pack contents appeared in the tested public
  responses.

## Remaining truthful boundaries

- One RemoteOK URL is shared by two different postings because that upstream
  data supplies a generic board landing URL; it is not treated as a duplicate
  posting identity.
- Previously accepted FR-006 historical exceptions remain unchanged.
- The named tunnel is durable, but this single-founder deployment still depends
  on its Windows production host, PostgreSQL service, and keepalive task being
  online.
- BRIEF-007 / Phase 6 remains blocked until Founder acceptance of this live
  Alpha.
