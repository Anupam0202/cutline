from __future__ import annotations

import concurrent.futures
import unittest

from cutline.domain import DomainError, edit_cue, new_project
from cutline.store import MemoryProjectStore


class MemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryProjectStore()
        self.project = self.store.create(new_project("owner", "fixture", 72))

    def test_owner_isolation(self) -> None:
        with self.assertRaisesRegex(DomainError, "not found"):
            self.store.get("other-owner", self.project["id"])

    def test_same_revision_allows_exactly_one_writer(self) -> None:
        def mutate(text: str) -> str:
            try:
                self.store.mutate(
                    "owner",
                    self.project["id"],
                    1,
                    lambda project: edit_cue(project, "c1", text),
                )
                return "ok"
            except DomainError as exc:
                return exc.code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(mutate, ["First edit", "Second edit"]))
        self.assertEqual(sorted(results), ["REVISION_CONFLICT", "ok"])

    def test_delete_removes_project(self) -> None:
        self.store.delete("owner", self.project["id"])
        with self.assertRaises(DomainError):
            self.store.get("owner", self.project["id"])


if __name__ == "__main__":
    unittest.main()
