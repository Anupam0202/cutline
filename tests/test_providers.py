from __future__ import annotations

import unittest

from cutline.providers import FixtureResearchService, LiveResearchService, _search_sources


class Item:
    def __init__(self, url: str, title: str, excerpt: str) -> None:
        self.url = url
        self.title = title
        self.excerpt = excerpt


class Response:
    def __init__(self) -> None:
        self.results = [
            Item("https://example.org/source", "Primary source", "Apollo 11 launched on July 16, 1969."),
            Item("javascript:alert(1)", "Bad", "Ignore"),
        ]


class ProviderBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_receipt_is_explicit(self) -> None:
        outcome = await FixtureResearchService().research(
            {"text": "Apollo 11 launched from Earth on July 16, 1969."}
        )
        self.assertFalse(outcome["provider_receipt"]["parallel_called"])
        self.assertFalse(outcome["provider_receipt"]["gemini_called"])

    def test_search_normalization_rejects_unsafe_url(self) -> None:
        sources = _search_sources(Response())
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["url"], "https://example.org/source")

    def test_unverifiable_citation_is_downgraded(self) -> None:
        sources = [
            {
                "id": "one",
                "url": "https://example.org",
                "title": "Source",
                "capture": "Apollo 11 launched on July 16, 1969.",
                "retrieved_at": "now",
                "provider": "PARALLEL_SEARCH",
            }
        ]
        assessment = {
            "assessment": "SUPPORTED",
            "span": "launch date",
            "proposition": "Apollo 11 launched July 16.",
            "rationale": "Claimed support",
            "supporting_source_indexes": [0],
            "supporting_quotes": ["A quotation that is not present"],
            "proposal": None,
        }
        result = LiveResearchService._validate_assessment("cue", sources, assessment)
        self.assertEqual(result["assessment"], "INSUFFICIENT")


if __name__ == "__main__":
    unittest.main()
