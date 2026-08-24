from __future__ import annotations

import json

import pytest

from src.search.company_classifier import (
    LLMCompanyClassifier,
    LLMProvider,
    LLMTokenUsage,
    SupplierRole,
    llm_cache_key,
    read_llm_cache,
)
from src.search.gemini import (
    GEMINI_API_URL,
    MAX_LLM_CALLS,
    GeminiAPIKeyMissingError,
    GeminiAuthError,
    GeminiLLMProvider,
    LLMCallGuard,
    LLMCallLimitError,
)


PRODUCT_CONTEXT = "titanium dioxide, rutile grade, CAS 13463-67-7"


def _gemini_response(model_text: str) -> dict[str, object]:
    return {
        "candidates": [
            {"content": {"parts": [{"text": model_text}], "role": "model"}}
        ],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 25,
            "totalTokenCount": 125,
        },
    }


class _FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self.payload = payload

    def json(self) -> object:
        return self.payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs) -> _FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def test_gemini_provider_retries_transient_errors_and_reports_real_tokens() -> None:
    model_text = json.dumps(
        {
            "role": "MANUFACTURER",
            "confidence": "HIGH",
            "citation": "own production plant",
            "reasoning": "Direct production evidence.",
        }
    )
    session = _FakeSession(
        [
            _FakeResponse(429, {}),
            _FakeResponse(503, {}),
            _FakeResponse(200, _gemini_response(model_text)),
        ]
    )
    sleeps: list[float] = []
    provider = GeminiLLMProvider(
        env={"GEMINI_API_KEY": "test-secret"},
        session=session,
        timeout_seconds=33,
        backoff_seconds=1,
        sleep=sleeps.append,
    )

    raw_response = provider.complete("classify this page")
    response_text, usage = provider.parse_response(raw_response)

    assert response_text == model_text
    assert usage == LLMTokenUsage(100, 25, 125)
    assert sleeps == [1, 2]
    assert len(session.calls) == 3
    assert session.calls[0]["url"] == GEMINI_API_URL
    assert session.calls[0]["timeout"] == 33
    assert session.calls[0]["json"] == {
        "contents": [{"parts": [{"text": "classify this page"}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    assert session.calls[0]["headers"] == {
        "Content-Type": "application/json",
        "x-goog-api-key": "test-secret",
    }
    assert provider.execution_metrics == {
        "model": "gemini-2.5-pro",
        "http_calls": 3,
        "call_limit": MAX_LLM_CALLS,
        "retries": 2,
        "errors_by_type": {"GeminiTransientError": 2},
        "input_tokens": 100,
        "output_tokens": 25,
        "total_tokens": 125,
    }


def test_gemini_provider_aborts_authentication_failure_without_retry() -> None:
    session = _FakeSession([_FakeResponse(403, {})])
    provider = GeminiLLMProvider(
        env={"GEMINI_API_KEY": "test-secret"},
        session=session,
        sleep=lambda _: pytest.fail("authentication failures must not retry"),
    )

    with pytest.raises(GeminiAuthError, match="HTTP 403"):
        provider.complete("prompt")

    assert len(session.calls) == 1
    assert provider.execution_metrics["retries"] == 0


def test_gemini_provider_aborts_before_request_when_call_cap_is_exhausted() -> None:
    session = _FakeSession(
        [
            _FakeResponse(200, _gemini_response("{}")),
            _FakeResponse(200, _gemini_response("{}")),
        ]
    )
    provider = GeminiLLMProvider(
        env={"GEMINI_API_KEY": "test-secret"},
        session=session,
        call_guard=LLMCallGuard(max_calls=1),
    )

    provider.complete("first")
    with pytest.raises(LLMCallLimitError, match="limit of 1"):
        provider.complete("second")

    assert len(session.calls) == 1


def test_gemini_provider_aborts_cleanly_when_environment_key_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(GeminiAPIKeyMissingError, match="was not found"):
        GeminiLLMProvider()


class _CacheOrderProvider(LLMProvider):
    provider_name = "cache_order_fake"

    def __init__(self, cache_dir, key: str) -> None:
        self.cache_dir = cache_dir
        self.key = key
        self.parse_called = False

    def complete(self, prompt: str) -> object:
        return {"raw": "provider envelope"}

    def parse_response(self, raw_response: object) -> tuple[object, LLMTokenUsage]:
        cached = read_llm_cache(self.cache_dir, self.key)
        assert isinstance(cached, dict)
        assert cached["raw_response"] == raw_response
        assert "model_response" not in cached
        self.parse_called = True
        return (
            json.dumps(
                {
                    "role": "MANUFACTURER",
                    "confidence": "HIGH",
                    "citation": "own production plant",
                    "reasoning": "Direct production evidence.",
                }
            ),
            LLMTokenUsage(50, 20, 70),
        )


def test_live_classifier_caches_raw_response_before_parse_and_replays_offline(
    tmp_path,
) -> None:
    domain = "example.com"
    title = "Example producer"
    content = "We operate our own production plant in Example City."
    key = llm_cache_key(domain, title, content, PRODUCT_CONTEXT)
    provider = _CacheOrderProvider(tmp_path, key)
    live_classifier = LLMCompanyClassifier(provider, tmp_path, on_miss="live")

    live_result = live_classifier.classify(
        domain,
        title,
        content,
        PRODUCT_CONTEXT,
    )
    cached = read_llm_cache(tmp_path, key)
    offline_classifier = LLMCompanyClassifier(None, tmp_path, on_miss="raise")
    offline_result = offline_classifier.classify(
        domain,
        title,
        content,
        PRODUCT_CONTEXT,
    )

    assert provider.parse_called is True
    assert live_result.role is SupplierRole.MANUFACTURER
    assert offline_result == live_result
    assert isinstance(cached, dict)
    assert cached["raw_response"] == {"raw": "provider envelope"}
    assert cached["usage_metadata"] == {
        "input_tokens": 50,
        "output_tokens": 20,
        "total_tokens": 70,
    }
