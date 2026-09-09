from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from cutline.config import ConfigurationError, Settings


class ConfigurationTests(unittest.TestCase):
    def test_fixture_defaults_are_safe(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.mode, "fixture")
        self.assertEqual(settings.data_backend, "memory")
        self.assertFalse(settings.live_ready)

    def test_live_mode_requires_all_controls(self) -> None:
        with patch.dict(os.environ, {"APP_MODE": "live"}, clear=True):
            with self.assertRaises(ConfigurationError):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
