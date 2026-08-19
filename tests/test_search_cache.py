from __future__ import annotations

import json

from src.search.budget import SearchBudget
from src.search.cache import CachedSearchProvider
from src.search.models import SearchResult
from src.search.provider import SearchProvider


class CountingProvider(SearchProvider):
    def __init__(self, budget: SearchBudget) -> None:
        self.budget = budget
        self.calls = 0

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        self.calls += 1
        self.budget.record_search(cache_hit=False)
        return [
            SearchResult(
                url="https://example.com",
                title="Example",
                snippet="snippet",
                content="content",
                raw_score=0.5,
                provider="fake",
                query=query,
                retrieved_at="2026-08-19T12:00:00Z",
            )
        ]


def test_cache_miss_calls_provider_and_hit_does_not_charge(tmp_path) -> None:
    budget = SearchBudget(tmp_path / "credit_usage.json")
    inner = CountingProvider(budget)
    provider = CachedSearchProvider(
        inner,
        provider_name="fake",
        depth="advanced",
        cache_dir=tmp_path / "search",
    )

    miss_results = provider.search("test query")
    hit_results = provider.search("test query")

    assert hit_results == miss_results
    assert inner.calls == 1
    assert budget.execution_credits == 2
    assert len(list((tmp_path / "search").glob("*.json"))) == 1


def test_cache_key_changes_with_max_results(tmp_path) -> None:
    budget = SearchBudget(tmp_path / "credit_usage.json")
    inner = CountingProvider(budget)
    provider = CachedSearchProvider(
        inner,
        provider_name="fake",
        depth="advanced",
        cache_dir=tmp_path / "search",
    )

    first_path = provider.cache_path("test query", 5)
    second_path = provider.cache_path("test query", 10)

    assert first_path != second_path


def test_cache_value_is_json_and_preserves_normalized_response(tmp_path) -> None:
    budget = SearchBudget(tmp_path / "credit_usage.json")
    provider = CachedSearchProvider(
        CountingProvider(budget),
        provider_name="fake",
        depth="advanced",
        cache_dir=tmp_path / "search",
    )

    provider.search("test query")
    payload = json.loads(provider.cache_path("test query").read_text(encoding="utf-8"))

    assert payload["provider"] == "fake"
    assert payload["query"] == "test query"
    assert payload["search_depth"] == "advanced"
    assert payload["format"] == "normalized_search_results"
    assert payload["results"][0]["url"] == "https://example.com"
