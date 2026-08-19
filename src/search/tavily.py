from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from .audit import RunRecorder
from .budget import SearchBudget
from .errors import (
    AuthError,
    CreditsExhaustedError,
    MalformedResponseError,
    RateLimitError,
    SearchTimeoutError,
    SearchTransportError,
    UnexpectedHTTPStatusError,
)
from .models import SearchResult
from .provider import SearchProvider


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_PROVIDER_NAME = "tavily"
TAVILY_SEARCH_DEPTH = "advanced"
MAX_RATE_LIMIT_ATTEMPTS = 2


def load_tavily_api_key(env_path: str | Path = ".env") -> str:
    path = Path(env_path)
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as error:
        raise AuthError(f"TAVILY_API_KEY is missing from {path}") from error

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() != "TAVILY_API_KEY":
            continue
        api_key = value.strip()
        if len(api_key) >= 2 and api_key[0] == api_key[-1] and api_key[0] in {'"', "'"}:
            api_key = api_key[1:-1]
        if api_key:
            return api_key
        break
    raise AuthError(f"TAVILY_API_KEY is missing from {path}")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TavilySearchProvider(SearchProvider):
    provider_name = TAVILY_PROVIDER_NAME
    search_depth = TAVILY_SEARCH_DEPTH

    def __init__(
        self,
        *,
        env_path: str | Path = ".env",
        session: requests.Session | None = None,
        budget: SearchBudget | None = None,
        run_recorder: RunRecorder | None = None,
        timeout_seconds: float = 20.0,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], str] = utc_now_iso,
    ) -> None:
        self._api_key = load_tavily_api_key(env_path)
        self._session = session or requests.Session()
        self._budget = budget or SearchBudget()
        self._run_recorder = run_recorder or RunRecorder()
        self._timeout_seconds = timeout_seconds
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._now = now
        self._last_raw_response: dict[str, Any] | None = None
        self._last_retrieved_at: str | None = None

    @property
    def last_raw_response(self) -> dict[str, Any]:
        if self._last_raw_response is None:
            raise MalformedResponseError("No successful Tavily response is available")
        return self._last_raw_response

    @property
    def last_retrieved_at(self) -> str:
        if self._last_retrieved_at is None:
            raise MalformedResponseError("No successful Tavily response is available")
        return self._last_retrieved_at

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        if not query.strip():
            raise ValueError("query is required")
        if isinstance(max_results, bool) or not isinstance(max_results, int) or max_results <= 0:
            raise ValueError("max_results must be a positive integer")

        charged_credits = self._budget.record_search(cache_hit=False)
        payload = {
            "query": query,
            "search_depth": self.search_depth,
            "max_results": max_results,
            "include_raw_content": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(1, MAX_RATE_LIMIT_ATTEMPTS + 1):
            response = self._post(payload, headers)
            if response.status_code == 429:
                if attempt == MAX_RATE_LIMIT_ATTEMPTS:
                    raise RateLimitError(
                        f"Tavily returned HTTP 429 after {attempt} attempts"
                    )
                self._sleep(self._backoff_seconds * (2 ** (attempt - 1)))
                continue
            self._raise_for_status(response.status_code)
            raw_response = self._parse_json(response)
            retrieved_at = self._now()
            results = self.normalize_raw_response(
                raw_response,
                query=query,
                retrieved_at=retrieved_at,
                max_results=max_results,
            )
            self._last_raw_response = raw_response
            self._last_retrieved_at = retrieved_at
            self._run_recorder.record_success(
                provider=self.provider_name,
                query=query,
                search_depth=self.search_depth,
                max_results=max_results,
                retrieved_at=retrieved_at,
                raw_response=raw_response,
                charged_credits=charged_credits,
                execution_credits=self._budget.execution_credits,
                monthly_credits=self._budget.monthly_credits(),
            )
            return results

        raise RateLimitError("Tavily rate-limit attempts were exhausted")

    def _post(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> requests.Response:
        try:
            return self._session.post(
                TAVILY_SEARCH_URL,
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        except requests.Timeout as error:
            raise SearchTimeoutError("Tavily search timed out") from error
        except requests.RequestException as error:
            raise SearchTransportError("Tavily search transport failed") from error

    def _raise_for_status(self, status_code: int) -> None:
        if 200 <= status_code < 300:
            return
        if status_code == 401:
            raise AuthError("Tavily rejected TAVILY_API_KEY with HTTP 401")
        if status_code in {402, 432}:
            raise CreditsExhaustedError(
                f"Tavily search credits are exhausted (HTTP {status_code})"
            )
        raise UnexpectedHTTPStatusError(
            f"Tavily returned unexpected HTTP status {status_code}"
        )

    def _parse_json(self, response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise MalformedResponseError("Tavily response is not valid JSON") from error
        if not isinstance(payload, dict):
            raise MalformedResponseError("Tavily response must be a JSON object")
        return payload

    def normalize_raw_response(
        self,
        raw_response: dict[str, Any],
        *,
        query: str,
        retrieved_at: str,
        max_results: int,
    ) -> list[SearchResult]:
        raw_results = raw_response.get("results")
        if not isinstance(raw_results, list):
            raise MalformedResponseError("Tavily response.results must be a list")

        normalized: list[SearchResult] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict):
                raise MalformedResponseError("Tavily result must be an object")
            try:
                url = item["url"]
                title = item["title"]
                score_value = item["score"]
            except KeyError as error:
                raise MalformedResponseError(
                    "Tavily result is missing url, title or score"
                ) from error
            if (
                not isinstance(url, str)
                or not isinstance(title, str)
                or isinstance(score_value, bool)
            ):
                raise MalformedResponseError("Tavily result fields have invalid types")
            try:
                raw_score = float(score_value)
            except (TypeError, ValueError) as error:
                raise MalformedResponseError("Tavily score must be numeric") from error

            snippet = item.get("content", "")
            content = item.get("raw_content", "")
            if snippet is None:
                snippet = ""
            if content is None:
                content = ""
            if not isinstance(snippet, str) or not isinstance(content, str):
                raise MalformedResponseError("Tavily result text must be strings")

            normalized.append(
                SearchResult(
                    url=url,
                    title=title,
                    snippet=snippet,
                    content=content,
                    raw_score=raw_score,
                    provider=self.provider_name,
                    query=query,
                    retrieved_at=retrieved_at,
                )
            )
        return normalized
