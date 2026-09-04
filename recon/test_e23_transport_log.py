"""BRIEF-FR-006 E23: transport-log assertion (order requirement 7) -- no source that
returned 403 or 429 during the E23 recon sweep was requested a second time in the same
run. `E23_RECON_REQUEST_LOG` below is a manual, hand-typed transcription of the dated
2026-09-03 recon requests (see docs/SOURCE_EVIDENCE.md), NOT a machine-replayed log --
the probe scripts that made those requests were not committed, and
`reports/evidence/FR-006/e23-recon-log.md` does not exist. This test replays the
transcription through `recon.transport_log.TransportLog`, in request order, and asserts
no retry-after-block occurred; it demonstrates `TransportLog`'s guard logic is
consistent with the transcribed sequence, not that the transcription itself was
independently machine-verified against raw request logs (council review 4, finding
15)."""
from __future__ import annotations

import unittest

from recon.transport_log import BlockedSourceRetryError, TransportLog

# (canonical_source_id, http_status_or_error, probe_pass) in the exact order the E23
# recon requests were made on 2026-09-03. Two passes: pass 1 = recon_probe.py (initial
# sweep); pass 2 = recon_probe2.py (retry of network/cert errors only -- 403/429 hosts
# were never included in pass 2).
E23_RECON_REQUEST_LOG: tuple[tuple[str, int | str, int], ...] = (
    ("hacker_news_who_is_hiring", 200, 1),
    ("hacker_news_who_is_hiring", 200, 1),
    ("reddit_forhire", 200, 1),   # robots.txt itself
    ("reddit_forhire", 403, 1),   # r/forhire.json -- BLOCKED
    ("ycombinator_work_at_a_startup", 200, 1),
    ("working_nomads", 200, 1),
    ("working_nomads", 404, 1),
    ("remote_co", "timeout", 1),
    ("justremote", 200, 1),
    ("wellfound", 200, 1),
    ("arc_dev", 200, 1),
    ("ai_jobs_net", "tls_error", 1),
    ("ai_jobs_net", "tls_error", 1),
    ("otta", 200, 1),
    ("wuzzuf", "tls_error", 1),
    ("bayt", 200, 1),
    ("gulftalent", 200, 1),
    ("naukrigulf", "timeout", 1),
    ("linkedin", 200, 1),
    ("indeed", 200, 1),
    ("mostaql", 200, 1),
    ("khamsat", 200, 1),
    ("contra", "tls_error", 1),
    ("peopleperhour", 200, 1),
    ("toptal", 200, 1),
    ("upwork", 403, 1),           # BLOCKED
    ("freelancer", 200, 1),
    ("preply", 200, 1),
    ("superprof", 403, 1),        # BLOCKED
    ("wyzant", "tls_error", 1),
    ("tutor_com", 200, 1),
    ("chegg", 200, 1),
    ("cambly", 200, 1),
    # Pass 2: retries of network/TLS errors only -- never a 403/429 host.
    ("remote_co", "timeout", 2),
    ("naukrigulf", "timeout", 2),
    ("ai_jobs_net", 200, 2),      # SPA fallback HTML, not a real robots.txt
    ("ai_jobs_net", "timeout", 2),
    ("wuzzuf", 200, 2),
    ("contra", 200, 2),
    ("wyzant", 200, 2),
    ("working_nomads", 404, 2),
    ("wellfound", 200, 2),
)

EXPECTED_BLOCKED = ("reddit_forhire", "superprof", "upwork")


class TransportLogGuardTests(unittest.TestCase):
    def test_guard_refuses_a_second_request_after_a_block(self):
        log = TransportLog()
        log.record("upwork", 403)
        with self.assertRaises(BlockedSourceRetryError):
            log.record("upwork", 403)

    def test_guard_allows_repeated_requests_that_are_not_blocking(self):
        log = TransportLog()
        log.record("remote_co", "timeout")
        log.record("remote_co", "timeout")  # non-blocking status: retry is fine
        self.assertEqual((), log.blocked_sources)

    def test_e23_recon_sweep_never_retried_a_blocked_source(self):
        log = TransportLog()
        for source_id, status, _pass_number in E23_RECON_REQUEST_LOG:
            log.record(source_id, status)  # raises BlockedSourceRetryError if this test should fail
        self.assertEqual(EXPECTED_BLOCKED, log.blocked_sources)


if __name__ == "__main__":
    unittest.main()
