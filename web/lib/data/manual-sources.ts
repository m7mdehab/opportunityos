/**
 * E23 UI half — the "Check manually" panel's data.
 *
 * BRIEF-FR-006 C5 UPDATE: `GET /api/manual-sources` now exists
 * (`api/routes_api.py::manual_sources_route`) and serves
 * `opportunity/manual_sources.py::MANUAL_SOURCES` directly, read-only, with
 * zero outbound network I/O (`api/test_api.py::ManualSourcesRouteTest`
 * asserts that). This file's static transcription is corrected against the
 * live module as of this order (the stale `hacker_news_who_is_hiring`
 * entry — removed from the Python catalogue by a prior council review
 * because it is a fully automated, read-allowed adapter, not a manual
 * fallback — is deleted here too), but it is still a duplicate, not the
 * live route: `components/feed/manual-sources-panel.tsx` (the only
 * consumer) is outside this order's allowed-files list and still imports
 * `MANUAL_SOURCES` as a synchronous array, so switching this file to an
 * async `fetch("/api/manual-sources")` would require also converting that
 * component to load state asynchronously — out of scope here. A future
 * order should do both together and delete this file's static array.
 *
 * Deliberately excludes every `opportunity_type: "platform_application"`
 * (tutoring) entry: the Python module's own docstring says those "must
 * never be rendered as job postings" and belong to a founder-readiness
 * checklist feature this order does not build.
 */

export type ManualSourceCategory = "aggregator" | "regional" | "freelance"

export interface ManualSource {
  sourceId: string
  name: string
  track: "employment" | "freelance"
  category: ManualSourceCategory
  deepLink: string
  policyNote: string
}

const FOUNDER_SEARCH_QUERY =
  "data engineer OR machine learning engineer OR AI engineer"

function deepLink(template: string, query: string = FOUNDER_SEARCH_QUERY): string {
  return template.includes("{query}")
    ? template.replace("{query}", encodeURIComponent(query))
    : template
}

const REDDIT_403_NOTE =
  "Public JSON endpoint returned HTTP 403 on the first request (checked via r/forhire, 2026-09-03); AGENTS.md 403-stop rule observed, not retried."

