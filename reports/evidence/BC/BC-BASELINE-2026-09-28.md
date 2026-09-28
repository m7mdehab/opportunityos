# BC baseline — 2026-09-28

Read-only snapshot of repository and hosted Supabase state before BC writes. Project: `sunjfepvdzfknglrjwhm` (`opportunityos-staging`, `eu-central-1`, PostgreSQL 17.6.1). The connected project tool reports `ACTIVE_HEALTHY`.

## Git

- Authoritative `origin/main`: `62acbcbf1761fa52120a637b0a3886ae13e45468`.
- Open PRs: 0; remote branches: `main` only.
- Work starts in `work/bc1-recommendation-foundation`, based directly on that SHA.

## Database and feed

- Database: `358,960,275` bytes (`342.33 MiB`). This is 7.67 MiB below the 350 MiB warning boundary; no capacity-driven source activation or broad write is safe without canary measurement.
- Lifecycle rows: HOT 11,213; PROTECTED 439; COLD 19,077.
- Visible feed rows: 8,296. All 8,296 have null `title_family`; all 8,296 have unspecified/unknown seniority.
- Largest relations by total relation size: `opportunities` 107,970,560; `match_evaluations` 67,502,080; `field_provenances` 67,403,776; `storage.objects` 54,321,152; `feed_projection` 25,747,456; `opportunity_cold_archive` 15,523,840 bytes.

## Visible source-family counts

| Family | Rows |
|---|---:|
| Greenhouse | 7,377 |
| Lever | 539 |
| Hacker News Who Is Hiring | 107 |
| We Work Remotely | 101 |
| Remote OK | 97 |
| Himalayas | 67 |
| Remotive | 8 |

## Founder history (preserve unchanged)

- Feedback: irrelevant_role 140; bad_match 24; eligibility_wrong 5; good_match 2.
- Current tracker states: saved 106; applied 13; submitted 2; rejected_by_founder 72; dismissed 165; snoozed 1.
- Activity history includes save 236, reject 73, mark_applied 15 (13 applied + 2 submitted), restore 129, dismiss 173, clear 6, snooze 1.

## Durable queue and source-poll behavior

| Status | Job type | Count |
|---|---|---:|
| COMPLETED | evaluate_new | 145 |
| COMPLETED | poll_source | 1,055 |
| DEAD_LETTER | poll_source | 76 |
| PENDING | evaluate_new | 1 |
| PENDING | poll_source | 119 |
| RUNNING | poll_source | 1 |

The RUNNING poll's lease expired at `2026-09-27 23:55:06 UTC`; the row is left untouched for the normal lease/reaper path. This is not evidence by itself that the queue runner is broken.

Recent `source_poll_runs` aggregate query shows severe fetch durations: Greenhouse maximum 5,372 seconds (89.5 minutes), Lever 1,935 seconds (32.2 minutes), Remote OK 550 seconds, and Hacker News 661 seconds across available recent history. This confirms the brief's Greenhouse performance concern and supports fixing fetch cost before increasing source volume.

No source schedule, queue, opportunity, feedback, action, or production data was changed for this snapshot.
