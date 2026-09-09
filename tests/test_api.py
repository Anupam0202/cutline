from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from cutline.api import create_app
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
        session_secret="test-secret-which-is-longer-than-32-characters",
        cookie_secure=False,
        allowed_hosts=("testserver",),
        project_ttl_hours=72,
        provider_timeout_seconds=30,
        max_body_bytes=32_768,
        max_projects_per_session=5,
    )


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app = create_app(settings(), MemoryProjectStore(), FixtureResearchService())
        self.client = TestClient(app)
        capabilities = self.client.get("/api/capabilities")
        self.assertEqual(capabilities.status_code, 200)
        self.csrf = capabilities.json()["csrf"]
        self.headers = {"X-CSRF-Token": self.csrf}
        created = self.client.post("/api/projects", json={}, headers=self.headers)
        self.assertEqual(created.status_code, 201)
        self.project = created.json()

    def test_security_headers_and_health(self) -> None:
        response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertEqual(self.client.get("/health/ready").status_code, 200)

    def test_csrf_and_owner_session(self) -> None:
        response = self.client.patch(
            f"/api/projects/{self.project['id']}/cues/c1",
            json={"expected_revision": 1, "text": "Changed"},
        )
        self.assertEqual(response.status_code, 403)
        other = TestClient(create_app(settings(), MemoryProjectStore(), FixtureResearchService()))
        other.get("/api/capabilities")
        self.assertEqual(other.get(f"/api/projects/{self.project['id']}").status_code, 404)

    def test_complete_fixture_workflow(self) -> None:
        project_id = self.project["id"]
        edited = self.client.patch(
            f"/api/projects/{project_id}/cues/c1",
            json={
                "expected_revision": self.project["revision"],
                "text": "Apollo 11 launched from Earth on July 20, 1969.",
            },
            headers=self.headers,
        )
        self.assertEqual(edited.status_code, 200)
        project = edited.json()
        self.assertFalse(project["recipes"]["main"]["current"])
        self.assertTrue(project["recipes"]["control"]["current"])

        researched = self.client.post(
            f"/api/projects/{project_id}/cues/c1/research",
            json={"expected_revision": project["revision"]},
            headers=self.headers,
        )
        project = researched.json()
        self.assertEqual(project["claims"]["k1"]["assessment"], "CONTRADICTED")

        applied = self.client.post(
            f"/api/projects/{project_id}/cues/c1/apply",
            json={"expected_revision": project["revision"], "confirmed": True},
            headers=self.headers,
        )
        project = applied.json()
        researched = self.client.post(
            f"/api/projects/{project_id}/cues/c1/research",
            json={"expected_revision": project["revision"]},
            headers=self.headers,
        )
        project = researched.json()
        reviewed = self.client.post(
            f"/api/projects/{project_id}/cues/c1/review",
            json={"expected_revision": project["revision"]},
            headers=self.headers,
        )
        project = reviewed.json()
        signed = self.client.post(
            f"/api/projects/{project_id}/signoff",
            json={"expected_revision": project["revision"]},
            headers=self.headers,
        )
        self.assertTrue(signed.json()["recipes"]["main"]["current"])
        exported = self.client.get(f"/api/projects/{project_id}/export?format=json")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("attachment", exported.headers["content-disposition"])

    def test_stale_research_result_cannot_commit(self) -> None:
        project_id = self.project["id"]
        first = self.client.patch(
            f"/api/projects/{project_id}/cues/c1",
            json={"expected_revision": 1, "text": "First edit"},
            headers=self.headers,
        )
        self.assertEqual(first.status_code, 200)
        conflict = self.client.patch(
            f"/api/projects/{project_id}/cues/c1",
            json={"expected_revision": 1, "text": "Second edit"},
            headers=self.headers,
        )
        self.assertEqual(conflict.status_code, 409)

    def test_delete(self) -> None:
        response = self.client.delete(f"/api/projects/{self.project['id']}", headers=self.headers)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get(f"/api/projects/{self.project['id']}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