export const MANUAL_SOURCES: ManualSource[] = [
  // --- aggregators and communities ---
  {
    sourceId: "reddit_forhire",
    name: "Reddit r/forhire",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink(
      "https://old.reddit.com/r/forhire/search?q={query}&restrict_sr=on&sort=new"
    ),
    policyNote: REDDIT_403_NOTE,
  },
  {
    sourceId: "reddit_remotejobs",
    name: "Reddit r/remotejobs",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink(
      "https://old.reddit.com/r/remotejobs/search?q={query}&restrict_sr=on&sort=new"
    ),
    policyNote: REDDIT_403_NOTE,
  },
  {
    sourceId: "reddit_machinelearningjobs",
    name: "Reddit r/MachineLearningJobs",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink(
      "https://old.reddit.com/r/MachineLearningJobs/search?q={query}&restrict_sr=on&sort=new"
    ),
    policyNote: REDDIT_403_NOTE,
  },
  {
    sourceId: "reddit_datajobs",
    name: "Reddit r/datajobs",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink(
      "https://old.reddit.com/r/datajobs/search?q={query}&restrict_sr=on&sort=new"
    ),
    policyNote: REDDIT_403_NOTE,
  },
  {
    sourceId: "reddit_hiring",
    name: "Reddit r/hiring",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink(
      "https://old.reddit.com/r/hiring/search?q={query}&restrict_sr=on&sort=new"
    ),
    policyNote: REDDIT_403_NOTE,
  },
  {
    sourceId: "reddit_jobbit",
    name: "Reddit r/jobbit",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink(
      "https://old.reddit.com/r/jobbit/search?q={query}&restrict_sr=on&sort=new"
    ),
    policyNote: REDDIT_403_NOTE,
  },
  {
    sourceId: "reddit_bigdatajobs",
    name: "Reddit r/bigdatajobs",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink(
      "https://old.reddit.com/r/bigdatajobs/search?q={query}&restrict_sr=on&sort=new"
    ),
    policyNote: REDDIT_403_NOTE,
  },
  {
    sourceId: "ycombinator_work_at_a_startup",
    name: "Y Combinator Work at a Startup",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink("https://www.workatastartup.com/jobs?query={query}"),
    policyNote:
      "robots.txt allows crawling but no documented public JSON/RSS jobs API was found; full listings require an applicant account.",
  },
  {
    sourceId: "working_nomads",
    name: "Working Nomads",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink("https://www.workingnomads.com/jobs?search={query}"),
    policyNote:
      "robots.txt allows crawling; guessed RSS/API paths returned HTTP 404. No documented public feed found.",
  },
  {
    sourceId: "remote_co",
    name: "Remote.co",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink(
      "https://remote.co/remote-jobs/search/?search_keywords={query}"
    ),
    policyNote:
      "robots.txt fetch timed out on two attempts, consistent with anti-bot mitigation; not retried a third time.",
  },
  {
    sourceId: "justremote",
    name: "JustRemote",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink("https://justremote.co/remote-jobs?search={query}"),
    policyNote:
      "robots.txt allows crawling; no documented public JSON/RSS jobs API found.",
  },
  {
    sourceId: "wellfound",
    name: "Wellfound (AngelList Talent)",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink("https://wellfound.com/jobs?query={query}"),
    policyNote:
      "Brief-designated alert-route source; job data API requires an authenticated account.",
  },
  {
    sourceId: "arc_dev",
    name: "Arc.dev",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink("https://arc.dev/remote-jobs?search={query}"),
    policyNote:
      "robots.txt allows crawling; no documented public jobs API found within recon budget.",
  },
  {
    sourceId: "ai_jobs_net",
    name: "ai-jobs.net",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink("https://ai-jobs.net/?s={query}"),
    policyNote:
      "Recon inconclusive: robots.txt request returned an HTML SPA fallback; not confirmed reachable this session.",
  },
  {
    sourceId: "otta",
    name: "Otta",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink("https://otta.com/jobs?q={query}"),
    policyNote:
      "Brief-designated alert-route source; job data requires an authenticated account.",
  },
  {
    sourceId: "jobicy",
    name: "Jobicy",
    track: "employment",
    category: "aggregator",
    deepLink: deepLink("https://jobicy.com/?s={query}"),
    policyNote:
      "robots.txt returned HTTP 403 on all three attempts. Not re-probed.",
  },

  // --- regional and Arabic-language ---
  {
    sourceId: "wuzzuf",
    name: "Wuzzuf",
    track: "employment",
    category: "regional",
    deepLink: deepLink("https://wuzzuf.net/search/jobs/?q={query}"),
    policyNote:
      "Alert-mailbox route already built (FR-004 inbox adapter); founder has not provided a mailbox to configure.",
  },
  {
    sourceId: "bayt",
    name: "Bayt.com",
    track: "employment",
    category: "regional",
    deepLink: deepLink("https://www.bayt.com/en/search/?q={query}"),
    policyNote:
      "Alert-mailbox route already built; founder has not provided a mailbox to configure.",
  },
  {
    sourceId: "gulftalent",
    name: "GulfTalent",
    track: "employment",
    category: "regional",
    deepLink: deepLink("https://www.gulftalent.com/jobs/search?keywords={query}"),
    policyNote:
      "Alert-mailbox route already built; founder has not provided a mailbox to configure.",
  },
  {
    sourceId: "naukrigulf",
    name: "Naukrigulf",
    track: "employment",
    category: "regional",
    deepLink: deepLink(
      "https://www.naukrigulf.com/jobs-in-uae?searchType=adv&keyword={query}"
    ),
    policyNote:
      "Alert-mailbox route already built; founder has not provided a mailbox to configure.",
  },
  {
    sourceId: "linkedin",
    name: "LinkedIn",
    track: "employment",
    category: "regional",
    deepLink: deepLink("https://www.linkedin.com/jobs/search/?keywords={query}"),
    policyNote:
      "robots.txt explicitly states automated access is strictly prohibited without express permission.",
  },
  {
    sourceId: "indeed",
    name: "Indeed",
    track: "employment",
    category: "regional",
    deepLink: deepLink("https://www.indeed.com/jobs?q={query}"),
    policyNote:
      "robots.txt permits generic SEO crawling but no public job-data API is documented; job alerts require an account.",
  },

  // --- freelance ---
  {
    sourceId: "mostaql",
    name: "Mostaql",
    track: "freelance",
    category: "freelance",
    deepLink: deepLink(
      "https://mostaql.com/projects?filters%5Bkeyword%5D={query}"
    ),
    policyNote:
      "robots.txt disallows /search* and /ajax/ but general browsing is not blocked; no documented public JSON/RSS projects API found.",
  },
  {
    sourceId: "khamsat",
    name: "Khamsat",
    track: "freelance",
    category: "freelance",
    deepLink: deepLink(
      "https://khamsat.com/community/services?filter%5Bkeyword%5D={query}"
    ),
    policyNote:
      "robots.txt allows general browsing with several dynamic-query disallows; no documented public API found.",
  },
  {
    sourceId: "contra",
    name: "Contra",
    track: "freelance",
    category: "freelance",
    deepLink: deepLink("https://contra.com/search/independents?q={query}"),
    policyNote:
      "robots.txt uses Content-Signal directives permitting search inclusion; no documented public gigs API found.",
  },
  {
    sourceId: "peopleperhour",
    name: "PeoplePerHour",
    track: "freelance",
    category: "freelance",
    deepLink: deepLink("https://www.peopleperhour.com/freelance-jobs?q={query}"),
    policyNote:
      "robots.txt allows general browsing; no documented public projects API found.",
  },
  {
    sourceId: "toptal",
    name: "Toptal",
    track: "freelance",
    category: "freelance",
    deepLink: "https://www.toptal.com/talent/apply",
    policyNote:
      "Application-based per brief; Toptal has no browsable open project feed for unaccepted applicants.",
  },
  {
    sourceId: "upwork",
    name: "Upwork",
    track: "freelance",
    category: "freelance",
    deepLink: deepLink("https://www.upwork.com/nx/search/jobs/?q={query}"),
    policyNote:
      "robots.txt request itself returned HTTP 403; host blocks non-browser access outright.",
  },
  {
    sourceId: "freelancer",
    name: "Freelancer.com",
    track: "freelance",
    category: "freelance",
    deepLink: deepLink("https://www.freelancer.com/jobs/?keyword={query}"),
    policyNote: "Stays credential-gated per brief instruction.",
  },
]
