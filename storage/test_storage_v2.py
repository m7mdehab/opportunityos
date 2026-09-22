from __future__ import annotations

import unittest

from storage.cold_storage import archive_key, pack, unpack


class StorageV2Tests(unittest.TestCase):
    def test_content_addressed_archive_round_trip_and_checksum(self):
        content_hash = "a" * 64
        payload = {"opportunity_id": "opp-1", "content_hash": content_hash, "description": "authoritative " * 100}
        compressed, digest, original_size = pack(payload)
        self.assertEqual(archive_key(content_hash), f"cold-opportunities/{content_hash}.json.zlib")
        self.assertGreater(original_size, len(compressed))
        self.assertEqual(unpack(compressed, digest, opportunity_id="opp-1", content_hash=content_hash), payload)

    def test_corruption_fails_closed(self):
        content_hash = "b" * 64
        compressed, digest, _ = pack({"opportunity_id": "opp-2", "content_hash": content_hash})
        with self.assertRaises(RuntimeError):
            unpack(compressed + b"x", digest, opportunity_id="opp-2", content_hash=content_hash)


if __name__ == "__main__":
    unittest.main()
