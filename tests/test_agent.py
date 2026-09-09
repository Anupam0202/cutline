from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from cutline.agents.claim_research import agent


class FakeSecretManagerClient:
    last_resource = ""

    def get_secret(self, resource_name: str) -> str:
        type(self).last_resource = resource_name
        return "resolved-key"


class AgentSecretTests(unittest.TestCase):
    def setUp(self) -> None:
        agent._parallel_api_key.cache_clear()
        FakeSecretManagerClient.last_resource = ""

    def tearDown(self) -> None:
        agent._parallel_api_key.cache_clear()

    def test_environment_key_takes_precedence(self) -> None:
        environment = {"PARALLEL_API_KEY": "direct-key"}  # noqa: S105
        with patch.dict(os.environ, environment, clear=False):
            self.assertEqual(agent._parallel_api_key(), "direct-key")

    def test_secret_manager_fallback_uses_latest_version(self) -> None:
        environment = {
            "PARALLEL_API_KEY": "",
            "GOOGLE_CLOUD_PROJECT": "example-project",
            "PARALLEL_API_KEY_SECRET": "parallel-api-key",
        }
        with patch.dict(os.environ, environment, clear=False):
            with patch.object(agent, "SecretManagerClient", FakeSecretManagerClient):
                self.assertEqual(agent._parallel_api_key(), "resolved-key")
        self.assertEqual(
            FakeSecretManagerClient.last_resource,
            "projects/example-project/secrets/parallel-api-key/versions/latest",
        )

    def test_application_default_project_is_supported(self) -> None:
        environment = {"PARALLEL_API_KEY": "", "GOOGLE_CLOUD_PROJECT": ""}
        with patch.dict(os.environ, environment, clear=False):
            with patch.object(agent, "google_auth_default", return_value=(object(), "adc-project")):
                with patch.object(agent, "SecretManagerClient", FakeSecretManagerClient):
                    self.assertEqual(agent._parallel_api_key(), "resolved-key")
        self.assertIn("projects/adc-project/", FakeSecretManagerClient.last_resource)


if __name__ == "__main__":
    unittest.main()
