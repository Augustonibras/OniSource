from __future__ import annotations

import json

import pytest

from src.search.cassette import (
    CassetteMalformedError,
    CassetteNotFoundError,
    CassetteSearchProvider,
)
from src.search.models import SearchResult
from src.search.provider import SearchProvider


def _write_cassette(
    provider: CassetteSearchProvider,
    query: str,
    *,
    max_results: int = 10,
) -> None:
    path = provider.cassette_path(query, max_results)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "provider": "tavily",
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "retrieved_at": "2026-08-19T12:00:00Z",
                "response": {
                    "results": [
                        {
                            "url": "https://example.com/product",
                            "title": "Product page",
                            "content": "Search result snippet",
                            "raw_content": "Extracted advanced-search content",
                            "score": 0.91,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )


def test_cassette_provider_satisfies_search_provider_contract(tmp_path) -> None:
    provider = CassetteSearchProvider(tmp_path)
    assert isinstance(provider, SearchProvider)
    _write_cassette(provider, "phosphoric acid manufacturer")

    results = provider.search("phosphoric acid manufacturer")

    assert results == [
        SearchResult(
            url="https://example.com/product",
            title="Product page",
            snippet="Search result snippet",
            content="Extracted advanced-search content",
            raw_score=0.91,
            provider="tavily",
            query="phosphoric acid manufacturer",
            retrieved_at="2026-08-19T12:00:00Z",
        )
    ]


def test_cassette_provider_missing_query_is_an_explicit_error(tmp_path) -> None:
    provider = CassetteSearchProvider(tmp_path)

    with pytest.raises(CassetteNotFoundError, match="No cassette exists"):
        provider.search("query not frozen")


def test_cassette_provider_rejects_mismatched_cassette(tmp_path) -> None:
    provider = CassetteSearchProvider(tmp_path)
    _write_cassette(provider, "expected query")
    path = provider.cassette_path("expected query")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["query"] = "different query"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CassetteMalformedError, match="query does not match"):
        provider.search("expected query")


def test_search_result_requires_utc_iso_timestamp() -> None:
    with pytest.raises(ValueError, match="UTC ISO 8601"):
        SearchResult(
            url="https://example.com",
            title="Example",
            snippet="",
            content="",
            raw_score=0.1,
            provider="cassette",
            query="example",
            retrieved_at="2026-08-19T12:00:00",
        )
