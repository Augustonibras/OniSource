from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from .keys import extract_storage_key
from .models import ExtractResult
from .provider import ExtractProvider


DEFAULT_EXTRACT_CACHE_DIR = Path(".cache") / "extract"


class ExtractCacheMalformedError(ValueError):
    """Raised when an extraction cache entry cannot be replayed."""


@runtime_checkable
class RawExtractCacheCodec(Protocol):
    @property
    def last_raw_response(self) -> dict[str, Any]: ...

    @property
    def last_retrieved_at(self) -> str: ...

    def normalize_raw_response(
        self,
        raw_response: dict[str, Any],
        *,
        retrieved_at: str,
    ) -> list[ExtractResult]: ...


class CachedExtractProvider(ExtractProvider):
    def __init__(
        self,
        provider: ExtractProvider,
        *,
        provider_name: str,
        depth: str,
        request_parameters: Mapping[str, Any] | None = None,
        cache_dir: str | Path = DEFAULT_EXTRACT_CACHE_DIR,
        refresh: bool = False,
    ) -> None:
        self.provider = provider
        self.provider_name = provider_name
        self.depth = depth
        self.request_parameters = dict(request_parameters or {})
        self.cache_dir = Path(cache_dir)
        self.refresh = refresh
        self.last_cache_hit = False

    def cache_path(self, urls: list[str]) -> Path:
        key = extract_storage_key(
            self.provider_name,
            urls,
            self.depth,
            self.request_parameters,
        )
        return self.cache_dir / f"{key}.json"

    def extract(self, urls: list[str]) -> list[ExtractResult]:
        path = self.cache_path(urls)
        if path.is_file() and not self.refresh:
            self.last_cache_hit = True
            return self._read(path, urls)
        self.last_cache_hit = False
        results = self.provider.extract(urls)
        self._write(path, self._build_payload(urls, results))
        return results

    def _build_payload(
        self,
        urls: list[str],
        results: list[ExtractResult],
    ) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "provider": self.provider_name,
            "urls": urls,
            "extract_depth": self.depth,
            "request_parameters": self.request_parameters,
        }
        if isinstance(self.provider, RawExtractCacheCodec):
            envelope.update(
                {
                    "format": "raw_provider_response",
                    "retrieved_at": self.provider.last_retrieved_at,
                    "response": self.provider.last_raw_response,
                }
            )
        else:
            retrieved_at = (
                results[0].retrieved_at
                if results
                else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            envelope.update(
                {
                    "format": "normalized_extract_results",
                    "retrieved_at": retrieved_at,
                    "results": [asdict(result) for result in results],
                }
            )
        return envelope

    def _read(self, path: Path, urls: list[str]) -> list[ExtractResult]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ExtractCacheMalformedError(
                f"Could not read extraction cache: {path}"
            ) from error
        expected = {
            "provider": self.provider_name,
            "urls": urls,
            "extract_depth": self.depth,
            "request_parameters": self.request_parameters,
        }
        if not isinstance(payload, dict) or any(
            payload.get(name) != value for name, value in expected.items()
        ):
            raise ExtractCacheMalformedError(
                f"Extraction cache does not match lookup: {path}"
            )
        cache_format = payload.get("format")
        if cache_format == "raw_provider_response":
            if not isinstance(self.provider, RawExtractCacheCodec):
                raise ExtractCacheMalformedError(
                    "Underlying provider cannot decode raw extraction cache"
                )
            raw_response = payload.get("response")
            retrieved_at = payload.get("retrieved_at")
            if not isinstance(raw_response, dict) or not isinstance(retrieved_at, str):
                raise ExtractCacheMalformedError("Raw extraction cache is incomplete")
            return self.provider.normalize_raw_response(
                raw_response,
                retrieved_at=retrieved_at,
            )
        if cache_format == "normalized_extract_results":
            raw_results = payload.get("results")
            if not isinstance(raw_results, list):
                raise ExtractCacheMalformedError(
                    "Normalized extraction cache is incomplete"
                )
            try:
                return [ExtractResult(**item) for item in raw_results]
            except (TypeError, ValueError) as error:
                raise ExtractCacheMalformedError(
                    "Normalized extraction cache contains invalid results"
                ) from error
        raise ExtractCacheMalformedError(f"Unknown extraction cache format: {path}")

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        except OSError as error:
            raise ExtractCacheMalformedError(
                f"Could not write extraction cache: {path}"
            ) from error
