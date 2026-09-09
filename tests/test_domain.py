from __future__ import annotations

import unittest

from cutline.domain import (
    DomainError,
    apply_proposal,
    apply_research,
    edit_cue,
    export_csv,
    export_handoff,
    new_project,
    review_claim,
    signoff_recipes,
    snapshot,
)
from cutline.providers import FixtureResearchService


class DomainTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.project = new_project("owner", "fixture", 72)

    def test_baseline_is_current(self) -> None:
        state = snapshot(self.project)
        self.assertFalse(state["stale_claim_ids"])
        self.assertTrue(all(recipe["current"] for recipe in state["recipes"].values()))

    def test_edit_invalidates_only_dependent_recipes(self) -> None:
        edit_cue(self.project, "c1", "Apollo 11 launched from Earth on July 20, 1969.")
        state = snapshot(self.project)
        self.assertEqual(state["stale_claim_ids"], ["k1"])
        self.assertFalse(state["recipes"]["main"]["current"])
        self.assertFalse(state["recipes"]["teaser"]["current"])
        self.assertTrue(state["recipes"]["control"]["current"])

    def test_quotation_is_immutable(self) -> None:
        with self.assertRaisesRegex(DomainError, "Quoted material"):
            edit_cue(self.project, "q1", "Different quote")

    async def test_research_repair_review_and_signoff(self) -> None:
        edit_cue(self.project, "c1", "Apollo 11 launched from Earth on July 20, 1969.")
        service = FixtureResearchService()
        outcome = await service.research(self.project["cues"]["c1"])
        apply_research(self.project, "c1", outcome)
        self.assertEqual(self.project["claims"]["k1"]["assessment"], "CONTRADICTED")
        with self.assertRaises(DomainError):
            review_claim(self.project, "c1")
        apply_proposal(self.project, "c1", True)
        outcome = await service.research(self.project["cues"]["c1"])
        apply_research(self.project, "c1", outcome)
        review_claim(self.project, "c1")
        signoff_recipes(self.project)
        self.assertTrue(snapshot(self.project)["recipes"]["main"]["current"])
        handoff = export_handoff(self.project)
        self.assertEqual(handoff["cues"][0]["after_text"], "Apollo 11 launched from Earth on July 16, 1969.")

    def test_export_stays_blocked_while_stale(self) -> None:
        edit_cue(self.project, "c1", "Apollo 11 launched from Earth on July 20, 1969.")
        with self.assertRaisesRegex(DomainError, "Export is blocked"):
            export_handoff(self.project)

    def test_csv_formula_neutralization(self) -> None:
        handoff = export_handoff(self.project)
        handoff["cues"][0]["after_text"] = "=HYPERLINK(\"https://example.com\")"
        rendered = export_csv(handoff)
        self.assertIn("'=HYPERLINK", rendered)


if __name__ == "__main__":
    unittest.main()
