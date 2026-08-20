from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .domain_filter import DEFAULT_NOISE_DOMAINS_PATH, SearchDomainFilter
from .keys import search_storage_key
from .models import SearchResult
from .provider import SearchProvider
from .query_builder import QUERY_SET_VERSION


class CassetteNotFoundError(FileNotFoundError):
    """Raised when a query has no frozen cassette."""


class CassetteMalformedError(ValueError):
    """Raised when a frozen cassette does not satisfy its contract."""


class CassetteSearchProvider(SearchProvider):
    """Replay committed search responses without any network access."""

    def __init__(
        self,
        cassette_dir: str | Path = "cassettes",
        *,
        provider_name: str = "tavily",
        search_depth: str = "advanced",
        query_set_version: str = QUERY_SET_VERSION,
        noise_domains_path: str | Path = DEFAULT_NOISE_DOMAINS_PATH,
    ) -> None:
        self.cassette_dir = Path(cassette_dir)
        self.provider_name = provider_name
        self.search_depth = search_depth
        self.query_set_version = query_set_version
        self._domain_filter = SearchDomainFilter(noise_domains_path)

    def cassette_path(self, query: str, max_results: int = 10) -> Path:
        key = search_storage_key(
            self.provider_name,
            query,
            self.search_depth,
            max_results,
        )
        return self.cassette_dir / f"{key}.json"

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        path = self.cassette_path(query, max_results)
        if not path.is_file():
            raise CassetteNotFoundError(
                f"No cassette exists for query {query!r} and max_results={max_results}"
            )

        try:
            with path.open("r", encoding="utf-8") as cassette_file:
                cassette = json.load(cassette_file)
        except (OSError, json.JSONDecodeError) as error:
            raise CassetteMalformedError(f"Could not read cassette: {path}") from error

        self._validate_envelope(cassette, query, max_results, path)
        raw_response = cassette["response"]
        raw_results = raw_response.get("results")
        if not isinstance(raw_results, list):
            raise CassetteMalformedError(
                f"Cassette response.results must be a list: {path}"
            )

        filtered_results = self._domain_filter.filter_raw_results(raw_results)
        return [
            self._normalize_result(item, query, cassette["retrieved_at"], path)
            for item in filtered_results[:max_results]
        ]

    def _validate_envelope(
        self,
        cassette: Any,
        query: str,
        max_results: int,
        path: Path,
    ) -> None:
        if not isinstance(cassette, dict):
            raise CassetteMalformedError(f"Cassette must contain an object: {path}")

        expected = {
            "provider": self.provider_name,
            "query": query,
            "search_depth": self.search_depth,
            "max_results": max_results,
            "query_set_version": self.query_set_version,
        }
        for field_name, expected_value in expected.items():
            if cassette.get(field_name) != expected_value:
                raise CassetteMalformedError(
                    f"Cassette {field_name} does not match its lookup: {path}"
                )
        if not isinstance(cassette.get("retrieved_at"), str):
            raise CassetteMalformedError(f"Cassette retrieved_at is required: {path}")
        if not isinstance(cassette.get("captured_at"), str):
            raise CassetteMalformedError(f"Cassette captured_at is required: {path}")
        if not isinstance(cassette.get("response"), dict):
            raise CassetteMalformedError(f"Cassette response must be an object: {path}")

    def _normalize_result(
        self,
        item: Any,
        query: str,
        retrieved_at: str,
        path: Path,
    ) -> SearchResult:
        if not isinstance(item, dict):
            raise CassetteMalformedError(f"Cassette result must be an object: {path}")
        try:
            url = item["url"]
            title = item["title"]
            raw_score = float(item["score"])
        except (KeyError, TypeError, ValueError) as error:
            raise CassetteMalformedError(
                f"Cassette result is missing a required field: {path}"
            ) from error
        if not isinstance(url, str) or not isinstance(title, str):
            raise CassetteMalformedError(f"Cassette result fields are invalid: {path}")

        snippet = item.get("content", "")
        content = item.get("raw_content", "")
        if snippet is None:
            snippet = ""
        if content is None:
            content = ""
        if not isinstance(snippet, str) or not isinstance(content, str):
            raise CassetteMalformedError(f"Cassette result text is invalid: {path}")

        return SearchResult(
            url=url,
            title=title,
            snippet=snippet,
            content=content,
            raw_score=raw_score,
            provider=self.provider_name,
            query=query,
            retrieved_at=retrieved_at,
        )
