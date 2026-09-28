import unittest

from opportunity.discovery.reddit import canonicalize_ats_url, parse_hiring_post


class RedditDiscoveryTests(unittest.TestCase):
    def test_hiring_post_canonicalizes_direct_ats_and_preserves_discovery_link(self):
        result = parse_hiring_post({
            "id": "abc123",
            "subreddit": "dataengineeringjobs",
            "permalink": "/r/dataengineeringjobs/comments/abc123/hiring/",
            "title": "[Hiring] Senior Data Engineer",
            "selftext": "We are hiring. Apply: https://job-boards.greenhouse.io/acme/jobs/123?gh_src=reddit",
            "created_utc": 1780000000,
            "employer": "Acme",
        })
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("dataengineeringjobs", result.subreddit)
        self.assertEqual("https://www.reddit.com/r/dataengineeringjobs/comments/abc123/hiring/", result.permalink)
        self.assertEqual("https://job-boards.greenhouse.io/acme/jobs/123", result.canonical_url)
        self.assertEqual("greenhouse", result.application_route)
        self.assertGreaterEqual(result.confidence, 0.8)

    def test_forhire_discussion_and_training_posts_are_not_job_candidates(self):
        self.assertIsNone(parse_hiring_post({"title": "[ForHire] Data Engineer", "selftext": "Available now"}))
        self.assertIsNone(parse_hiring_post({"title": "How do I find data jobs?", "selftext": "Discussion thread"}))
        self.assertIsNone(parse_hiring_post({"title": "[Hiring] Data Engineer Bootcamp", "selftext": "Training program"}))

    def test_reddit_only_hiring_post_is_kept_at_lower_confidence(self):
        result = parse_hiring_post({
            "id": "xyz",
            "subreddit": "RemotePython",
            "permalink": "/r/RemotePython/comments/xyz/hiring/",
            "title": "[Hiring] Python Data Engineer",
            "selftext": "We are hiring remotely; details in the post.",
        })
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("", result.application_url)
        self.assertEqual("unknown", result.application_route)
        self.assertEqual(0.75, result.confidence)

    def test_only_known_ats_routes_are_canonicalized(self):
        self.assertEqual(
            ("lever", "https://jobs.lever.co/acme/123"),
            canonicalize_ats_url("https://jobs.lever.co/acme/123?source=reddit"),
        )
        self.assertIsNone(canonicalize_ats_url("https://example.com/jobs/1"))


if __name__ == "__main__":
    unittest.main()
