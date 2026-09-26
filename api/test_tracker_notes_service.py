from __future__ import annotations

import unittest

from fastapi import HTTPException

from api.routes_api import get_tracker_notes


class DeferredDeepTrackerContractTest(unittest.TestCase):
    def test_get_tracker_notes_is_explicitly_deferred(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            get_tracker_notes("synthetic", page=1, page_size=10, session=None)
        self.assertEqual(raised.exception.status_code, 501)
        self.assertIn("deferred", str(raised.exception.detail).lower())


if __name__ == "__main__":
    unittest.main()
