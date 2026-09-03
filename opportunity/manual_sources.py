"""Manual-source catalogue for BRIEF-FR-006 E23 (Track E, nodes E2+E3).

Every entry here corresponds to a `docs/SOURCE_REGISTRY.yaml` source whose dated recon
outcome is `manual_only` or `BLOCKED_POLICY`: automated reading is disallowed by robots,
terms, or credential-gating, or the source is a platform-application (tutoring) rather
than a postings feed. No adapter reads any of these. Work order C3 renders this
catalogue as the "Check manually" panel; this module only supplies the data and a
resolvable-deep-link test (`opportunity/test_manual_sources.py`).

Tutoring entries are `opportunity_type="platform_application"` and must never be
rendered as job postings -- they are registration/profile platforms, surfaced under
`track = tutoring` with a founder readiness checklist instead of posting fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote

from opportunity.models import Track

# The founder's default search terms for prefilled deep links (data/ML/AI engineering).
FOUNDER_SEARCH_QUERY = "data engineer OR machine learning engineer OR AI engineer"


@dataclass(frozen=True, slots=True)
class ManualSource:
    source_id: str
    name: str
    track: Track
    opportunity_type: str  # "manual_only" | "platform_application"
    deep_link_template: str  # "{query}" is substituted with a URL-quoted search term, if present
    category: str  # "aggregator" | "regional" | "freelance" | "tutoring"
    policy_note: str = ""
    alert_route_available: bool = False
    alert_route_configured: bool = False
    readiness_checklist: tuple[str, ...] = field(default_factory=tuple)

    def deep_link(self, query: str = FOUNDER_SEARCH_QUERY) -> str:
        if "{query}" in self.deep_link_template:
            return self.deep_link_template.format(query=quote(query))
        return self.deep_link_template


_REDDIT_403_NOTE = (
    "Public JSON endpoint (https://www.reddit.com/r/<subreddit>.json) returned HTTP 403 "
    "on the first request (checked via r/forhire, 2026-09-03); AGENTS.md 403-stop rule "
    "observed, not retried, and generalized to the other six listed subreddits sharing "
    "the same host, endpoint pattern, and anti-bot policy rather than requesting each one "
    "individually against an already-blocking host."
)

TUTORING_READINESS_CHECKLIST: tuple[str, ...] = (
    "Founder profile photo and bio drafted",
    "Subject/skill areas selected",
    "Identity verification documents ready (platform-specific)",
    "Availability calendar defined",
    "Introductory/demo video recorded (where required)",
)

MANUAL_SOURCES: tuple[ManualSource, ...] = (
    # --- E2: aggregators and communities -----------------------------------------
    ManualSource(
        "hacker_news_who_is_hiring", "Hacker News \"Who is hiring?\"", Track.EMPLOYMENT,
        "manual_only", "https://hn.algolia.com/?q={query}&type=comment", "aggregator",
        "Registered here only as a fallback deep link; the primary route is the read-allowed "
        "adapter (see docs/SOURCE_REGISTRY.yaml: hacker_news_who_is_hiring, read=allowed).",
    ),
    ManualSource("reddit_forhire", "Reddit r/forhire", Track.EMPLOYMENT, "manual_only",
                 "https://old.reddit.com/r/forhire/search?q={query}&restrict_sr=on&sort=new", "aggregator", _REDDIT_403_NOTE),
    ManualSource("reddit_remotejobs", "Reddit r/remotejobs", Track.EMPLOYMENT, "manual_only",
                 "https://old.reddit.com/r/remotejobs/search?q={query}&restrict_sr=on&sort=new", "aggregator", _REDDIT_403_NOTE),
    ManualSource("reddit_machinelearningjobs", "Reddit r/MachineLearningJobs", Track.EMPLOYMENT, "manual_only",
                 "https://old.reddit.com/r/MachineLearningJobs/search?q={query}&restrict_sr=on&sort=new", "aggregator", _REDDIT_403_NOTE),
    ManualSource("reddit_datajobs", "Reddit r/datajobs", Track.EMPLOYMENT, "manual_only",
                 "https://old.reddit.com/r/datajobs/search?q={query}&restrict_sr=on&sort=new", "aggregator", _REDDIT_403_NOTE),
    ManualSource("reddit_hiring", "Reddit r/hiring", Track.EMPLOYMENT, "manual_only",
                 "https://old.reddit.com/r/hiring/search?q={query}&restrict_sr=on&sort=new", "aggregator", _REDDIT_403_NOTE),
    ManualSource("reddit_jobbit", "Reddit r/jobbit", Track.EMPLOYMENT, "manual_only",
                 "https://old.reddit.com/r/jobbit/search?q={query}&restrict_sr=on&sort=new", "aggregator", _REDDIT_403_NOTE),
    ManualSource("reddit_bigdatajobs", "Reddit r/bigdatajobs", Track.EMPLOYMENT, "manual_only",
                 "https://old.reddit.com/r/bigdatajobs/search?q={query}&restrict_sr=on&sort=new", "aggregator", _REDDIT_403_NOTE),
    ManualSource("ycombinator_work_at_a_startup", "Y Combinator Work at a Startup", Track.EMPLOYMENT, "manual_only",
                 "https://www.workatastartup.com/jobs?query={query}", "aggregator",
                 "robots.txt allows crawling (checked 2026-09-03) but no documented public JSON/RSS jobs API "
                 "was found within recon budget; full listings require an applicant account. Deep link only."),
    ManualSource("working_nomads", "Working Nomads", Track.EMPLOYMENT, "manual_only",
                 "https://www.workingnomads.com/jobs?search={query}", "aggregator",
                 "robots.txt allows crawling (checked 2026-09-03); guessed RSS/API paths "
                 "(/jobs.rss, /api/exposed_jobs/rss) returned HTTP 404. No documented public feed found. Deep link only."),
    ManualSource("remote_co", "Remote.co", Track.EMPLOYMENT, "manual_only",
                 "https://remote.co/remote-jobs/search/?search_keywords={query}", "aggregator",
                 "robots.txt fetch timed out on two attempts (2026-09-03), consistent with anti-bot mitigation "
                 "against a non-browser user agent; not retried a third time. Deep link only."),
    ManualSource("justremote", "JustRemote", Track.EMPLOYMENT, "manual_only",
                 "https://justremote.co/remote-jobs?search={query}", "aggregator",
                 "robots.txt allows crawling (checked 2026-09-03); no documented public JSON/RSS jobs API found. Deep link only."),
    ManualSource("wellfound", "Wellfound (AngelList Talent)", Track.EMPLOYMENT, "manual_only",
                 "https://wellfound.com/jobs?query={query}", "aggregator",
                 "Brief-designated alert-route source; job data API requires an authenticated account. "
                 "robots.txt checked 2026-09-03 (partial disallow on job/session paths).",
                 alert_route_available=True, alert_route_configured=False),
    ManualSource("arc_dev", "Arc.dev", Track.EMPLOYMENT, "manual_only",
                 "https://arc.dev/remote-jobs?search={query}", "aggregator",
                 "robots.txt allows crawling (checked 2026-09-03); no documented public jobs API found within recon budget. Deep link only."),
    ManualSource("ai_jobs_net", "ai-jobs.net", Track.EMPLOYMENT, "manual_only",
                 "https://ai-jobs.net/?s={query}", "aggregator",
                 "Recon inconclusive (checked 2026-09-03): robots.txt request returned an HTML SPA fallback "
                 "rather than a text robots file, and the candidate API path timed out. Not confirmed reachable "
                 "in this session; registered manual_only pending a future, successful recon pass."),
    ManualSource("otta", "Otta", Track.EMPLOYMENT, "manual_only",
                 "https://otta.com/jobs?q={query}", "aggregator",
                 "Brief-designated alert-route source; job data requires an authenticated account. "
                 "robots.txt checked 2026-09-03 (generic allow).",
                 alert_route_available=True, alert_route_configured=False),
    ManualSource("jobicy", "Jobicy", Track.EMPLOYMENT, "manual_only",
                 "https://jobicy.com/?s={query}", "aggregator",
                 "Already registered by prior recon: robots.txt returned HTTP 403 on all three attempts "
                 "(2026-09-02). Not re-probed per this order's facts. Deep link only."),

    # --- E2: regional and Arabic-language -----------------------------------------
    ManualSource("wuzzuf", "Wuzzuf", Track.EMPLOYMENT, "manual_only",
                 "https://wuzzuf.net/search/jobs/?q={query}", "regional",
                 "Alert-mailbox route already built (FR-004 inbox adapter); founder has not provided a mailbox "
                 "to configure. robots.txt uses Content-Signal directives, not classic Disallow (checked 2026-09-03).",
                 alert_route_available=True, alert_route_configured=False),
    ManualSource("bayt", "Bayt.com", Track.EMPLOYMENT, "manual_only",
                 "https://www.bayt.com/en/search/?q={query}", "regional",
                 "Alert-mailbox route already built; founder has not provided a mailbox to configure. "
                 "robots.txt explicitly disallows named bots (008, LinkedInBot, IndexBot) (checked 2026-09-03).",
                 alert_route_available=True, alert_route_configured=False),
    ManualSource("gulftalent", "GulfTalent", Track.EMPLOYMENT, "manual_only",
                 "https://www.gulftalent.com/jobs/search?keywords={query}", "regional",
                 "Alert-mailbox route already built; founder has not provided a mailbox to configure. "
                 "robots.txt explicitly disallows named bots (checked 2026-09-03).",
                 alert_route_available=True, alert_route_configured=False),
    ManualSource("naukrigulf", "Naukrigulf", Track.EMPLOYMENT, "manual_only",
                 "https://www.naukrigulf.com/jobs-in-uae?searchType=adv&keyword={query}", "regional",
                 "Alert-mailbox route already built; founder has not provided a mailbox to configure. "
                 "robots.txt fetch timed out on two attempts (2026-09-03); not retried a third time.",
                 alert_route_available=True, alert_route_configured=False),
    ManualSource("linkedin", "LinkedIn", Track.EMPLOYMENT, "manual_only",
                 "https://www.linkedin.com/jobs/search/?keywords={query}", "regional",
                 "robots.txt explicitly states automated access is strictly prohibited without express permission "
                 "(checked 2026-09-03). Alert-mailbox route available, unconfigured (no founder mailbox).",
                 alert_route_available=True, alert_route_configured=False),
    ManualSource("indeed", "Indeed", Track.EMPLOYMENT, "manual_only",
                 "https://www.indeed.com/jobs?q={query}", "regional",
                 "robots.txt permits generic SEO crawling but no public job-data API is documented; job alerts "
                 "require an account. Alert-mailbox route available, unconfigured (checked 2026-09-03).",
                 alert_route_available=True, alert_route_configured=False),

    # --- E3: freelance ---------------------------------------------------------
    ManualSource("mostaql", "Mostaql", Track.FREELANCE, "manual_only",
                 "https://mostaql.com/projects?filters%5Bkeyword%5D={query}", "freelance",
                 "robots.txt disallows /search* and /ajax/ but general browsing is not blocked (checked 2026-09-03); "
                 "no documented public JSON/RSS projects API found. Deep link only."),
    ManualSource("khamsat", "Khamsat", Track.FREELANCE, "manual_only",
                 "https://khamsat.com/community/services?filter%5Bkeyword%5D={query}", "freelance",
                 "robots.txt allows general browsing with several dynamic-query disallows (checked 2026-09-03); "
                 "no documented public API found. Deep link only."),
    ManualSource("contra", "Contra", Track.FREELANCE, "manual_only",
                 "https://contra.com/search/independents?q={query}", "freelance",
                 "robots.txt uses Content-Signal directives permitting search inclusion (ai-train=no, search=yes) "
                 "(checked 2026-09-03); no documented public gigs API found. Deep link only."),
    ManualSource("peopleperhour", "PeoplePerHour", Track.FREELANCE, "manual_only",
                 "https://www.peopleperhour.com/freelance-jobs?q={query}", "freelance",
                 "robots.txt allows general browsing (checked 2026-09-03); no documented public projects API found. Deep link only."),
    ManualSource("toptal", "Toptal", Track.FREELANCE, "manual_only",
                 "https://www.toptal.com/talent/apply", "freelance",
                 "Application-based per brief; Toptal has no browsable open project feed for unaccepted applicants. Deep link only."),
    ManualSource("upwork", "Upwork", Track.FREELANCE, "manual_only",
                 "https://www.upwork.com/nx/search/jobs/?q={query}", "freelance",
                 "robots.txt request itself returned HTTP 403 (checked 2026-09-03); host blocks non-browser access "
                 "outright, confirming the brief's note that the API is partner-only. Not retried; RSS search "
                 "feeds could not be safely reconned without a second request to an already-blocking host."),
    ManualSource("freelancer", "Freelancer.com", Track.FREELANCE, "manual_only",
                 "https://www.freelancer.com/jobs/?keyword={query}", "freelance",
                 "Stays credential-gated per brief instruction; existing registry entry (docs/SOURCE_REGISTRY.yaml) "
                 "left as-is. Deep link only."),

    # --- E3: tutoring (platform_application, never rendered as postings) -----------
    ManualSource("preply", "Preply", Track.TUTORING, "platform_application",
                 "https://preply.com/en/apply-to-preply-tutor", "tutoring",
                 "Platform application, not a postings feed (checked 2026-09-03).",
                 readiness_checklist=TUTORING_READINESS_CHECKLIST),
    ManualSource("superprof", "Superprof", Track.TUTORING, "platform_application",
                 "https://www.superprof.com/apply.html", "tutoring",
                 "Platform application, not a postings feed; robots.txt request itself returned HTTP 403 "
                 "(Cloudflare bot mitigation, checked 2026-09-03), confirming no automated route exists.",
                 readiness_checklist=TUTORING_READINESS_CHECKLIST),
    ManualSource("wyzant", "Wyzant", Track.TUTORING, "platform_application",
                 "https://www.wyzant.com/tutor/apply", "tutoring",
                 "Platform application, not a postings feed (checked 2026-09-03).",
                 readiness_checklist=TUTORING_READINESS_CHECKLIST),
    ManualSource("tutor_com", "Tutor.com", Track.TUTORING, "platform_application",
                 "https://www.tutor.com/apply", "tutoring",
                 "Platform application, not a postings feed (checked 2026-09-03).",
                 readiness_checklist=TUTORING_READINESS_CHECKLIST),
    ManualSource("chegg", "Chegg Tutors", Track.TUTORING, "platform_application",
                 "https://www.chegg.com/tutors/apply/", "tutoring",
                 "Platform application, not a postings feed (checked 2026-09-03).",
                 readiness_checklist=TUTORING_READINESS_CHECKLIST),
    ManualSource("cambly", "Cambly", Track.TUTORING, "platform_application",
                 "https://www.cambly.com/tutor", "tutoring",
                 "Platform application, not a postings feed (checked 2026-09-03).",
                 readiness_checklist=TUTORING_READINESS_CHECKLIST),
)


def by_category(category: str) -> tuple[ManualSource, ...]:
    return tuple(item for item in MANUAL_SOURCES if item.category == category)


def tutoring_platform_cards() -> tuple[ManualSource, ...]:
    return tuple(item for item in MANUAL_SOURCES if item.track == Track.TUTORING and item.opportunity_type == "platform_application")
