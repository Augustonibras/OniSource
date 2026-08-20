from __future__ import annotations

from math import ceil
from pathlib import Path

from src.search.budget import (
    DEFAULT_CREDIT_STATE_PATH,
    EXECUTION_CREDIT_LIMIT,
    MONTHLY_CREDIT_LIMIT,
    BudgetExceededError,
    SearchBudget,
)


MAX_EXTRACT_URLS_PER_REQUEST = 20


class ExtractBudget(SearchBudget):
    def __init__(self, state_path: str | Path = DEFAULT_CREDIT_STATE_PATH, **kwargs) -> None:
        super().__init__(state_path, **kwargs)

    @staticmethod
    def credits_for_successes(successful_urls: int) -> int:
        if isinstance(successful_urls, bool) or not isinstance(successful_urls, int):
            raise ValueError("successful_urls must be a non-negative integer")
        if successful_urls < 0:
            raise ValueError("successful_urls must be a non-negative integer")
        return ceil(successful_urls / 5) if successful_urls else 0

    def ensure_batch_available(self, url_count: int) -> None:
        if (
            isinstance(url_count, bool)
            or not isinstance(url_count, int)
            or not 1 <= url_count <= MAX_EXTRACT_URLS_PER_REQUEST
        ):
            raise ValueError("extract batches must contain between 1 and 20 URLs")
        self._ensure_credits_available(self.credits_for_successes(url_count))

    def record_extraction(self, successful_urls: int) -> int:
        credits = self.credits_for_successes(successful_urls)
        if credits:
            self._record_credits(credits)
        return credits

    def _ensure_credits_available(self, credits: int) -> tuple[str, int]:
        current_month = self._current_month()
        persisted_month, monthly_credits = self._load_monthly_state(current_month)
        if self._execution_credits + credits > EXECUTION_CREDIT_LIMIT:
            raise BudgetExceededError(
                f"Execution credit limit of {EXECUTION_CREDIT_LIMIT} would be exceeded"
            )
        if monthly_credits + credits > MONTHLY_CREDIT_LIMIT:
            raise BudgetExceededError(
                f"Monthly credit limit of {MONTHLY_CREDIT_LIMIT} would be exceeded"
            )
        return persisted_month, monthly_credits

    def _record_credits(self, credits: int) -> None:
        month, monthly_credits = self._ensure_credits_available(credits)
        self._write_monthly_state(month, monthly_credits + credits)
        self._execution_credits += credits
