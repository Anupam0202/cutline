from __future__ import annotations

import unittest

from cutline.security import SessionManager


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = SessionManager("x" * 48)

    def test_round_trip_and_csrf(self) -> None:
        token, issued = self.manager.issue()
        loaded = self.manager.context(token)
        self.assertEqual(issued, loaded)
        self.assertTrue(self.manager.csrf_valid(loaded, loaded.csrf_token))
        self.assertFalse(self.manager.csrf_valid(loaded, "wrong"))

    def test_tampered_token_is_rejected(self) -> None:
        token, _ = self.manager.issue()
        with self.assertRaises(ValueError):
            self.manager.context(token + "x")


if __name__ == "__main__":
    unittest.main()
