from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from cutline.api import create_app
from cutline.cockpit_api import attach_cockpit_routes
from cutline.config import Settings
from cutline.providers import FixtureResearchService
from cutline.store import MemoryProjectStore


def settings() -> Settings:
    return Settings(
        mode="fixture",
        data_backend="memory",
        google_cloud_project="",
        google_cloud_location="global",
        model_id="gemini-3.5-flash",
        parallel_api_key="",
        session_secret="test-secret-which-is-longer-than-32-characters",  # noqa: S106
        cookie_secure=False,
        allowed_hosts=("testserver",),
        project_ttl_hours=72,
        provider_timeout_seconds=30,
        max_body_bytes=32_768,
        max_projects_per_session=5,
    )


class CockpitApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryProjectStore()
        app = attach_cockpit_routes(create_app(settings(), self.store, FixtureResearchService()))
        self.client = TestClient(app)
        capabilities = self.client.get("/api/capabilities")
        self.csrf = capabilities.json()["csrf"]
        self.headers = {"X-CSRF-Token": self.csrf}

    def test_custom_project_and_private_resume_summary(self) -> None:
        created = self.client.post(
            "/api/custom-projects",
            json={
                "title": "Archive rough cut",
                "cues": [
                    {
                        "text": "The archive opened in 1975.",
                        "start_ms": 0,
                        "end_ms": 4_500,
                        "kind": "NARRATION_DRAFT",
                    }
                ],
            },
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["stale_claim_ids"], ["k1"])
        listed = self.client.get("/api/project-summaries")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["projects"][0]["id"], created.json()["id"])

        other = TestClient(
            attach_cockpit_routes(create_app(settings(), self.store, FixtureResearchService()))
        )
        other.get("/api/capabilities")
        self.assertEqual(other.get("/api/project-summaries").json()["projects"], [])

    def test_custom_project_requires_csrf(self) -> None:
        response = self.client.post(
            "/api/custom-projects",
            json={
                "title": "Blocked",
                "cues": [
                    {"text": "Claim", "start_ms": 0, "end_ms": 4_500, "kind": "NARRATION_DRAFT"}
                ],
            },
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
