from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .keys import extract_storage_key
from .models import ExtractResult
from .provider import ExtractProvider


EXTRACT_SET_VERSION = "phase0-extract-v1"
DEFAULT_EXTRACT_CASSETTE_DIR = Path("cassettes") / "extract"
DEFAULT_EXTRACT_REQUEST_PARAMETERS = {
    "include_images": False,
    "format": "markdown",
    "include_usage": True,
}


class ExtractCassetteNotFoundError(FileNotFoundError):
    """Raised when an extraction batch has no frozen cassette."""


class ExtractCassetteMalformedError(ValueError):
    """Raised when an extraction cassette violates its envelope."""


class CassetteExtractProvider(ExtractProvider):
    def __init__(
        self,
        cassette_dir: str | Path = DEFAULT_EXTRACT_CASSETTE_DIR,
        *,
        provider_name: str = "tavily_extract",
        extract_depth: str = "basic",
        request_parameters: Mapping[str, Any] | None = None,
        extract_set_version: str = EXTRACT_SET_VERSION,
    ) -> None:
        self.cassette_dir = Path(cassette_dir)
        self.provider_name = provider_name
        self.extract_depth = extract_depth
        self.request_parameters = dict(
            DEFAULT_EXTRACT_REQUEST_PARAMETERS
            if request_parameters is None
            else request_parameters
        )
        self.extract_set_version = extract_set_version

    def cassette_path(self, urls: list[str]) -> Path:
        key = extract_storage_key(
            self.provider_name,
            urls,
            self.extract_depth,
            self.request_parameters,
        )
        return self.cassette_dir / f"{key}.json"

    def extract(self, urls: list[str]) -> list[ExtractResult]:
        path = self.cassette_path(urls)
        if not path.is_file():
            raise ExtractCassetteNotFoundError(
                f"No extraction cassette exists for {len(urls)} URLs"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ExtractCassetteMalformedError(
                f"Could not read extraction cassette: {path}"
            ) from error
        expected = {
            "provider": self.provider_name,
            "urls": urls,
            "extract_depth": self.extract_depth,
            "request_parameters": self.request_parameters,
            "extract_set_version": self.extract_set_version,
        }
        if not isinstance(payload, dict) or any(
            payload.get(name) != value for name, value in expected.items()
        ):
            raise ExtractCassetteMalformedError(
                f"Extraction cassette does not match lookup: {path}"
            )
        raw_response = payload.get("response")
        retrieved_at = payload.get("retrieved_at")
        if not isinstance(raw_response, dict) or not isinstance(retrieved_at, str):
            raise ExtractCassetteMalformedError(
                f"Extraction cassette response is incomplete: {path}"
            )
        return self.normalize_raw_response(raw_response, retrieved_at=retrieved_at)

    def normalize_raw_response(
        self,
        raw_response: dict[str, Any],
        *,
        retrieved_at: str,
    ) -> list[ExtractResult]:
        raw_results = raw_response.get("results")
        if not isinstance(raw_results, list):
            raise ExtractCassetteMalformedError(
                "Extraction cassette response.results must be a list"
            )
        normalized: list[ExtractResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                raise ExtractCassetteMalformedError(
                    "Extraction cassette result must be an object"
                )
            url = item.get("url")
            raw_content = item.get("raw_content")
            if not isinstance(url, str) or not isinstance(raw_content, str):
                raise ExtractCassetteMalformedError(
                    "Extraction cassette result fields are invalid"
                )
            normalized.append(
                ExtractResult(
                    url=url,
                    raw_content=raw_content,
                    provider=self.provider_name,
                    retrieved_at=retrieved_at,
                )
            )
        return normalized
