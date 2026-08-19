from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .keys import search_storage_key
from .models import SearchResult
from .provider import SearchProvider


DEFAULT_SEARCH_CACHE_DIR = Path(".cache") / "search"


class CacheMalformedError(ValueError):
    """Raised when a cache entry cannot be replayed safely."""


@runtime_checkable
class RawResponseCacheCodec(Protocol):
    @property
    def last_raw_response(self) -> dict[str, Any]: ...

    @property
    def last_retrieved_at(self) -> str: ...

    def normalize_raw_response(
        self,
        raw_response: dict[str, Any],
        *,
        query: str,
        retrieved_at: str,
        max_results: int,
    ) -> list[SearchResult]: ...


class CachedSearchProvider(SearchProvider):
    def __init__(
        self,
        provider: SearchProvider,
        *,
        provider_name: str,
        depth: str,
        cache_dir: str | Path = DEFAULT_SEARCH_CACHE_DIR,
    ) -> None:
        self.provider = provider
        self.provider_name = provider_name
        self.depth = depth
        self.cache_dir = Path(cache_dir)

    def cache_path(self, query: str, max_results: int = 10) -> Path:
        key = search_storage_key(
            self.provider_name,
            query,
            self.depth,
            max_results,
        )
        return self.cache_dir / f"{key}.json"

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        path = self.cache_path(query, max_results)
        if path.is_file():
            return self._read(path, query, max_results)

        results = self.provider.search(query, max_results)
        payload = self._build_payload(query, max_results, results)
        self._write(path, payload)
        return results

    def _build_payload(
        self,
        query: str,
        max_results: int,
        results: list[SearchResult],
    ) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "provider": self.provider_name,
            "query": query,
            "search_depth": self.depth,
            "max_results": max_results,
        }
        if isinstance(self.provider, RawResponseCacheCodec):
            envelope.update(
                {
                    "format": "raw_provider_response",
                    "retrieved_at": self.provider.last_retrieved_at,
                    "response": self.provider.last_raw_response,
                }
            )
        else:
            envelope.update(
                {
                    "format": "normalized_search_results",
                    "results": [asdict(result) for result in results],
                }
            )
        return envelope

    def _read(
        self,
        path: Path,
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CacheMalformedError(f"Could not read search cache: {path}") from error
        if not isinstance(payload, dict):
            raise CacheMalformedError(f"Search cache must contain an object: {path}")

        expected = {
            "provider": self.provider_name,
            "query": query,
            "search_depth": self.depth,
            "max_results": max_results,
        }
        for field_name, expected_value in expected.items():
            if payload.get(field_name) != expected_value:
                raise CacheMalformedError(
                    f"Search cache {field_name} does not match lookup: {path}"
                )

        cache_format = payload.get("format")
        if cache_format == "raw_provider_response":
            if not isinstance(self.provider, RawResponseCacheCodec):
                raise CacheMalformedError(
                    "Underlying provider cannot decode its raw cached response"
                )
            raw_response = payload.get("response")
            retrieved_at = payload.get("retrieved_at")
            if not isinstance(raw_response, dict) or not isinstance(retrieved_at, str):
                raise CacheMalformedError(f"Raw search cache is incomplete: {path}")
            return self.provider.normalize_raw_response(
                raw_response,
                query=query,
                retrieved_at=retrieved_at,
                max_results=max_results,
            )

        if cache_format == "normalized_search_results":
            raw_results = payload.get("results")
            if not isinstance(raw_results, list):
                raise CacheMalformedError(
                    f"Normalized search cache is incomplete: {path}"
                )
            try:
                return [SearchResult(**item) for item in raw_results]
            except (TypeError, ValueError) as error:
                raise CacheMalformedError(
                    f"Normalized search cache has invalid results: {path}"
                ) from error

        raise CacheMalformedError(f"Unknown search cache format: {path}")

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, path)
        except OSError as error:
            raise CacheMalformedError(f"Could not write search cache: {path}") from error
