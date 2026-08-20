from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import requests

from src.search.errors import (
    AuthError,
    CreditsExhaustedError,
    MalformedResponseError,
    RateLimitError,
    SearchProviderError,
    SearchTimeoutError,
    SearchTransportError,
    UnexpectedHTTPStatusError,
)
from src.search.tavily import load_tavily_api_key, utc_now_iso

from .audit import ExtractRunRecorder
from .budget import ExtractBudget, MAX_EXTRACT_URLS_PER_REQUEST
from .cassette import DEFAULT_EXTRACT_REQUEST_PARAMETERS
from .models import ExtractResult
from .provider import ExtractProvider


TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
TAVILY_EXTRACT_PROVIDER_NAME = "tavily_extract"
TAVILY_EXTRACT_DEPTH = "basic"
MAX_RATE_LIMIT_ATTEMPTS = 2


class TavilyExtractProvider(ExtractProvider):
    provider_name = TAVILY_EXTRACT_PROVIDER_NAME
    extract_depth = TAVILY_EXTRACT_DEPTH

    def __init__(
        self,
        *,
        env_path: str | Path = ".env",
        session: requests.Session | None = None,
        budget: ExtractBudget | None = None,
        runs_dir: str | Path = Path("runs") / "extract",
        timeout_seconds: float = 60.0,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], str] = utc_now_iso,
    ) -> None:
        self._api_key = load_tavily_api_key(env_path)
        self._session = session or requests.Session()
        self._budget = budget or ExtractBudget()
        self._run_recorder = ExtractRunRecorder(runs_dir)
        self._timeout_seconds = timeout_seconds
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._now = now
        self._last_raw_response: dict[str, Any] | None = None
        self._last_retrieved_at: str | None = None
        self._last_failed_urls: tuple[str, ...] = ()
        self.last_charged_credits = 0
        self.last_retries = 0
        self.last_error_counts: dict[str, int] = {}

    @property
    def request_parameters(self) -> dict[str, Any]:
        return dict(DEFAULT_EXTRACT_REQUEST_PARAMETERS)

    @property
    def last_raw_response(self) -> dict[str, Any]:
        if self._last_raw_response is None:
            raise MalformedResponseError("No successful Tavily Extract response is available")
        return self._last_raw_response

    @property
    def last_retrieved_at(self) -> str:
        if self._last_retrieved_at is None:
            raise MalformedResponseError("No successful Tavily Extract response is available")
        return self._last_retrieved_at

    @property
    def last_failed_urls(self) -> tuple[str, ...]:
        return self._last_failed_urls

    def extract(self, urls: list[str]) -> list[ExtractResult]:
        self._validate_urls(urls)
        self._budget.ensure_batch_available(len(urls))
        payload = {
            "urls": urls,
            "extract_depth": self.extract_depth,
            **self.request_parameters,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        retries = 0
        error_counts: dict[str, int] = {}

        for attempt in range(1, MAX_RATE_LIMIT_ATTEMPTS + 1):
            try:
                response = self._post(payload, headers)
            except (SearchTimeoutError, SearchTransportError) as error:
                self._record_failure(urls, retries, error_counts, error)
                raise
            if response.status_code == 429:
                error_counts[RateLimitError.__name__] = (
                    error_counts.get(RateLimitError.__name__, 0) + 1
                )
                if attempt == MAX_RATE_LIMIT_ATTEMPTS:
                    error = RateLimitError(
                        f"Tavily Extract returned HTTP 429 after {attempt} attempts"
                    )
                    self._record_failure(urls, retries, error_counts, error)
                    raise error
                retries += 1
                self._sleep(self._backoff_seconds * (2 ** (attempt - 1)))
                continue
            try:
                self._raise_for_status(response.status_code)
                raw_response = self._parse_json(response)
                retrieved_at = self._now()
                results = self.normalize_raw_response(
                    raw_response,
                    retrieved_at=retrieved_at,
                )
            except SearchProviderError as error:
                error_type = type(error).__name__
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
                self._record_failure(urls, retries, error_counts, error)
                raise

            charged_credits = self._budget.record_extraction(len(results))
            self._last_raw_response = raw_response
            self._last_retrieved_at = retrieved_at
            self.last_charged_credits = charged_credits
            self.last_retries = retries
            self.last_error_counts = dict(error_counts)
            self._run_recorder.record(
                provider=self.provider_name,
                urls=urls,
                extract_depth=self.extract_depth,
                request_parameters=self.request_parameters,
                retrieved_at=retrieved_at,
                raw_response=raw_response,
                charged_credits=charged_credits,
                execution_credits=self._budget.execution_credits,
                monthly_credits=self._budget.monthly_credits(),
                retries=retries,
                error_counts=error_counts,
            )
            return results

        raise RateLimitError("Tavily Extract rate-limit attempts were exhausted")

    @staticmethod
    def _validate_urls(urls: list[str]) -> None:
        if not isinstance(urls, list) or not 1 <= len(urls) <= MAX_EXTRACT_URLS_PER_REQUEST:
            raise ValueError("Tavily Extract requires between 1 and 20 URLs")
        if any(not isinstance(url, str) or not url.strip() for url in urls):
            raise ValueError("Tavily Extract URLs must be non-empty text")
        if len(set(urls)) != len(urls):
            raise ValueError("Tavily Extract URLs must be unique within a batch")

    def _record_failure(
        self,
        urls: list[str],
        retries: int,
        error_counts: dict[str, int],
        error: SearchProviderError,
    ) -> None:
        error_type = type(error).__name__
        if error_type not in error_counts:
            error_counts[error_type] = 1
        self.last_retries = retries
        self.last_error_counts = dict(error_counts)
        self._run_recorder.record(
            provider=self.provider_name,
            urls=urls,
            extract_depth=self.extract_depth,
            request_parameters=self.request_parameters,
            retrieved_at=self._now(),
            raw_response=None,
            charged_credits=0,
            execution_credits=self._budget.execution_credits,
            monthly_credits=self._budget.monthly_credits(),
            retries=retries,
            error_counts=error_counts,
            error_type=error_type,
        )

    def _post(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> requests.Response:
        try:
            return self._session.post(
                TAVILY_EXTRACT_URL,
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        except requests.Timeout as error:
            raise SearchTimeoutError("Tavily Extract timed out") from error
        except requests.RequestException as error:
            raise SearchTransportError("Tavily Extract transport failed") from error

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if 200 <= status_code < 300:
            return
        if status_code == 401:
            raise AuthError("Tavily rejected TAVILY_API_KEY with HTTP 401")
        if status_code in {402, 432}:
            raise CreditsExhaustedError(
                f"Tavily Extract credits are exhausted (HTTP {status_code})"
            )
        raise UnexpectedHTTPStatusError(
            f"Tavily Extract returned unexpected HTTP status {status_code}"
        )

    @staticmethod
    def _parse_json(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise MalformedResponseError(
                "Tavily Extract response is not valid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise MalformedResponseError(
                "Tavily Extract response must be a JSON object"
            )
        return payload

    def normalize_raw_response(
        self,
        raw_response: dict[str, Any],
        *,
        retrieved_at: str,
    ) -> list[ExtractResult]:
        raw_results = raw_response.get("results")
        failed_results = raw_response.get("failed_results", [])
        if not isinstance(raw_results, list) or not isinstance(failed_results, list):
            raise MalformedResponseError(
                "Tavily Extract results and failed_results must be lists"
            )
        normalized: list[ExtractResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                raise MalformedResponseError("Tavily Extract result must be an object")
            url = item.get("url")
            raw_content = item.get("raw_content")
            if not isinstance(url, str) or not isinstance(raw_content, str):
                raise MalformedResponseError(
                    "Tavily Extract result fields are invalid"
                )
            normalized.append(
                ExtractResult(
                    url=url,
                    raw_content=raw_content,
                    provider=self.provider_name,
                    retrieved_at=retrieved_at,
                )
            )
        failed_urls: list[str] = []
        for item in failed_results:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                failed_urls.append(item["url"])
        self._last_failed_urls = tuple(failed_urls)
        return normalized
