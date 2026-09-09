from __future__ import annotations

import unittest
from typing import Any

from cutline.cockpit import new_custom_project, project_summary
from cutline.domain import DomainError, snapshot
from cutline.store import MemoryProjectStore


def cue(
    text: str,
    start_ms: int = 0,
    end_ms: int = 4_500,
    kind: str = "NARRATION_DRAFT",
) -> dict[str, Any]:
    return {"text": text, "start_ms": start_ms, "end_ms": end_ms, "kind": kind}


class CockpitDomainTests(unittest.TestCase):
    def test_custom_project_starts_unreviewed(self) -> None:
        project = new_custom_project(
            "owner",
            "fixture",
            72,
            "Archive rough cut",
            [
                cue("The archive opened in 1975."),
                cue("An attributed quotation.", 5_000, 9_500, "QUOTATION"),
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
                [cue("One", 0, 5_000), cue("Two", 4_000, 8_000)],
            )

    def test_store_lists_only_owned_projects(self) -> None:
        store = MemoryProjectStore()
        first = store.create(new_custom_project("owner", "fixture", 72, "One", [cue("Claim one")]))
        second = store.create(new_custom_project("owner", "fixture", 72, "Two", [cue("Claim two")]))
        store.create(new_custom_project("other", "fixture", 72, "Other", [cue("Other claim")]))

        self.assertEqual({item["id"] for item in store.list("owner")}, {first["id"], second["id"]})
        self.assertEqual(store.list("unknown"), [])


if __name__ == "__main__":
    unittest.main()
