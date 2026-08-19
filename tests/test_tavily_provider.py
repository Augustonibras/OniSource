from __future__ import annotations

import json
from typing import Any

import pytest
import requests

from src.search.audit import RunRecorder
from src.search.budget import SearchBudget
from src.search.cache import CachedSearchProvider
from src.search.domain_filter import load_noise_domains
from src.search.errors import (
    AuthError,
    CreditsExhaustedError,
    MalformedResponseError,
    RateLimitError,
    SearchTimeoutError,
)
from src.search.tavily import TAVILY_SEARCH_URL, TavilySearchProvider


class FakeResponse:
    def __init__(self, status_code: int, payload: Any = None, *, invalid_json: bool = False):
        self.status_code = status_code
        self.payload = payload
        self.invalid_json = invalid_json

    def json(self):
        if self.invalid_json:
            raise ValueError("invalid json")
        return self.payload


class FakeSession:
    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("TAVILY_API_KEY=test-secret\n", encoding="utf-8")
    return path


def _provider(tmp_path, session, **kwargs):
    budget = SearchBudget(tmp_path / "credit_usage.json")
    provider = TavilySearchProvider(
        env_path=_env_file(tmp_path),
        session=session,
        budget=budget,
        run_recorder=RunRecorder(tmp_path / "runs"),
        now=lambda: "2026-08-19T12:00:00Z",
        **kwargs,
    )
    return provider, budget


def _valid_response():
    return {
        "query": "phosphoric acid manufacturer",
        "results": [
            {
                "url": "https://example.com/product",
                "title": "Product",
                "content": "result snippet",
                "raw_content": "advanced extracted text",
                "score": 0.95,
            }
        ],
    }


def test_tavily_uses_direct_advanced_http_and_records_audit(tmp_path) -> None:
    session = FakeSession(FakeResponse(200, _valid_response()))
    provider, budget = _provider(tmp_path, session)

    results = provider.search("phosphoric acid manufacturer")

    assert results[0].snippet == "result snippet"
    assert results[0].content == "advanced extracted text"
    assert results[0].provider == "tavily"
    assert budget.execution_credits == 2
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == TAVILY_SEARCH_URL
    assert call["json"] == {
        "query": "phosphoric acid manufacturer",
        "search_depth": "advanced",
        "max_results": 10,
        "include_raw_content": True,
        "exclude_domains": list(load_noise_domains()),
    }
    assert call["headers"]["Authorization"] == "Bearer test-secret"
    response_files = list((tmp_path / "runs").glob("*/response.json"))
    assert len(response_files) == 1
    assert json.loads(response_files[0].read_text(encoding="utf-8"))["response"] == _valid_response()
    credit_log = json.loads(
        (response_files[0].parent / "credits.json").read_text(encoding="utf-8")
    )
    assert credit_log["charged_credits"] == 2
    assert credit_log["retries"] == 0
    assert credit_log["error_counts"] == {}


def test_missing_api_key_fails_during_provider_construction(tmp_path) -> None:
    with pytest.raises(AuthError, match="TAVILY_API_KEY is missing"):
        TavilySearchProvider(env_path=tmp_path / "missing.env")


def test_http_401_raises_auth_error_without_retry(tmp_path) -> None:
    session = FakeSession(FakeResponse(401, {"detail": "unauthorized"}))
    provider, _ = _provider(tmp_path, session)

    with pytest.raises(AuthError, match="HTTP 401"):
        provider.search("test query")

    assert len(session.calls) == 1


def test_http_429_uses_exponential_backoff_for_at_most_two_attempts(tmp_path) -> None:
    session = FakeSession(
        FakeResponse(429, {"detail": "rate limited"}),
        FakeResponse(429, {"detail": "rate limited"}),
    )
    sleeps: list[float] = []
    provider, _ = _provider(tmp_path, session, sleep=sleeps.append)

    with pytest.raises(RateLimitError, match="after 2 attempts"):
        provider.search("test query")

    assert len(session.calls) == 2
    assert sleeps == [1.0]
    credit_log = json.loads(
        next((tmp_path / "runs").glob("*/credits.json")).read_text(encoding="utf-8")
    )
    assert credit_log["charged_credits"] == 2
    assert credit_log["retries"] == 1
    assert credit_log["error_counts"] == {"RateLimitError": 2}


@pytest.mark.parametrize("status_code", [402, 432])
def test_credits_exhausted_stops_immediately_without_retry(
    tmp_path, status_code: int
) -> None:
    session = FakeSession(FakeResponse(status_code, {"detail": "no credits"}))
    provider, _ = _provider(tmp_path, session)

    with pytest.raises(CreditsExhaustedError, match="credits are exhausted"):
        provider.search("test query")

    assert len(session.calls) == 1
    credit_log = json.loads(
        next((tmp_path / "runs").glob("*/credits.json")).read_text(encoding="utf-8")
    )
    assert credit_log["retries"] == 0
    assert credit_log["error_counts"] == {"CreditsExhaustedError": 1}


def test_timeout_raises_search_timeout_error(tmp_path) -> None:
    session = FakeSession(requests.Timeout("timeout"))
    provider, _ = _provider(tmp_path, session)

    with pytest.raises(SearchTimeoutError, match="timed out"):
        provider.search("test query")

    assert len(session.calls) == 1
    credit_log = json.loads(
        next((tmp_path / "runs").glob("*/credits.json")).read_text(encoding="utf-8")
    )
    assert credit_log["retries"] == 0
    assert credit_log["error_counts"] == {"SearchTimeoutError": 1}


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(200, invalid_json=True),
        FakeResponse(200, {"unexpected": []}),
    ],
)
def test_malformed_response_raises_explicit_error(tmp_path, response) -> None:
    session = FakeSession(response)
    provider, _ = _provider(tmp_path, session)

    with pytest.raises(MalformedResponseError):
        provider.search("test query")


def test_tavily_raw_json_cache_hit_avoids_network_and_credit_charge(tmp_path) -> None:
    session = FakeSession(FakeResponse(200, _valid_response()))
    live_provider, budget = _provider(tmp_path, session)
    provider = CachedSearchProvider(
        live_provider,
        provider_name="tavily",
        depth="advanced",
        cache_dir=tmp_path / "cache",
    )

    first = provider.search("phosphoric acid manufacturer")
    second = provider.search("phosphoric acid manufacturer")
    cache_payload = json.loads(
        provider.cache_path("phosphoric acid manufacturer").read_text(encoding="utf-8")
    )

    assert second == first
    assert len(session.calls) == 1
    assert budget.execution_credits == 2
    assert cache_payload["format"] == "raw_provider_response"
    assert cache_payload["response"] == _valid_response()
