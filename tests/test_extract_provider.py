from __future__ import annotations

import json

import pytest
import requests

from src.extract.audit import freeze_extract_cache_as_cassette
from src.extract.budget import ExtractBudget
from src.extract.cache import CachedExtractProvider
from src.extract.cassette import CassetteExtractProvider, ExtractCassetteNotFoundError
from src.extract.models import ExtractResult
from src.extract.provider import ExtractProvider
from src.extract.tavily import TavilyExtractProvider
from src.search.company_evaluation import build_company_classification_report
from src.search.errors import AuthError, RateLimitError
from src.search.models import SearchResult


class FakeExtractProvider(ExtractProvider):
    provider_name = "fake_extract"
    extract_depth = "basic"
    request_parameters = {"format": "markdown"}

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, urls: list[str]) -> list[ExtractResult]:
        self.calls += 1
        return [
            ExtractResult(
                url=url,
                raw_content=f"content for {url}",
                provider=self.provider_name,
                retrieved_at="2026-08-20T12:00:00Z",
            )
            for url in urls
        ]


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def post(self, url, *, json, headers, timeout):
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        return self.responses.pop(0)


def _env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("TAVILY_API_KEY=test-key\n", encoding="utf-8")
    return path


def test_extract_cache_hit_does_not_call_provider_again(tmp_path) -> None:
    raw = FakeExtractProvider()
    provider = CachedExtractProvider(
        raw,
        provider_name=raw.provider_name,
        depth=raw.extract_depth,
        request_parameters=raw.request_parameters,
        cache_dir=tmp_path / "cache",
    )
    urls = ["https://one.example", "https://two.example"]

    first = provider.extract(urls)
    second = provider.extract(urls)

    assert first == second
    assert raw.calls == 1
    assert provider.last_cache_hit is True


def test_extract_cache_key_includes_request_parameters(tmp_path) -> None:
    raw = FakeExtractProvider()
    first = CachedExtractProvider(
        raw,
        provider_name=raw.provider_name,
        depth="basic",
        request_parameters={"format": "markdown"},
        cache_dir=tmp_path,
    )
    second = CachedExtractProvider(
        raw,
        provider_name=raw.provider_name,
        depth="basic",
        request_parameters={"format": "text"},
        cache_dir=tmp_path,
    )

    assert first.cache_path(["https://example.com"]) != second.cache_path(
        ["https://example.com"]
    )


def test_extract_cassette_is_separate_and_replayable(tmp_path) -> None:
    raw = FakeExtractProvider()
    cached = CachedExtractProvider(
        raw,
        provider_name=raw.provider_name,
        depth=raw.extract_depth,
        request_parameters=raw.request_parameters,
        cache_dir=tmp_path / "cache",
    )
    urls = ["https://example.com/product"]
    cached.extract(urls)
    cassette_path = freeze_extract_cache_as_cassette(
        cached.cache_path(urls),
        cassette_dir=tmp_path / "cassettes" / "extract",
    )
    cassette = CassetteExtractProvider(
        tmp_path / "cassettes" / "extract",
        provider_name=raw.provider_name,
        extract_depth=raw.extract_depth,
        request_parameters=raw.request_parameters,
    )

    replayed = cassette.extract(urls)

    assert cassette_path.is_file()
    assert replayed[0].raw_content == "content for https://example.com/product"
    assert json.loads(cassette_path.read_text(encoding="utf-8"))[
        "extract_set_version"
    ] == "phase0-extract-v1"


def test_missing_extract_cassette_is_explicit(tmp_path) -> None:
    provider = CassetteExtractProvider(tmp_path)

    with pytest.raises(ExtractCassetteNotFoundError, match="No extraction cassette"):
        provider.extract(["https://missing.example"])


def test_tavily_extract_posts_basic_batch_and_counts_success_credits(tmp_path) -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "results": [
                        {"url": f"https://{index}.example", "raw_content": "text"}
                        for index in range(6)
                    ],
                    "failed_results": [],
                    "usage": {"credits": 2},
                },
            )
        ]
    )
    budget = ExtractBudget(tmp_path / "credits.json")
    provider = TavilyExtractProvider(
        env_path=_env_file(tmp_path),
        session=session,
        budget=budget,
        runs_dir=tmp_path / "runs" / "extract",
        now=lambda: "2026-08-20T12:00:00Z",
    )
    urls = [f"https://{index}.example" for index in range(6)]

    results = provider.extract(urls)

    assert len(results) == 6
    assert budget.execution_credits == 2
    assert session.calls[0]["json"] == {
        "urls": urls,
        "extract_depth": "basic",
        "include_images": False,
        "format": "markdown",
        "include_usage": True,
    }
    assert "test-key" not in str(provider.last_raw_response)


def test_tavily_extract_maps_auth_and_rate_limit_errors(tmp_path) -> None:
    auth = TavilyExtractProvider(
        env_path=_env_file(tmp_path),
        session=FakeSession([FakeResponse(401, {})]),
        budget=ExtractBudget(tmp_path / "auth-credits.json"),
        runs_dir=tmp_path / "auth-runs",
    )
    with pytest.raises(AuthError):
        auth.extract(["https://example.com"])

    rate_limited = TavilyExtractProvider(
        env_path=_env_file(tmp_path),
        session=FakeSession([FakeResponse(429, {}), FakeResponse(429, {})]),
        budget=ExtractBudget(tmp_path / "rate-credits.json"),
        runs_dir=tmp_path / "rate-runs",
        sleep=lambda _: None,
    )
    with pytest.raises(RateLimitError):
        rate_limited.extract(["https://example.com"])


def test_extracted_content_is_additional_company_evidence() -> None:
    search_result = SearchResult(
        url="https://candidate.example/product",
        title="Candidate product",
        snippet="Product information only.",
        content="",
        raw_score=1.0,
        provider="cassette",
        query="product manufacturer",
        retrieved_at="2026-08-20T12:00:00Z",
    )

    report = build_company_classification_report(
        "unconfigured_category",
        [search_result],
        extracted_content_by_url={
            search_result.url: (
                "Candidate is a manufacturer of industrial chemicals and uses "
                "the chloride process for production."
            )
        },
    )

    classification = report["results"][0]["domain_classification"]
    assert classification["role"] == "MANUFACTURER"
    assert classification["evidence"][0]["source_type"] == "EXTRACTED_CONTENT"
