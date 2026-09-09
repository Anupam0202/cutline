from __future__ import annotations

import unittest

from cutline.cockpit import new_custom_project, project_summary
from cutline.domain import DomainError, snapshot
from cutline.store import MemoryProjectStore


class CockpitDomainTests(unittest.TestCase):
    def test_custom_project_starts_unreviewed(self) -> None:
        project = new_custom_project(
            "owner",
            "fixture",
            72,
            "Archive rough cut",
            [
                {
                    "text": "The archive opened in 1975.",
                    "start_ms": 0,
                    "end_ms": 4_500,
                    "kind": "NARRATION_DRAFT",
                },
                {
                    "text": "An attributed quotation.",
                    "start_ms": 5_000,
                    "end_ms": 9_500,
                    "kind": "QUOTATION",
                },
            ],
        )
        state = snapshot(project)
        self.assertEqual(state["title"], "Archive rough cut")
        self.assertEqual(state["stale_claim_ids"], ["k1"])
        self.assertFalse(state["recipes"]["main"]["current"])
        self.assertEqual(state["events"][0]["template"], "CUSTOM_SCRIPT")
        self.assertNotIn("cues", project_summary(project))

    def test_custom_project_rejects_overlapping_cues(self) -> None:
        with self.assertRaisesRegex(DomainError, "cannot overlap"):
            new_custom_project(
                "owner",
                "fixture",
                72,
                "Invalid cut",
                [
                    {"text": "One", "start_ms": 0, "end_ms": 5_000, "kind": "NARRATION_DRAFT"},
                    {"text": "Two", "start_ms": 4_000, "end_ms": 8_000, "kind": "NARRATION_DRAFT"},
                ],
            )

    def test_store_lists_only_owned_projects(self) -> None:
        store = MemoryProjectStore()
        first = store.create(new_custom_project("owner", "fixture", 72, "One", [
            {"text": "Claim one", "start_ms": 0, "end_ms": 4_500, "kind": "NARRATION_DRAFT"}
        ]))
        second = store.create(new_custom_project("owner", "fixture", 72, "Two", [
            {"text": "Claim two", "start_ms": 0, "end_ms": 4_500, "kind": "NARRATION_DRAFT"}
        ]))
        store.create(new_custom_project("other", "fixture", 72, "Other", [
            {"text": "Other claim", "start_ms": 0, "end_ms": 4_500, "kind": "NARRATION_DRAFT"}
        ]))
        self.assertEqual({item["id"] for item in store.list("owner")}, {first["id"], second["id"]})
        self.assertEqual(store.list("unknown"), [])


if __name__ == "__main__":
    unittest.main()
