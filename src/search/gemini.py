from __future__ import annotations

import os
import time
from collections.abc import Mapping
from typing import Callable

import requests

from .company_classifier import LLMProvider, LLMTokenUsage


# Gemini 2.5 is still listed but retired for new projects; Pro requires billing.
GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_API_VERSION = "v1beta"
GEMINI_MAX_OUTPUT_TOKENS = 512
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/{GEMINI_API_VERSION}/models/"
    f"{GEMINI_MODEL}:generateContent"
)
MAX_LLM_CALLS = 80
MAX_GEMINI_ATTEMPTS = 3


class GeminiProviderError(RuntimeError):
    """Base error for the approved Gemini REST provider."""


class GeminiAPIKeyMissingError(GeminiProviderError):
    """Raised before a request when GEMINI_API_KEY is unavailable."""


class GeminiHTTPError(GeminiProviderError):
    """Raised for HTTP failures with a sanitized response body."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_body: str,
        api_key: str,
    ) -> None:
        sanitized_message = message.replace(api_key, "***")
        sanitized_body = response_body.replace(api_key, "***")
        self.status_code = status_code
        self.response_body = sanitized_body
        super().__init__(f"{sanitized_message}\nResponse body: {sanitized_body}")


class GeminiAuthError(GeminiHTTPError):
    """Raised immediately for Gemini authentication failures."""


class GeminiTransientError(GeminiHTTPError):
    """Raised after all transient-response attempts are exhausted."""


class GeminiTimeoutError(GeminiProviderError):
    """Raised when the explicit Gemini request timeout expires."""


class GeminiTransportError(GeminiProviderError):
    """Raised for non-timeout transport failures."""


class GeminiMalformedResponseError(GeminiProviderError, ValueError):
    """Raised when a Gemini response cannot satisfy the provider contract."""


class LLMCallLimitError(GeminiProviderError):
    """Raised before a request that would exceed the session call cap."""


class LLMCallGuard:
    def __init__(self, max_calls: int = MAX_LLM_CALLS) -> None:
        if isinstance(max_calls, bool) or not isinstance(max_calls, int):
            raise ValueError("max_calls must be a positive integer")
        if max_calls <= 0 or max_calls > MAX_LLM_CALLS:
            raise ValueError(f"max_calls must be between 1 and {MAX_LLM_CALLS}")
        self.max_calls = max_calls
        self.calls_used = 0

    def consume(self) -> None:
        if self.calls_used >= self.max_calls:
            raise LLMCallLimitError(
                f"LLM call limit of {self.max_calls} would be exceeded"
            )
        self.calls_used += 1


class GeminiLLMProvider(LLMProvider):
    provider_name = "google_gemini"
    model = GEMINI_MODEL

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        session: requests.Session | None = None,
        call_guard: LLMCallGuard | None = None,
        timeout_seconds: float = 120.0,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        environment = os.environ if env is None else env
        api_key = environment.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise GeminiAPIKeyMissingError("GEMINI_API_KEY was not found")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative")
        self._api_key = api_key
        self._session = session or requests.Session()
        self._call_guard = call_guard or LLMCallGuard()
        self._timeout_seconds = timeout_seconds
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._retries = 0
        self._error_counts: dict[str, int] = {}
        self._input_tokens = 0
        self._output_tokens = 0
        self._thoughts_tokens = 0
        self._total_tokens = 0

    @property
    def execution_metrics(self) -> dict[str, object]:
        return {
            "model": self.model,
            "http_calls": self._call_guard.calls_used,
            "call_limit": self._call_guard.max_calls,
            "retries": self._retries,
            "errors_by_type": dict(self._error_counts),
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "thoughts_tokens": self._thoughts_tokens,
            "total_tokens": self._total_tokens,
        }

    def complete(self, prompt: str) -> object:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
            },
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }
        for attempt in range(1, MAX_GEMINI_ATTEMPTS + 1):
            self._call_guard.consume()
            try:
                response = self._session.post(
                    GEMINI_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            except requests.Timeout as error:
                self._record_error(GeminiTimeoutError)
                raise GeminiTimeoutError("Gemini request timed out") from error
            except requests.RequestException as error:
                self._record_error(GeminiTransportError)
                raise GeminiTransportError("Gemini request transport failed") from error

            if response.status_code in {401, 403}:
                self._record_error(GeminiAuthError)
                raise GeminiAuthError(
                    f"Gemini authentication failed with HTTP {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text,
                    api_key=self._api_key,
                )
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                self._record_error(GeminiTransientError)
                if attempt == MAX_GEMINI_ATTEMPTS:
                    raise GeminiTransientError(
                        "Gemini transient failure persisted after "
                        f"{MAX_GEMINI_ATTEMPTS} attempts with HTTP "
                        f"{response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                        api_key=self._api_key,
                    )
                self._retries += 1
                self._sleep(self._backoff_seconds * (2 ** (attempt - 1)))
                continue
            if not 200 <= response.status_code < 300:
                self._record_error(GeminiHTTPError)
                raise GeminiHTTPError(
                    f"Gemini returned unexpected HTTP status {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text,
                    api_key=self._api_key,
                )
            try:
                raw_response = response.json()
            except ValueError as error:
                self._record_error(GeminiMalformedResponseError)
                raise GeminiMalformedResponseError(
                    "Gemini response is not valid JSON"
                ) from error
            if not isinstance(raw_response, dict):
                self._record_error(GeminiMalformedResponseError)
                raise GeminiMalformedResponseError(
                    "Gemini response must be a JSON object"
                )
            return raw_response

        raise AssertionError("Gemini attempt loop exited unexpectedly")

    def parse_response(self, raw_response: object) -> tuple[object, LLMTokenUsage]:
        if not isinstance(raw_response, Mapping):
            raise GeminiMalformedResponseError(
                "Gemini raw response must be an object"
            )
        candidates = raw_response.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise GeminiMalformedResponseError("Gemini candidates are missing")
        first_candidate = candidates[0]
        if not isinstance(first_candidate, Mapping):
            raise GeminiMalformedResponseError("Gemini candidate is invalid")
        finish_reason = first_candidate.get("finishReason", "")
        if not isinstance(finish_reason, str):
            raise GeminiMalformedResponseError("Gemini finishReason is invalid")
        usage_metadata = raw_response.get("usageMetadata")
        if not isinstance(usage_metadata, Mapping):
            raise GeminiMalformedResponseError("Gemini usageMetadata is missing")
        content = first_candidate.get("content")
        parts = content.get("parts") if isinstance(content, Mapping) else None
        empty_response = finish_reason == "MAX_TOKENS" or not parts
        text_parts: list[str] = []
        if not empty_response:
            if not isinstance(parts, list):
                raise GeminiMalformedResponseError("Gemini candidate parts are invalid")
            for part in parts:
                if not isinstance(part, Mapping) or not isinstance(
                    part.get("text"), str
                ):
                    raise GeminiMalformedResponseError("Gemini text part is invalid")
                text_parts.append(part["text"])
            empty_response = not "".join(text_parts).strip()

        usage = LLMTokenUsage(
            input_tokens=self._usage_value(usage_metadata, "promptTokenCount"),
            output_tokens=self._usage_value(
                usage_metadata,
                "candidatesTokenCount",
                required=False,
            ),
            total_tokens=self._usage_value(usage_metadata, "totalTokenCount"),
            thoughts_tokens=self._usage_value(
                usage_metadata,
                "thoughtsTokenCount",
                required=False,
            ),
            finish_reason=finish_reason,
            empty_response=empty_response,
        )
        self._input_tokens += usage.input_tokens
        self._output_tokens += usage.output_tokens
        self._thoughts_tokens += usage.thoughts_tokens
        self._total_tokens += usage.total_tokens
        return "".join(text_parts), usage

    @staticmethod
    def _usage_value(
        usage_metadata: Mapping[object, object],
        field: str,
        *,
        required: bool = True,
    ) -> int:
        value = usage_metadata.get(field)
        if value is None and not required:
            return 0
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise GeminiMalformedResponseError(
                f"Gemini usageMetadata.{field} is invalid"
            )
        return value

    def _record_error(self, error_type: type[GeminiProviderError]) -> None:
        name = error_type.__name__
        self._error_counts[name] = self._error_counts.get(name, 0) + 1
